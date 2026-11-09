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


def p07_hedging_effect(stats: dict) -> dict:
    """What hedging changed, in percentage points: hedged minus unhedged return, volatility and deepest fall."""
    u, h = stats.get("eur_unhedged", {}), stats.get("eur_hedged", {})

    def diff(key):
        a, b = h.get(key), u.get(key)
        return round(100 * (a - b), 6) if a is not None and b is not None else None
    return {"return_pp": diff("annualized_return"), "volatility_pp": diff("annualized_volatility"),
            "max_drawdown_pp": diff("max_drawdown"), "months": u.get("months", 0)}


def _p07(points: dict, view: dict) -> Computed:
    today = view_today(view)
    ends = {role: complete_months(month_end(values), today) for role, values in points.items()}
    values = p07_hedging(ends["usd_per_eur"], ends["equity_netr_usd"], ends["eur_short_rate"],
                         ends["usd_short_rate"], ends["ea_hicp"])
    values["wealth"] = p07_wealth(values["rows"])
    values["drawdown"] = {kind: p07_drawdown(paths) for kind, paths in values["wealth"].items()}
    values["hedging_effect"] = {"nominal": p07_hedging_effect(values["nominal"]), "real": p07_hedging_effect(values["real_eur"])}
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
        applied("yield_difference", applied_to=["eur_hedged", "eur_unhedged"], produces=["hedging_effect"],
                on="annualized return, volatility and maximum drawdown, in percentage points"),
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

def matched_ratio(a: list[tuple[date, float]], b: list[tuple[date, float]], scale_by: float = 1.0) -> list[list]:
    """[period, scale_by * a / b] on periods both series report."""
    da, db = dict(a), dict(b)
    return [[day.isoformat(), scale_by * da[day] / db[day]] for day in sorted(set(da) & set(db)) if db[day]]


def _f05(points: dict, view: dict) -> Computed:
    economies, history = [], {}
    for area in CREDIT_AREAS:
        h, c = dict(points.get(f"household:{area}", [])), dict(points.get(f"corporate:{area}", []))
        history[area] = {"household": _series(points.get(f"household:{area}", [])),
                         "corporate": _series(points.get(f"corporate:{area}", []))}
        day = max(set(h) & set(c), default=None)
        if day is None:
            continue
        government = sorted(points.get(f"government:{area}", []))
        economies.append({"area": area, "as_of": day.isoformat(), "household": h[day], "corporate": c[day],
                          "government": government[-1][1] if government else None,
                          "government_year": str(government[-1][0].year) if government else None})
    leverage = matched_ratio(points.get("bank_equity", []), points.get("bank_assets", []), 100)
    values = {"economies": economies, "history": history,
              "bank": {"equity_to_assets": leverage[-1][1] if leverage else None, "as_of": leverage[-1][0] if leverage else None,
                       "history": leverage}}
    return Computed(values=values, estimates=None, comparison=["economies", "bank"], transforms=[
        applied("matched_day", applied_to=["household", "corporate"], produces=["economies"]),
        applied("matched_ratio", applied_to=["bank_equity", "bank_assets"], scale_by=100, produces=["bank"])])


F05 = AnalysisDefinition("F05", {
    **{f"household:{a}": f"credit.{a.lower()}.household_gdp_bis" for a in CREDIT_AREAS},
    **{f"corporate:{a}": f"credit.{a.lower()}.corporate_gdp_bis" for a in CREDIT_AREAS},
    **{f"government:{a}": f"fiscal.{a.lower()}.public_debt" for a in ("US", "JP", "CN")},
    "bank_assets": "bank.us.fdic_total_assets", "bank_equity": "bank.us.fdic_total_equity",
}, _f05)

PROPERTY_AREAS = ("US", "DE", "JP", "PT", "EA", "WORLD")


def _position(points: list[tuple[date, float]]) -> dict | None:
    own = _with_range(points)
    if own is None:
        return None
    five = now_and_years_ago(points, 5)
    return {**own, "change_5y_pct": 100 * (five["latest"] / five["back"] - 1) if five["back"] else None,
            "back_as_of": five["back_as_of"]}


