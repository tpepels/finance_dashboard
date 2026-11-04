"""Original OFR Financial Stress Index daily download (fsi.csv).

Values are the publisher's standardized index: zero is average stress, positive
is above-average stress. Category and region contributions are separately
published partitions of the same total, never added to unrelated indicators.
"""
from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal, InvalidOperation
import io

from .bis import ProviderError

OFR_FSI_URL = "https://www.financialresearch.gov/financial-stress-index/data/fsi.csv"
OFR_FSI_COLUMNS = ("OFR FSI", "Credit", "Equity valuation", "Safe assets", "Funding", "Volatility",
                   "United States", "Other advanced economies", "Emerging markets")
OFR_FSI_SERIES = {
    "stress.global.ofr_fsi": "OFR FSI",
    "stress.global.ofr_fsi.credit": "Credit",
    "stress.global.ofr_fsi.equity_valuation": "Equity valuation",
    "stress.global.ofr_fsi.safe_assets": "Safe assets",
    "stress.global.ofr_fsi.funding": "Funding",
    "stress.global.ofr_fsi.volatility": "Volatility",
    "stress.global.ofr_fsi.region_united_states": "United States",
    "stress.global.ofr_fsi.region_other_advanced": "Other advanced economies",
    "stress.global.ofr_fsi.region_emerging_markets": "Emerging markets",
}
# Each of the five categories and each of the three regions partitions the
# total; every number carries three published decimals.
CATEGORY_COLUMNS = OFR_FSI_COLUMNS[1:6]
REGION_COLUMNS = OFR_FSI_COLUMNS[6:]
PUBLISHED_DECIMALS = Decimal("0.001")


def parse_ofr_fsi(text: str, column: str, start: date | None = None) -> dict[date, Decimal]:
    if column not in OFR_FSI_COLUMNS:
        raise ProviderError("Unregistered OFR FSI column")
    reader = csv.reader(io.StringIO(text.lstrip("\ufeff")))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise ProviderError("OFR FSI download is empty") from exc
    if tuple(header) != ("Date", *OFR_FSI_COLUMNS):
        raise ProviderError("OFR FSI download columns changed")
    position = header.index(column)
    values: dict[date, Decimal] = {}
    for row in reader:
        if len(row) != len(header):
            raise ProviderError("OFR FSI row has an unexpected number of fields")
        try:
            day = date.fromisoformat(row[0])
        except ValueError as exc:
            raise ProviderError("OFR FSI observation date is invalid") from exc
        if day > date.today() or day in values:
            raise ProviderError("OFR FSI observation date is future-dated or duplicated")
        if row[position].strip() == "":
            continue
        try:
            value = Decimal(row[position])
        except InvalidOperation as exc:
            raise ProviderError("OFR FSI value is not numeric") from exc
        if not value.is_finite():
            raise ProviderError("OFR FSI value is not finite")
        if start is None or day >= start:
            values[day] = value
    if not values:
        raise ProviderError("OFR FSI has no observations in the requested period")
    return values


def audit_ofr_fsi_partitions(text: str) -> dict:
    """Count rows where categories or regions miss the published total by more than rounding.

    The bound is half a published decimal for every rounded component plus the
    rounded total, not a fitted threshold.
    """
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    rows = 0
    failures = {"categories": 0, "regions": 0}
    largest = {"categories": Decimal(0), "regions": Decimal(0)}
    for row in reader:
        rows += 1
        total = Decimal(row["OFR FSI"])
        for label, columns in (("categories", CATEGORY_COLUMNS), ("regions", REGION_COLUMNS)):
            residual = abs(sum((Decimal(row[column]) for column in columns), Decimal(0)) - total)
            largest[label] = max(largest[label], residual)
            if residual > (len(columns) + 1) * PUBLISHED_DECIMALS / 2:
                failures[label] += 1
    return {"rows": rows, "partition_failures": failures,
            "largest_absolute_residual": {key: str(value) for key, value in largest.items()},
            "numeric_bound_method": "half a published decimal per rounded component plus the rounded total"}
