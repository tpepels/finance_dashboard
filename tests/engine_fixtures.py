"""Shared fixtures for engine tests: an in-memory corpus with seeded observations."""
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from finance_dashboard.database import Base, IngestionRun, ObservationVersion, SeriesRow


def memory_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine


def seed(engine, observations: dict[str, list[tuple[date, float]]]):
    when = datetime(2026, 11, 8, tzinfo=timezone.utc)
    with Session(engine) as session, session.begin():
        for series_id, points in observations.items():
            run = f"seed-{series_id}"
            session.add(SeriesRow(id=series_id, provider="TEST", source_key=series_id, updated_at=when))
            session.add(IngestionRun(id=run, series_id=series_id, started_at=when, ended_at=when,
                                     status="success", observations_received=len(points),
                                     versions_added=len(points)))
            for day, value in points:
                session.add(ObservationVersion(series_id=series_id, period=day, value=Decimal(str(value)),
                                               first_seen_at=when, ingestion_run_id=run))


def monthly(start: tuple[int, int], values: list[float], day: int = 28, skip: tuple[int, int] | None = None):
    out, (y, m) = [], start
    for v in values:
        if (y, m) != skip:
            out.append((date(y, m, day), v))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out
