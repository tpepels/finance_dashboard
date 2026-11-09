"""Analysis definitions computed by the engine.

Pure functions over observed values; nothing is interpolated or filled.
Month-end values are the last observation published in each calendar month.
Monthly returns use only adjacent months that are both observed; cumulative
series cover the longest contiguous run ending at the latest common month.
"""
from __future__ import annotations

from datetime import date, timedelta
import math
from statistics import pstdev

from .bundle import AnalysisDefinition, Computed
from .transforms import (applied, complete_months, contiguous_tail, index_100, month_end, own_history,
                         percentile, previous_month, return_summary)


def view_today(view: dict) -> date:
    today = view.get("today")
    if isinstance(today, str):
        return date.fromisoformat(today)
    return today or date.today()


def p07_hedging(fx: dict, equity: dict, eur_rate: dict, usd_rate: dict, hicp: dict) -> dict:
    """Unhedged vs hedged EUR returns of a USD equity index.

    fx is USD per EUR. Unhedged EUR return = (1+r_usd)·fx[t-1]/fx[t] − 1.
    Hedged ≈ (1+r_usd)·(1 + (i_eur − i_usd)/1200) − 1 using the short-rate
    differential observed at the start of the month (covered-interest-parity
    approximation of forward points; stated as a method limitation).
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
        "rows": rows,
        "nominal": {name: return_summary([row[name] for row in rows])
                    for name in ("usd_return", "eur_unhedged", "eur_hedged")},
        "real_eur": {name: return_summary([(1 + row[name]) / (1 + row["eur_inflation"]) - 1 for row in real])
                     for name in ("eur_unhedged", "eur_hedged")},
        "real_period": {"start": real[0]["month"], "end": real[-1]["month"]} if real else None,
    }


def p07_wealth(rows: list[dict]) -> dict:
    """Wealth from 100: nominal over all rows, real over rows with observed inflation."""
    out = {"nominal": {}, "real": {}}
    for key in ("eur_unhedged", "eur_hedged"):
        out["nominal"][key] = [[m, v] for m, v in index_100([(row["month"], row[key]) for row in rows])]
        out["real"][key] = [[m, v] for m, v in index_100(
            [(row["month"], (1 + row[key]) / (1 + row["eur_inflation"]) - 1)
             for row in rows if row["eur_inflation"] is not None])]
    return out


def p07_drawdown(wealth: dict) -> dict:
    """Fall below the running peak of each wealth path (peak starts at 100)."""
    out = {}
    for key, path in wealth.items():
        peak = 100.0
        series = []
        for month, level in path:
            peak = max(peak, level)
            series.append([month, level / peak - 1])
        out[key] = series
    return out


def _p07(points: dict, view: dict) -> Computed:
    today = view_today(view)
    ends = {role: complete_months(month_end(values), today) for role, values in points.items()}
    values = p07_hedging(ends["usd_per_eur"], ends["equity_netr_usd"], ends["eur_short_rate"],
                         ends["usd_short_rate"], ends["ea_hicp"])
    values["wealth"] = p07_wealth(values["rows"])
    values["drawdown"] = {kind: p07_drawdown(paths) for kind, paths in values["wealth"].items()}
    roles = list(points)
    return Computed(values=values, estimates=None, comparison=["eur_unhedged", "eur_hedged"], transforms=[
        applied("month_end", applied_to=roles),
        applied("complete_months", applied_to=roles, today=today.isoformat()),
        applied("monthly_return", applied_to=["equity_netr_usd", "ea_hicp"], produces=["usd_return", "eur_inflation"]),
        applied("fx_translation", applied_to=["usd_return", "usd_per_eur"], produces=["eur_unhedged"]),
        applied("hedge_carry", applied_to=["eur_short_rate", "usd_short_rate", "usd_return"],
                produces=["hedge_carry", "eur_hedged"]),
        applied("real_deflation", applied_to=["eur_unhedged", "eur_hedged", "eur_inflation"],
                produces=["real_eur", "wealth.real"]),
        applied("contiguous_tail", applied_to=["rows", "real_eur"]),
        applied("return_summary", applied_to=["usd_return", "eur_unhedged", "eur_hedged"],
                produces=["nominal", "real_eur"]),
        applied("index_100", applied_to=["eur_unhedged", "eur_hedged"], produces=["wealth"]),
        applied("drawdown", applied_to=["wealth"], produces=["drawdown"]),
    ])


P07 = AnalysisDefinition("P07", {
    "usd_per_eur": "fx.usd_per_eur.ecb",
    "equity_netr_usd": "equity.world.msci_acwi_netr_usd",
    "eur_short_rate": "policy_rate.ea.ecb_dfr",
    "usd_short_rate": "policy_rate.us.fed_effective",
    "ea_hicp": "prices.ea.hicp_index_2025",
}, _p07)



def trailing_inflation(hicp: dict) -> dict | None:
    if not hicp:
        return None
    key = max(hicp)
    prior = (key[0] - 1, key[1])
    if prior not in hicp:
        return None
    return {"month": f"{key[0]:04d}-{key[1]:02d}", "rate": hicp[key][1] / hicp[prior][1] - 1}


def calibration_points(cape: dict, real_tr: dict, horizon_years: int) -> list[list]:
    """[start month, 1/CAPE at the start, realised annualized real return over the horizon] per full window."""
    months = horizon_years * 12
    ordered = sorted(real_tr)
    index = {key: i for i, key in enumerate(ordered)}
    out = []
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
        out.append([f"{key[0]:04d}-{key[1]:02d}", 1 / cape_value, realised])
    return out


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
    residuals = sorted(realised - earnings_yield
                       for _, earnings_yield, realised in calibration_points(cape, real_tr, horizon_years))
    equity = None
    if cape:
        key = max(cape)
        ey = 1 / cape[key][1]
        equity = {"as_of": cape[key][0].isoformat(), "cape": cape[key][1], "earnings_yield": ey,
                  "range_real": {"p10": ey + percentile(residuals, 0.1), "p50": ey + percentile(residuals, 0.5),
                                 "p90": ey + percentile(residuals, 0.9)} if residuals else None,
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
    return {"horizon_years": horizon_years, "equity_us": equity, "equity_world_snapshot": world,
            "bonds": bonds, "ea_inflation": inflation}


def _p06(points: dict, view: dict) -> Computed:
    ends = {role: month_end(values) for role, values in points.items()}
    latest = {name: ends[name][max(ends[name])] if ends[name] else None
              for name in ("us_nominal_10y", "us_real_10y", "ea_aaa_10y")}
    result = p06_expected_returns(ends["us_cape"], ends["us_real_total_return"], ends["global_earnings_yield"],
                                  latest, ends["ea_hicp"])
    equity = result.pop("equity_us")
    result["history"] = {
        "cape": [[f"{k[0]:04d}-{k[1]:02d}", v] for k, (_, v) in sorted(ends["us_cape"].items())],
        "calibration": calibration_points(ends["us_cape"], ends["us_real_total_return"], result["horizon_years"]),
    }
    return Computed(values=result, estimates={"equity_us": equity},
                    comparison=["equity_us", "equity_world_snapshot", "bonds"], transforms=[
        applied("month_end", applied_to=list(points)),
        applied("percent_to_fraction", applied_to=["us_nominal_10y", "us_real_10y", "ea_aaa_10y",
                                                   "global_earnings_yield"]),
        applied("earnings_yield", applied_to=["us_cape"], produces=["equity_us.earnings_yield"]),
        applied("valuation_residual_range", applied_to=["us_cape", "us_real_total_return"],
                produces=["equity_us.range_real"], horizon_years=result["horizon_years"]),
        applied("calibration_points", applied_to=["us_cape", "us_real_total_return"],
                produces=["history.calibration"], horizon_years=result["horizon_years"]),
        applied("overlapping_window_percentiles", applied_to=["equity_us.range_real"],
                percentiles=[0.1, 0.5, 0.9], horizon_years=result["horizon_years"]),
        applied("year_on_year_change", applied_to=["ea_hicp"], produces=["ea_inflation"]),
        applied("yield_difference", applied_to=["us_nominal_10y", "us_real_10y"], produces=["bonds.us_breakeven_10y"]),
        applied("real_deflation", applied_to=["ea_aaa_10y", "ea_inflation"],
                produces=["bonds.ea_aaa_10y_real_trailing"]),
    ])


P06 = AnalysisDefinition("P06", {
    "us_cape": "valuation.us.cape",
    "us_real_total_return": "returns.us.shiller_real_total_return",
    "global_earnings_yield": "valuation.world.global_earnings_yield",
    "us_nominal_10y": "bond.us.nominal_10y",
    "us_real_10y": "bond.us.real_10y",
    "ea_aaa_10y": "bond.ea.aaa_10y_spot",
    "ea_hicp": "prices.ea.hicp_index_2025",
}, _p06)

CREDIT_GAPS = {"US": "credit_gap.us.bis", "EA": "credit_gap.ea.bis", "JP": "credit_gap.jp.bis",
               "DE": "credit_gap.de.bis", "CN": "credit_gap.cn.bis", "PT": "credit_gap.pt.bis"}
PRIVATE_DSR = {"US": "debt_service.us.private.bis", "JP": "debt_service.jp.private.bis",
               "DE": "debt_service.de.private.bis", "CN": "debt_service.cn.private.bis",
               "PT": "debt_service.pt.private.bis"}
# BIS/Basel III countercyclical buffer guide: buffer starts above a 2 pp gap and
# reaches its maximum at 10 pp (Drehmann & Juselius 2013; BIS credit-gap notes).
GAP_GUIDE_LOW, GAP_GUIDE_HIGH = 2.0, 10.0


def f03_credit(gaps: dict, dsr: dict) -> dict:
    rows = []
    for area in sorted(set(gaps) | set(dsr)):
        gap = own_history(gaps.get(area, []))
        debt = own_history(dsr.get(area, []))
        band = None
        if gap:
            band = ("above_10pp" if gap["latest"] > GAP_GUIDE_HIGH else
                    "between_2_and_10pp" if gap["latest"] > GAP_GUIDE_LOW else "below_2pp")
        rows.append({"area": area, "credit_gap": gap, "gap_guide_band": band, "private_dsr": debt})
    return {"rows": rows, "guide": {"low_pp": GAP_GUIDE_LOW, "high_pp": GAP_GUIDE_HIGH}}


def f03_history(gaps: dict, dsr: dict) -> dict:
    """Each economy's full credit-gap and debt-service history with its own range."""
    def series(points):
        return [[day.isoformat(), value] for day, value in sorted(points)]

    def own_range(points):
        values = [value for _, value in points]
        return {"min": min(values), "max": max(values)} if values else None
    return {area: {"credit_gap": series(gaps.get(area, [])), "credit_gap_range": own_range(gaps.get(area, [])),
                   "private_dsr": series(dsr.get(area, [])), "private_dsr_range": own_range(dsr.get(area, []))}
            for area in sorted(set(gaps) | set(dsr))}


