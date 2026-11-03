"""Provider-neutral atomic ingestion with append-only corrections and app snapshots."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
import re
from uuid import uuid4

import httpx

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .providers import ProviderRouter
from .catalog import load_documents
from .database import IngestionRun, ObservationVersion, SeriesRow, now_utc


def safe_source_failure_code(exc: BaseException) -> str:
    """Fixed vocabulary only; credentials, full URLs and provider bodies never persist."""
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return "provider_http_" + str(code) if 400 <= code < 600 else "provider_failed"
    match = re.search(r"Provider HTTP ([0-9]{3})", str(exc))
    if match:
        code = int(match.group(1))
        return "provider_http_" + str(code) if 400 <= code < 600 else "provider_failed"
    if isinstance(exc, httpx.TimeoutException) or isinstance(exc, httpx.TransportError):
        return "source_transport_failed"
    if isinstance(exc, ValueError):
        # Error categories are derived from fixed application-controlled error
        # phrases. Never persist free-form exception text or provider content.
        # Keep source_invalid as the fallback for unknown validation failures.
        reason = str(exc)
        known_prefixes = (
            ("FRED observations list missing", "fred_schema_invalid"),
            ("FRED response contains no usable observations", "fred_empty"),
            ("FRED public DATE/VALUE table missing or ambiguous", "fred_table_invalid"),
            ("FRED table page does not identify the expected series", "fred_table_invalid"),
            ("FRED public table", "fred_table_invalid"),
            ("FRED DATE/VALUE table", "fred_table_invalid"),
            ("Malformed extended FRED observation row", "fred_table_invalid"),
            ("Unexpected FRED CSV header", "fred_schema_invalid"),
            ("FRED CSV", "fred_schema_invalid"),
            ("Invalid observation period:", "source_date_invalid"),
            ("Repeated observation:", "source_duplicate_period"),
            ("Conflicting duplicate observation:", "source_duplicate_period"),
            ("Invalid source numeric value:", "source_value_invalid"),
            ("Source returned an infinite numeric value", "source_value_invalid"),
            ("Provider returned no data or wrong series", "source_empty"),
            ("Provider returned observations outside requested window", "source_window_invalid"),
            ("Provider returned future-dated observations", "source_future_date"),
            ("Source mapping changed:", "source_mapping_mismatch"),
            ("Shiller source workbook has incomplete monthly CAPE history", "shiller_incomplete"),
            ("Shiller workbook", "shiller_schema_invalid"),
            ("ECB FX series identity mismatch", "fx_identity_mismatch"),
            ("ECB FX CSV columns missing", "fx_schema_invalid"),
            ("No ECB FX observations", "fx_empty"),
            ("Invalid ECB FX period or value", "fx_value_invalid"),
        )
        for prefix, code in known_prefixes:
            if reason.startswith(prefix):
                return code
        return "source_invalid"
    return "provider_failed"


class IngestionService:
    def __init__(self, engine, provider=None):
        self.engine = engine
        self.provider = provider or ProviderRouter()

    def refresh(self, series_id: str, *, full: bool = False, today: date | None = None) -> dict:
        definitions, _ = load_documents()
        definition = next((item for item in definitions["series"] if item["id"] == series_id), None)
        if not definition or definition["status"] != "mapped":
            raise ValueError("Unmapped catalog source")
        with Session(self.engine) as session, session.begin():
            row = session.get(SeriesRow, series_id)
            if row is None:
                session.add(SeriesRow(
                    id=series_id, provider=definition["provider"], source_key=definition["source_key"],
                    updated_at=now_utc(),
                ))
            elif row.source_key != definition["source_key"] or row.provider != definition["provider"]:
                raise ValueError("Source mapping changed: requires explicit migration")
        with Session(self.engine) as session:
            last_date = session.scalar(
                select(func.max(ObservationVersion.period)).where(ObservationVersion.series_id == series_id)
            )
        # Overlap makes backward revisions detectable; first run fetches full history.
        overlap = 120 if definition["frequency"] == "D" else 730 if definition["frequency"] == "M" else 365 * 5
        start = None if full or last_date is None else last_date - timedelta(days=overlap)
        run_id = str(uuid4())
        with Session(self.engine) as session, session.begin():
            session.add(IngestionRun(
                id=run_id, series_id=series_id, started_at=now_utc(),
                status="running", requested_from=start,
                observations_received=0, versions_added=0,
            ))
        try:
            fetched = self.provider.fetch(series_id, start)
            if fetched.series_id != series_id or not fetched.observations:
                raise ValueError("Provider returned no data or wrong series")
            if start and min(fetched.observations) < start:
                raise ValueError("Provider returned observations outside requested window")
            if any(day > (today or date.today()) for day in fetched.observations):
                raise ValueError("Provider returned future-dated observations")
            with Session(self.engine) as session, session.begin():
                # Serialize ingestion of a series in PostgreSQL via the parent series row.
                session.execute(
                    select(SeriesRow).where(SeriesRow.id == series_id).with_for_update()
                ).scalar_one()
                previous = session.scalars(
                    select(ObservationVersion).where(ObservationVersion.series_id == series_id)
                    .order_by(ObservationVersion.id.desc())
                )
                latest: dict[date, Decimal] = {}
                for version in previous:
                    latest.setdefault(version.period, version.value)
                added = 0
                seen = now_utc()
                for day, value in fetched.observations.items():
                    if not isinstance(value, Decimal) or not value.is_finite():
                        raise ValueError(f"Invalid provider value for {day}")
                    if latest.get(day) != value:
                        session.add(ObservationVersion(
                            series_id=series_id, period=day, value=value,
                            first_seen_at=seen, ingestion_run_id=run_id,
                        ))
                        added += 1
                run = session.get(IngestionRun, run_id)
                run.ended_at = now_utc()
                run.status = "success"
                run.request_url = fetched.request_url
                run.response_prepared_at = fetched.prepared_at.isoformat() if fetched.prepared_at else None
                run.observations_received = len(fetched.observations)
                run.versions_added = added
                session.get(SeriesRow, series_id).updated_at = now_utc()
            return {"id": run_id, "series_id": series_id, "status": "success", "received": len(fetched.observations), "versions_added": added}
        except Exception as exc:
            # A failed transaction leaves *all* earlier observations untouched.
            with Session(self.engine) as session, session.begin():
                run = session.get(IngestionRun, run_id)
                run.status = "failed"
                run.ended_at = now_utc()
                run.error = safe_source_failure_code(exc)
            raise


def current_observations(
    session: Session, series_id: str, start: date | None = None,
    end: date | None = None, snapshot_at: datetime | None = None,
) -> list[ObservationVersion]:
    """The snapshot is when OUR application saw data, not an economic publication vintage."""
    statement = select(ObservationVersion).where(ObservationVersion.series_id == series_id)
    if start:
        statement = statement.where(ObservationVersion.period >= start)
    if end:
        statement = statement.where(ObservationVersion.period <= end)
    if snapshot_at:
        statement = statement.where(ObservationVersion.first_seen_at <= snapshot_at)
    rows = session.scalars(statement.order_by(ObservationVersion.period, ObservationVersion.id.desc()))
    latest = {}
    for row in rows:
        latest.setdefault(row.period, row)
    return list(latest.values())
