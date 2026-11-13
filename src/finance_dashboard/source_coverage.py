"""Read-only, source-by-source local evidence census.

Store counts and source-period ranges separately from ingestion attempts:
successfully imported observations remain available after a later failed refresh.
No raw provider errors, credentials, request URLs or personal data leave this API.
"""
from __future__ import annotations

from datetime import date
from os import environ

from sqlalchemy import distinct, func, select, literal
from sqlalchemy.orm import Session

from .database import (
    IngestionRun, ObservationVersion, MarketIngestionRun, MarketPriceVersion,
    FxIngestionRun, FxRateVersion,
)
from .oecd_tiva import TIVA_SERIES
from .research_returns import SWINKELS_SERIES

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
# Official DSR overview/calendar and all eight exact SDMX keys checked on
# 2026-11-04: data/reference/bis_dsr_2026q1.json. These are publisher bounds,
# not observation-level first-publication vintages or proof of local ingestion.
BIS_DSR_RELEASE = {
    "version": "BIS debt service ratios, 14 September 2026",
    "released": date(2026, 9, 14),
    "expires": date(2026, 12, 7),
    "through": date(2026, 1, 1),
    "url": "https://data.bis.org/topics/DSR",
}
SOURCE_LAGS = {"D": 10, "W": 22, "M": 95, "Q": 220, "A": 1100}

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
# These named series use the fixed TiVA 2025 edition, dataflow version 1.1.
# Its January 2026 revision retains the 1995--2022 reference years; this is
# current for that pinned edition, not a provider-wide freshness exemption.
PUBLICATION_BOUNDS.update({
    identifier: {
        "version": "TiVA 2025 edition, January 2026 revision",
        "released": date(2026, 1, 22),
        "through": date(2022, 1, 1),
        "url": (
            "https://data-explorer.oecd.org/vis?bp=true&df%5Bag%5D=OECD.STI.PIE"
            "&df%5Bds%5D=dsDisseminateFinalDMZ&df%5Bid%5D=DSD_TIVA_MAINLV%40DF_MAINLV"
            "&df%5Bvs%5D=1.1&pg=0&snb=12&tm=TiVA"
        ),
    }
    for identifier in TIVA_SERIES
})
# The immutable original Swinkels v6 workbook ends December 2022. Its
# January 2023 scholarly dataset release is distinct from the 2025 repository
# migration and does not establish any historical observation first release.
PUBLICATION_BOUNDS.update({
    identifier: {
        "version": "Swinkels original dataset v6",
        "released": date(2023, 1, 10),
        "through": date(2022, 12, 1),
        "url": "https://doi.org/10.25397/eur.8152748.v6",
    }
    for identifier in SWINKELS_SERIES
})
# Publication-aware bounds confirmed against the current publisher release
# pages on 2026-11-12. These are not generic source-frequency exemptions:
# source content must actually reach the stated last published reference date.
#
# 2025 EUKLEMS & INTANProd spans through 2021. The exact publisher publication
# DAY is not asserted: verified_as_of is our evidence check date.
_EUKLEMS_COUNTRIES = ("de", "es", "fr", "gb", "it", "nl", "pt", "us")
_EUKLEMS_MEASURES = (
    "hours_worked", "labour_compensation", "value_added",
    "value_added_price_index",
)
PUBLICATION_BOUNDS.update({
    f"labour.{country}.euklems_{measure}": {
        "version": "EUKLEMS & INTANProd 2025 release",
        "verified_as_of": date(2026, 11, 12),
        # 30-day re-verification deadline, NOT an asserted publisher release.
        # Without this, a yearly version could be suppressed forever.
        "expires": date(2026, 12, 12),
        "through": date(2021, 1, 1),
        "url": "https://euklems-intanprod-llee.luiss.it/",
    } for country in _EUKLEMS_COUNTRIES for measure in _EUKLEMS_MEASURES
})

# The World Bank's Poverty and Inequality Platform survey Gini histories are
# irregular household-survey series, NOT observations due every calendar year.
# Publisher country pages checked 2026-11-13 explicitly show the listed
# latest years. A 30-day expiration prevents silently carrying an obsolete
# "latest published" claim into the future. Check the exact publisher series
# again after expiration; do not invent a missing survey observation.
_PIP_GINI_LATEST = {"cn": (2022, "CN"), "fr": (2023, "FR"),
                    "in": (2023, "IN"), "pt": (2023, "PT")}