def _f06(points: dict, view: dict) -> Computed:
    residential = [{"area": a, **p} for a in PROPERTY_AREAS if (p := _position(points.get(f"residential:{a}", [])))]
    commercial = [{"area": a, **p} for a in ("US", "PT") if (p := _position(points.get(f"commercial:{a}", [])))]
    values = {"residential": residential, "commercial": commercial,
              "history": {**{f"residential:{a}": _series(points.get(f"residential:{a}", [])) for a in PROPERTY_AREAS},
                          **{f"commercial:{a}": _series(points.get(f"commercial:{a}", [])) for a in ("US", "PT")}}}
    return Computed(values=values, estimates=None, comparison=["residential", "commercial"], transforms=[
        applied("own_history", applied_to=list(points), produces=["residential", "commercial"]),
        applied("now_and_years_ago", applied_to=list(points), years=5, produces=["change_5y_pct"])])


F06 = AnalysisDefinition("F06", {
    **{f"residential:{a}": f"property.{a.lower()}.real_residential.bis" for a in PROPERTY_AREAS},
    "commercial:US": "property.us.commercial_all.bis", "commercial:PT": "property.pt.commercial_all.bis",
}, _f06)


def _f07(points: dict, view: dict) -> Computed:
    leverage = matched_ratio(points.get("broker_assets", []), points.get("broker_equity", []))
    repo = matched_ratio(points.get("broker_repo", []), points.get("broker_liabilities", []), 100)
    mmf = now_and_years_ago(points.get("mmf_assets", []), 5)
    values = {"latest": {"broker_leverage": leverage[-1][1] if leverage else None,
                         "repo_share": repo[-1][1] if repo else None, "as_of": leverage[-1][0] if leverage else None,
                         "mmf_assets": mmf["latest"], "mmf_assets_5y_ago": mmf["back"], "mmf_as_of": mmf["as_of"]},
              "history": {"broker_leverage": leverage, "repo_share": repo, "mmf_assets": _series(points.get("mmf_assets", [])),
                          "finance_company_assets": _series(points.get("finance_assets", []))}}
    as_points = lambda line: [(date.fromisoformat(d), v) for d, v in line]  # noqa: E731
    positions = [("broker_leverage", "Broker-dealer assets per unit of equity", "×", as_points(leverage)),
                 ("repo_share", "Broker-dealer liabilities funded by repo", "%", as_points(repo)),
                 ("mmf_assets", "Money-market fund assets", "USD million", points.get("mmf_assets", []))]
    values["positions"] = [{"key": key, "name": name, "unit": unit, **own}
                           for key, name, unit, line in positions if (own := _with_range(line))]
    return Computed(values=values, estimates=None, comparison=["broker_leverage", "repo_share", "mmf_assets"], transforms=[
        applied("matched_ratio", applied_to=["broker_assets", "broker_equity"], produces=["broker_leverage"]),
        applied("matched_ratio", applied_to=["broker_repo", "broker_liabilities"], scale_by=100, produces=["repo_share"]),
        applied("now_and_years_ago", applied_to=["mmf_assets"], years=5),
        applied("own_history", applied_to=["broker_leverage", "repo_share", "mmf_assets"], produces=["positions"])])


F07 = AnalysisDefinition("F07", {
    "broker_assets": "funding.us.broker_assets", "broker_equity": "funding.us.broker_equity_capital",
    "broker_liabilities": "funding.us.broker_liabilities", "broker_repo": "funding.us.broker_repo_liabilities",
    "mmf_assets": "funding.us.money_market_assets", "finance_assets": "funding.us.finance_company_total_assets",
}, _f07)

def _monthly_points(ends: dict) -> list[tuple[date, float]]:
    return [(date(k[0], k[1], 1), v) for k, (_, v) in sorted(ends.items())]


def _gauge(key: str, name: str, points: list[tuple[date, float]], unit: str) -> dict | None:
    own = _with_range(points)
    return {"key": key, "name": name, "unit": unit, **own} if own else None


