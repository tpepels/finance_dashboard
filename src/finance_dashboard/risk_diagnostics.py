"""Phase 4 source-specific risk diagnostics, without synthetic crisis probabilities.

Every threshold has a publisher-defined meaning. Percentile is only a description
of the distribution of revised observations already in the local database, not
a backtest, event forecast, or source publication vintage.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.engine import Engine

from .catalog import load_documents
from .service import current_observations

D = Decimal
# Explicit jurisdictions and source-defined semantic criteria. No hidden score.
DIAGNOSTICS = (
    dict(id="us_sahm", scope="us", series_id="recession.us.sahm",
         title="Sahm recession-onset criterion", threshold="0.50",
         direction="gte", unit="percentage_points", indicator="monthly_sahm",
         reference="https://fred.stlouisfed.org/series/SAHMREALTIME",
         meaning="Real-time-method unemployment-rate three-month average at least 0.50 percentage points above its prior 12-month minimum.",
         caveat="Onset diagnostic, not a forecast. Revised source observations are not actual ALFRED release vintages."),
    dict(id="us_yield_inversion", scope="us", series_id="rates.us.treasury_10y_3m_spread",
         title="US Treasury 10y−3m inversion", threshold="0",
         direction="lt", unit="percentage_points", indicator="term_spread",
         reference="https://www.newyorkfed.org/research/capital_markets/ycfaq",
         meaning="A negative Treasury 10-year minus 3-month term spread signifies an inverted yield curve.",
         caveat="An inversion has historical predictive associations, but does not establish recession timing or probability."),
    dict(id="us_credit", scope="us", series_id="credit_gap.us.bis",
         title="US BIS private-credit gap / Basel guide", threshold="2",
         direction="gte", unit="percentage_points", indicator="credit_gap",
         reference="https://data.bis.org/topics/CREDIT_GAPS",
         meaning="Basel III +2 percentage-point credit-to-GDP gap reference for considering countercyclical capital buffers.",
         caveat="Authorities use multiple indicators and may calculate national gaps differently. This is not a crisis probability."),
    dict(id="euro_area_credit", scope="europe", series_id="credit_gap.ea.bis",
         title="Euro-area BIS credit gap / Basel guide", threshold="2",
         direction="gte", unit="percentage_points", indicator="credit_gap",
         reference="https://data.bis.org/topics/CREDIT_GAPS",
         meaning="BIS credit gap relative to one-sided local statistical trend, compared with a +2 pp Basel guide.",
         caveat="Euro-area coverage differs from EU27; credit gap is neither credit growth nor an official regional capital-buffer decision."),
    dict(id="japan_credit", scope="japan", series_id="credit_gap.jp.bis",
         title="Japan BIS credit gap / Basel guide", threshold="2",
         direction="gte", unit="percentage_points", indicator="credit_gap",
         reference="https://data.bis.org/topics/CREDIT_GAPS",
         meaning="BIS private credit/GDP relative to statistical trend, with +2 pp reference.",
         caveat="Use as an early-warning context variable only; no mechanical crisis probability."),
    dict(id="us_cape_rank", scope="us", series_id="valuation.us.cape",
         title="US CAPE rank in observed history", threshold=None,
         direction=None, unit="ratio", indicator="empirical_rank",
         reference="https://shillerdata.com/",
         meaning="Fraction of available source observations at or below the current Shiller CAPE. No threshold or forecast.",
         caveat="Historical source values may be revised; sample and monthly coverage determine rank, not fair value or an expected return."),
    dict(id="global_credit", scope="world", series_id="credit.world.private_gdp_gap",
         title="International BIS gap composite (research proxy)", threshold=None,
         direction=None, unit="percentage_points", indicator="descriptive",
         reference="https://data.bis.org/topics/CREDIT_GAPS",
         meaning="GDP-weighted composite of reported national credit gaps; read only alongside its own world GDP coverage series.",
         caveat="Researcher aggregation of national BIS gaps, not an official global BIS series; coverage is variable."),
)
BY_ID = {item["id"]: item for item in DIAGNOSTICS}
SCOPES = ("world", "us", "europe", "japan")
STALE_DAYS = {"D": 32, "M": 90, "Q": 210, "A": 600}
MAX_GAP_DAYS = {"D": 7, "M": 48, "Q": 115, "A": 430}
MIN_PERCENTILE = {"D": 60, "M": 24, "Q": 24, "A": 15}


def _passes(value: Decimal, rule: dict) -> bool | None:
    if rule["threshold"] is None:
        return None
    threshold = D(rule["threshold"])
    if rule["direction"] == "gte":
        return value >= threshold
    if rule["direction"] == "lt":
        return value < threshold
    raise ValueError("Unknown economic signal rule")


def interpret(rule: dict, raw: list[Any], *, today: date | None = None) -> dict[str, Any]:
    """Calculate descriptive evidence from exact native observations, never synthesize dates."""
    today = today or datetime.now(timezone.utc).date()
    values: dict[date, Decimal] = {}
    for row in raw:
        day, value = (row if isinstance(row, tuple) else (row.period, row.value))
        if day > today:
            continue
        number = D(str(value))
        if number.is_finite():
            values[day] = number
    ordered = sorted(values.items())
    output = {k: rule[k] for k in
              ("id", "scope", "series_id", "title", "indicator", "threshold",
               "direction", "unit", "reference", "meaning", "caveat")}
    output.update(status="no_data", latest=None, sample_count=len(ordered),
                  threshold_crossed=None, consecutive_source_observations=0,
                  historical_rank_pct=None, rank_sample_count=None,
                  rank_method=None, start=None, end=None)
    if not ordered:
        return output
    latest, value = ordered[-1]
    output["latest"] = {"date": latest.isoformat(), "value": str(value)}
    output["start"] = ordered[0][0].isoformat()
    output["end"] = latest.isoformat()
    age = (today - latest).days
    output["staleness_days"] = age
    # Stale readings are shown for education but never presented as active signals.
    freq = rule.get("frequency", "M")
    output["status"] = "stale" if age > STALE_DAYS[freq] else "observed"
    crossed = _passes(value, rule)
    output["threshold_crossed"] = crossed if output["status"] == "observed" else None
    if crossed and output["status"] == "observed":
        count = 1
        previous_day = latest
        for day, v in reversed(ordered[:-1]):
            if (previous_day - day).days > MAX_GAP_DAYS[freq] or not _passes(v, rule):
                break
            count += 1
            previous_day = day
        output["consecutive_source_observations"] = count

    enough = MIN_PERCENTILE[freq]
    if len(ordered) >= enough:
        # Include current observation; full sample is *revised latest known*.
        less_or_equal = sum(1 for _, sample in ordered if sample <= value)
        output["historical_rank_pct"] = str(
            (D(less_or_equal) * D(100) / D(len(ordered))).quantize(D("0.01")))
        output["rank_sample_count"] = len(ordered)
        output["rank_method"] = ("Empirical ≤ rank among recorded, potentially "
                                 "revised observations in the selected date range; "
                                 "not a historically as-known percentile.")
    return output


def diagnostic_catalog() -> dict:
    return {
        "indicators": list(DIAGNOSTICS),
        "scopes": list(SCOPES),
        "method": ("No composite risk score, forecasts or opaque weights. Thresholds "
                   "and jurisdictions are documented per measure. No extrapolation "
                   "from a stale/missing series. Historical values are current-vintage "
                   "revisions, NOT genuine as-published historical releases."),
    }


def read_diagnostics(engine: Engine, scope: str, *, start: date | None = None,
                     end: date | None = None, today: date | None = None) -> dict:
    if scope not in SCOPES:
        raise ValueError("Unknown geographic diagnostic scope")
    catalog, _ = load_documents()
    metadata = {s["id"]: s for s in catalog["series"]}
    rules = [rule for rule in DIAGNOSTICS if rule["scope"] == scope]
    out = []
    with Session(engine) as session:
        for rule in rules:
            source = metadata[rule["series_id"]]
            enriched = {**rule, "frequency": source["frequency"]}
            values = current_observations(session, rule["series_id"], start=start, end=end)
            result = interpret(enriched, values, today=today)
            result["source_name"] = source["name"]
            result["provider"] = source["provider"]
            result["source_url"] = source["source_url"]
            result["frequency"] = source["frequency"]
            out.append(result)
    return {"scope": scope, "indicators": out, "method": diagnostic_catalog()["method"]}