PUBLICATION_BOUNDS.update({
    f"inequality.{country}.gini_survey_wdi": {
        "version": "World Bank PIP Gini country history, verified 2026-11-13",
        "verified_as_of": date(2026, 11, 13),
        "expires": date(2026, 12, 13),
        "through": date(latest_year, 1, 1),
        "url": f"https://data.worldbank.org/indicator/SI.POV.GINI?locations={iso}",
    }
    for country, (latest_year, iso) in _PIP_GINI_LATEST.items()
})

# BIS Data Portal exact series pages verified on 2026-11-13. The
# selected residential real indexes have country-specific end periods. Do
# not apply the portal's *general* release-calendar quarter to every key.
# Recheck before the scheduled 26 November selected-residential update.
_BIS_PROPERTY_SERIES_END = {
    "property.jp.real_residential.bis": ("JP", date(2025, 10, 1)),
    "property.world.real_residential.bis": ("XW", date(2026, 1, 1)),
    "property.us.real_residential.bis": ("US", date(2026, 4, 1)),
    "property.ea.real_residential.bis": ("XM", date(2026, 4, 1)),
}
PUBLICATION_BOUNDS.update({
    sid: {
        "version": f"BIS selected residential property prices WS_SPP Q.{area}.R.628",
        "verified_as_of": date(2026, 11, 13),
        "expires": date(2026, 11, 26),
        "through": through,
        "url": f"https://data.bis.org/topics/RPP/BIS%2CWS_SPP%2C1.0/Q.{area}.R.628",
    }
    for sid, (area, through) in _BIS_PROPERTY_SERIES_END.items()
})

# Immutable primary-source artifacts: a verified *original edition* does
# not acquire new months. Do not claim the scientific content is the latest
# live market price or a publisher's current issue. The archived FRED original
# is a 2025-11-04T20:41Z snapshot, not the current FRED HYOAS series.
PUBLICATION_BOUNDS.update({
    "stress.us.high_yield_oas_fred_archive": {
        "version": "Pinned FRED archived BAMLH0A0HYM2 capture 20251104204105",
        "verified_as_of": date(2026, 11, 13),
        "through": date(2025, 11, 3),
        "url": "https://web.archive.org/web/20251104204105id_/https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2",
    },
    "returns.doeswijk_swinkels.global_multiasset.usd.nominal": {
        "version": "Pinned Doeswijk-Swinkels GMP JIMF original workbook (SHA-256 a66ce1c1...)",
        "verified_as_of": date(2026, 11, 13),
        "through": date(2022, 12, 1),
        "url": "https://laurensswinkels.com/wp-content/uploads/2025/11/public-data-file-jimf-3.xlsx",
    },
})

# Fed G.17 direct original diff_sa.txt was checked against the current
# published October 16 release on 2026-11-13: all three source blocks end
# in August 2026. Empty September/October cells are absent, not zeros.
# The official next monthly release is 2026-11-17 at 09:15 ET.
# These are time-bounded *publisher document* bounds, not an exemption
# for an unverified or missing local source history.
PUBLICATION_BOUNDS.update({
    f"activity.us.industrial_production_diffusion_{span}m": {
        "version": "Federal Reserve G.17 October 16 2026 diffusion source",
        "verified_as_of": date(2026, 11, 13),
        "expires": date(2026, 11, 17),
        "through": date(2026, 8, 1),
        "url": "https://www.federalreserve.gov/Releases/G17/Current/ipdisk/diff_sa.txt",
    } for span in (1, 3, 6)
})

# Next 2026-Q2 BIS total-credit update is scheduled for 2026-12-07.
_BIS_CREDIT_COUNTRIES = ("cn", "de", "jp", "pt", "us")
_BIS_CREDIT_MEASURES = (
    "corporate_gdp_bis", "household_gdp_bis",
    "private_nonfinancial_gdp_bis", "private_nonfinancial_stock_bis",
)
PUBLICATION_BOUNDS.update({
    f"credit.{country}.{measure}": {
        "version": "BIS total credit, September 2026 (2026-Q1)",
        "released": date(2026, 9, 14),
        "through": date(2026, 1, 1),
        "expires": date(2026, 12, 7),
        "url": "https://data.bis.org/topics/TOTAL_CREDIT",
    } for country in _BIS_CREDIT_COUNTRIES for measure in _BIS_CREDIT_MEASURES
})

