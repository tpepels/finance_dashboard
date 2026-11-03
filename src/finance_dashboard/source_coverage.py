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
# Official BIS credit-to-GDP gaps release 2026-09-14 contains 2026-Q1
# observations; the next official release is scheduled for 2026-12-07.
# This is a time-bounded bulletin, not a permanent publication-lag exemption.
BIS_CREDIT_RELEASE = {
    "version": "BIS credit-to-GDP gaps, 14 September 2026",
    "released": date(2026, 9, 14),
    "expires": date(2026, 12, 7),
    "through": date(2026, 1, 1),
    "url": "https://data.bis.org/topics/CREDIT_GAPS",
}
SOURCE_LAGS = {"D": 10, "M": 95, "Q": 220, "A": 1100}

# Version-pinned official publication bounds, not a claim that the source
# publishes each calendar year. PWT 11.0 (released 2025-10-07) ends in 2023.
# Never use this exception for an empty history or an outdated 2022 history.
# Review/update this mapping when the canonical source contract changes version.
PUBLICATION_BOUNDS = {
    "labour." + country + ".pwt_labour_share": {
        "version": "Penn World Table 11.0",
        "released": date(2025, 10, 7),
        "through": date(2023, 1, 1),
        "url": "https://www.rug.nl/ggdc/productivity/pwt/",
    }
    for country in ("us", "jp", "de", "fr", "it")
}
SAFE_ERROR_CODES = {
    "provider_http_400", "provider_http_401", "provider_http_403",
    "provider_http_404", "provider_http_429", "provider_http_500",
    "provider_http_502", "provider_http_503", "provider_http_504",
    "source_parse_failed", "source_empty", "source_transport_failed",
    "source_invalid", "provider_failed", "fred_schema_invalid",
    "fred_empty", "fred_table_invalid", "source_date_invalid",
    "source_duplicate_period", "source_value_invalid", "source_empty",
    "source_window_invalid", "source_future_date", "source_mapping_mismatch",
    "shiller_incomplete", "shiller_schema_invalid",
    "shiller_link_unavailable", "shiller_download_unapproved",
    "shiller_workbook_invalid", "shiller_download_invalid", "shiller_header_invalid",
    "shiller_empty", "shiller_window_empty", "fred_window_empty", "fx_identity_mismatch",
    "fx_schema_invalid", "fx_empty", "fx_value_invalid",
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


def _internal_calendar_gaps(first: date | None, last: date | None,
                            frequency: str, recorded: int) -> int | None:
    # No daily gap guessing: weekends, closures, exchange holidays and irregular
    # releases require a publisher-specific calendar.
    if first is None or last is None or frequency not in ("A","Q","M"):
        return None
    span_months = (last.year-first.year)*12 + last.month-first.month
    if frequency == "A":
        slots = last.year-first.year+1
    elif frequency == "Q":
        slots = span_months//3+1
    else:
        slots = span_months+1
    return max(0, slots-recorded)


def _make_item(*, family: str, id: str, name: str, provider: str, frequency: str,
               configured: bool, mapped: bool, counts: dict,
               runs: dict, successes: dict, asof: date) -> dict:
    count, oldest, latest, versions = counts.get(id, (0, None, None, 0))
    last = runs.get(id)
    successful = successes.get(id)
    lag = (asof - latest).days if latest is not None else None
    publication = PUBLICATION_BOUNDS.get(id) if family == "macro" else None
    if (family == "macro" and provider in ("BIS_CREDIT_GAP", "BIS_WORLD_WEIGHTED")
            and BIS_CREDIT_RELEASE["released"] <= asof < BIS_CREDIT_RELEASE["expires"]):
        publication = BIS_CREDIT_RELEASE
    release_known = bool(publication and asof >= publication["released"]
                         and asof < publication.get("expires", date.max))
    published_through = publication["through"] if release_known else None
    is_complete_for_release = bool(
        latest is not None and published_through is not None
        and latest >= published_through
    )
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
    elif lag is not None and lag > SOURCE_LAGS[frequency] and not is_complete_for_release:
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
        "published_through": published_through.isoformat()
            if published_through else None,
        "published_release": publication["version"] if release_known else None,
        "published_release_date": publication["released"].isoformat()
            if release_known else None,
        "complete_for_pinned_release": is_complete_for_release,
        # Revisions are legitimate append-only versions, not corrupt duplicates.
        "stored_versions": int(versions),
        "additional_revisions": max(0, int(versions)-int(count)),
        "unobserved_internal_periods": _internal_calendar_gaps(
            oldest, latest, frequency, int(count)),
        "regular_cadence_assumed": provider not in (
            "MSCI_PUBLISHED_TOP10", "SIBLIS_FREE", "SIBLIS_WORLD_PE",
            "SIBLIS_WORLD_EARNINGS_YIELD", "CORGANO_SPOT"),
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
                  func.min(period), func.max(period),
                  func.count()).group_by(key)
    return {sid: (count, first, last, revisions)
            for sid, count, first, last, revisions in session.execute(stmt)}


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
                   "Internal calendar gaps are diagnostic only for regular annual, "
                   "quarterly and monthly sources; irregular publications may "
                   "legitimately omit years, and daily exchange holidays are not "
                   "interpreted as missing data. Pinned published PWT 11.0 coverage "
                   "through 2023 is considered current for that release, not stale. "
                   "BIS credit-gap Q1 2026 is current only for its verified "
                   "14 September to 6 December 2026 release window. "
                   "Additional versions preserve source revisions."),
    }
