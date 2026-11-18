"""AQR data-set workbooks (www.aqr.com): quality, low-beta and century-of-factor-premia returns.

Each workbook's first sheet holds monthly self-financing excess returns as
decimal ratios (0.0111 = 1.11%), one column per country/region or factor, with
an ``MM/DD/YYYY`` month-end date in the first column below a ``DATE``/``Date``
header row. AQR states that it reconstructs the full history at every update,
so every refresh is a full revision. Blank cells are absent observations,
never zero. The workbooks do not state a currency; the cited papers report USD.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import math
import re

from .bis import ProviderError

AQR_ROOT = "https://www.aqr.com/-/media/AQR/Documents/Insights/Data-Sets"
# workbook file -> (data sheet, phrase that must appear in the sheet's description)
AQR_WORKBOOKS = {
    "Quality-Minus-Junk-Factors-Monthly.xlsx": ("QMJ Factors", "Quality Minus Junk (QMJ) factors"),
    "Betting-Against-Beta-Equity-Factors-Monthly.xlsx": ("BAB Factors", "Betting Against Beta (BAB) factors"),
    "Century-of-Factor-Premia-Monthly.xlsx": ("Century of Factor Premia", "A Century of Evidence"),
}
# series id -> (workbook file, column header)
AQR_SERIES = {
    "returns.aqr.us.quality_qmj": ("Quality-Minus-Junk-Factors-Monthly.xlsx", "USA"),
    "returns.aqr.global.quality_qmj": ("Quality-Minus-Junk-Factors-Monthly.xlsx", "Global"),
    "returns.aqr.us.low_beta_bab": ("Betting-Against-Beta-Equity-Factors-Monthly.xlsx", "USA"),
    "returns.aqr.global.low_beta_bab": ("Betting-Against-Beta-Equity-Factors-Monthly.xlsx", "Global"),
    "returns.aqr.commodities.market": ("Century-of-Factor-Premia-Monthly.xlsx", "Commodities Market"),
    "returns.aqr.commodities.carry": ("Century-of-Factor-Premia-Monthly.xlsx", "Commodities Carry"),
    "returns.aqr.commodities.momentum": ("Century-of-Factor-Premia-Monthly.xlsx", "Commodities Momentum"),
    "returns.aqr.equity_indices.value": ("Century-of-Factor-Premia-Monthly.xlsx", "Equity indices Value"),
    "returns.aqr.equity_indices.momentum": ("Century-of-Factor-Premia-Monthly.xlsx", "Equity indices Momentum"),
    "returns.aqr.fixed_income.carry": ("Century-of-Factor-Premia-Monthly.xlsx", "Fixed income Carry"),
}
_DATE = re.compile(r"(0[1-9]|1[0-2])/([0-2][0-9]|3[01])/(\d{4})")


def aqr_source_key(series_id: str) -> str:
    workbook, column = AQR_SERIES[series_id]
    return f"{workbook}#{AQR_WORKBOOKS[workbook][0]}:{column}"


def aqr_url(workbook: str) -> str:
    return f"{AQR_ROOT}/{workbook}"


def _cell_text(value) -> str:
    return "" if value is None else str(value).strip()


def parse_aqr_rows(rows: list[list], series_id: str, start: date | None = None) -> dict[date, Decimal]:
    """Select one column of one AQR data sheet, already read as rows of cell values."""
    if series_id not in AQR_SERIES:
        raise ProviderError("Unregistered AQR data-set series")
    workbook, column_label = AQR_SERIES[series_id]
    _sheet, phrase = AQR_WORKBOOKS[workbook]
    if not any(phrase in _cell_text(row[0]) for row in rows[:12] if row):
        raise ProviderError("AQR workbook description does not identify the data set")
    if not any("self-financing excess returns" in _cell_text(row[0]) for row in rows[:12] if row):
        raise ProviderError("AQR workbook no longer states self-financing excess returns")
    headers = [index for index, row in enumerate(rows[:40]) if row and _cell_text(row[0]) in ("DATE", "Date")]
    if len(headers) != 1:
        raise ProviderError("AQR data header row missing or ambiguous")
    header = [_cell_text(cell) for cell in rows[headers[0]]]
    if header.count(column_label) != 1:
        raise ProviderError("AQR column missing or ambiguous")
    column = header.index(column_label)
    values: dict[date, Decimal] = {}
    previous = None
    for row in rows[headers[0] + 1:]:
        stamp = _cell_text(row[0]) if row else ""
        cell = row[column] if row and column < len(row) else None
        if not stamp:
            if _cell_text(cell):
                raise ProviderError("AQR value without a date")
            continue
        match = _DATE.fullmatch(stamp)
        if not match:
            raise ProviderError("AQR date is not MM/DD/YYYY")
        try:
            day = datetime.strptime(stamp, "%m/%d/%Y").date()
        except ValueError as exc:
            raise ProviderError("AQR date is invalid") from exc
        month = date(day.year, day.month, 1)
        if previous is not None and month <= previous:
            raise ProviderError("AQR months are duplicated or out of order")
        if month > date.today():
            raise ProviderError("AQR month is in the future")
        previous = month
        if not _cell_text(cell):
            continue
        if isinstance(cell, bool) or not isinstance(cell, (int, float)) or not math.isfinite(cell):
            raise ProviderError("AQR value is not a finite number")
        try:
            value = Decimal(repr(float(cell)))
        except InvalidOperation as exc:
            raise ProviderError("AQR value is invalid") from exc
        if abs(value) >= 1:
            raise ProviderError("AQR monthly decimal return is implausibly large")
        if start is None or month >= start:
            values[month] = value
    if not values and start is None:
        raise ProviderError("AQR column contains no observations")
    return values