def _f03(points: dict, view: dict) -> Computed:
    gaps = {key.split(":")[1]: values for key, values in points.items() if key.startswith("credit_gap:")}
    dsr = {key.split(":")[1]: values for key, values in points.items() if key.startswith("private_dsr:")}
    values = f03_credit(gaps, dsr)
    values["history"] = f03_history(gaps, dsr)
    return Computed(values=values, estimates=None, comparison=["credit_gap", "private_dsr"],
                    transforms=[applied("own_history", applied_to=list(points)),
                                applied("threshold_band", applied_to=[k for k in points if k.startswith("credit_gap:")],
                                        produces=["gap_guide_band"], low_pp=GAP_GUIDE_LOW, high_pp=GAP_GUIDE_HIGH,
                                        source="BIS/Basel III countercyclical buffer guide")])


F03 = AnalysisDefinition("F03", {**{f"credit_gap:{area}": sid for area, sid in CREDIT_GAPS.items()},
                                 **{f"private_dsr:{area}": sid for area, sid in PRIVATE_DSR.items()}}, _f03)


def _month_label(key: tuple[int, int]) -> str:
    return f"{key[0]:04d}-{key[1]:02d}"


def cycle_positions(points: list[tuple[date, float]]) -> dict | None:
    """Clock position of an amplitude-adjusted CLI: (month, level - 100, 1-month change), last 12 consecutive months."""
    ends = month_end(points)
    positions = [(key, ends[key][1] - 100, ends[key][1] - ends[previous_month(key)][1])
                 for key in sorted(ends) if previous_month(key) in ends]
    if not positions:
        return None
    tail = set(contiguous_tail(key for key, *_ in positions)[-12:])
    trail = [[_month_label(key), level, change] for key, level, change in positions if key in tail]
    _, level, change = trail[-1]
    phase = ("expansion" if change >= 0 else "slowdown") if level >= 0 else ("recovery" if change >= 0 else "contraction")
    return {"as_of": trail[-1][0], "phase": phase, "trail": trail}


