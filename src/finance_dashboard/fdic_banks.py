"""FDIC BankFind quarterly aggregates over all institutions reporting at each date.

Totals are FDIC-computed sums of institution-level Call Report financials in
thousands of US dollars. The reporting population changes every quarter (the
institution count falls from about 17,900 to about 4,300), so each aggregate is
the FDIC-insured industry at that date, not a fixed cohort; the count is kept
as its own series and a same-date asset/equity ratio shares one perimeter.
"""
from __future__ import annotations

from datetime import date
from calendar import monthrange
from decimal import Decimal, InvalidOperation
import re

from .bis import ProviderError

FDIC_FINANCIALS_URL = "https://api.fdic.gov/banks/financials"
FDIC_QUERY = {"agg_by": "REPDTE", "agg_sum_fields": "ASSET,EQ", "agg_limit": "1000", "limit": "1",
              "fields": "REPDTE", "agg_sort_by": "REPDTE", "agg_sort_order": "ASC"}
FDIC_SERIES = {
    "bank.us.fdic_total_assets": "sum_ASSET",
    "bank.us.fdic_total_equity": "sum_EQ",
    "bank.us.fdic_reporting_institutions": "count",
}


def parse_fdic_aggregates(payload: dict, series_id: str, start: date | None = None) -> dict[date, Decimal]:
    field = FDIC_SERIES.get(series_id)
    if field is None:
        raise ProviderError("Unregistered FDIC aggregate series")
    try:
        meta = payload["meta"]["parameters"]["aggsMetaData"]
        rows = payload["data"]
    except (KeyError, TypeError) as exc:
        raise ProviderError("Malformed FDIC aggregate response") from exc
    if (meta.get("by") != "REPDTE" or sorted(meta.get("sumFields", [])) != ["ASSET", "EQ"]
            or not isinstance(rows, list) or not rows or len(rows) >= int(FDIC_QUERY["agg_limit"])):
        raise ProviderError("FDIC aggregate request identity or completeness changed")
    values: dict[date, Decimal] = {}
    for row in rows:
        record = row["data"]
        label = record.get("REPDTE", "")
        match = re.fullmatch(r"(\d{4})(03|06|09|12)(30|31)", label)
        if not match:
            raise ProviderError("FDIC report date is not a calendar quarter end")
        year, month, reported_day = map(int, match.groups())
        if reported_day != monthrange(year, month)[1]:
            raise ProviderError("FDIC report date is not an actual quarter end")
        day = date(year, month - 2, 1)
        try:
            value = Decimal(str(record[field]))
        except (KeyError, InvalidOperation) as exc:
            raise ProviderError("FDIC aggregate value is missing or invalid") from exc
        if not value.is_finite() or value <= 0 or day in values:
            raise ProviderError("FDIC aggregate value is nonpositive or duplicated")
        if day > date.today():
            raise ProviderError("FDIC aggregate contains a future report date")
        if start is None or day >= start:
            values[day] = value
    if not values:
        raise ProviderError("FDIC aggregate has no observations in the requested period")
    return values