# US Financial Accounts Z.1 2026-Q2: 11 September 2026;
# Distributional Financial Accounts 2026-Q2: 18 September 2026.
_FED_Z1_SERIES = (
    "funding.us.broker_assets",
    "funding.us.broker_equity_capital",
    "funding.us.broker_liabilities",
    "funding.us.broker_repo_liabilities",
    "funding.us.broker_total_liabilities_equity",
    "funding.us.finance_company_total_assets",
    "funding.us.finance_company_total_liabilities",
    "funding.us.money_market_assets",
    "valuation.us.equity_net_worth",
)
_FED_DISTRIBUTIONAL_SERIES = (
    "wealth.us.bottom50.assets", "wealth.us.bottom50.equities_mutual_funds",
    "wealth.us.bottom50.liabilities", "wealth.us.bottom50_share",
    "wealth.us.middle40.assets", "wealth.us.middle40.equities_mutual_funds",
    "wealth.us.middle40.liabilities", "wealth.us.middle40_share",
    "wealth.us.next9.assets", "wealth.us.next9.equities_mutual_funds",
    "wealth.us.next9.liabilities", "wealth.us.next9_share",
    "wealth.us.next_point9_share",
    "wealth.us.top1.assets", "wealth.us.top1.equities_mutual_funds",
    "wealth.us.top1.liabilities", "wealth.us.top1_share",
    "wealth.us.top_point1_share",
)
PUBLICATION_BOUNDS.update({
    sid: {
        "version": "Federal Reserve Financial Accounts Z.1, 2026-Q2",
        "released": date(2026, 9, 11),
        "expires": date(2026, 12, 10),
        "through": date(2026, 4, 1),
        "url": "https://www.federalreserve.gov/releases/z1/",
    } for sid in _FED_Z1_SERIES
})
PUBLICATION_BOUNDS.update({
    sid: {
        "version": "Federal Reserve Distributional Financial Accounts, 2026-Q2",
        "released": date(2026, 9, 18),
        "expires": date(2026, 12, 10),
        "through": date(2026, 4, 1),
        "url": "https://www.federalreserve.gov/releases/efa/efa-distributional-financial-accounts.htm",
    } for sid in _FED_DISTRIBUTIONAL_SERIES
})

# FDIC published 2026-Q2 Quarterly Banking Profile 25 August 2026.
# Treat the next expected late-November release conservatively as an expiry
# boundary; never assume that a Q3 figure exists before it is published.
PUBLICATION_BOUNDS.update({
    sid: {
        "version": "FDIC Quarterly Banking Profile, 2026-Q2",
        "released": date(2026, 8, 25),
        "expires": date(2026, 11, 21),
        "through": date(2026, 4, 1),
        "url": "https://www.fdic.gov/quarterly-banking-profile",
    } for sid in (
        "bank.us.fdic_reporting_institutions", "bank.us.fdic_total_assets",
        "bank.us.fdic_total_equity",
    )
})