def log_change(points: list[tuple[date, float]], months: int) -> list[list]:
    """[month, 100 * ln(x[t] / x[t - months])] where both ends are observed."""
    ends = month_end(points)
    out = []
    for key in sorted(ends):
        back = key
        for _ in range(months):
            back = previous_month(back)
        if back in ends and ends[back][1] > 0 and ends[key][1] > 0:
            out.append([_month_label(key), 100 * math.log(ends[key][1] / ends[back][1])])
    return out


CLI_AREAS = {"US": "activity.us.oecd_cli", "JP": "activity.jp.oecd_cli", "DE": "activity.de.oecd_cli",
             "FR": "activity.fr.oecd_cli", "GB": "activity.gb.oecd_cli", "CN": "activity.cn.oecd_cli",
             "IN": "activity.in.oecd_cli", "G7": "activity.g7.oecd_cli", "G20": "activity.g20.oecd_cli"}


def _series(points: list[tuple[date, float]]) -> list[list]:
    return [[day.isoformat(), value] for day, value in sorted(points)]


def _c01(points: dict, view: dict) -> Computed:
    clock, history = [], {}
    for area in CLI_AREAS:
        values = points.get(f"cli:{area}", [])
        history[area] = _series(values)
        position = cycle_positions(values)
        if position:
            clock.append({"area": area, **position})
    values = {
        "clock": clock,
        "history": history,
        "trend_restored": {area: _series(points.get(f"cli_trend_restored:{area}", [])) for area in ("US", "JP")},
        "us_activity": {"industrial_production_yoy": log_change(points.get("ip", []), 12),
                        "gdp_qoq": log_change(points.get("gdp", []), 3),
                        "unemployment": _series(points.get("unemployment", []))},
        "diffusion": {span: _series(points.get(f"diffusion:{span}", [])) for span in ("1m", "3m", "6m")},
    }
    clis = [f"cli:{area}" for area in CLI_AREAS]
    return Computed(values=values, estimates=None, comparison=["clock", "us_activity", "diffusion"], transforms=[
        applied("month_end", applied_to=clis + ["ip", "gdp"]),
        applied("cycle_position", applied_to=clis, produces=["clock"]),
        applied("log_change", applied_to=["ip"], months=12, produces=["us_activity.industrial_production_yoy"]),
        applied("log_change", applied_to=["gdp"], months=3, produces=["us_activity.gdp_qoq"]),
    ])


