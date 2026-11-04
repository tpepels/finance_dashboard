"""BIS original total credit (WS_TC 2.0) stocks and ratios, plus published trend/gap keys.

Credit stocks are national-currency amounts in billions (BIS UNIT_MULT 9);
credit/GDP ratios are percent of GDP with one published decimal. BIS does not
publish the underlying nominal GDP series for these ratios, so a ratio is never
re-derived here: the published ratio stays distinct from any reconstruction.
"""
from __future__ import annotations

from datetime import date, datetime
from calendar import monthrange
from decimal import Decimal, InvalidOperation
import re
from typing import Any

from .bis import ProviderError, _dimension_code

BIS_TC_ROOT = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_TC/2.0"
TC_DIMENSIONS = ("FREQ", "BORROWERS_CTY", "TC_BORROWERS", "TC_LENDERS", "VALUATION", "UNIT_TYPE", "TC_ADJUST")
COUNTRIES = {"us": ("US", "USD"), "jp": ("JP", "JPY"), "de": ("DE", "EUR"), "cn": ("CN", "CNY"), "pt": ("PT", "EUR")}
# concept -> (borrower sector, unit type, expected native unit measure, unit multiplier)
CONCEPTS = {
    "private_nonfinancial_stock_bis": ("P", "XDC", None, "9"),
    "private_nonfinancial_gdp_bis": ("P", "770", "367", "0"),
    "household_gdp_bis": ("H", "770", "367", "0"),
    "corporate_gdp_bis": ("N", "770", "367", "0"),
}
TC_SERIES = {
    f"credit.{label}.{concept}": (code, sector, unit_type, unit_measure or currency, multiplier)
    for label, (code, currency) in COUNTRIES.items()
    for concept, (sector, unit_type, unit_measure, multiplier) in CONCEPTS.items()
}


def tc_key(country: str, sector: str, unit_type: str) -> str:
    return f"Q.{country}.{sector}.A.M.{unit_type}.A"


def _selected(definitions: list[dict], indices: list) -> dict[str, str]:
    if len(definitions) != len(indices):
        raise ProviderError("BIS attribute structure is inconsistent")
    try:
        return {definition["id"]: definition["values"][index]["id"]
                for definition, index in zip(definitions, indices) if index is not None}
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ProviderError("BIS attribute index or metadata is invalid") from exc


def parse_bis_total_credit(payload: Any, series_id: str, start: date | None = None) -> tuple[dict[date, Decimal], datetime | None]:
    spec = TC_SERIES.get(series_id)
    if spec is None:
        raise ProviderError("Unregistered BIS total-credit series")
    country, sector, unit_type, unit_measure, multiplier = spec
    expected = dict(zip(TC_DIMENSIONS, tc_key(country, sector, unit_type).split(".")))
    try:
        block = payload["data"]
        structure = block.get("structure", block.get("structures"))
        if isinstance(structure, list):
            if len(structure) != 1:
                raise ProviderError("BIS total credit ambiguous structure")
            structure = structure[0]
        series_dimensions = structure["dimensions"]["series"]
        observation_dimensions = structure["dimensions"]["observation"]
        datasets = block["dataSets"]
        series_attributes = structure["attributes"]["series"]
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        raise ProviderError("Malformed BIS total-credit SDMX-JSON response") from exc
    if (tuple(d.get("id") for d in series_dimensions) != TC_DIMENSIONS
            or [d.get("id") for d in observation_dimensions] != ["TIME_PERIOD"] or len(datasets) != 1):
        raise ProviderError("BIS total-credit dimensions changed")
    values: dict[date, Decimal] = {}
    matched = 0
    for key, node in datasets[0].get("series", {}).items():
        if _dimension_code(series_dimensions, key) != expected:
            raise ProviderError("BIS total-credit country, sector, unit or adjustment mismatch")
        matched += 1
        native = _selected(series_attributes, node.get("attributes", []))
        if native.get("UNIT_MEASURE") != unit_measure or native.get("UNIT_MULT") != multiplier:
            raise ProviderError("BIS total-credit native unit or multiplier changed")
        for time_key, row in node.get("observations", {}).items():
            period = _dimension_code(observation_dimensions, time_key)["TIME_PERIOD"]
            match = re.fullmatch(r"(\d{4})-Q([1-4])", period)
            if not match:
                raise ProviderError("BIS total-credit reference period is not quarterly")
            year, quarter = int(match.group(1)), int(match.group(2))
            first_month, last_month = 1 + 3 * (quarter - 1), 3 * quarter
            day = date(year, first_month, 1)
            if not isinstance(row, (list, tuple)) or not row:
                raise ProviderError("BIS total-credit observation has no value field")
            raw = row[0]
            if raw is None or raw in ("", "NaN", "NA", "N/A"):
                continue
            if date(year, last_month, monthrange(year, last_month)[1]) > date.today():
                raise ProviderError("BIS total-credit quarter has not ended")
            try:
                value = Decimal(str(raw))
            except (InvalidOperation, ValueError) as exc:
                raise ProviderError("BIS total-credit observation is invalid") from exc
            if not value.is_finite() or value < 0 or day in values:
                raise ProviderError("BIS total-credit value is negative, nonfinite or duplicated")
            if start is None or day >= start:
                values[day] = value
    if matched != 1 or not values:
        raise ProviderError("BIS total credit has no observations for the requested series")
    prepared = payload.get("meta", {}).get("prepared")
    try:
        return dict(sorted(values.items())), (datetime.fromisoformat(prepared.replace("Z", "+00:00")) if prepared else None)
    except (ValueError, AttributeError) as exc:
        raise ProviderError("BIS total-credit preparation timestamp is invalid") from exc