def _v01(points: dict, view: dict) -> Computed:
    ends = {role: month_end(values) for role, values in points.items()}
    cape, price, earnings, dividend, real = (ends.get(k, {}) for k in ("cape", "price", "earnings", "dividend", "real_10y"))
    pe = {k: (None, price[k][1] / earnings[k][1]) for k in sorted(set(price) & set(earnings)) if earnings[k][1]}
    dy = {k: (None, 100 * dividend[k][1] / price[k][1]) for k in sorted(set(price) & set(dividend)) if price[k][1]}
    excess = {k: (None, 100 / cape[k][1] - real[k][1]) for k in sorted(set(cape) & set(real)) if cape[k][1]}
    series = {"cape": _monthly_points(cape), "pe": _monthly_points(pe), "dividend_yield": _monthly_points(dy),
              "excess_cape_yield": _monthly_points(excess)}
    names = {"cape": ("CAPE: price over 10-year average real earnings", "×"), "pe": ("Price over trailing 12-month earnings", "×"),
             "dividend_yield": ("Dividend yield", "%"), "excess_cape_yield": ("Excess CAPE yield over the real 10-year yield", "pp")}
    gauges = [g for key, (name, unit) in names.items() if (g := _gauge(key, name, series[key], unit))]
    return Computed(values={"gauges": gauges, "history": {k: _series(v) for k, v in series.items()}}, estimates=None,
                    comparison=["cape", "pe", "dividend_yield", "excess_cape_yield"], transforms=[
        applied("month_end", applied_to=list(points)),
        applied("matched_ratio", applied_to=["price", "earnings"], produces=["pe"]),
        applied("matched_ratio", applied_to=["dividend", "price"], scale_by=100, produces=["dividend_yield"]),
        applied("earnings_yield", applied_to=["cape"], produces=["excess_cape_yield"]),
        applied("yield_difference", applied_to=["1/cape", "real_10y"], produces=["excess_cape_yield"]),
        applied("own_history", applied_to=list(names), produces=["gauges"])])


V01 = AnalysisDefinition("V01", {"cape": "valuation.us.cape", "price": "valuation.us.shiller_price",
                                 "earnings": "valuation.us.shiller_earnings", "dividend": "valuation.us.shiller_dividend",
                                 "cpi": "prices.us.shiller_cpi", "real_10y": "bond.us.real_10y"}, _v01)


def _v02(points: dict, view: dict) -> Computed:
    names = {"q1": "BEA Q1: equity value over produced assets", "q2": "BEA Q2: adds bonds at book value",
             "q3": "BEA Q3: market bonds and net liquid assets", "cape": "CAPE (monthly)"}
    gauges = [g for key, name in names.items() if (g := _gauge(key, name, points.get(key, []), "×"))]
    return Computed(values={"gauges": gauges, "history": {k: _series(points.get(k, [])) for k in names}}, estimates=None,
                    comparison=list(names), transforms=[applied("own_history", applied_to=list(names), produces=["gauges"])])


V02 = AnalysisDefinition("V02", {"q1": "valuation.us.tobins_q", "q2": "valuation.us.tobins_q2", "q3": "valuation.us.tobins_q3",
                                 "cape": "valuation.us.cape"}, _v02)

MSCI_REGIONS = ("ACWI", "WORLD", "USA", "EUROPE", "JAPAN", "EM", "EAFE")


def _v03(points: dict, view: dict) -> Computed:
    regions, history = [], {}
    for region in MSCI_REGIONS:
        trailing, forward = sorted(points.get(f"trailing:{region}", [])), sorted(points.get(f"forward:{region}", []))
        history[region] = {"trailing": _series(trailing), "forward": _series(forward)}
        if not trailing:
            continue
        day, latest = trailing[-1]
        values = [v for _, v in trailing]
        regions.append({"region": region, "as_of": day.isoformat(), "trailing": latest, "forward": dict(forward).get(day),
                        "trailing_min": min(values), "trailing_max": max(values), "months": len(values)})
    return Computed(values={"regions": regions, "history": history}, estimates=None, comparison=["trailing", "forward"],
                    transforms=[applied("own_range_window", applied_to=[f"trailing:{r}" for r in MSCI_REGIONS], n="all")])


