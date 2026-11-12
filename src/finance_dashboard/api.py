"""Read-only API: exposes actual stored observations, never synthetic chart values."""
from __future__ import annotations

from datetime import date, datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path
from os import environ
import re
import json

from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, model_validator, ConfigDict
from sqlalchemy import select, text, func, distinct
from sqlalchemy.orm import Session

from .providers import ProviderRouter, PROVIDER_CODES
from .catalog import load_documents, validate
from .database import IngestionRun, ObservationVersion, MarketPriceVersion, FxRateVersion, make_engine
from .service import current_observations
from .market import instruments
from .market_service import MarketIngestionService
from .vintage import SOURCES as VINTAGE_SOURCES, read_snapshot as read_alfred_snapshot, available_snapshots, latest_asof_reading
from .sec_holdings import list_holdings, read_position_source, HoldingsError
from .ucits_holdings import read_ucits_sources, UcitsHoldingsError

from .source_coverage import build_coverage
from .source_policy import policy_summary
from .research_corpus import load_research_corpus, validate_research_corpus
from .research_runtime import evaluate_corpus
from .engine.acceptance import AcceptanceCache, AcceptanceLoading, AcceptanceUnavailable, snapshot_from_report
from .engine.export import export_text
from .engine.artifacts import load_artifact
from .owner_inputs import OwnerInputError, load_owner_inputs, save_owner_inputs
from .engine.runner import analysis_bundle, conditionals, list_analyses
from .engine.recessions import SERIES_ID as RECESSION_SERIES, recession_periods
from .engine.views import figure_capabilities
from .engine.evidence_guard import EvidenceState, AcceptedInputsChanged
from .engine.cache import BundleCache
from .icio import read_icio_evidence
from .maintenance import MaintenanceManager, BusyMaintenance
from .developer_logs import read_events, recent_jobs, record_event
from .database import MarketIngestionRun, FxIngestionRun
from .standalone import mount_built_dashboard, standalone_lifespan


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


class SavedViewCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    name: str = Field(min_length=1, max_length=120)
    analysis_id: str
    spec: dict


class SavedViewUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    name: str = Field(min_length=1, max_length=120)
    spec: dict
    revision: int = Field(ge=1)


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
    bundles = BundleCache(db)

    @asynccontextmanager
    async def lifespan(app):
        try:
            async with standalone_lifespan(app, engine=db):
                yield
        finally:
            bundles.close()

    app = FastAPI(title="Global Capital Monitor", version="0.2.0",
                  lifespan=lifespan)
    catalog, chart_catalog = load_documents()
    errors = validate(catalog, chart_catalog)
    if errors:
        raise RuntimeError("Catalog invalid: " + "; ".join(errors))
    research_sources = load_research_corpus()
    corpus_issues = validate_research_corpus(research_sources, catalog["series"])
    if corpus_issues:
        raise RuntimeError("Phase 2 research source inventory invalid: " + "; ".join(corpus_issues))
    by_id = {s["id"]: s for s in catalog["series"]}
    supported = {sid for sid, s in by_id.items() if s["status"] == "mapped" and s["provider"] in PROVIDER_CODES}
    maintenance = MaintenanceManager(db)
    market_registry = instruments()

    @app.middleware("http")
    async def record_unexpected_api_failure(request: Request, call_next):
        # Do not persist request paths, query parameters, headers or exception
        # details. A 5xx code is enough to correlate a server fault with the
        # time and a subsequent source/status inspection.
        try:
            response = await call_next(request)
        except Exception:
            record_event("system", "collector_failed", level="error",
                         stage="api", reason="internal_error")
            raise
        # Acceptance may return 503 with Retry-After while re-evaluating
        # evidence. This is an expected wait, not a failed source collector.
        if response.status_code >= 500 and not (
                response.status_code == 503 and response.headers.get("Retry-After")):
            record_event("system", "collector_failed", level="error",
                         stage="api", reason="http_5xx",
                         http_status=response.status_code)
        return response

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

    @app.get("/api/developer-log")
    def developer_log():
        """Small, non-sensitive browser diagnostic report; no raw server logs.

        Generated only on request. The private LAN dashboard is not designed
        for direct public exposure; this endpoint returns pre-whitelisted
        status codes, never headers, exception text, provider payloads or URLs.
        """
        census = build_coverage(db, catalog["series"], market_registry)
        issues = [{
            "family": item["family"],
            "id": item["id"],
            "state": item["state"],
            "latest_source_date": item["latest_source_date"],
            "last_failure_code": item["last_failure_code"],
        } for item in census["items"] if item["state"] != "available"]
        fred_key = environ.get("FRED_API_KEY", "").strip()
        sec_contact = environ.get("SEC_USER_AGENT", "").strip()
        fred_mode = ("authenticated_api" if fred_key else
                     "public_csv" if environ.get("FRED_PUBLIC_CSV_FALLBACK") == "1"
                     else "public_table")
        return {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "configuration": {
                "fred_mode": fred_mode,
                "fred_key_present": bool(fred_key),
                "fred_key_format_valid": bool(re.fullmatch(r"[a-z0-9]{32}", fred_key)),
                "sec_contact_present": "@" in sec_contact and len(sec_contact) >= 10,
                "scheduled_refresh_enabled": environ.get(
                    "FINANCE_AUTO_REFRESH", "1").lower() in ("1","yes","true","on"),
            },
            "coverage": {
                "registered": len(census["items"]),
                "with_data": sum(item["stored_periods"] > 0
                                 for item in census["items"]),
                "needs_attention": len(issues),
            },
            "issues": issues,
            "jobs": recent_jobs(maintenance.list()["jobs"]),
            "events": read_events(limit=400),
            "retention": "Latest 400 structured events; latest 8 job summaries",
        }

    @app.get("/api/source-policy")
    def source_policy_status():
        """Canonical publisher restrictions and current safe, redacted cooldowns."""
        return policy_summary()

    @app.get("/api/source-coverage")
    def source_coverage():
        """Complete safe inventory of all mapped macro, market and ECB FX histories."""
        return build_coverage(db, catalog["series"], market_registry)

    @app.get("/api/research-corpus")
    def source_research_corpus():
        """Phase 2 approved-question source evidence, with actual stored-source periods."""
        return current_corpus_report()

    @app.get("/api/source-evidence/icio")
    def original_icio_evidence():
        """Original matrix accounting evidence; no native cells or source request secrets."""
        try:
            return read_icio_evidence(Path(environ.get("FINANCE_SOURCE_EVIDENCE_DIR", "/data/source-evidence")))
        except (OSError, ValueError, KeyError, TypeError):
            raise HTTPException(422, "Original ICIO matrix evidence failed validation") from None

    def current_corpus_evaluation(analyses=None):
        root = Path(environ.get("FINANCE_SOURCE_EVIDENCE_DIR", "/data/source-evidence"))
        document = research_sources if analyses is None else {**research_sources, "analyses": analyses}
        return evaluate_corpus(db, catalog["series"], document,
            evidence_root=root, market_registry=market_registry,
            vintage_root=Path(environ.get("FINANCE_VINTAGE_DIR", "/data/vintages")),
            holdings_root=Path(environ.get("FINANCE_HOLDINGS_DIR", "/data/holdings")))

    def current_corpus_report(analyses=None):
        return current_corpus_evaluation(analyses).public_report

    def acceptance_snapshot():
        evidence = EvidenceState.capture([Path(environ.get(key, default)) for key, default in [
            ('FINANCE_SOURCE_EVIDENCE_DIR', '/data/source-evidence'),
            ('FINANCE_VINTAGE_DIR', '/data/vintages'), ('FINANCE_HOLDINGS_DIR', '/data/holdings'),
            ('FINANCE_OWNER_INPUTS', '/data/owner-inputs.json'),
            ('FINANCE_PORTFOLIO_HOLDINGS', '/data/portfolio-holdings.json')]])
        evaluation = current_corpus_evaluation()
        if not evidence.unchanged():
            raise AcceptedInputsChanged('Evidence changed during assessment')
        versions = {sid: coverage['all_current_versions_sha256'] for panel in evaluation.comparative['panels']
                    for sid, coverage in panel['input_coverage'].items()}
        values = {row['series_id']:row['stored_observations_sha256'] for row in evaluation.source_proof['series']
                  if row.get('stored_observations_sha256')}
        return snapshot_from_report(evaluation.public_report, datetime.now(timezone.utc), source_versions=versions,
                                    source_values=values, evidence_state=evidence)

    app.state.acceptance = AcceptanceCache(
        acceptance_snapshot, ttl_seconds=float(environ.get("FINANCE_ACCEPTANCE_TTL_SECONDS", "3600")))
    # The live evaluation takes minutes: start it with the application's other
    # background work, so the first visitor rarely waits. Only a persistent
    # database is evaluated concurrently; an in-memory one is a test fixture
    # whose single shared connection cannot serve a second thread.
    persistent = db.url.get_backend_name() != "sqlite" or db.url.database not in (None, "", ":memory:")
    if persistent and environ.get("FINANCE_AUTO_REFRESH", "1").lower() in ("1", "yes", "true", "on"):
        app.state.acceptance.warm()

    def acceptance_or_503():
        try:
            snapshot = app.state.acceptance.get()
            if snapshot.evidence_state is not None and not snapshot.evidence_state.unchanged():
                app.state.acceptance.invalidate()
                raise AcceptanceLoading()
            return snapshot
        except AcceptanceLoading:
            raise HTTPException(503, "Phase 2 acceptance evaluation in progress",
                                headers={"Retry-After": "30"}) from None
        except AcceptanceUnavailable as error:
            record_event("system", "collector_failed", level="error", stage="phase2_acceptance",
                         reason=str(error))
            if str(error) == 'AcceptedInputsChanged':
                raise HTTPException(503, 'Sources changed during assessment; this page will retry',
                                    headers={'Retry-After': '30'}) from None
            raise HTTPException(503, "Phase 2 acceptance evaluation unavailable") from None

    def engine_bundle(analysis_id: str, today: date | None, raw_view: str | None = None):
        if not any(row['id'] == analysis_id for row in research_sources['analyses']):
            raise HTTPException(404, 'Unknown analysis')
        snapshot = acceptance_or_503()
        view = {"today": (today or date.today()).isoformat()}
        if raw_view is not None:
            try:
                if len(raw_view) > 16000: raise ValueError('Figure specification is too large')
                parsed = json.loads(raw_view)
                if not isinstance(parsed, dict) or 'today' in parsed: raise ValueError('Use a figure object; today is a separate query parameter')
                if 'figure_id' not in parsed: raise ValueError('Select a figure')
                view.update(parsed)
            except (ValueError, TypeError) as error:
                raise HTTPException(422, str(error)) from None
        def compute():
            with Session(db) as session:
                return analysis_bundle(session, analysis_id, snapshot=snapshot, corpus_document=research_sources,
                                         catalog_series=by_id, view=view, artifact_loader=lambda name: load_artifact(
                                             name, evidence_root=Path(environ.get("FINANCE_SOURCE_EVIDENCE_DIR", "/data/source-evidence")),
                                             holdings_root=Path(environ.get("FINANCE_HOLDINGS_DIR", "/data/holdings"))))
        try:
            owner_state = EvidenceState.capture([Path(environ.get(key, default)) for key, default in (
                ('FINANCE_OWNER_INPUTS', '/data/owner-inputs.json'),
                ('FINANCE_PORTFOLIO_HOLDINGS', '/data/portfolio-holdings.json'))])
            request_key = (analysis_id, json.dumps(view, sort_keys=True), owner_state.entries,
                           environ.get('FINANCE_SOURCE_EVIDENCE_DIR', '/data/source-evidence'),
                           environ.get('FINANCE_HOLDINGS_DIR', '/data/holdings'))
            bundle = bundles.get(request_key, snapshot, compute)
        except ValueError as error:
            if raw_view is None: raise
            raise HTTPException(422, str(error)) from None
        except AcceptedInputsChanged:
            app.state.acceptance.invalidate()
            raise HTTPException(503, 'Input evidence changed; acceptance is being reassessed',
                                headers={'Retry-After':'30'}) from None
        if bundle is None:
            raise HTTPException(404, "Unknown analysis")
        return bundle

    @app.get("/api/analysis")
    def analysis_list():
        """Every corpus analysis with its Phase 2 state and whether the engine computes it."""
        return list_analyses(acceptance_or_503(), research_sources)

    @app.get('/api/research-status')
    def research_status_report():
        """Research scope and current evidence boundaries, without recomputing figures."""
        from .research_status import research_status
        return research_status(acceptance_or_503(), research_sources)

    @app.get("/api/analysis/{analysis_id}")
    def analysis_result(analysis_id: str, today: date | None = None, view: str | None = None):
        """One analysis as a self-describing result bundle."""
        return engine_bundle(analysis_id, today, view)

    @app.get('/api/analysis/{analysis_id}/views/capabilities')
    def analysis_view_capabilities(analysis_id: str, today: date | None = None):
        bundle = engine_bundle(analysis_id, today)
        return figure_capabilities(analysis_id, by_id, bundle)

    @app.get("/api/analysis/{analysis_id}/export", response_class=PlainTextResponse)
    def analysis_export(analysis_id: str, today: date | None = None, view: str | None = None):
        """The bundle as one text file for discussing it with an AI."""
        bundle = engine_bundle(analysis_id, today, view)
        name = f"{analysis_id}-{bundle['computed_at'][:10]}.txt"
        return PlainTextResponse(export_text(bundle),
                                 headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.get("/api/owner-inputs")
    def owner_inputs():
        """The owner's portfolio parameters, or the labelled example until they are saved."""
        return load_owner_inputs()

    def holdings_operation(action):
        from .portfolio_holdings import (PortfolioHoldingsError, PortfolioHoldingsConflict,
                                         PortfolioHoldingsUnavailable)
        try:
            return action()
        except PortfolioHoldingsConflict as error:
            raise HTTPException(409, str(error)) from None
        except PortfolioHoldingsUnavailable:
            raise HTTPException(503, 'Your holdings could not be read; preserve the file and restore a verified backup') from None
        except PortfolioHoldingsError as error:
            raise HTTPException(422, str(error)) from None
        except OSError:
            raise HTTPException(503, 'Your holdings could not be stored; check the writable data directory') from None

    @app.get('/api/portfolio-holdings')
    def owner_holdings():
        from .portfolio_holdings import load_portfolio_holdings
        return holdings_operation(load_portfolio_holdings)

    @app.put('/api/portfolio-holdings')
    def save_owner_holdings(body: dict):
        from .portfolio_holdings import save_portfolio_holdings
        saved = holdings_operation(lambda: save_portfolio_holdings(body))
        app.state.acceptance.invalidate()
        return saved

    def saved_store_operation(action):
        from .saved_views import (SavedViewStore, SavedViewConflict, SavedViewNotFound,
                                  SavedViewUnavailable, SavedViewError)
        try:
            return action(SavedViewStore())
        except SavedViewConflict as error:
            raise HTTPException(409, str(error)) from None
        except SavedViewNotFound as error:
            raise HTTPException(404, str(error)) from None
        except SavedViewUnavailable:
            raise HTTPException(503, 'Saved figures could not be read; preserve the file and restore a verified backup') from None
        except SavedViewError as error:
            raise HTTPException(422, str(error)) from None
        except OSError:
            raise HTTPException(503, 'Saved figures could not be stored; check the writable data directory') from None

    def normalized_saved_spec(analysis_id, spec):
        bundle = engine_bundle(analysis_id, None, json.dumps(spec))
        return {k: v for k, v in bundle['view'].items() if k != 'today'}

    @app.get('/api/saved-views')
    def saved_views_list():
        return {'items': saved_store_operation(lambda store: store.list())}

    @app.post('/api/saved-views', status_code=201)
    def saved_view_create(body: SavedViewCreate):
        normalized = normalized_saved_spec(body.analysis_id, body.spec)
        return saved_store_operation(lambda store: store.create(body.name, body.analysis_id, normalized))

    @app.put('/api/saved-views/{view_id}')
    def saved_view_update(view_id: str, body: SavedViewUpdate):
        rows = saved_store_operation(lambda store: store.list())
        current = next((r for r in rows if r['id'] == view_id), None)
        if current is None: raise HTTPException(404, 'Saved figure not found')
        normalized = normalized_saved_spec(current['analysis_id'], body.spec)
        return saved_store_operation(lambda store: store.update(view_id, body.name, normalized, body.revision))

    @app.delete('/api/saved-views/{view_id}', status_code=204)
    def saved_view_delete(view_id: str, revision: int):
        saved_store_operation(lambda store: store.delete(view_id, revision))
        from fastapi.responses import Response
        return Response(status_code=204)

    @app.put("/api/owner-inputs")
    def save_owner(body: dict):
        """Validate and store the owner's portfolio parameters locally."""
        try:
            saved = save_owner_inputs(None, body)
        except (OwnerInputError, ValueError, TypeError, KeyError) as error:
            raise HTTPException(422, str(error) or "Invalid portfolio inputs") from None
        except OSError:
            raise HTTPException(500, "Your portfolio inputs could not be stored; check that the data folder is writable") from None
        # Phase 2 accepts owner-supplied roles from these inputs: re-evaluate in the background.
        if persistent:
            app.state.acceptance.refresh()
        return saved

    @app.get("/api/recessions")
    def recessions():
        """NBER US recession periods for shading every time chart."""
        with Session(db) as session:
            points = [(row.period, float(row.value))
                      for row in current_observations(session, RECESSION_SERIES)]
        return {"series_id": RECESSION_SERIES, "periods": recession_periods(points),
                "note": "NBER-dated US recessions; not world or regional recession dates."}

    @app.get("/api/conditionals")
    def conditional_analyses():
        """Every conditional analysis with its Phase 2 limitations."""
        return conditionals(acceptance_or_503())

    @app.get("/api/research-corpus/{analysis_id}")
    def research_corpus_question(analysis_id: str):
        """Return explicit source references, missing evidence and fallbacks."""
        match = next((row for row in research_sources["analyses"] if row["id"] == analysis_id), None)
        if match is None:
            raise HTTPException(404, "Unknown approved scientific question")
        return current_corpus_report([match])["analyses"][0]

    @app.get("/api/series")
    def list_series():
        return {"items": catalog["series"]}

    @app.get("/api/series/{series_id:path}")
    def get_series(series_id: str):
        item = by_id.get(series_id)
        if item is None:
            raise HTTPException(404, "Unknown series")
        return item

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

    @app.get("/api/holdings/ucits/sources")
    def original_ucits_sources():
        try:
            return read_ucits_sources(Path(environ.get("FINANCE_HOLDINGS_DIR", "/data/holdings")))
        except UcitsHoldingsError:
            raise HTTPException(422, "Original UCITS source evidence failed validation") from None

    @app.get("/api/holdings/{instrument_id:path}/positions")
    def original_sec_positions(instrument_id: str, accession: str):
        try:
            return read_position_source(Path(environ.get("FINANCE_HOLDINGS_DIR", "/data/holdings")),
                instrument_id, accession)
        except HoldingsError:
            raise HTTPException(422, "Original SEC position evidence failed validation") from None

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

    # Shared API, production data mount and canonical original evidence store.
    from .original_uploads import OriginalImportManager, install_original_uploads
    from .diagnostics_api import install_diagnostics
    app.state.original_imports = OriginalImportManager()
    install_original_uploads(app, app.state.original_imports, persistent=persistent)
    install_diagnostics(app, db=db, catalog=catalog, market_registry=market_registry,
                        maintenance=maintenance, importer=app.state.original_imports)

    # Existing API routes always take priority over bundled Vite assets.
    mount_built_dashboard(app)
    return app


# Used by uvicorn: make database configuration explicit at application startup.
def app_factory() -> FastAPI:
    return create_app()
