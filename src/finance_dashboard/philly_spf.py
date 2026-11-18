"""Philadelphia Fed Survey of Professional Forecasters: median inflation expectations (Inflation.xlsx).

The single sheet ``INFLATION`` has the columns YEAR, QUARTER, INFPGDP1YR,
INFCPI1YR and INFCPI10YR: the survey's median expected annual-average
inflation over the next 1 year (GDP price index, CPI) and next 10 years (CPI),
in percent. Each row is a survey round, so the values are real-time by
construction. ``#N/A`` cells are absent observations.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import math

from .bis import ProviderError

PHILLY_SPF_URL = ("https://www.philadelphiafed.org/-/media/frbp/assets/surveys-and-data/"
                  "survey-of-professional-forecasters/historical-data/inflation.xlsx")
PHILLY_SPF_SHEET = "INFLATION"
PHILLY_SPF_COLUMNS = ["YEAR", "QUARTER", "INFPGDP1YR", "INFCPI1YR", "INFCPI10YR"]
PHILLY_SPF_SERIES = {
    "expectations.us.spf_inflation_gdp_price_1y": "INFPGDP1YR",
    "expectations.us.spf_inflation_cpi_1y": "INFCPI1YR",
    "expectations.us.spf_inflation_cpi_10y": "INFCPI10YR",
}


def _whole(value, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value != int(value):
        raise ProviderError("Philadelphia Fed SPF year or quarter is not a whole number")
    number = int(value)
    if not low <= number <= high:
        raise ProviderError("Philadelphia Fed SPF year or quarter is out of range")
    return number


def parse_philly_spf_rows(rows: list[list], series_id: str, start: date | None = None) -> dict[date, Decimal]:
    column = PHILLY_SPF_SERIES.get(series_id)
    if column is None:
        raise ProviderError("Unregistered Philadelphia Fed SPF series")
    if not rows or [str(cell).strip() for cell in rows[0][:len(PHILLY_SPF_COLUMNS)]] != PHILLY_SPF_COLUMNS:
        raise ProviderError("Philadelphia Fed SPF columns changed")
    index = PHILLY_SPF_COLUMNS.index(column)
    values: dict[date, Decimal] = {}
    previous = None
    for row in rows[1:]:
        if not row or all(cell in ("", None) for cell in row):
            continue
        quarter_start = date(_whole(row[0], 1968, 2100), 3 * _whole(row[1], 1, 4) - 2, 1)
        if (previous is not None and quarter_start <= previous) or quarter_start > date.today():
            raise ProviderError("Philadelphia Fed SPF rounds are duplicated, unordered or in the future")
        previous = quarter_start
        cell = row[index] if index < len(row) else None
        if cell in ("#N/A", "", None):
            continue
        if isinstance(cell, bool) or not isinstance(cell, (int, float)) or not math.isfinite(cell):
            raise ProviderError("Philadelphia Fed SPF value is not a finite number")
        try:
            value = Decimal(repr(float(cell)))
        except InvalidOperation as exc:
            raise ProviderError("Philadelphia Fed SPF value is invalid") from exc
        if not -5 < value < 30:
            raise ProviderError("Philadelphia Fed SPF inflation expectation is implausible")
        if start is None or quarter_start >= start:
            values[quarter_start] = value
    if not values and start is None:
        raise ProviderError("Philadelphia Fed SPF column contains no observations")
    return values