V03 = AnalysisDefinition("V03", {
    **{f"trailing:{r}": f"valuation.{r.lower()}.msci_trailing_pe" for r in MSCI_REGIONS},
    **{f"forward:{r}": f"valuation.{r.lower()}.msci_forward_pe" for r in MSCI_REGIONS},
}, _v03)


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(x: list[float], y: list[float]) -> float | None:
    """Spearman rank correlation with average ranks for ties; None when undefined."""
    if len(x) < 3 or len(x) != len(y):
        return None
    rx, ry = _ranks(list(x)), _ranks(list(y))
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx, vy = sum((a - mx) ** 2 for a in rx), sum((b - my) ** 2 for b in ry)
    return cov / math.sqrt(vx * vy) if vx and vy else None


V05_ERAS = (("1881–1944", 1881, 1944), ("1945–1979", 1945, 1979), ("1980 onward", 1980, 9999), ("All years", 0, 9999))


def _v05(points: dict, view: dict) -> Computed:
    cape, real_tr = month_end(points.get("cape", [])), month_end(points.get("real_tr", []))
    cells = []
    for horizon in (5, 10, 15):
        windows = calibration_points(cape, real_tr, horizon)
        for era, start, end in V05_ERAS:
            chosen = [w for w in windows if start <= int(w[0][:4]) <= end]
            effective = round(len(chosen) / (12 * horizon), 1)
            rho = spearman([w[1] for w in chosen], [w[2] for w in chosen]) if effective >= 2 else None
            cells.append({"horizon_years": horizon, "era": era, "windows": len(chosen), "effective_windows": effective,
                          "rho": rho, "first_start": chosen[0][0] if chosen else None, "last_start": chosen[-1][0] if chosen else None})
    return Computed(values={"cells": cells, "eras": [e for e, *_ in V05_ERAS], "horizons": [5, 10, 15]}, estimates=None,
                    comparison=["cells"], transforms=[
        applied("calibration_points", applied_to=["cape", "real_tr"], horizons=[5, 10, 15]),
        applied("rank_correlation", applied_to=["calibration_points"], produces=["cells"], eras=[e for e, *_ in V05_ERAS])])


V05 = AnalysisDefinition("V05", {"cape": "valuation.us.cape", "real_tr": "returns.us.shiller_real_total_return",
                                 "real_10y": "bond.us.real_10y", "cpi": "prices.us.shiller_cpi"}, _v05)

G05_AREAS = ("US", "JP", "DE", "CN", "PT")


def _g05(points: dict, view: dict) -> Computed:
    economies, history = [], {}
    for area in G05_AREAS:
        ca = sorted(points.get(f"ca_gdp:{area}", []))
        position = [[str(date.fromisoformat(d).year), v] for d, v in
                    matched_ratio(points.get(f"niip:{area}", []), points.get(f"gdp:{area}", []), 100)]
        history[area] = {"current_account_gdp": _series(ca), "net_position_gdp": position}
        if not ca and not position:
            continue
        economies.append({"area": area,
                          "current_account_gdp": ca[-1][1] if ca else None, "current_account_year": str(ca[-1][0].year) if ca else None,
                          "net_position_gdp": position[-1][1] if position else None,
                          "net_position_year": position[-1][0] if position else None})
    return Computed(values={"economies": economies, "history": history}, estimates=None,
                    comparison=["current_account_gdp", "net_position_gdp"], transforms=[
        applied("matched_ratio", applied_to=["niip", "gdp"], scale_by=100, produces=["net_position_gdp"])])


G05 = AnalysisDefinition("G05", {
    **{f"ca_gdp:{a}": f"external.{a.lower()}.current_account_gdp" for a in ("US", "JP", "DE", "CN")},
    **{f"niip:{a}": f"external.{a.lower()}.imf_iip_net_position_usd" for a in G05_AREAS},
    **{f"gdp:{a}": f"gdp.nominal_usd.{a.lower()}" for a in G05_AREAS},
}, _g05)

G06_AREAS = ("US", "DE", "FR", "PT", "JP", "CN", "IN")


def _g06(points: dict, view: dict) -> Computed:
    economies, history = [], {}
    for area in G06_AREAS:
        share = sorted(points.get(f"share:{area}", []))
        history[area] = _series(share)
        if share:
            economies.append({"area": area, "first": share[0][1], "first_year": str(share[0][0].year),
                              "latest": share[-1][1], "latest_year": str(share[-1][0].year)})
    return Computed(values={"economies": economies, "history": history}, estimates=None, comparison=["economies"],
                    transforms=[])