SAFE_ERROR_CODES = {
    "provider_http_400", "provider_http_401", "provider_http_403",
    "provider_http_404", "provider_http_429", "provider_http_500",
    "provider_http_502", "provider_http_503", "provider_http_504",
    "source_policy_deferred", "source_policy_denied",
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
    "gold_spot_invalid_response", "gold_spot_identity_mismatch",
    "gold_spot_conversion_mismatch", "gold_spot_invalid_timestamp",
    "gold_spot_future_timestamp", "gold_spot_stale_quote",
    "gold_spot_before_window", "gold_spot_invalid_price",
    "gold_spot_source_mapping_mismatch",
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
    # Preserve attempt-level operational deferrals separately from actionable
    # observation-health problems. A blocked optional refresh cannot make
    # in-cadence stored observations stale.
    result["deferred_attempts_with_data"] = sum(
        item["stored_periods"] > 0 and item["refresh_state"] == "deferred"
        for item in items)
    result["deferred_attempts_current_data"] = sum(
        item["stored_periods"] > 0 and item["refresh_state"] == "deferred"
        and item["observation_state"] == "current" for item in items)
    result["deferred_attempts_stale_data"] = sum(
        item["stored_periods"] > 0 and item["refresh_state"] == "deferred"
        and item["observation_state"] == "stale" for item in items)
    result["needs_attention"] = sum(item["state"] in {
        "not_ingested", "collection_disabled", "collection_failed",
        "collection_deferred", "refresh_deferred_with_data",
        "refresh_failed_with_data", "stale", "source_unresolved",
    } for item in items)
    result['observations'] = {state: sum(item['observation_state'] == state for item in items)
                              for state in ('current', 'stale', 'missing')}
    return result


def _next_action(*, mapped, count, stale, complete, status, error):
    if not mapped:
        return 'Resolve the source identity before collection.'
    if error in ('provider_http_401', 'provider_http_403'):
        return 'Access was refused; configure authorized access before retrying.'
    if status == 'deferred' and complete:
        return 'Complete for the pinned release; previous network deferral does not require another download.'
    if status == 'deferred' and count and not stale:
        return ('Retained history is within its expected source-age window; '
                'the last refresh was deferred. Recheck the publisher and retry '
                'when source-policy availability permits.')
    if status == 'deferred':
        return 'Refresh was deferred; the observation is stale or missing. Recheck the publisher and retry when source-policy availability permits.'
    if status == 'failed':
        return 'Review the recorded failure and collector; existing observations are preserved.'
    if not count:
        return 'Collect the original history before using this source.'
    if complete:
        return 'Complete for the named pinned release; check the publisher for a newer edition.'
    if stale:
        return 'Check the latest publisher release and refresh this history if new observations exist.'
    return 'Within the expected source-date window; continue scheduled collection.'


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
    if (family == "macro" and provider == "BIS_DSR"
            and BIS_DSR_RELEASE["released"] <= asof < BIS_DSR_RELEASE["expires"]):
        publication = BIS_DSR_RELEASE
    release_confirmed_on = (publication.get("released") or publication.get("verified_as_of")) if publication else None
    release_known = bool(release_confirmed_on and asof >= release_confirmed_on
                         and asof < publication.get("expires", date.max))
    published_through = publication["through"] if release_known else None
    is_complete_for_release = bool(
        latest is not None and published_through is not None
        and latest >= published_through
    )
    if not mapped:
        state = "source_unresolved"
    elif count == 0 and last is not None and last["status"] == "deferred":
        state = "collection_deferred"
    elif count == 0 and last is not None and last["status"] == "failed":
        state = "collection_failed"
    elif count == 0 and not configured:
        state = "collection_disabled"
    elif count == 0:
        state = "not_ingested"
    elif last is not None and last["status"] == "deferred" and (
            is_complete_for_release or (
                latest is not None and lag <= SOURCE_LAGS[frequency])):
        # A deferred attempted refresh does not invalidate existing data
        # that are still within the explicitly configured reporting window.
        # This is ONLY source-age classification, not evidence that a newer
        # publisher release does not exist. Last-attempt deferral and its code
        # remain visible independently, including in the complete audit CSV.
        state = "available"
    elif last is not None and last["status"] == "deferred":
        state = "refresh_deferred_with_data"
    elif last is not None and last["status"] == "failed":
        state = "refresh_failed_with_data"
    elif lag is not None and lag > SOURCE_LAGS[frequency] and not is_complete_for_release:
        state = "stale"
    else:
        state = "available"
    last_error = last["error"] if last is not None else None
    regular_cadence = provider not in (
        "MSCI_PUBLISHED_TOP10", "MSCI_REGIONAL_FACTSHEETS", "SIBLIS_FREE", "SIBLIS_WORLD_PE",
        "SIBLIS_WORLD_EARNINGS_YIELD", "GOLD_API_SPOT") and not (
            provider == "WORLD_BANK" and id.endswith(".gini_survey_wdi"))
    stale = lag is not None and lag > SOURCE_LAGS[frequency] and not is_complete_for_release
    refresh_state = last['status'] if last else 'never'
    # This is an engine dependency map, not a claim that every mapped input is
    # accepted. Market/explorer-only histories can legitimately have no engine use.
    from .engine.analyses import DEFINITIONS
    used_by = sorted(aid for aid, definition in DEFINITIONS.items()
                     if family == 'macro' and id in definition.inputs.values())
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
            if release_known and publication.get("released") else None,
        "publisher_release_verified_as_of": publication["verified_as_of"].isoformat()
            if release_known and publication.get("verified_as_of") else None,
        "complete_for_pinned_release": is_complete_for_release,
        "scheduled_download_unnecessary_for_pinned_release": bool(
            is_complete_for_release and publication and family == "macro"),
        # Revisions are legitimate append-only versions, not corrupt duplicates.
        "stored_versions": int(versions),
        "additional_revisions": max(0, int(versions)-int(count)),
        "unobserved_internal_periods": _internal_calendar_gaps(
            oldest, latest, frequency, int(count)) if regular_cadence else None,
        "regular_cadence_assumed": regular_cadence,
        'observation_state': 'missing' if count == 0 else 'stale' if stale else 'current',
        'freshness_basis': 'missing' if count == 0 else 'pinned_release' if is_complete_for_release else 'calendar_age',
        'expected_lag_days': SOURCE_LAGS[frequency],
        'refresh_state': refresh_state,
        'research_questions': used_by,
        'next_action': _next_action(mapped=mapped, count=count, stale=stale,
                                    complete=is_complete_for_release, status=refresh_state,
                                    error=last_error),
        "last_attempt_utc": last["started_at"].isoformat() if last else None,
        "last_attempt_state": last["status"] if last else "never",
        "last_success_utc": successful["ended_at"].isoformat()
            if successful and successful["ended_at"] else None,
        "evidence_kind": successful.get("evidence_kind") if successful else None,
        "evidence_scope": successful.get("evidence_scope") if successful else None,
        "evidence_bundle_digest": (
            successful.get("evidence_bundle_digest") if successful else None),
        "evidence_receipt_recorded": bool(
            successful.get("evidence_receipt_name")) if successful else False,
        "first_publication_verified": False,
        "last_failure_code": last_error
            if isinstance(last_error, str) and last_error in SAFE_ERROR_CODES
            else ("provider_failed" if last and last["status"] == "failed" else None),
    }


