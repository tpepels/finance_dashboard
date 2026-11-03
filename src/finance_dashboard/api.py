"""Read-only API: exposes actual stored observations, never synthetic chart values."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from .wisesheets import load_sec_profit_snapshot
from os import environ
import re

from fastapi import FastAPI, HTTPException, Request, Header
from pydantic import BaseModel, Field, model_validator, ConfigDict
from sqlalchemy import select, text, func, distinct
from sqlalchemy.orm import Session

from .providers import ProviderRouter, PROVIDER_CODES
from .catalog import load_documents, validate
from .database import IngestionRun, ObservationVersion, MarketPriceVersion, FxRateVersion, make_engine
from .service import current_observations
from .market import instruments
from .market_service import MarketIngestionService
from .market_analytics import rolling_gold_vs_global_etf
from .insights import same_measure, summarize
from .risk_diagnostics import diagnostic_catalog, read_diagnostics, SCOPES as RISK_SCOPES
from .portfolio_risk import compare_market_histories
from .vintage import SOURCES as VINTAGE_SOURCES, read_snapshot as read_alfred_snapshot, available_snapshots, latest_asof_reading
from .vintage_backtest import walk_forward
from .sec_holdings import list_holdings, HoldingsError
from .marx_accounts import read as read_oecd_accounts, compute_country_year, SCENARIOS as MARX_SCENARIOS, AccountingError

from .research import BY_ID as RESEARCH_INDICATORS, list_research, load_indicator
from .source_coverage import build_coverage
from .maintenance import MaintenanceManager, BusyMaintenance
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


class MaintenanceCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str
    series_ids: list[str] | None = None
    instrument_ids: list[str] | None = None
    currencies: list[str] | None = None
    start: str | None = None
    end: str | None = None
    max_requests: int | None = None
    complete_range: bool | None = None
    limit: int | None = None


class PortfolioComparison(BaseModel):
    instrument_ids: list[str] = Field(min_length=2, max_length=5)
    currency: str = "EUR"
    start: date | None = None
    end: date | None = None
    snapshot_at: datetime | None = None
    weights_pct: dict[str, float] | None = None

    @model_validator(mode="after")
    def validate_comparison(self):
        if len(self.instrument_ids) != len(set(self.instrument_ids)):
            raise ValueError("Duplicate portfolio assets")
        if self.currency not in ("EUR", "USD"):
            raise ValueError("Only EUR or USD analysis is available")
        if self.start and self.end and self.start > self.end:
            raise ValueError("Invalid comparison date window")
        if self.weights_pct is not None:
            from math import isfinite
            if set(self.weights_pct) != set(self.instrument_ids):
                raise ValueError("Weights must cover exactly the selected assets")
            if any(not isfinite(x) or x < 0 or x > 100 for x in self.weights_pct.values()):
                raise ValueError("Each asset weight must be between zero and 100")
            if abs(sum(self.weights_pct.values()) - 100) > 1e-6:
                raise ValueError("The selected weights must total 100 percent")
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
    maintenance = MaintenanceManager(db)
    market_registry = instruments()

    @app.get("/api/health")
    def health():
        with db.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}

    @app.get("/api/operations")
    def operations():
        """Local source coverage and backup monitoring, without URLs or credentials."""
        with Session(db) as session:
            macro_count = session.scalar(
                select(func.count(distinct(ObservationVersion.series_id)))) or 0
            market_count = session.scalar(
                select(func.count(distinct(MarketPriceVersion.instrument_id)))) or 0
            fx_count = session.scalar(
                select(func.count(distinct(FxRateVersion.currency)))) or 0
            macro_failures = session.scalar(
                select(func.count()).select_from(IngestionRun).where(
                    IngestionRun.status == "failed")) or 0
            most_recent = session.scalar(
                select(func.max(IngestionRun.ended_at)).where(
                    IngestionRun.status == "success"))
        from .standalone import enabled
        folder = Path(environ.get("FINANCE_BACKUP_DIR", "/data/backups"))
        backups = sorted(
            (p for p in folder.glob("finance-*Z.json") if p.is_file()),
            reverse=True,
        ) if folder.is_dir() else []
        # Read-only source readiness. Report credentials as booleans only and
        # preserve distinct states for configured collection and stored evidence.
        vintage_folder = Path(environ.get("FINANCE_VINTAGE_DIR", "/data/vintages"))
        vintage_counts = {item["series_id"]: item["count"]
                          for item in available_snapshots(vintage_folder)["series"]}
        holdings_folder = Path(environ.get("FINANCE_HOLDINGS_DIR", "/data/holdings"))
        sec_reports = sum(1 for file in holdings_folder.glob("*/????-??-??--*.json")
                          if file.is_file()) if holdings_folder.is_dir() else 0
        surplus_exists = (Path(environ.get("FINANCE_SURPLUS_DIR", "/data/surplus"))
                          / "oecd_iot_2025_normalized.json").is_file()
        earnings_exists = Path(environ.get(
            "WISESHEETS_SNAPSHOT_PATH", "/data/wisesheets/sec_filer_profit.json")).is_file()
        fred_key = environ.get("FRED_API_KEY", "").strip()
        wisesheets_key = environ.get("WISESHEETS_API_KEY", "").strip()
        sec_agent = environ.get("SEC_USER_AGENT", "").strip()
        return {
            "source_setup": {
                "fred_key_present": bool(fred_key),
                "fred_key_format_valid": bool(re.fullmatch(r"[a-z0-9]{32}", fred_key)),
                "wisesheets_key_present": bool(wisesheets_key),
                "sec_contact_present": "@" in sec_agent and len(sec_agent) >= 10,
                "macro_collection_enabled": enabled("FINANCE_AUTO_REFRESH", "1"),
                "market_collection_enabled": enabled("FINANCE_INCLUDE_MARKETS", "0"),
                "earnings_collection_enabled": enabled("FINANCE_WISESHEETS_REFRESH", "1"),
                "alfred_collection_enabled": enabled("FINANCE_VINTAGE_REFRESH", "1"),
                "nport_collection_enabled": enabled("FINANCE_SEC_HOLDINGS_REFRESH", "0"),
                "vintage_snapshots_by_series": vintage_counts,
                "sec_nport_reports_stored": sec_reports,
                "oecd_surplus_accounts_installed": surplus_exists,
                "sec_earnings_snapshot_present": earnings_exists,
            },
            "catalog_series": len(by_id),
            "sources_with_at_least_one_observation": int(macro_count),
            "registered_market_instruments": len(market_registry),
            "market_instruments_with_prices": int(market_count),
            "currencies_with_fx_history": int(fx_count),
            "failed_macro_ingestion_runs_total": int(macro_failures),
            "last_successful_macro_run_utc": most_recent.isoformat() if most_recent else None,
            "macro_refresh_configured": enabled("FINANCE_AUTO_REFRESH", "1"),
            "optional_market_refresh_configured": enabled("FINANCE_INCLUDE_MARKETS", "0"),
            "automatic_backups_configured": enabled("FINANCE_AUTO_BACKUP", "1"),
            "local_backup_manifest_count": len(backups),
            "most_recent_backup_manifest": backups[0].name if backups else None,
            "limitations": ("Coverage counts indicate local data availability, not provider "
                            "freshness or source publication vintage. Backup manifests must "
                            "be copied to separate storage to survive disk failure."),
        }

    def require_dashboard_action(request: Request, marker: str | None) -> None:
        # JSON + custom header enforce a browser CORS preflight for cross-origin
        # requests. A cross-site form or embedded page cannot schedule imports.
        if marker != "dashboard":
            raise HTTPException(403, "Dashboard action header required")
        origin = request.headers.get("origin")
        if origin:
            from urllib.parse import urlsplit
            parsed = urlsplit(origin)
            if parsed.scheme not in ("http", "https") or parsed.netloc != request.headers.get("host"):
                raise HTTPException(403, "Cross-origin maintenance request rejected")
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Cross-site maintenance request rejected")

    @app.get("/api/maintenance")
    def maintenance_status():
        return maintenance.list()

    @app.post("/api/maintenance", status_code=202)
    def start_maintenance(command: MaintenanceCommand, request: Request,
                          x_gcm_action: str | None = Header(default=None)):
        require_dashboard_action(request, x_gcm_action)
        values = command.model_dump(exclude_none=True)
        action = values.pop("action")
        try:
            return maintenance.submit(action, values,
                valid_sources=supported, valid_markets=set(market_registry))
        except BusyMaintenance:
            raise HTTPException(409, "Another data operation is already running") from None
        except ValueError:
            raise HTTPException(422, "Invalid data operation or source selection") from None

    @app.post("/api/maintenance/{job_id}/cancel", status_code=202)
    def cancel_maintenance(job_id: str, request: Request,
                           x_gcm_action: str | None = Header(default=None)):
        require_dashboard_action(request, x_gcm_action)
        try:
            return maintenance.cancel(job_id)
        except ValueError:
            raise HTTPException(409, "This data operation is not active") from None

    @app.get("/api/source-coverage")
    def source_coverage():
        """Complete safe inventory of all mapped macro, market and ECB FX histories."""
        return build_coverage(db, catalog["series"], market_registry)

    @app.get("/api/research")
    def research_catalog():
        """Documented economic questions, actual source contracts and scoped regions."""
        return list_research()

    @app.get("/api/research/{indicator_id}")
    def research_indicator(indicator_id: str, start: date | None = None,
                           end: date | None = None):
        """Measured source series and validated same-period economic transformations."""
        if indicator_id not in RESEARCH_INDICATORS:
            raise HTTPException(404, "Unknown research indicator")
        if start and end and start > end:
            raise HTTPException(422, "Invalid analysis date range")
        try:
            return load_indicator(db, indicator_id, start=start, end=end)
        except ValueError:
            raise HTTPException(422, "Research source combination invalid") from None

    @app.get("/api/series")
    def list_series():
        return {"items": catalog["series"]}

    @app.get("/api/series/{series_id:path}")
    def get_series(series_id: str):
        item = by_id.get(series_id)
        if item is None:
            raise HTTPException(404, "Unknown series")
        return item

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

    @app.get("/api/vintages")
    def vintage_inventory():
        """Official ALFRED point-in-time cache; never a substitute for app snapshots."""
        return available_snapshots(Path(environ.get("FINANCE_VINTAGE_DIR","/data/vintages")))

    @app.get("/api/vintages/{series_id}")
    def vintage_series(series_id: str, asof: date):
        if series_id not in VINTAGE_SOURCES:
            raise HTTPException(404, "Unrecognized ALFRED series")
        if asof > date.today():
            raise HTTPException(422, "No future historical source vintages")
        try:
            data = read_alfred_snapshot(
                Path(environ.get("FINANCE_VINTAGE_DIR","/data/vintages")),
                series_id, asof)
        except (ValueError, KeyError):
            raise HTTPException(422, "Invalid source-vintage cache") from None
        if data is None:
            raise HTTPException(404, "No verified ALFRED vintage stored for this source date")
        return {**data, "latest_asof_reading":latest_asof_reading(data)}

    @app.get("/api/vintage/backtest")
    def vintage_recession_backtest(horizon_months: int = 12):
        if horizon_months not in (6,12):
            raise HTTPException(422, "Only pre-registered 6/12 month horizons are supported")
        return walk_forward(Path(environ.get("FINANCE_VINTAGE_DIR","/data/vintages")),
                            horizon=horizon_months)

    @app.get("/api/holdings/{instrument_id:path}")
    def dated_etf_holdings(instrument_id: str, asof: date | None = None):
        if instrument_id not in market_registry:
            raise HTTPException(404,"Unknown registered instrument")
        if asof and asof > date.today():
            raise HTTPException(422,"Future holdings availability date")
        try:
            return list_holdings(
                Path(environ.get("FINANCE_HOLDINGS_DIR","/data/holdings")),
                instrument_id, asof=asof)
        except HoldingsError:
            raise HTTPException(422, "No official SEC holdings contract for this asset") from None

    @app.get("/api/marx")
    def marx_data_availability():
        dataset = read_oecd_accounts(Path(environ.get("FINANCE_SURPLUS_DIR","/data/surplus")))
        if dataset is None:
            return {"status":"not_ingested","source":"OECD_IOT_2025_VALUE_ADDED_COMPONENTS",
                    "scenarios":list(MARX_SCENARIOS),
                    "warning":"No audited OECD IOT extract; never manufacture a surplus-value rate."}
        return {"status":"source_extract_available","source":dataset["release"],
                "country_years":sorted(set((r["country"],r["year"]) for r in dataset["rows"])),
                "scenarios":list(MARX_SCENARIOS),
                "source_extract_sha256":dataset["normalized_extract_sha256"],
                "warning":"National accounts accounting sensitivity, not an observed Marxian exploitation rate."}

    @app.get("/api/marx/{country}/{year}")
    def marx_accounting(country: str,year: int,scenario: str = "all_industries",
                        adjust_selfemployment: bool = False):
        if (scenario not in MARX_SCENARIOS or len(country) != 2
            or not country.isalpha() or year<1995 or year>2022):
            raise HTTPException(422,"Unsupported country/year/classification scope")
        data = read_oecd_accounts(Path(environ.get("FINANCE_SURPLUS_DIR","/data/surplus")))
        if data is None:
            raise HTTPException(404,"Audited OECD IOT extract not yet ingested")
        try:
            return compute_country_year(data,country=country.upper(),year=year,
                                        scenario=scenario,
                                        adjust_selfemployment=adjust_selfemployment)
        except AccountingError:
            raise HTTPException(422,"OECD source components incomplete or inconsistent") from None

    @app.get("/api/risk")
    def risk_catalog():
        """Source-defined diagnostic criteria; no composite scores."""
        return diagnostic_catalog()

    @app.get("/api/risk/{scope}")
    def risk_view(scope: str, start: date | None = None, end: date | None = None):
        if scope not in RISK_SCOPES:
            raise HTTPException(404, "Unknown risk scope")
        if start and end and start > end:
            raise HTTPException(422, "Invalid period")
        return read_diagnostics(db, scope, start=start, end=end)

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

    @app.post("/api/market/compare")
    def market_comparison(request: PortfolioComparison):
        """Actual stored market/ECB histories, currency-aligned common months."""
        invalid = [sid for sid in request.instrument_ids if sid not in market_registry]
        if invalid:
            raise HTTPException(404, "Unknown selected market instruments")
        if request.currency == "USD" and any(
            market_registry[sid]["trading_currency"] != "USD"
            for sid in request.instrument_ids
        ):
            raise HTTPException(
                422, "USD comparison requires USD-quoted assets; EUR-to-USD conversion is not provided"
            )
        service = MarketIngestionService(db, registry=market_registry)
        histories = {
            sid: service.read_performance(sid, start=request.start,
                                          end=request.end, snapshot_at=request.snapshot_at)
            for sid in request.instrument_ids
        }
        if any(len(item.get("observations", [])) > 100_000
               for item in histories.values()):
            raise HTTPException(413, "Market comparison exceeds source observation limit")
        try:
            weights = ({k: v / 100 for k, v in request.weights_pct.items()}
                       if request.weights_pct is not None else None)
            return compare_market_histories(
                histories, market_registry, currency=request.currency, weights=weights,
            )
        except ValueError:
            raise HTTPException(422, "Invalid market/currency comparison inputs") from None

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

    @app.post("/api/chart-insight")
    def chart_insight(request: SeriesQuery):
        """Backend-only descriptive statistics; compare like-for-like measures."""
        for sid in request.series_ids:
            if sid not in supported:
                raise HTTPException(422, f"Unavailable source: {sid}")
        if not same_measure(request.series_ids):
            raise HTTPException(422, "Unrelated economic measurements cannot share an insight")
        with Session(db) as session:
            rows = [(by_id[sid], current_observations(
                session, sid, request.start, request.end, request.snapshot_at))
                    for sid in request.series_ids]
        if any(len(points) > 100_000 for _, points in rows):
            raise HTTPException(413, "Readout exceeds source observation limit")
        return summarize(rows)

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