G06 = AnalysisDefinition("G06", {f"share:{a}": f"supply_chain.{a.lower()}.foreign_final_demand_share" for a in G06_AREAS}, _g06)

KLEMS_AREAS = ("US", "DE", "FR", "PT", "GB", "IT", "ES", "NL")
NFC_AREAS = ("US", "DE", "FR", "PT", "GB", "IT", "ES", "NL")


def _by_period(points: list[tuple[date, float]]) -> dict:
    return {day: value for day, value in points}


def _real_per_hour(nominal: dict, price: dict, hours: dict) -> dict:
    return {d: (nominal[d] / price[d]) / hours[d] for d in set(nominal) & set(price) & set(hours) if price[d] and hours[d]}


def _l01(points: dict, view: dict) -> Computed:
    economies, history = [], {}
    for area in KLEMS_AREAS:
        price, hours = _by_period(points.get(f"va_price:{area}", [])), _by_period(points.get(f"hours:{area}", []))
        prod = _real_per_hour(_by_period(points.get(f"va:{area}", [])), price, hours)
        pay = _real_per_hour(_by_period(points.get(f"pay:{area}", [])), price, hours)
        common = sorted(set(prod) & set(pay))
        if not common:
            history[area] = {"productivity": [], "pay": []}
            continue
        base = common[0]
        p_idx = {d: 100 * prod[d] / prod[base] for d in common}
        w_idx = {d: 100 * pay[d] / pay[base] for d in common}
        history[area] = {"productivity": [[d.isoformat(), p_idx[d]] for d in common], "pay": [[d.isoformat(), w_idx[d]] for d in common]}
        economies.append({"area": area, "base_year": str(base.year), "latest_year": str(common[-1].year),
                          "productivity": p_idx[common[-1]], "pay": w_idx[common[-1]]})
    prod, comp, defl = (_by_period(points.get(k, [])) for k in ("bls_productivity", "bls_hourly_comp", "bls_deflator"))
    common = sorted(d for d in set(prod) & set(comp) & set(defl) if d >= date(1995, 1, 1))
    if common:
        base = common[0]
        real = {d: comp[d] / defl[d] for d in common}
        p_idx = {d: 100 * prod[d] / prod[base] for d in common}
        w_idx = {d: 100 * real[d] / real[base] for d in common}
        history["US_BLS"] = {"productivity": [[d.isoformat(), p_idx[d]] for d in common], "pay": [[d.isoformat(), w_idx[d]] for d in common]}
        economies.append({"area": "US_BLS", "base_year": base.isoformat()[:7], "latest_year": common[-1].isoformat()[:7],
                          "productivity": p_idx[common[-1]], "pay": w_idx[common[-1]]})
    return Computed(values={"economies": economies, "history": history}, estimates=None, comparison=["productivity", "pay"],
                    transforms=[applied("real_per_hour_index", applied_to=["va", "pay", "va_price", "hours"]),
                                applied("index_100", applied_to=["bls_productivity", "bls_hourly_comp/bls_deflator"], base="1995Q1")])


L01 = AnalysisDefinition("L01", {
    **{f"{k}:{a}": f"labour.{a.lower()}.euklems_{s}" for a in KLEMS_AREAS
       for k, s in (("va", "value_added"), ("va_price", "value_added_price_index"), ("hours", "hours_worked"), ("pay", "labour_compensation"))},
    "bls_productivity": "labour.us.nonfarm_productivity", "bls_hourly_comp": "labour.us.nonfarm_hourly_comp",
    "bls_deflator": "prices.us.nonfarm_output_deflator",
}, _l01)


