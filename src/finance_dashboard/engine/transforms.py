"""Named transforms shared by every analysis.

Each transform has a registered formula that bundles record, so a reader can
recompute every derived value from the inputs. Nothing is interpolated or
filled: month-ends are observed values and gaps break contiguous runs.
"""
from __future__ import annotations

from datetime import date
from math import sqrt
from statistics import pstdev
from typing import Iterable

TRANSFORMS: dict[str, str] = {
    "month_end": "last observation in each calendar month; the observed date is retained",
    "complete_months": "drop the current calendar month, whose last value is not yet a month-end",
    "contiguous_tail": "longest run of consecutive months ending at the latest month; a missing month ends the run",
    "monthly_return": "r[t] = x[t] / x[t-1] - 1, only when both adjacent months are observed",
    "return_summary": "annualized return = (prod(1 + r))^(12/n) - 1; annualized volatility = population sd(r) * sqrt(12); "
                      "max drawdown = min over t of W[t] / max(W[..t]) - 1",
    "own_history": "latest value against the series' own full history: mean, deviation from the mean, and "
                   "percentile = (number of observations below the latest) / (n - 1); range = own minimum and maximum",
    "index_100": "W[t] = 100 * prod over s <= t of (1 + r[s]); starts one month before the first return",
    "fx_translation": "EUR return of a USD asset: (1 + r_usd[t]) * fx[t-1] / fx[t] - 1, with fx in USD per EUR",
    "hedge_carry": "monthly carry of a EUR hedge, covered-interest-parity approximation: (i_eur[t-1] - i_usd[t-1]) / 1200 "
                   "with rates in percent a year; hedged return = (1 + r_usd[t]) * (1 + carry) - 1",
    "real_deflation": "real return or yield = (1 + nominal) / (1 + inflation) - 1",
    "earnings_yield": "earnings yield = 1 / CAPE (cyclically adjusted price/earnings)",
    "valuation_residual_range": "for each start month with a full horizon: residual = realised annualized real return over "
                                "the horizon - 1 / CAPE at the start; range = today's 1 / CAPE + percentiles of the residuals",
    "year_on_year_change": "x[t] / x[t-12 months] - 1",
    "yield_difference": "difference of two yields in the same unit, e.g. breakeven = nominal - real",
    "percent_to_fraction": "value / 100 (percent to fraction)",
    "threshold_band": "classify the latest value against published thresholds; the thresholds are given as params",
    "drawdown": "D[t] = W[t] / max(100, max over s <= t of W[s]) - 1, the fall below the running peak "
                "of wealth started at 100",
    "calibration_points": "for each start month with a full horizon: (1 / CAPE at the start, realised annualized "
                          "real total return over the next horizon years)",
    "cycle_position": "OECD business-cycle clock: position = CLI - 100 (amplitude-adjusted, long-term average 100) and "
                      "direction = CLI[t] - CLI[t-1]; phase: expansion (>= 100, rising), slowdown (>= 100, falling), "
                      "contraction (< 100, falling), recovery (< 100, rising); trail = last 12 consecutive months",
    "log_change": "100 * ln(x[t] / x[t-k]) with both ends observed; k given as months",
    "own_range_window": "minimum and maximum of a series over its last n observations (n given as params)",
    "cross_section_sd": "population standard deviation across a fixed cohort, only for periods where every member is observed",
    "matched_pairs": "pairs of two series on exactly the same period; unmatched periods are dropped",
    "now_and_year_ago": "latest observation and the last observation on or before the same day a year (365 days) "
                        "earlier; change = latest - year ago",
    "now_and_years_ago": "latest observation and the last observation on or before the same day n years "
                          "(365.25 n days) earlier; change = latest - then",
    "additive_parts": "published components on one date where every component is observed; they sum to the published total",
    "matched_ratio": "a[t] / b[t] on periods both series report (times 100 for shares)",
    "rank_correlation": "Spearman rank correlation (average ranks for ties) between starting earnings yield and the "
                        "realised annualized real return over the horizon, per era of start months; reported only when "
                        "the era holds at least two independent horizons of windows",
    "real_per_hour_index": "real value per hour = (nominal / value-added price index) / hours, indexed to 100 in the first "
                           "year where every input is observed; pay and productivity use the same price index",
    "share_of_total": "part / total * 100 on the same period; parts that do not add up leave an explicit remainder",
    "pearson_correlation": "Pearson correlation of matched monthly returns in euros, per period; reported only with at "
                           "least 24 months (12 for the stock-fall subset)",
    "drawdown_episodes": "peak-to-trough-to-recovery episodes of month-end levels whose depth exceeds the threshold; "
                         "depth = trough / peak - 1",
    "splice_identical": "join an archived history with the publisher's current series only if every shared day has the "
                        "identical value; current values after the archive's end are appended; any difference withholds the join",
    "par_bond_return": "Swinkels' par-bond revaluation: a 10-year par bond bought at last month's month-end yield y0 and "
                       "revalued at this month's yield y1 with 10 - 1/12 years left, semi-annual discounting: "
                       "r = y0/1200 + (y0/y1)(1 - (1 + y1/200)^(-2(10 - 1/12))) + (1 + y1/200)^(-2(10 - 1/12)) - 1; "
                       "only consecutive observed months",
    "signal_timing": "for each NBER recession start: the first month the yield spread was below zero in the preceding "
                     "window, the first month the Sahm indicator reached its threshold around the start, and the NBER "
                     "peak announcement, each in months relative to the start; signals outside every window are "
                     "listed as false alarms (open while the window has not yet passed)",
    "recovery_to_peak": "pre-recession peak = highest level in the 12 months before the recession start; trough = lowest "
                        "level from the start to 12 months after the end; depth = trough / peak - 1; months to recover = "
                        "months from the peak month to the first later month at or above the peak level",
    "first_order_shock": "impact on portfolio value = - weight x sensitivity x shock (duration for yields, unhedged "
                         "foreign share for the dollar); first-order, ignores convexity and correlations",
    "rebalancing_simulation": "monthly: grow each holding by its EUR return, add contributions at target weights, withdraw "
                              "pro rata, rebalance to target by rule (never, every n months, when a weight drifts beyond "
                              "the band), charge trading cost on turnover; with cost basis per asset, tax either the gains realised by "
                              "selling (no loss credit) or a yearly share of value",
    "native_icio_direct_final_demand": "for each complete edition-native annual ICIO matrix, sum each source industry's "
        "gross direct sales into final-demand columns of foreign countries (current USD millions); "
        "CN1/CN2 map to China, MX1/MX2 to Mexico where non-overlapping. No Leontief "
        "value-added tracing; never treated as OECD TiVA FFD_DVA. Editions remain distinct.",
    "matched_day": "latest date on which both series are observed (market-date match, no carry-forward)",
    "overlapping_window_percentiles": "percentiles (linear interpolation) of overlapping fixed-horizon window "
                                      "statistics; effective independent windows = windows / horizon months",
}