C01 = AnalysisDefinition("C01", {
    **{f"cli:{area}": sid for area, sid in CLI_AREAS.items()},
    "cli_trend_restored:US": "activity.us.oecd_cli_trend_restored",
    "cli_trend_restored:JP": "activity.jp.oecd_cli_trend_restored",
    "ip": "activity.us.industrial_production",
    "gdp": "activity.us.real_gdp_level",
    "unemployment": "activity.us.unemployment_rate",
    "diffusion:1m": "activity.us.industrial_production_diffusion_1m",
    "diffusion:3m": "activity.us.industrial_production_diffusion_3m",
    "diffusion:6m": "activity.us.industrial_production_diffusion_6m",
}, _c01)


def window_range(points: list[tuple[date, float]], n: int) -> dict | None:
    """Minimum and maximum over the last n observations."""
    last = sorted(points)[-n:]
    if not last:
        return None
    values = [value for _, value in last]
    return {"min": min(values), "max": max(values), "from": last[0][0].isoformat(), "observations": len(last)}


def cross_section_sd(cohort: dict[str, list[tuple[date, float]]]) -> list[list]:
    """[year, population SD across the cohort] for years where every member is observed."""
    by_member = {member: {day.year: value for day, value in points} for member, points in cohort.items()}
    years = set.intersection(*(set(values) for values in by_member.values())) if by_member else set()
    return [[str(year), pstdev([values[year] for values in by_member.values()])] for year in sorted(years)]


def year_on_year(points: list[tuple[date, float]]) -> list[list]:
    """[month, x[t] / x[t-12] - 1] where both months are observed."""
    ends = month_end(points)
    return [[_month_label(key), ends[key][1] / ends[(key[0] - 1, key[1])][1] - 1]
            for key in sorted(ends) if (key[0] - 1, key[1]) in ends and ends[(key[0] - 1, key[1])][1]]