def _l02(points: dict, view: dict) -> Computed:
    economies, history = [], {}
    for area in NFC_AREAS:
        get = lambda k: _by_period(points.get(f"{k}:{area}", []))  # noqa: E731
        gva, comp, gos, cfc, taxes, subs = (get(k) for k in ("gva", "comp", "gos", "cfc", "taxes", "subsidies"))
        history[area] = {"labour_share": [[d.isoformat(), 100 * comp[d] / gva[d]] for d in sorted(set(gva) & set(comp)) if gva[d]]}
        days = sorted(set(gva) & set(comp) & set(gos) & set(cfc) & set(taxes))
        if not days:
            continue
        d = days[-1]
        net_taxes = taxes[d] - subs.get(d, 0.0)
        parts = {"compensation": comp[d], "net_operating_surplus": gos[d] - cfc[d], "depreciation": cfc[d],
                 "net_production_taxes": net_taxes}
        remainder = gva[d] - sum(parts.values())
        shares = [{"key": k, "share": 100 * v / gva[d]} for k, v in parts.items()]
        if abs(remainder) / gva[d] > 0.001:
            shares.append({"key": "remainder", "share": 100 * remainder / gva[d]})
        economies.append({"area": area, "year": str(d.year), "parts": shares, "subsidies_reported": d in subs})
    return Computed(values={"economies": economies, "history": history}, estimates=None, comparison=["parts"],
                    transforms=[applied("share_of_total", applied_to=["comp", "gos", "cfc", "taxes", "subsidies"], total="gva")])


L02 = AnalysisDefinition("L02", {
    **{f"{k}:{a}": f"profit.{a.lower()}.nfc_{s}" for a in NFC_AREAS
       for k, s in (("gva", "gross_value_added"), ("comp", "compensation"), ("gos", "gross_operating_surplus"),
                    ("cfc", "consumption_fixed_capital"), ("taxes", "other_production_taxes"))},
    **{f"subsidies:{a}": f"profit.{a.lower()}.nfc_other_production_subsidies" for a in NFC_AREAS if a != "US"},
}, _l02)


def _l03(points: dict, view: dict) -> Computed:
    economies, history = [], {}
    for area in NFC_AREAS:
        gos, cfc, capital = (_by_period(points.get(f"{k}:{area}", [])) for k in ("gos", "cfc", "capital"))
        rate = [[d.isoformat(), 100 * (gos[d] - cfc[d]) / capital[d]] for d in sorted(set(gos) & set(cfc) & set(capital)) if capital[d]]
        history[area] = rate
        if rate:
            economies.append({"area": area, "first": rate[0][1], "first_year": rate[0][0][:4],
                              "latest": rate[-1][1], "latest_year": rate[-1][0][:4]})
    return Computed(values={"economies": economies, "history": history}, estimates=None, comparison=["economies"],
                    transforms=[applied("matched_ratio", applied_to=["gos - cfc", "capital"], scale_by=100)])


L03 = AnalysisDefinition("L03", {
    **{f"{k}:{a}": f"profit.{a.lower()}.nfc_{s}" for a in NFC_AREAS
       for k, s in (("gos", "gross_operating_surplus"), ("cfc", "consumption_fixed_capital"), ("capital", "net_fixed_assets"))},
}, _l03)

WEALTH_GROUPS = {"top_point1": "Top 0.1%", "next_point9": "Next 0.9%", "next9": "Next 9%", "middle40": "Middle 40%", "bottom50": "Bottom 50%"}


def _l05(points: dict, view: dict) -> Computed:
    series = {k: sorted(points.get(k, [])) for k in WEALTH_GROUPS}
    days = sorted(set.intersection(*(set(d for d, _ in v) for v in series.values()))) if all(series.values()) else []
    by = {k: dict(v) for k, v in series.items()}
    groups = [{"key": k, "label": label, "first": by[k][days[0]] if days else None, "latest": by[k][days[-1]] if days else None}
              for k, label in WEALTH_GROUPS.items()]
    values = {"groups": groups, "first_date": days[0].isoformat() if days else None, "latest_date": days[-1].isoformat() if days else None,
              "history": {k: _series(v) for k, v in series.items()}}
    return Computed(values=values, estimates=None, comparison=["groups"], transforms=[
        applied("matched_day", applied_to=list(WEALTH_GROUPS), produces=["first_date", "latest_date"])])


L05 = AnalysisDefinition("L05", {
    "top_point1": "wealth.us.top_point1_share", "next_point9": "wealth.us.next_point9_share", "next9": "wealth.us.next9_share",
    "middle40": "wealth.us.middle40_share", "bottom50": "wealth.us.bottom50_share"}, _l05)