def applied(name: str, **params) -> dict:
    """The record of one transform applied, for a bundle's transform list."""
    return {"name": name, "formula": TRANSFORMS[name], "params": params}


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


def complete_months(ends: dict, today: date | None = None) -> dict:
    """Drop the current calendar month: its last value is not a month-end."""
    current = month_key(today or date.today())
    return {key: value for key, value in ends.items() if key < current}


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


def return_summary(returns: list[float]) -> dict:
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


def own_history(points: list[tuple[date, float]]) -> dict | None:
    """Latest value against the series' own history (no cross-country ranking)."""
    if not points:
        return None
    points = sorted(points)
    values = [v for _, v in points]
    day, latest = points[-1]
    mean = sum(values) / len(values)
    below = sum(v < latest for v in values)
    return {"as_of": day.isoformat(), "latest": latest, "history_start": points[0][0].isoformat(),
            "observations": len(values), "own_mean": mean, "deviation_from_own_mean": latest - mean,
            "own_percentile": below / (len(values) - 1) if len(values) > 1 else None}


def index_100(returns: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Cumulative level from 100, one point per observed return; nothing inserted."""
    level = 100.0
    out = []
    for label, r in returns:
        level *= 1 + r
        out.append((label, level))
    return out


def percentile(sorted_values: list[float], q: float) -> float | None:
    """Linear-interpolation percentile of an already sorted list."""
    if not sorted_values:
        return None
    position = q * (len(sorted_values) - 1)
    low = int(position)
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def par_bond_returns(yields: dict[tuple[int, int], float]) -> dict[tuple[int, int], float]:
    """Monthly simple returns of a hypothetical 10-year par bond from month-end yields in percent (Swinkels' formula)."""
    n = -2 * (10 - 1 / 12)
    out = {}
    for key in sorted(yields):
        back = previous_month(key)
        if back in yields and yields[key]:
            y0, y1 = yields[back], yields[key]
            out[key] = y0 / 1200 + (y0 / y1) * (1 - (1 + y1 / 200) ** n) + (1 + y1 / 200) ** n - 1
    return out


def splice_identical(archive: list[tuple], current: list[tuple]) -> tuple[list[tuple], dict]:
    """Archive then current; joined only when every shared date carries the same value."""
    a, c = dict(archive), dict(current)
    shared = set(a) & set(c)
    differing = sum(1 for day in shared if a[day] != c[day])
    check = {"overlap_days": len(shared), "differing_days": differing}
    if differing:
        return [], check
    return sorted({**a, **c}.items()), check