def stagflation_points(growth: list[tuple[date, float]], inflation: list[tuple[date, float]], n: int) -> list[list]:
    """[year, growth, inflation] on years both are reported; the last n of them."""
    g = {day.year: value for day, value in growth}
    i = {day.year: value for day, value in inflation}
    return [[str(year), g[year], i[year]] for year in sorted(set(g) & set(i))][-n:]


GROWTH_AREAS = {"WORLD": "gdp.real_growth.world", "US": "gdp.real_growth.us", "EU": "gdp.real_growth.eu",
                "CN": "gdp.real_growth.cn", "IN": "gdp.real_growth.in", "JP": "gdp.real_growth.jp"}


def _c03(points: dict, view: dict) -> Computed:
    strip = []
    for area in GROWTH_AREAS:
        values = sorted(points.get(f"growth:{area}", []))
        if values:
            strip.append({"area": area, "latest": values[-1][1], "year": str(values[-1][0].year),
                          "range": window_range(values, 10)})
    cohort = {area: points.get(f"growth:{area}", []) for area in GROWTH_AREAS if area != "WORLD"}
    values = {"strip": strip,
              "history": {area: _series(points.get(f"growth:{area}", [])) for area in GROWTH_AREAS},
              "dispersion": cross_section_sd(cohort), "dispersion_cohort": sorted(cohort)}
    roles = [f"growth:{area}" for area in GROWTH_AREAS]
    return Computed(values=values, estimates=None, comparison=["strip", "dispersion"], transforms=[
        applied("own_range_window", applied_to=roles, n=10, produces=["strip.range"]),
        applied("cross_section_sd", applied_to=[f"growth:{a}" for a in cohort], produces=["dispersion"]),
    ])


C03 = AnalysisDefinition("C03", {f"growth:{area}": sid for area, sid in GROWTH_AREAS.items()}, _c03)

C06_COUNTRIES = ("US", "JP", "CN")
COMMODITIES = {"brent": ("Brent crude oil", "prices.commodity.brent_usd"),
               "gas": ("US natural gas", "prices.commodity.natural_gas_us_usd"),
               "maize": ("Maize", "prices.commodity.maize_usd")}


def _c06(points: dict, view: dict) -> Computed:
    commodities = []
    for key, (name, _) in COMMODITIES.items():
        changes = year_on_year(points.get(f"commodity:{key}", []))
        commodities.append({"key": key, "name": name, "latest": changes[-1][1] if changes else None,
                            "as_of": changes[-1][0] if changes else None, "history": changes})
    values = {
        "commodities": commodities,
        "map": {c: stagflation_points(points.get(f"growth:{c}", []), points.get(f"inflation:{c}", []), 8)
                for c in C06_COUNTRIES},
        "inflation": {c: _series(points.get(f"inflation:{c}", [])) for c in C06_COUNTRIES},
        "growth": {c: _series(points.get(f"growth:{c}", [])) for c in C06_COUNTRIES},
    }
    return Computed(values=values, estimates=None, comparison=["map", "commodities"], transforms=[
        applied("month_end", applied_to=[f"commodity:{k}" for k in COMMODITIES]),
        applied("year_on_year_change", applied_to=[f"commodity:{k}" for k in COMMODITIES], produces=["commodities"]),
        applied("matched_pairs", applied_to=[f"growth:{c}" for c in C06_COUNTRIES] + [f"inflation:{c}" for c in C06_COUNTRIES],
                produces=["map"], last_years=8),
    ])


C06 = AnalysisDefinition("C06", {
    **{f"growth:{c}": f"gdp.real_growth.weo.{c.lower()}" for c in C06_COUNTRIES},
    **{f"inflation:{c}": f"prices.{c.lower()}.imf_cpi_inflation" for c in C06_COUNTRIES},
    **{f"commodity:{key}": sid for key, (_, sid) in COMMODITIES.items()},
}, _c06)


def now_and_years_ago(points: list[tuple[date, float]], years: int) -> dict:
    """Latest value and the last value on or before the same day `years` earlier."""
    ordered = sorted(points)
    if not ordered:
        return {"latest": None, "as_of": None, "back": None, "back_as_of": None, "change": None}
    day, latest = ordered[-1]
    earlier = [p for p in ordered if p[0] <= day - timedelta(days=round(365.25 * years))]
    then = earlier[-1] if earlier else None
    return {"latest": latest, "as_of": day.isoformat(), "back": then[1] if then else None,
            "back_as_of": then[0].isoformat() if then else None, "change": latest - then[1] if then else None}