INEQUALITY_AREAS = ("US", "FR", "PT", "CN", "IN", "WORLD")


def _l07(points: dict, view: dict) -> Computed:
    economies, history = [], {}
    for area in INEQUALITY_AREAS:
        top, bottom = _by_period(points.get(f"top1:{area}", [])), _by_period(points.get(f"bottom50:{area}", []))
        history[area] = {"top1": [[d.isoformat(), 100 * v] for d, v in sorted(top.items())],
                         "bottom50": [[d.isoformat(), 100 * v] for d, v in sorted(bottom.items())]}
        days = sorted(set(top) & set(bottom))
        if not days:
            continue
        then = next((d for d in days if d.year >= 1980), days[0])
        economies.append({"area": area, "then_year": str(then.year), "latest_year": str(days[-1].year),
                          "top1_then": 100 * top[then], "top1_latest": 100 * top[days[-1]],
                          "bottom50_then": 100 * bottom[then], "bottom50_latest": 100 * bottom[days[-1]]})
    return Computed(values={"economies": economies, "history": history}, estimates=None, comparison=["top1", "bottom50"],
                    transforms=[applied("percent_to_fraction", applied_to=["top1", "bottom50"], direction="fraction to percent")])


L07 = AnalysisDefinition("L07", {
    **{f"top1:{a}": f"inequality.{a.lower()}.pretax_income.top1" for a in INEQUALITY_AREAS},
    **{f"bottom50:{a}": f"inequality.{a.lower()}.pretax_income.bottom50" for a in INEQUALITY_AREAS},
}, _l07)

def pearson(x: list[float], y: list[float]) -> float | None:
    if len(x) < 3 or len(x) != len(y):
        return None
    mx, my = sum(x) / len(x), sum(y) / len(y)
    vx, vy = sum((a - mx) ** 2 for a in x), sum((b - my) ** 2 for b in y)
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / math.sqrt(vx * vy) if vx and vy else None


def _eur_returns(levels: dict | None, returns: dict | None, fx: dict) -> dict:
    """Monthly EUR returns from USD month-end levels or USD monthly returns; fx in USD per EUR."""
    out = {}
    source = returns if returns is not None else {k: levels[k][1] / levels[previous_month(k)][1] - 1
                                                   for k in levels if previous_month(k) in levels}
    for key, r in source.items():
        prev = previous_month(key)
        if key in fx and prev in fx:
            out[key] = (1 + r) * fx[prev][1] / fx[key][1] - 1
    return out


P02_PAIRS = {"stocks_bonds": ("equity", "bonds"), "stocks_gold": ("equity", "gold"), "bonds_gold": ("bonds", "gold")}
P02_PERIODS = (("2000–2009", 2000, 2009), ("2010–2019", 2010, 2019), ("2020 onward", 2020, 9999), ("All years", 0, 9999))


def _p02(daily: dict, view: dict) -> Computed:
    points = _completed(daily, view)
    fx = month_end(points.get("usd_per_eur", []))
    rets = {"equity": _eur_returns(month_end(points.get("equity", [])), None, fx),
            "gold": _eur_returns(month_end(points.get("gold", [])), None, fx),
            "bonds": _eur_returns(None, {k: v for k, (_, v) in month_end(points.get("bonds", [])).items()}, fx)}
    falls = {k for k, r in rets["equity"].items() if r < -0.05}
    cells, rolling = [], {}
    for pair, (a, b) in P02_PAIRS.items():
        months = sorted(set(rets[a]) & set(rets[b]))
        periods = [(name, [m for m in months if start <= m[0] <= end], 24) for name, start, end in P02_PERIODS]
        periods.append(("Months stocks fell over 5%", [m for m in months if m in falls], 12))
        for name, chosen, minimum in periods:
            rho = pearson([rets[a][m] for m in chosen], [rets[b][m] for m in chosen]) if len(chosen) >= minimum else None
            cells.append({"pair": pair, "period": name, "rho": rho, "months": len(chosen),
                          "from": _month_label(chosen[0]) if chosen else None, "to": _month_label(chosen[-1]) if chosen else None})
        series = []
        for i in range(35, len(months)):
            window = months[i - 35:i + 1]
            if (window[-1][0] - window[0][0]) * 12 + window[-1][1] - window[0][1] == 35:
                series.append([_month_label(window[-1]), pearson([rets[a][m] for m in window], [rets[b][m] for m in window])])
        rolling[pair] = series
    return Computed(values={"cells": cells, "rolling": rolling, "pairs": list(P02_PAIRS),
                            "periods": [p for p, *_ in P02_PERIODS] + ["Months stocks fell over 5%"]}, estimates=None,
                    comparison=["cells", "rolling"], transforms=[
        applied("complete_months", applied_to=list(daily), today=view_today(view).isoformat()),
        applied("month_end", applied_to=list(daily)),
        applied("monthly_return", applied_to=["equity", "gold"]),
        applied("fx_translation", applied_to=["equity", "gold", "bonds"], produces=["EUR returns"]),
        applied("pearson_correlation", applied_to=list(P02_PAIRS), produces=["cells", "rolling"], rolling_months=36)])


