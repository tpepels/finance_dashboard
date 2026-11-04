"""Original Bank of Japan uncollateralized overnight call-rate downloads.

The daily average (FM01'STRDCLUCON, from 1998) and the monthly average / end-
of-month series (FM02'STRACLUCON, FM02'STRECLUCON, from 1985) are separately
published definitions. They are preserved as different series; the consistency
audit below only checks them against each other, never substitutes one for
another or interpolates.
"""
from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal, InvalidOperation
import io
import re

from .bis import ProviderError

BOJ_ROOT = "https://www.stat-search.boj.or.jp/ssi/mtshtml/csv"
BOJ_UNIT = "percent per annum"
# series id -> (download file, series code, value column, native frequency)
BOJ_SERIES = {
    "policy_rate.jp.boj_call_daily": ("fm01_d_1_en", "FM01'STRDCLUCON", 0, "D"),
    "policy_rate.jp.boj_call_monthly_end": ("fm02_m_1_en", "FM02'STRECLUCON", 0, "M"),
    "policy_rate.jp.boj_call_monthly_average": ("fm02_m_1_en", "FM02'STRACLUCON", 1, "M"),
}
# Analyst partition used only to group the consistency audit; these months are
# not source observations and do not assert exact BOJ announcement dates.
REGIME_WINDOWS = (
    ("market_rate_before_zero_rate_policy", "1985-07", "1999-01"),
    ("zero_interest_rate_policy_1999_2000", "1999-02", "2000-08"),
    ("interval_after_zero_rate_policy_2000_2001", "2000-09", "2001-02"),
    ("quantitative_easing_2001_2006", "2001-03", "2006-06"),
    ("normalization_2006_2008", "2006-07", "2008-09"),
    ("crisis_easing_2008_2010", "2008-10", "2010-09"),
    ("comprehensive_monetary_easing_2010_2013", "2010-10", "2013-03"),
    ("quantitative_qualitative_easing_2013_2016", "2013-04", "2016-01"),
    ("negative_rate_and_yield_curve_control_2016_2024", "2016-02", "2024-03"),
    ("after_negative_rate_policy_from_2024", "2024-04", "9999-12"),
)


def boj_url(file_name: str) -> str:
    return f"{BOJ_ROOT}/{file_name}.csv"


def _period(label: str, frequency: str) -> date:
    pattern = r"(\d{4})/(\d{2})/(\d{2})" if frequency == "D" else r"(\d{4})/(\d{2})"
    match = re.fullmatch(pattern, label)
    if not match:
        raise ProviderError("BOJ observation period label is invalid")
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)) if frequency == "D" else 1)
    except ValueError as exc:
        raise ProviderError("BOJ observation period is not a calendar date") from exc


def parse_boj_csv(text: str, series_id: str, start: date | None = None) -> dict[date, Decimal]:
    """Return numeric observations; explicit NA remains absent, never zero."""
    spec = BOJ_SERIES.get(series_id)
    if spec is None:
        raise ProviderError("Unregistered BOJ time-series")
    _, code, column, frequency = spec
    rows = list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))
    labelled = {row[0]: row[1:] for row in rows if row and row[0] in (
        "Series code", "Unit", "Start of the time-series", "End of the time-series")}
    codes = labelled.get("Series code")
    if codes is None or column >= len(codes) or codes[column] != code:
        raise ProviderError("BOJ series code or column identity changed")
    if labelled.get("Unit", [None] * (column + 1))[column] != BOJ_UNIT:
        raise ProviderError("BOJ native unit changed")
    values: dict[date, Decimal] = {}
    seen: set[date] = set()
    for row in rows:
        if not row or not re.fullmatch(r"\d{4}/\d{2}(/\d{2})?", row[0]):
            continue
        if len(row) != len(codes) + 1:
            raise ProviderError("BOJ row has an unexpected number of fields")
        day = _period(row[0], frequency)
        if day in seen or day > date.today():
            raise ProviderError("BOJ observation is duplicated or future-dated")
        seen.add(day)
        raw = row[column + 1].strip()
        if raw in ("", "NA"):
            continue
        try:
            value = Decimal(raw)
        except InvalidOperation as exc:
            raise ProviderError("BOJ observation value is invalid") from exc
        if not value.is_finite():
            raise ProviderError("BOJ observation value is not finite")
        if start is None or day >= start:
            values[day] = value
    if not seen or not values:
        raise ProviderError("BOJ download has no usable observations in the requested period")
    first, last = labelled.get("Start of the time-series", [None] * (column + 1))[column], labelled.get("End of the time-series", [None] * (column + 1))[column]
    if first != min(seen).strftime("%Y/%m/%d" if frequency == "D" else "%Y/%m") or last != max(seen).strftime("%Y/%m/%d" if frequency == "D" else "%Y/%m"):
        raise ProviderError("BOJ declared series bounds differ from the downloaded rows")
    return values


