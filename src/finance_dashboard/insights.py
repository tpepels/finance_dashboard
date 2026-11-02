"""Descriptive macro readouts using the original observation timeline.

Comparisons are deliberately limited to the same economic measure. No
interpolation, artificial alignment, investment signal, or causal inference.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable, Any

_YEAR_TOLERANCE_DAYS = {"D": 40, "M": 55, "Q": 120, "A": 210}


def measure_family(sid: str) -> str:
    if sid in {"policy_rate.us.bis", "policy_rate.ea.bis", "policy_rate.jp.bis"}:
        return "bis_harmonized_policy"
    if sid.startswith("gdp.real_growth."):
        return "real_gdp_growth"
    if sid in {"credit_gap.us.bis", "credit_gap.ea.bis", "credit_gap.jp.bis"}:
        return "bis_credit_gap"
    if sid in {"valuation.domestic_cap_gdp.us", "valuation.domestic_cap_gdp.jp"}:
        return "domestic_equity_cap_to_gdp"
    return sid


def same_measure(ids: list[str]) -> bool:
    return not ids or len({measure_family(sid) for sid in ids}) == 1


def _change_unit(unit: str) -> str:
    if unit in {"percent", "percentage_points"}:
        return "percentage_points"
    if unit == "index":
        return "index_points"
    return unit


def _observations(raw: Iterable[Any]) -> list[tuple[date, Decimal]]:
    """Accept stored SQLAlchemy observations or fixture/date-value pairs."""
    by_date: dict[date, Decimal] = {}
    for item in raw:
        period, value = (item if isinstance(item, tuple) else (item.period, item.value))
        if isinstance(value, Decimal) and value.is_finite():
            by_date[period] = value
    return sorted(by_date.items())


def _year_ago(points: list[tuple[date, Decimal]], frequency: str):
    latest_date = points[-1][0]
    previous_year = latest_date - timedelta(days=365)
    tolerance = _YEAR_TOLERANCE_DAYS[frequency]
    matches = [(abs((day - previous_year).days), day, value)
               for day, value in points[:-1]
               if abs((day - previous_year).days) <= tolerance]
    if not matches:
        return None
    _, day, value = min(matches, key=lambda row: (row[0], row[1]))
    return day, value


def summarize(
    records: list[tuple[dict[str, Any], Iterable[Any]]]
) -> dict[str, Any]:
    """Source-dated one-year differences and exact shared-date dispersion.

    The calling API validates that series represent the same measurement
    family before granting a combined readout.
    """
    ids = [meta["id"] for meta, _ in records]
    if not same_measure(ids):
        raise ValueError("Unrelated economic measurements cannot share an insight comparison")
    full = []
    summaries: list[dict[str, Any]] = []
    for meta, raw in records:
        points = _observations(raw)
        full.append((meta, dict(points)))
        if not points:
            summaries.append({"id": meta["id"], "name": meta["name"],
                              "status": "no_data", "count": 0})
            continue
        recent_date, recent_value = points[-1]
        result = {
            "id": meta["id"], "name": meta["name"], "status": "ready",
            "frequency": meta["frequency"], "unit": meta["unit"],
            "count": len(points), "date": recent_date.isoformat(),
            "value": str(recent_value), "year_change": None,
        }
        prior = _year_ago(points, meta["frequency"])
        if prior:
            prev_date, prev_value = prior
            result["year_change"] = {
                "from_date": prev_date.isoformat(),
                "to_date": recent_date.isoformat(),
                "difference": str(recent_value - prev_value),
                "unit": _change_unit(meta["unit"]),
            }
        summaries.append(result)

    spread = None
    usable = [(meta, readings) for meta, readings in full if readings]
    # Never present a full-chart geographic range if a requested source is
    # unavailable; partial participation would silently change the cohort.
    if len(usable) >= 2 and len(usable) == len(records):
        units = {meta["unit"] for meta, _ in usable}
        frequencies = {meta["frequency"] for meta, _ in usable}
        if len(units) == 1 and len(frequencies) == 1:
            shared = set.intersection(*(set(readings) for _, readings in usable))
            if shared:
                common = max(shared)
                measured = sorted(((readings[common], meta["id"], meta["name"])
                                  for meta, readings in usable))
                low, high = measured[0], measured[-1]
                spread = {
                    "date": common.isoformat(),
                    "highest": {"id": high[1], "name": high[2], "value": str(high[0])},
                    "lowest": {"id": low[1], "name": low[2], "value": str(low[0])},
                    "difference": str(high[0] - low[0]),
                    "unit": _change_unit(usable[0][0]["unit"]),
                }
    return {
        "series": summaries,
        "matched_spread": spread,
        "method": ("Annual comparison uses closest recorded observation to "
                   "365 days earlier within a frequency-specific tolerance; "
                   "spread requires exactly matching source-native dates; "
                   "no resampling, forward filling, causal claims or forecasts."),
    }
