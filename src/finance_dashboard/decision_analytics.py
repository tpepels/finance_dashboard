"""Decision-layer analytics for a EUR-based long-term investor (P06, P07).

Pure functions over observed values; nothing is interpolated or filled. Month-end
values are the last observation published in each calendar month. Monthly returns
use only adjacent months that are both observed; cumulative series cover the
longest contiguous run ending at the latest common month, so no return is skipped.
"""
from __future__ import annotations

from datetime import date
from math import sqrt
from statistics import pstdev
from typing import Iterable

from sqlalchemy.orm import Session

from .service import current_observations

P07_INPUTS = {
    "usd_per_eur": "fx.usd_per_eur.ecb",
    "equity_netr_usd": "equity.world.msci_acwi_netr_usd",
    "eur_short_rate": "policy_rate.ea.ecb_dfr",
    "usd_short_rate": "policy_rate.us.fed_effective",
    "ea_hicp": "prices.ea.hicp_index_2025",
}
P06_INPUTS = {
    "us_cape": "valuation.us.cape",
    "us_real_total_return": "returns.us.shiller_real_total_return",
    "global_earnings_yield": "valuation.world.global_earnings_yield",
    "us_nominal_10y": "bond.us.nominal_10y",
    "us_real_10y": "bond.us.real_10y",
    "ea_aaa_10y": "bond.ea.aaa_10y_spot",
    "ea_hicp": "prices.ea.hicp_index_2025",
}


def month_key(day: date) -> tuple[int, int]:
    return day.year, day.month


def previous_month(key: tuple[int, int]) -> tuple[int, int]:
    year, month = key
    return (year - 1, 12) if month == 1 else (year, month - 1)


def month_end(points: Iterable[tuple[date, float]]) -> dict[tuple[int, int], tuple[date, float]]:
    """Last observed value in each calendar month (observed date retained)."""
    out: dict[tuple[int, int], tuple[date, float]] = {}
    for day, value in sorted(points):
        out[month_key(day)] = (day, value)
    return out


