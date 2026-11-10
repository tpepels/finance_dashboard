"""Deutsche Bundesbank time-series database downloads (api.statistiken.bundesbank.de).

The 10-year par yield on listed Federal securities at month end
(BBSIS.M.I.ZAR...R10XX) is the series Swinkels names as the input of his
German hypothetical 10-year bond return; with his formula it reproduces all 603
of his published monthly returns, and the Bundesbank keeps publishing it.
Explicit "." values are absent observations, never zero.
"""
from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal, InvalidOperation
import io
import re

from .bis import ProviderError

BUNDESBANK_ROOT = "https://api.statistiken.bundesbank.de/rest/data"
BUNDESBANK_UNIT = "percent"
# series id -> (dataflow, full series key, native frequency)
BUNDESBANK_SERIES = {
    "bond.de.bund_10y_par_yield_month_end": ("BBSIS", "BBSIS.M.I.ZAR.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A", "M"),
}


def bundesbank_url(flow: str, key: str) -> str:
    return f"{BUNDESBANK_ROOT}/{flow}/{key[len(flow) + 1:]}"


def parse_bundesbank_csv(text: str, series_id: str, start: date | None = None) -> dict[date, Decimal]:
    spec = BUNDESBANK_SERIES.get(series_id)
    if spec is None:
        raise ProviderError("Unregistered Bundesbank time-series")
    _, key, frequency = spec
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    if not rows or len(rows[0]) < 2 or rows[0][1] != key:
        raise ProviderError("Bundesbank series key changed")
    unit = next((row[1] for row in rows if row and row[0] == "BBK_UNIT_ENG"), None)
    if unit != BUNDESBANK_UNIT:
        raise ProviderError("Bundesbank native unit changed")
    pattern = r"\d{4}-\d{2}" if frequency == "M" else r"\d{4}-\d{2}-\d{2}"
    values: dict[date, Decimal] = {}
    seen: set[date] = set()
    for row in rows:
        if not row or not re.fullmatch(pattern, row[0]):
            continue
        day = date(int(row[0][:4]), int(row[0][5:7]), 1 if frequency == "M" else int(row[0][8:10]))
        if day in seen or day > date.today():
            raise ProviderError("Bundesbank observation is duplicated or future-dated")
        seen.add(day)
        raw = row[1].strip() if len(row) > 1 else ""
        if raw in ("", "."):
            continue
        try:
            value = Decimal(raw)
        except InvalidOperation as exc:
            raise ProviderError("Bundesbank observation value is invalid") from exc
        if not value.is_finite():
            raise ProviderError("Bundesbank observation value is not finite")
        if start is None or day >= start:
            values[day] = value
    if not values:
        raise ProviderError("Bundesbank download has no usable observations in the requested period")
    return values