def _runs(session: Session, model, key) -> tuple[dict, dict]:
    # Do not load ORM instances or source request/error text unnecessarily.
    provenance_fields = (
        "evidence_kind", "evidence_scope", "evidence_bundle_digest",
        "evidence_receipt_name")
    stmt = select(
        key, model.started_at, model.ended_at, model.status,
        model.error if hasattr(model, "error") else model.status,
        *(getattr(model, field) if hasattr(model, field) else literal(None)
          for field in provenance_fields)
    ).order_by(model.started_at.desc(), model.id.desc())
    newest, successful = {}, {}
    for sid, started, ended, status, failure, *provenance in session.execute(stmt):
        if sid not in newest:
            newest[sid] = {"started_at": started, "ended_at": ended,
                           "status": status, "error": failure if hasattr(model, "error") else None}
        if status == "success" and sid not in successful:
            successful[sid] = {"ended_at": ended, **dict(zip(provenance_fields, provenance))}
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
    with Session(engine) as session:
        return coverage_from_session(session, catalog, market_registry, asof=asof)


def coverage_from_session(session: Session, catalog: list[dict], market_registry: dict[str, dict],
                          *, asof: date | None = None) -> dict:
    """Use the caller's read snapshot for source counts and ingestion history."""
    today = asof or date.today()
    macro_enabled = _yes("FINANCE_AUTO_REFRESH", "1")
    market_enabled = macro_enabled and _yes("FINANCE_INCLUDE_MARKETS", "0")
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
                   "Selected TiVA 2025 series through 2022 are current for the "
                   "pinned January 2026 revision, not for later reference years. "
                   "BIS credit-gap and debt-service Q1 2026 are current only for their verified "
                   "14 September to 6 December 2026 release window. "
                   "Additional versions preserve source revisions."),
    }