def now_and_year_ago(points: list[tuple[date, float]]) -> dict:
    """Latest value and the last value on or before the same day a year earlier."""
    ordered = sorted(points)
    if not ordered:
        return {"latest": None, "as_of": None, "year_ago": None, "year_ago_as_of": None, "change": None}
    day, latest = ordered[-1]
    target = day - timedelta(days=365)
    earlier = [p for p in ordered if p[0] <= target]
    then = earlier[-1] if earlier else None
    return {"latest": latest, "as_of": day.isoformat(),
            "year_ago": then[1] if then else None, "year_ago_as_of": then[0].isoformat() if then else None,
            "change": latest - then[1] if then else None}


def monthly_difference(a: list[tuple[date, float]], b: list[tuple[date, float]]) -> list[list]:
    """[month, a - b] on month-ends both series report."""
    ea, eb = month_end(a), month_end(b)
    return [[_month_label(key), ea[key][1] - eb[key][1]] for key in sorted(set(ea) & set(eb))]


def _month_series(points: list[tuple[date, float]]) -> list[list]:
    return [[_month_label(key), value] for key, (_, value) in sorted(month_end(points).items())]


def matched_day(a: list[tuple[date, float]], b: list[tuple[date, float]], before: date | None = None) -> date | None:
    days = {d for d, _ in a} & {d for d, _ in b}
    if before is not None:
        days = {d for d in days if d <= before}
    return max(days) if days else None


def _completed(points: dict, view: dict) -> dict:
    """Inputs without the current calendar month, whose last value is not yet a month-end."""
    today = view_today(view)
    return {role: [(d, v) for d, v in values if (d.year, d.month) < (today.year, today.month)]
            for role, values in points.items()}


POLICY_BANKS = {"fed": "Federal Reserve (effective funds rate)", "ecb": "ECB (deposit facility)",
                "boj": "Bank of Japan (overnight call rate)"}


def _m01(daily: dict, view: dict) -> Computed:
    ladder = [{"bank": bank, "name": name, **now_and_year_ago(daily.get(bank, []))} for bank, name in POLICY_BANKS.items()]
    points = _completed(daily, view)
    lower, upper = month_end(points.get("fed_lower", [])), month_end(points.get("fed_upper", []))
    values = {
        "ladder": ladder,
        "fed_target": {"lower": now_and_year_ago(daily.get("fed_lower", []))["latest"],
                       "upper": now_and_year_ago(daily.get("fed_upper", []))["latest"]},
        "gaps": {"eur_minus_usd": monthly_difference(points.get("ecb", []), points.get("fed", [])),
                 "eur_minus_jpy": monthly_difference(points.get("ecb", []), points.get("boj", []))},
        "history": {**{bank: _month_series(points.get(bank, [])) for bank in POLICY_BANKS},
                    "fed_range": [[_month_label(k), lower[k][1], upper[k][1]] for k in sorted(set(lower) & set(upper))]},
    }
    return Computed(values=values, estimates=None, comparison=["ladder", "gaps"], transforms=[
        applied("now_and_year_ago", applied_to=list(POLICY_BANKS), produces=["ladder"]),
        applied("complete_months", applied_to=list(points), today=view_today(view).isoformat()),
        applied("month_end", applied_to=list(points), produces=["history"]),
        applied("yield_difference", applied_to=["ecb", "fed", "boj"], produces=["gaps"], on="matched month-ends"),
    ])


M01 = AnalysisDefinition("M01", {"fed": "policy_rate.us.fed_effective", "ecb": "policy_rate.ea.ecb_dfr",
                                 "boj": "policy_rate.jp.boj_call_daily", "fed_lower": "policy_rate.us.fed_lower",
                                 "fed_upper": "policy_rate.us.fed_upper"}, _m01)


