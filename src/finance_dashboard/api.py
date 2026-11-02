"""Read-only API: exposes actual stored observations, never synthetic chart values."""
from __future__ import annotations

from datetime import date, datetime
from os import environ

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .providers import ProviderRouter, PROVIDER_CODES
from .catalog import load_documents, validate
from .database import IngestionRun, make_engine
from .service import current_observations


class SeriesQuery(BaseModel):
    series_ids: list[str] = Field(min_length=1, max_length=12)
    start: date | None = None
    end: date | None = None
    snapshot_at: datetime | None = None

    @model_validator(mode="after")
    def check(self):
        if len(self.series_ids) != len(set(self.series_ids)):
            raise ValueError("Duplicate series IDs")
        if self.start and self.end and self.start > self.end:
            raise ValueError("start must be on or before end")
        return self


def create_app(engine=None) -> FastAPI:
    app = FastAPI(title="Global Capital Monitor", version="0.2.0")
    db = engine or make_engine()
    catalog, chart_catalog = load_documents()
    errors = validate(catalog, chart_catalog)
    if errors:
        raise RuntimeError("Catalog invalid: " + "; ".join(errors))
    by_id = {s["id"]: s for s in catalog["series"]}
    supported = {sid for sid, s in by_id.items() if s["status"] == "mapped" and s["provider"] in PROVIDER_CODES}

    @app.get("/api/health")
    def health():
        with db.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}

    @app.get("/api/series")
    def list_series():
        return {"items": catalog["series"]}

    @app.get("/api/series/{series_id:path}")
    def get_series(series_id: str):
        item = by_id.get(series_id)
        if item is None:
            raise HTTPException(404, "Unknown series")
        return item

    @app.get("/api/charts")
    def charts():
        return {"items": chart_catalog["charts"]}

    @app.post("/api/query")
    def query(request: SeriesQuery):
        for sid in request.series_ids:
            if sid not in by_id:
                raise HTTPException(404, f"Unknown series: {sid}")
            if sid not in supported:
                raise HTTPException(422, f"Series not yet supported by an ingestion adapter: {sid}")
        output = []
        with Session(db) as session:
            for sid in request.series_ids:
                versions = current_observations(session, sid, request.start, request.end, request.snapshot_at)
                if len(versions) > 100_000:
                    raise HTTPException(413, "Query exceeds 100000 observations for one series")
                output.append({
                    "series_id": sid, "name": by_id[sid]["name"],
                    "unit": by_id[sid]["unit"], "frequency": by_id[sid]["frequency"],
                    "source_url": by_id[sid]["source_url"],
                    "status": "ready" if versions else "no_data",
                    "observations": [
                        {
                            "date": v.period.isoformat(), "value": str(v.value),
                            "first_seen_at": v.first_seen_at.isoformat(),
                            "ingestion_run_id": v.ingestion_run_id,
                        } for v in versions
                    ]
                })
        return {"series": output, "snapshot_kind": "app_first_seen_not_publication_vintage"}

    @app.get("/api/data-status")
    def data_status():
        result = []
        with Session(db) as session:
            for sid in sorted(by_id):
                last = session.scalars(
                    select(IngestionRun).where(IngestionRun.series_id == sid)
                    .order_by(IngestionRun.started_at.desc(), IngestionRun.id.desc()).limit(1)
                ).first()
                result.append({
                    "series_id": sid,
                    "provider": by_id[sid]["provider"],
                    "mapped": sid in supported,
                    "status": last.status if last else ("never_ingested" if sid in supported else "source_unresolved"),
                    "last_attempt": last.started_at.isoformat() if last else None,
                    "last_success": None,
                    "received": last.observations_received if last else 0,
                    "versions_added": last.versions_added if last else 0,
                    "error": last.error if last else None,
                })
                success = session.scalars(
                    select(IngestionRun).where(
                        IngestionRun.series_id == sid, IngestionRun.status == "success"
                    ).order_by(IngestionRun.started_at.desc()).limit(1)
                ).first()
                result[-1]["last_success"] = success.ended_at.isoformat() if success and success.ended_at else None
        return {"items": result}

    return app


# Used by uvicorn: make database configuration explicit at application startup.
def app_factory() -> FastAPI:
    return create_app()
