"""Federal Reserve excess bond premium (Gilchrist and Zakrajšek 2012; Favara, Gilchrist, Lewis and Zakrajšek 2016).

The Board publishes one monthly CSV with the columns ``date`` (YYYY-MM-01),
``gz_spread`` and ``ebp`` (percentage points) and ``est_prob`` (the Board's
model probability of a recession in the next 12 months). Only the two credit
measures are registered; the model probability is a forecast, not data. The
Board re-estimates the decomposition, so every refresh is a full revision.
"""
from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal, InvalidOperation
import io
import re

from .bis import ProviderError

FED_EBP_URL = "https://www.federalreserve.gov/econres/notes/feds-notes/ebp_csv.csv"
FED_EBP_COLUMNS = ["date", "gz_spread", "ebp", "est_prob"]
FED_EBP_SERIES = {
    "credit.us.gz_spread": "gz_spread",
    "credit.us.excess_bond_premium": "ebp",
}


def parse_fed_ebp(text: str, series_id: str, start: date | None = None) -> dict[date, Decimal]:
    column = FED_EBP_SERIES.get(series_id)
    if column is None:
        raise ProviderError("Unregistered Federal Reserve EBP series")
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    if not rows or [cell.strip() for cell in rows[0]] != FED_EBP_COLUMNS:
        raise ProviderError("Federal Reserve EBP columns changed")
    index = FED_EBP_COLUMNS.index(column)
    values: dict[date, Decimal] = {}
    previous = None
    for row in rows[1:]:
        if not row or not any(cell.strip() for cell in row):
            continue
        if len(row) != len(FED_EBP_COLUMNS) or not re.fullmatch(r"\d{4}-\d{2}-01", row[0].strip()):
            raise ProviderError("Federal Reserve EBP row is malformed")
        day = date.fromisoformat(row[0].strip())
        if (previous is not None and day <= previous) or day > date.today():
            raise ProviderError("Federal Reserve EBP months are duplicated, unordered or in the future")
        previous = day
        raw = row[index].strip()
        if raw in ("", "NA", "NaN"):
            continue
        try:
            value = Decimal(raw)
        except InvalidOperation as exc:
            raise ProviderError("Federal Reserve EBP value is invalid") from exc
        if not value.is_finite() or abs(value) > 50:
            raise ProviderError("Federal Reserve EBP value is not plausible")
        if start is None or day >= start:
            values[day] = value
    if not values and start is None:
        raise ProviderError("Federal Reserve EBP column contains no observations")
    return values
