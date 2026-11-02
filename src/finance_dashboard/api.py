"""Read-only API: exposes actual stored observations, never synthetic chart values."""
from __future__ import annotations

from datetime import date, datetime
from .wisesheets import load_sec_profit_snapshot
from os import environ

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .providers import ProviderRouter, PROVIDER_CODES
from .catalog import load_documents, validate
from .database import IngestionRun, make_engine
from .service import current_observations
from .market import instruments
from .market_service import MarketIngestionService
from .market_analytics import rolling_gold_vs_global_etf
from .database import MarketIngestionRun, FxIngestionRun
from .standalone import mount_built_dashboard, standalone_lifespan
from functools import partial


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


class MarketQuery(BaseModel):
    instrument_ids: list[str] = Field(min_length=1, max_length=48)
    start: date | None = None
    end: date | None = None
    snapshot_at: datetime | None = None

    @model_validator(mode="after")
    def check(self):
        if len(self.instrument_ids) != len(set(self.instrument_ids)):
            raise ValueError("Duplicate instrument IDs")
        if self.start and self.end and self.start > self.end:
            raise ValueError("start must be before end")
        return self


def create_app(engine=None) -> FastAPI:
    db = engine or make_engine()
    app = FastAPI(title="Global Capital Monitor", version="0.2.0",
                  lifespan=partial(standalone_lifespan, engine=db))
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

    market_registry = instruments()

    @app.get("/api/earnings/sec-filers")
    def sec_filer_earnings():
        """Monthly snapshot of current SEC reporting-company universe, not world."""
        try:
            payload = load_sec_profit_snapshot()
        except Exception:
            raise HTTPException(503, "SEC earnings snapshot invalid") from None
        if payload is None:
            raise HTTPException(404, "SEC earnings full-universe scan not yet collected")
        return payload

    @app.get("/api/markets")
    def markets():
        return {"items": [market_registry[sid] for sid in sorted(market_registry)],
                "count": len(market_registry),
                "return_methods": [
                    "raw_price_index",
                    "vendor_adjusted_index",
                    "cash_dividend_reinvested_index",
                    "eur_adjusted_index",
                ]}

    @app.get("/api/markets/{instrument_id:path}")
    def market_instrument(instrument_id: str):
        definition = market_registry.get(instrument_id)
        if definition is None:
            raise HTTPException(404, "Unknown market instrument")
        return definition

    @app.post("/api/market/query")
    def market_query(request: MarketQuery):
        unknown = [sid for sid in request.instrument_ids if sid not in market_registry]
        if unknown:
            raise HTTPException(404, f"Unknown market instruments: {unknown}")
        service = MarketIngestionService(db, registry=market_registry)
        result = [
            service.read_performance(sid, start=request.start, end=request.end,
                                     snapshot_at=request.snapshot_at)
            for sid in request.instrument_ids
        ]
        if any(len(item.get("observations", [])) > 100000 for item in result):
            raise HTTPException(413, "One market series exceeds 100000 observations")
        return {"series": result, "base_currency": "EUR",
                "snapshot_kind": "app_first_seen_not_source_publication_vintage",
                "calendar_alignment": "Native trading dates; no invented market closures or FX"}

    @app.get("/api/market/gold-world-proxy")
    def gold_world_proxy(currency: str = "USD", window_months: int = 36):
        if currency not in ("USD", "EUR") or not 12 <= window_months <= 120:
            raise HTTPException(422, "Invalid correlation currency or window")
        service=MarketIngestionService(db,registry=market_registry)
        gold=service.read_performance("gld")
        world=service.read_performance("vt")
        if gold["status"]!="ready" or world["status"]!="ready":
            raise HTTPException(409, "Gold/VT proxy histories not yet ingested")
        return rolling_gold_vs_global_etf(gold,world,months=window_months,currency=currency)

    @app.get("/api/market/status")
    def market_status():
        out = []
        with Session(db) as session:
            for sid in sorted(market_registry):
                last = session.scalars(
                    select(MarketIngestionRun).where(MarketIngestionRun.instrument_id == sid)
                    .order_by(MarketIngestionRun.started_at.desc(), MarketIngestionRun.id.desc())
                    .limit(1)).first()
                success = session.scalars(
                    select(MarketIngestionRun).where(
                        MarketIngestionRun.instrument_id == sid, MarketIngestionRun.status == "success")
                    .order_by(MarketIngestionRun.started_at.desc()).limit(1)).first()
                out.append({
                    "id": sid, "symbol": market_registry[sid]["source_symbol"],
                    "status": last.status if last else "never_ingested",
                    "last_success": success.ended_at.isoformat() if success and success.ended_at else None,
                    "received": last.observations_received if last else 0,
                    "error": last.error if last else None,
                })
            fx_items = []
            for currency in ("USD", "GBP", "CHF"):
                last = session.scalars(
                    select(FxIngestionRun).where(FxIngestionRun.currency == currency)
                    .order_by(FxIngestionRun.started_at.desc()).limit(1)).first()
                fx_items.append({"currency": currency,
                                 "status": last.status if last else "never_ingested",
                                 "received": last.observations_received if last else 0})
        return {"instruments": out, "fx": fx_items}


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
                    "status": last.status if last else (
                        "source_unresolved" if sid not in supported
                        else "never_ingested"
                    ),
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

    # Existing API routes always take priority over bundled Vite assets.
    mount_built_dashboard(app)
    return app


# Used by uvicorn: make database configuration explicit at application startup.
def app_factory() -> FastAPI:
    return create_app()