P02 = AnalysisDefinition("P02", {"equity": "equity.world.msci_acwi_netr_usd", "gold": "gold.usd.monthly_average",
                                 "bonds": "returns.swinkels.us.sovereign_10y_original_1962_usd",
                                 "usd_per_eur": "fx.usd_per_eur.ecb"}, _p02)


def drawdown_episodes(points: list[tuple[date, float]], threshold: float, recession_months: set) -> list[dict]:
    """Peak → trough → recovery episodes of month-end levels deeper than `threshold` (a negative fraction)."""
    ends = month_end(points)
    keys = sorted(ends)
    episodes, peak, trough, start = [], None, None, None

    def months_between(a, b):
        return (b[0] - a[0]) * 12 + b[1] - a[1]

    def close(recovery):
        depth = ends[trough][1] / ends[start][1] - 1
        if depth <= threshold:
            span_end = recovery or keys[-1]
            episodes.append({"peak": _month_label(start), "trough": _month_label(trough),
                             "recovery": _month_label(recovery) if recovery else None, "depth": depth,
                             "months_down": months_between(start, trough),
                             "months_to_recover": months_between(trough, recovery) if recovery else None,
                             "us_recession": any(start <= m <= span_end for m in recession_months)})
    for key in keys:
        level = ends[key][1]
        if peak is None or level >= ends[peak][1]:
            if start is not None:
                close(key)
                start = None
            peak = key
            continue
        if start is None:
            start, trough = peak, key
        elif level < ends[trough][1]:
            trough = key
    if start is not None:
        close(None)
    return episodes


def _p03(daily: dict, view: dict) -> Computed:
    points = _completed(daily, view)
    recession = {k for k, (_, v) in month_end(points.get("recession", [])).items() if v >= 0.5}
    ends = month_end(points.get("equity", []))
    peak, underwater = None, []
    for key in sorted(ends):
        level = ends[key][1]
        peak = level if peak is None else max(peak, level)
        underwater.append([_month_label(key), level / peak - 1])
    values = {"episodes": drawdown_episodes(points.get("equity", []), -0.15, recession), "underwater": underwater}
    return Computed(values=values, estimates=None, comparison=["episodes"], transforms=[
        applied("complete_months", applied_to=list(daily), today=view_today(view).isoformat()),
        applied("month_end", applied_to=["equity", "recession"]),
        applied("drawdown_episodes", applied_to=["equity"], threshold=-0.15, produces=["episodes"]),
        applied("drawdown", applied_to=["equity"], produces=["underwater"])])


P03 = AnalysisDefinition("P03", {"equity": "equity.world.msci_acwi_netr_usd", "recession": "recession.us.nber_indicator"}, _p03)

DEFINITIONS: dict[str, AnalysisDefinition] = {"P06": P06, "P07": P07, "F03": F03, "C01": C01, "C03": C03, "C06": C06,
                                              "M01": M01, "M02": M02, "M04": M04, "F01": F01, "F02": F02, "F04": F04,
                                              "F05": F05, "F06": F06, "F07": F07, "V01": V01, "V02": V02, "V03": V03,
                                              "V05": V05, "G05": G05, "G06": G06, "L01": L01, "L02": L02,
                                              "L03": L03, "L05": L05, "L07": L07, "P02": P02, "P03": P03}