def contiguous_tail(months: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    """Longest run of consecutive months ending at the latest month."""
    ordered = sorted(set(months))
    if not ordered:
        return []
    run = [ordered[-1]]
    for key in reversed(ordered[:-1]):
        if key != previous_month(run[0]):
            break
        run.insert(0, key)
    return run


def summary(returns: list[float]) -> dict:
    if not returns:
        return {"months": 0}
    wealth = []
    level = 1.0
    peak = 1.0
    drawdown = 0.0
    for r in returns:
        level *= 1 + r
        peak = max(peak, level)
        drawdown = min(drawdown, level / peak - 1)
        wealth.append(level)
    years = len(returns) / 12
    return {"months": len(returns),
            "annualized_return": level ** (1 / years) - 1,
            "annualized_volatility": pstdev(returns) * sqrt(12) if len(returns) > 1 else None,
            "max_drawdown": drawdown, "final_wealth": wealth[-1]}


def p07_hedging(fx: dict, equity: dict, eur_rate: dict, usd_rate: dict, hicp: dict) -> dict:
    """Unhedged vs hedged EUR returns of a USD equity index.

    fx is USD per EUR. Unhedged EUR return = (1+r_usd)·fx[t-1]/fx[t] − 1.
    Hedged ≈ (1+r_usd)·(1 + (i_eur − i_usd)/1200) − 1 using the short-rate
    differential observed at the start of the month (covered-interest-parity
    approximation of forward points; stated as a limitation).
    """
    candidates = []
    for key in equity:
        prev = previous_month(key)
        if all(prev in s for s in (equity, fx, eur_rate, usd_rate)) and key in fx:
            candidates.append(key)
    months = contiguous_tail(candidates)
    rows = []
    for key in months:
        prev = previous_month(key)
        r_usd = equity[key][1] / equity[prev][1] - 1
        unhedged = (1 + r_usd) * fx[prev][1] / fx[key][1] - 1
        carry = (eur_rate[prev][1] - usd_rate[prev][1]) / 1200
        hedged = (1 + r_usd) * (1 + carry) - 1
        inflation = hicp[key][1] / hicp[prev][1] - 1 if key in hicp and prev in hicp else None
        rows.append({"month": f"{key[0]:04d}-{key[1]:02d}", "usd_return": r_usd,
                     "eur_unhedged": unhedged, "eur_hedged": hedged, "hedge_carry": carry,
                     "eur_inflation": inflation})
    real_rows = [row for row in rows if row["eur_inflation"] is not None]
    # Real statistics only over the contiguous run where inflation is observed.
    real_tail = contiguous_tail(tuple(int(x) for x in row["month"].split("-")) for row in real_rows)
    real_set = {f"{y:04d}-{m:02d}" for y, m in real_tail}
    real = [row for row in real_rows if row["month"] in real_set]
    return {
        "analysis_id": "P07",
        "rows": rows,
        "nominal": {name: summary([row[name] for row in rows]) for name in ("usd_return", "eur_unhedged", "eur_hedged")},
        "real_eur": {name: summary([(1 + row[name]) / (1 + row["eur_inflation"]) - 1 for row in real])
                     for name in ("eur_unhedged", "eur_hedged")},
        "real_period": {"start": real[0]["month"], "end": real[-1]["month"]} if real else None,
        "limitations": [
            "Hedged returns approximate forward points by the ECB deposit-facility minus effective federal funds rate; actual hedge costs, basis and fund fees are not included.",
            "Month-end values are the last published observation in each month; ECB reference rates are not transaction rates.",
            "MSCI ACWI net total return in USD is an index, not an investable fund; ETF fees and tracking differences are excluded.",
        ],
    }


def trailing_inflation(hicp: dict) -> dict | None:
    if not hicp:
        return None
    key = max(hicp)
    prior = (key[0] - 1, key[1])
    if prior not in hicp:
        return None
    return {"month": f"{key[0]:04d}-{key[1]:02d}", "rate": hicp[key][1] / hicp[prior][1] - 1}


def p06_expected_returns(cape: dict, real_tr: dict, global_ey: dict, latest: dict, hicp: dict,
                         horizon_years: int = 10) -> dict:
    """Building-block expected real/nominal returns with an empirical equity range.

    Equity: earnings yield 1/CAPE as the long-run real return estimate. The range is
    the 10th–90th percentile of (realised annualized real return over the next
    `horizon_years` − earnings yield at the start) across all fully observed start
    months, added to today's earnings yield. Windows overlap heavily, so the
    effective number of independent observations is about months/(12·horizon).
    """
    months = horizon_years * 12
    residuals = []
    ordered = sorted(real_tr)
    index = {key: i for i, key in enumerate(ordered)}
    for key, (_, cape_value) in cape.items():
        if key not in index:
            continue
        i = index[key]
        if i + months >= len(ordered):
            continue
        end = ordered[i + months]
        # Require the end month to be exactly horizon_years later (no gaps).
        if (end[0] - key[0]) * 12 + end[1] - key[1] != months:
            continue
        realised = (real_tr[end][1] / real_tr[key][1]) ** (1 / horizon_years) - 1
        residuals.append(realised - 1 / cape_value)
    residuals.sort()

    def pct(q):
        if not residuals:
            return None
        position = q * (len(residuals) - 1)
        low = int(position)
        high = min(low + 1, len(residuals) - 1)
        return residuals[low] + (residuals[high] - residuals[low]) * (position - low)

    equity = None
    if cape:
        key = max(cape)
        ey = 1 / cape[key][1]
        equity = {"as_of": cape[key][0].isoformat(), "cape": cape[key][1], "earnings_yield": ey,
                  "range_real": {"p10": ey + pct(0.1), "p50": ey + pct(0.5), "p90": ey + pct(0.9)}
                  if residuals else None,
                  "calibration_windows": len(residuals),
                  "effective_independent_windows": round(len(residuals) / months, 1)}
    world = None
    if global_ey:
        key = max(global_ey)
        world = {"as_of": global_ey[key][0].isoformat(), "earnings_yield": global_ey[key][1] / 100,
                 "snapshots": len(global_ey)}
    inflation = trailing_inflation(hicp)
    bonds = {name: {"as_of": value[0].isoformat(), "yield": value[1] / 100} for name, value in latest.items() if value}
    if "us_nominal_10y" in bonds and "us_real_10y" in bonds:
        bonds["us_breakeven_10y"] = {"as_of": bonds["us_real_10y"]["as_of"],
                                     "yield": bonds["us_nominal_10y"]["yield"] - bonds["us_real_10y"]["yield"]}
    if "ea_aaa_10y" in bonds and inflation:
        bonds["ea_aaa_10y_real_trailing"] = {
            "as_of": bonds["ea_aaa_10y"]["as_of"],
            "yield": (1 + bonds["ea_aaa_10y"]["yield"]) / (1 + inflation["rate"]) - 1,
            "assumption": "Nominal AAA yield deflated by trailing 12-month HICP inflation, not a market inflation expectation."}
    return {
        "analysis_id": "P06", "horizon_years": horizon_years,
        "equity_us": equity, "equity_world_snapshot": world, "bonds": bonds, "ea_inflation": inflation,
        "limitations": [
            "Expected-return estimates are model-based planning ranges, not forecasts or timing signals.",
            "The equity range uses latest revised Shiller data and overlapping windows; V05 evaluates the relationship on real-time data.",
            "Bond yields approximate nominal returns only when held to maturity; euro AAA curve is model-fitted, not a traded bond.",
        ],
    }


def _points(session: Session, series_id: str) -> list[tuple[date, float]]:
    return [(row.period, float(row.value)) for row in current_observations(session, series_id)]


def complete_months(ends: dict, today: date | None = None) -> dict:
    """Drop the current calendar month: its last value is not a month-end."""
    current = month_key(today or date.today())
    return {key: value for key, value in ends.items() if key < current}


def load_p07(session: Session, today: date | None = None) -> dict:
    data = {name: complete_months(month_end(_points(session, sid)), today)
            for name, sid in P07_INPUTS.items()}
    result = p07_hedging(data["usd_per_eur"], data["equity_netr_usd"], data["eur_short_rate"],
                         data["usd_short_rate"], data["ea_hicp"])
    result["inputs"] = P07_INPUTS
    return result


def load_p06(session: Session) -> dict:
    data = {name: month_end(_points(session, sid)) for name, sid in P06_INPUTS.items()}
    latest = {}
    for name in ("us_nominal_10y", "us_real_10y", "ea_aaa_10y"):
        latest[name] = data[name][max(data[name])] if data[name] else None
    result = p06_expected_returns(data["us_cape"], data["us_real_total_return"],
                                  data["global_earnings_yield"], latest, data["ea_hicp"])
    result["inputs"] = P06_INPUTS
    return result
