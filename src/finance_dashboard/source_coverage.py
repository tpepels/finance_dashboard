"""Read-only, source-by-source local evidence census.

Store counts and source-period ranges separately from ingestion attempts:
successfully imported observations remain available after a later failed refresh.
No raw provider errors, credentials, request URLs or personal data leave this API.
"""
from __future__ import annotations

from datetime import date
from os import environ

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from .database import (
    IngestionRun, ObservationVersion, MarketIngestionRun, MarketPriceVersion,
    FxIngestionRun, FxRateVersion,
)

FX_CURRENCIES = ("USD", "GBP", "CHF")
SOURCE_LAGS = {"D": 10, "M": 95, "Q": 220, "A": 1100}
SAFE_ERROR_CODES = {
    "provider_http_400", "provider_http_401", "provider_http_403",
    "provider_http_404", "provider_http_429", "provider_http_500",
    "provider_http_502", "provider_http_503", "provider_http_504",
    "source_parse_failed", "source_empty", "source_transport_failed",
    "source_invalid", "provider_failed",
}


def _yes(name: str, default: str) -> bool:
    return environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _summary(items: list[dict]) -> dict:
    result = {"total": len(items)}
    for item in items:
        state = item["state"]
        result[state] = result.get(state, 0) + 1
    result["with_data"] = sum(item["stored_periods"] > 0 for item in items)
    result["without_data"] = result["total"] - result["with_data"]
    result["needs_attention"] = sum(item["state"] in {
        "not_ingested", "collection_disabled", "collection_failed",
        "refresh_failed_with_data", "stale", "source_unresolved",
    } for item in items)
    return result


def _make_item(*, family: str, id: str, name: str, provider: str, frequency: str,
               configured: bool, mapped: bool, counts: dict,
               runs: dict, successes: dict, asof: date) -> dict:
    count, oldest, latest = counts.get(id, (0, None, None))
    last = runs.get(id)
    successful = successes.get(id)
    lag = (asof - latest).days if latest is not None else None
    if not mapped:
        state = "source_unresolved"
    elif count == 0 and last is not None and last["status"] == "failed":
        state = "collection_failed"
    elif count == 0 and not configured:
        state = "collection_disabled"
    elif count == 0:
        state = "not_ingested"
    elif last is not None and last["status"] == "failed":
        state = "refresh_failed_with_data"
    elif lag is not None and lag > SOURCE_LAGS[frequency]:
        state = "stale"
    else:
        state = "available"
    last_error = last["error"] if last is not None else None
    return {
        "family": family, "id": id, "name": name, "provider": provider,
        "frequency": frequency, "state": state, "collection_enabled": configured,
        "mapped": mapped, "stored_periods": int(count),
        "oldest_source_date": oldest.isoformat() if oldest else None,
        "latest_source_date": latest.isoformat() if latest else None,
        "days_since_latest_observation": lag,
        "last_attempt_utc": last["started_at"].isoformat() if last else None,
        "last_attempt_state": last["status"] if last else "never",
        "last_success_utc": successful["ended_at"].isoformat()
            if successful and successful["ended_at"] else None,
        "last_failure_code": last_error
            if isinstance(last_error, str) and last_error in SAFE_ERROR_CODES
            else ("provider_failed" if last and last["status"] == "failed" else None),
    }


def _runs(session: Session, model, key) -> tuple[dict, dict]:
    # Do not load ORM instances or source request/error text unnecessarily.
    stmt = select(key, model.started_at, model.ended_at, model.status,
                  model.error if hasattr(model, "error") else model.status).order_by(
                      model.started_at.desc(), model.id.desc())
    newest, successful = {}, {}
    for sid, started, ended, status, failure in session.execute(stmt):
        if sid not in newest:
            newest[sid] = {"started_at": started, "ended_at": ended,
                           "status": status, "error": failure if hasattr(model, "error") else None}
        if status == "success" and sid not in successful:
            successful[sid] = {"ended_at": ended}
    return newest, successful


def _counts(session: Session, model, key, period) -> dict:
    stmt = select(key, func.count(distinct(period)),
                  func.min(period), func.max(period)).group_by(key)
    return {sid: (count, first, last)
            for sid, count, first, last in session.execute(stmt)}


def build_coverage(engine, catalog: list[dict], market_registry: dict[str, dict],
                   *, asof: date | None = None) -> dict:
    """Account for each registered source, even if it has never been imported."""
    today = asof or date.today()
    macro_enabled = _yes("FINANCE_AUTO_REFRESH", "1")
    market_enabled = macro_enabled and _yes("FINANCE_INCLUDE_MARKETS", "0")
    with Session(engine) as session:
        macro_counts = _counts(session, ObservationVersion,
                               ObservationVersion.series_id, ObservationVersion.period)
        market_counts = _counts(session, MarketPriceVersion,
                                MarketPriceVersion.instrument_id, MarketPriceVersion.day)
        fx_counts = _counts(session, FxRateVersion, FxRateVersion.currency, FxRateVersion.day)
        macro_runs, macro_success = _runs(session, IngestionRun, IngestionRun.series_id)
        market_runs, market_success = _runs(session, MarketIngestionRun,
                                           MarketIngestionRun.instrument_id)
        fx_runs, fx_success = _runs(session, FxIngestionRun, FxIngestionRun.currency)

    macros = [_make_item(
        family="macro", id=item["id"], name=item["name"],
        provider=item["provider"], frequency=item.get("frequency") or "A",
        configured=macro_enabled, mapped=item["status"] == "mapped",
        counts=macro_counts, runs=macro_runs, successes=macro_success, asof=today,
    ) for item in sorted(catalog, key=lambda row: row["id"])]

    markets = [_make_item(
        family="markets", id=ident, name=instrument["name"],
        provider="YAHOO_CHART", frequency="D", configured=market_enabled,
        mapped=True, counts=market_counts, runs=market_runs,
        successes=market_success, asof=today,
    ) for ident, instrument in sorted(market_registry.items())]

    fx = [_make_item(
        family="fx", id=currency, name="ECB " + currency + " per EUR",
        provider="ECB", frequency="D", configured=market_enabled,
        mapped=True, counts=fx_counts, runs=fx_runs, successes=fx_success, asof=today,
    ) for currency in FX_CURRENCIES]

    return {
        "asof": today.isoformat(),
        "summary": {
            "macro": _summary(macros),
            "markets": _summary(markets),
            "fx": _summary(fx),
        },
        "items": macros + markets + fx,
        "method": ("Distinct source reference periods with first and last stored dates. "
                   "Latest failed attempts do not erase previous data. Currency and market "
                   "source freshness is measured against source days, not application refresh. "
                   "Annual and quarterly lag thresholds are descriptive; some published "
                   "sources intentionally stop before the current year."),
    }