def _half_unit(raw: Decimal) -> Decimal:
    return Decimal(5).scaleb(raw.as_tuple().exponent - 1)


def audit_boj_consistency(daily_csv: str, monthly_csv: str) -> dict:
    """Compare published monthly averages and month-end values with the daily series.

    A published value is a rounding of an unrounded rate. The residual bound is
    therefore the half-unit of the monthly rounding plus the mean half-unit of
    the rounded daily values (or the single daily value for month-end), the
    exact publisher-precision bound rather than a fitted tolerance.
    """
    def table(text, column):
        out = {}
        for row in csv.reader(io.StringIO(text.lstrip("\ufeff"))):
            if row and re.fullmatch(r"\d{4}/\d{2}(/\d{2})?", row[0]) and row[column + 1] not in ("", "NA"):
                out[row[0]] = Decimal(row[column + 1])
        return out
    daily, average, month_end = table(daily_csv, 0), table(monthly_csv, 1), table(monthly_csv, 0)
    by_month: dict[str, list[tuple[str, Decimal]]] = {}
    for label, value in daily.items():
        by_month.setdefault(label[:7], []).append((label, value))
    last_month = max(by_month)
    regimes = {name: {"months": 0, "average_failures": 0, "month_end_failures": 0,
                      "largest_average_residual": Decimal(0), "largest_month_end_residual": Decimal(0)}
               for name, _, _ in REGIME_WINDOWS}
    uncovered = []
    for month in sorted(set(average) & set(by_month)):
        if month == last_month:
            continue  # the newest month can be incomplete
        label = month.replace("/", "-")
        regime = next((name for name, low, high in REGIME_WINDOWS if low <= label <= high), None)
        if regime is None:
            uncovered.append(month)
            continue
        values = [value for _, value in by_month[month]]
        mean = sum(values, Decimal(0)) / len(values)
        average_bound = _half_unit(average[month]) + sum((_half_unit(v) for v in values), Decimal(0)) / len(values)
        residual = abs(mean - average[month])
        item = regimes[regime]
        item["months"] += 1
        item["largest_average_residual"] = max(item["largest_average_residual"], residual)
        item["average_failures"] += residual > average_bound
        if month in month_end:
            last_label, last_value = max(by_month[month])
            end_residual = abs(last_value - month_end[month])
            item["largest_month_end_residual"] = max(item["largest_month_end_residual"], end_residual)
            item["month_end_failures"] += end_residual > _half_unit(month_end[month]) + _half_unit(last_value)
    return {"overlap_first_month": min(set(average) & set(by_month)), "last_complete_month_checked": max(
                m for m in set(average) & set(by_month) if m != last_month),
            "regimes": {name: {**stats, "largest_average_residual": str(stats["largest_average_residual"]),
                               "largest_month_end_residual": str(stats["largest_month_end_residual"])}
                        for name, stats in regimes.items() if stats["months"]},
            "months_outside_regime_windows": uncovered,
            "regime_boundaries": "analyst diagnostic partition, not source data",
            "numeric_bound_method": "monthly half-unit plus mean daily half-unit; month-end half-unit plus daily half-unit"}
