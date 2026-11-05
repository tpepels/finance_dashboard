"""Persistence model: append-only observation history plus ingest-run audit trail."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from os import environ

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def database_url() -> str:
    url = environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is required; no silent in-memory database fallback")
    return url


def make_engine(url: str | None = None):
    target = url or database_url()
    if not target.startswith("sqlite"):
        return create_engine(target, pool_pre_ping=True)
    # One persistent local DB serves refresh and HTTP reads concurrently.
    engine = create_engine(target, pool_pre_ping=True, connect_args={"timeout": 30})

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection, _record):
        cur = connection.cursor()
        try:
            cur.execute("PRAGMA busy_timeout = 30000")
            cur.execute("PRAGMA journal_mode = WAL")
            cur.execute("PRAGMA synchronous = NORMAL")
        finally:
            cur.close()
    return engine


class Base(DeclarativeBase):
    pass


class SeriesRow(Base):
    __tablename__ = "series"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
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
    response_prepared_at: Mapped[str | None] = mapped_column(Text())
    evidence_kind: Mapped[str | None] = mapped_column(String(32))
    evidence_scope: Mapped[str | None] = mapped_column(String(64))
    evidence_bundle_digest: Mapped[str | None] = mapped_column(String(64))
    evidence_receipt_name: Mapped[str | None] = mapped_column(String(96))
    observations_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    versions_added: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text())


class ObservationVersion(Base):
    __tablename__ = "observation_versions"
    __table_args__ = (Index("ix_observation_versions_series_period", "series_id", "period"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    series_id: Mapped[str] = mapped_column(ForeignKey("series.id"), index=True)
    period: Mapped[date] = mapped_column(Date(), index=True, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(32, 10), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingestion_run_id: Mapped[str] = mapped_column(ForeignKey("ingestion_runs.id"), nullable=False)


# Market prices, corporate actions, and ECB FX are deliberately distinct
# from single-valued macro indicators. Every row is immutable once inserted.
class MarketInstrumentRow(Base):
    __tablename__ = "market_instruments"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    exchange_mic: Mapped[str] = mapped_column(String(12), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MarketIngestionRun(Base):
    __tablename__ = "market_ingestion_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("market_instruments.id"), index=True, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_from: Mapped[date | None] = mapped_column(Date())
    observations_received: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    versions_added: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text())


class MarketPriceVersion(Base):
    __tablename__ = "market_price_versions"
    __table_args__ = (Index("ix_market_price_versions_instrument_day", "instrument_id", "day"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("market_instruments.id"), index=True, nullable=False)
    day: Mapped[date] = mapped_column(Date(), index=True, nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(28, 12), nullable=False)
    adjusted_close: Mapped[Decimal] = mapped_column(Numeric(28, 12), nullable=False)
    volume: Mapped[int | None] = mapped_column(BigInteger())
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingestion_run_id: Mapped[str] = mapped_column(ForeignKey("market_ingestion_runs.id"), nullable=False)


class MarketActionVersion(Base):
    """Exact source corporate-action ex-date, even when the exchange was closed."""
    __tablename__ = "market_action_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("market_instruments.id"), index=True, nullable=False)
    ex_date: Mapped[date] = mapped_column(Date(), index=True, nullable=False)
    action_type: Mapped[str] = mapped_column(String(16), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(28, 12), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingestion_run_id: Mapped[str] = mapped_column(ForeignKey("market_ingestion_runs.id"), nullable=False)


class FxIngestionRun(Base):
    __tablename__ = "fx_ingestion_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    observations_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    versions_added: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text())


class FxRateVersion(Base):
    __tablename__ = "fx_rate_versions"
    __table_args__ = (Index("ix_fx_rate_versions_currency_day", "currency", "day"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    currency: Mapped[str] = mapped_column(String(8), index=True, nullable=False)
    day: Mapped[date] = mapped_column(Date(), index=True, nullable=False)
    foreign_per_eur: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingestion_run_id: Mapped[str] = mapped_column(ForeignKey("fx_ingestion_runs.id"), nullable=False)
