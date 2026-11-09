"""Analysis definitions computed by the engine.

Pure functions over observed values; nothing is interpolated or filled.
Month-end values are the last observation published in each calendar month.
Monthly returns use only adjacent months that are both observed; cumulative
series cover the longest contiguous run ending at the latest common month.
"""
from __future__ import annotations

from datetime import date

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

DEFINITIONS: dict[str, AnalysisDefinition] = {"P06": P06, "P07": P07, "F03": F03}
