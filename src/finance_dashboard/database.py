"""Persistence model: append-only observation history plus ingest-run audit trail."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from os import environ

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def database_url() -> str:
    url = environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is required; no silent in-memory database fallback")
    return url


def make_engine(url: str | None = None):
    return create_engine(url or database_url(), pool_pre_ping=True)


class Base(DeclarativeBase):
    pass


class SeriesRow(Base):
    __tablename__ = "series"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    provider: Mapped[str] = mapped_column(String(24), nullable=False)
    source_key: Mapped[str] = mapped_column(String(160), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    series_id: Mapped[str] = mapped_column(ForeignKey("series.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_from: Mapped[date | None] = mapped_column(Date())
    request_url: Mapped[str | None] = mapped_column(Text())
    response_prepared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observations_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    versions_added: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text())


class ObservationVersion(Base):
    __tablename__ = "observation_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    series_id: Mapped[str] = mapped_column(ForeignKey("series.id"), index=True)
    period: Mapped[date] = mapped_column(Date(), index=True, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingestion_run_id: Mapped[str] = mapped_column(ForeignKey("ingestion_runs.id"), nullable=False)