def _m02(points: dict, view: dict) -> Computed:
    nominal, real = points.get("nominal", []), points.get("real", [])
    n, r, published = dict(nominal), dict(real), dict(points.get("breakeven", []))

    def split(day):
        return None if day is None else {"date": day.isoformat(), "nominal": n[day], "real": r[day],
                                         "breakeven": n[day] - r[day]}
    day = matched_day(nominal, real)
    then = matched_day(nominal, real, before=day - timedelta(days=365)) if day else None
    values = {"split": {"now": split(day), "year_ago": split(then),
                        "published_breakeven": published.get(day) if day else None},
              "history": {key: _month_series(points.get(key, [])) for key in ("nominal", "real", "breakeven")}}
    return Computed(values=values, estimates=None, comparison=["nominal", "real", "breakeven"], transforms=[
        applied("matched_day", applied_to=["nominal", "real"], produces=["split"]),
        applied("yield_difference", applied_to=["nominal", "real"], produces=["split.breakeven"]),
        applied("month_end", applied_to=["nominal", "real", "breakeven"], produces=["history"]),
    ])


M02 = AnalysisDefinition("M02", {"nominal": "bond.us.nominal_10y", "real": "bond.us.real_10y",
                                 "breakeven": "bond.us.breakeven_10y"}, _m02)

CURRENCIES = {"USD": ("usd_per_eur", "fed"), "JPY": ("jpy_per_eur", "boj")}


def _m04(daily: dict, view: dict) -> Computed:
    points = _completed(daily, view)
    currencies = []
    for currency, (fx_role, rate_role) in CURRENCIES.items():
        moves = log_change(points.get(fx_role, []), 12)
        gaps = monthly_difference(points.get("ecb", []), points.get(rate_role, []))
        gap_by_month = dict(gaps)
        currencies.append({
            "currency": currency, "move_12m": moves[-1][1] if moves else None, "move_as_of": moves[-1][0] if moves else None,
            "gap": gaps[-1][1] if gaps else None, "gap_as_of": gaps[-1][0] if gaps else None,
            "fx": _month_series(points.get(fx_role, [])), "moves": moves, "gaps": gaps,
            "scatter": [[month, gap_by_month[month], move] for month, move in moves if month in gap_by_month],
        })
    return Computed(values={"currencies": currencies}, estimates=None, comparison=["moves", "gaps"], transforms=[
        applied("complete_months", applied_to=list(points), today=view_today(view).isoformat()),
        applied("month_end", applied_to=list(points)),
        applied("log_change", applied_to=["usd_per_eur", "jpy_per_eur"], months=12, produces=["moves"]),
        applied("yield_difference", applied_to=["ecb", "fed", "boj"], produces=["gaps"], on="matched month-ends"),
        applied("matched_pairs", applied_to=["moves", "gaps"], produces=["scatter"]),
    ])


M04 = AnalysisDefinition("M04", {"fed": "policy_rate.us.fed_effective", "ecb": "policy_rate.ea.ecb_dfr",
                                 "boj": "policy_rate.jp.boj_call_daily", "usd_per_eur": "fx.usd_per_eur.ecb",
                                 "jpy_per_eur": "fx.jpy_per_eur.ecb"}, _m04)

CREDIT_AREAS = ("US", "JP", "DE", "CN", "PT")


def _with_range(points: list[tuple[date, float]]) -> dict | None:
    history = own_history(points)
    if history is None:
        return None
    values = [v for _, v in points]
    return {**history, "min": min(values), "max": max(values)}


def _f01(points: dict, view: dict) -> Computed:
    economies, history = [], {}
    for area in CREDIT_AREAS:
        ratio, trend, gap = (points.get(f"{kind}:{area}", []) for kind in ("ratio", "trend", "gap"))
        history[area] = {"ratio": _series(ratio), "trend": _series(trend), "gap": _series(gap)}
        if not ratio or not trend:
            continue
        r, t = dict(ratio), dict(trend)
        day = max(set(r) & set(t), default=None)
        if day is None:
            continue
        five = now_and_years_ago(ratio, 5)
        economies.append({"area": area, "as_of": day.isoformat(), "ratio": r[day], "trend": t[day],
                          "gap": dict(gap).get(day), "ratio_change_5y": five["change"], "ratio_5y_ago_as_of": five["back_as_of"]})
    history["EA"] = {"ratio": [], "trend": [], "gap": _series(points.get("gap:EA", []))}
    return Computed(values={"economies": economies, "history": history}, estimates=None, comparison=["ratio", "trend", "gap"],
                    transforms=[applied("matched_day", applied_to=["ratio", "trend", "gap"], produces=["economies"]),
                                applied("now_and_years_ago", applied_to=["ratio"], years=5, produces=["economies.ratio_change_5y"])])


