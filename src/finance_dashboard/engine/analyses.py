"""Analysis definitions computed by the engine.

Pure functions over observed values; nothing is interpolated or filled.
Month-end values are the last observation published in each calendar month.
Monthly returns use only adjacent months that are both observed; cumulative
series cover the longest contiguous run ending at the latest common month.
"""
from __future__ import annotations

from datetime import date

from .bundle import AnalysisDefinition, Computed
from .transforms import (applied, complete_months, contiguous_tail, index_100, month_end, previous_month,
                         return_summary)


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


def _p07(points: dict, view: dict) -> Computed:
    today = view_today(view)
    ends = {role: complete_months(month_end(values), today) for role, values in points.items()}
    values = p07_hedging(ends["usd_per_eur"], ends["equity_netr_usd"], ends["eur_short_rate"],
                         ends["usd_short_rate"], ends["ea_hicp"])
    values["wealth"] = p07_wealth(values["rows"])
    roles = list(points)
    return Computed(values=values, estimates=None, comparison=["eur_unhedged", "eur_hedged"], transforms=[
        applied("month_end", applied_to=roles),
        applied("complete_months", applied_to=roles, today=today.isoformat()),
        applied("monthly_return", applied_to=["equity_netr_usd", "usd_per_eur", "ea_hicp"]),
        applied("contiguous_tail", applied_to=["rows"]),
        applied("return_summary", applied_to=["usd_return", "eur_unhedged", "eur_hedged"]),
        applied("index_100", applied_to=["eur_unhedged", "eur_hedged"]),
    ])


P07 = AnalysisDefinition("P07", {
    "usd_per_eur": "fx.usd_per_eur.ecb",
    "equity_netr_usd": "equity.world.msci_acwi_netr_usd",
    "eur_short_rate": "policy_rate.ea.ecb_dfr",
    "usd_short_rate": "policy_rate.us.fed_effective",
    "ea_hicp": "prices.ea.hicp_index_2025",
}, _p07)

DEFINITIONS: dict[str, AnalysisDefinition] = {"P07": P07}