F01 = AnalysisDefinition("F01", {
    **{f"ratio:{a}": f"credit.{a.lower()}.private_nonfinancial_gdp_bis" for a in CREDIT_AREAS},
    **{f"trend:{a}": f"credit_gap.{a.lower()}.bis_trend" for a in CREDIT_AREAS},
    **{f"gap:{a}": f"credit_gap.{a.lower()}.bis" for a in CREDIT_AREAS + ("EA",)},
}, _f01)

DSR_SERIES = {("private", a): f"debt_service.{a.lower()}.private.bis" for a in CREDIT_AREAS}
DSR_SERIES.update({("households", "US"): "debt_service.us.households.bis", ("households", "PT"): "debt_service.pt.households.bis",
                   ("corporations", "US"): "debt_service.us.corporations.bis"})


def _f02(points: dict, view: dict) -> Computed:
    rows, history = [], {}
    for (series, area) in DSR_SERIES:
        values = points.get(f"{series}:{area}", [])
        history[f"{series}:{area}"] = _series(values)
        if not values:
            continue
        five, own = now_and_years_ago(values, 5), _with_range(values)
        rows.append({"series": series, "area": area, **five, "own_mean": own["own_mean"], "min": own["min"], "max": own["max"]})
    return Computed(values={"rows": rows, "history": history}, estimates=None, comparison=["rows"], transforms=[
        applied("now_and_years_ago", applied_to=list(points), years=5, produces=["rows"]),
        applied("own_history", applied_to=list(points), produces=["rows.own_mean"])])


F02 = AnalysisDefinition("F02", {f"{series}:{area}": sid for (series, area), sid in DSR_SERIES.items()}, _f02)

STRESS_GAUGES = {"nfci": ("Chicago Fed financial conditions (NFCI)", "stress.us.nfci"),
                 "adjusted_nfci": ("NFCI adjusted for the economy", "stress.us.adjusted_nfci"),
                 "ofr_fsi": ("OFR financial stress index (global)", "stress.global.ofr_fsi"),
                 "baa": ("Baa corporate bond spread over 10-year Treasuries", "credit.us.baa_10y_spread")}
FSI_CATEGORIES = ("credit", "equity_valuation", "safe_assets", "funding", "volatility")
FSI_REGIONS = ("region_united_states", "region_other_advanced", "region_emerging_markets")


def _parts(points: dict, names: tuple[str, ...]) -> dict | None:
    series = [dict(points.get(f"fsi_part:{n}", [])) for n in names]
    days = set.intersection(*(set(s) for s in series)) if all(series) else set()
    if not days:
        return None
    day = max(days)
    return {"date": day.isoformat(), "parts": [{"key": n, "value": s[day]} for n, s in zip(names, series)]}


def _f04(points: dict, view: dict) -> Computed:
    gauges = []
    for key, (name, _) in STRESS_GAUGES.items():
        own = _with_range(points.get(key, []))
        if own:
            gauges.append({"key": key, "name": name, **own})
    categories, regions = _parts(points, FSI_CATEGORIES), _parts(points, FSI_REGIONS)
    values = {"gauges": gauges,
              "fsi_parts": {"date": categories["date"], "categories": categories["parts"],
                            "regions": regions["parts"] if regions and regions["date"] == categories["date"] else []}
              if categories else None,
              "history": {key: _month_series(points.get(key, [])) for key in STRESS_GAUGES}}
    return Computed(values=values, estimates=None, comparison=["gauges", "fsi_parts"], transforms=[
        applied("own_history", applied_to=list(STRESS_GAUGES), produces=["gauges"]),
        applied("additive_parts", applied_to=[f"fsi_part:{n}" for n in FSI_CATEGORIES + FSI_REGIONS], produces=["fsi_parts"]),
        applied("month_end", applied_to=list(STRESS_GAUGES), produces=["history"])])


F04 = AnalysisDefinition("F04", {
    **{key: sid for key, (_, sid) in STRESS_GAUGES.items()},
    **{f"fsi_part:{n}": f"stress.global.ofr_fsi.{n}" for n in FSI_CATEGORIES + FSI_REGIONS},
}, _f04)

DEFINITIONS: dict[str, AnalysisDefinition] = {"P06": P06, "P07": P07, "F03": F03, "C01": C01, "C03": C03, "C06": C06,
                                              "M01": M01, "M02": M02, "M04": M04, "F01": F01, "F02": F02, "F04": F04}
