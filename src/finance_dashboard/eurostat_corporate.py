"""Official Eurostat ESA-2010 EU27 annual corporate operating-surplus shares.

Shares are calculated in a *single geographic and currency universe*, directly
from reported gross operating surplus of the S11/S12 sectors and reported S1
GDP. Unlike a global listed-company earnings figure, this includes nonlisted
corporations and is limited to the EU27-2020 geographic aggregate.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

EUROSTAT_JSON_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/nasa_10_nf_tr"
EUROSTAT_KI_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/nasa_10_ki"
EU27 = "EU27_2020"


class EurostatMacroError(ValueError):
    pass


def parse_eurostat_annual_series(payload: Any, *,
                                dataset: str,
                                sector: str,
                                na_item: str,
                                unit: str,
                                direct: str | None = None,
                                start: date | None = None) -> dict[date, Decimal]:
    """Strictly decode a *fully filtered* Eurostat JSON-stat observation cube.

    No implicit selection of a different region, sector, accounting direction,
    unit, transaction or frequency. Missing GDP years remain unobserved.
    """
    if dataset not in ("nasa_10_nf_tr", "nasa_10_ki") or not isinstance(payload, dict):
        raise EurostatMacroError("Unrecognized Eurostat dataset or payload")
    dims = ["freq", "unit", "direct", "na_item", "sector", "geo", "time"] if dataset == "nasa_10_nf_tr" else ["freq", "unit", "na_item", "sector", "geo", "time"]
    if payload.get("id") != dims or payload.get("source") != "ESTAT" or payload.get("class") != "dataset":
        raise EurostatMacroError("Eurostat data source or dimensions mismatch")
    shape = payload.get("size")
    if not isinstance(shape, list) or len(shape) != len(dims) or shape[-1] < 1 or any(n != 1 for n in shape[:-1]):
        raise EurostatMacroError("Ambiguous Eurostat geographic/sector selection")
    dimensions = payload.get("dimension", {})
    required = {"freq": "A", "unit": unit, "na_item": na_item, "sector": sector, "geo": EU27}
    if direct is not None:
        required["direct"] = direct
    elif dataset == "nasa_10_nf_tr":
        raise EurostatMacroError("Eurostat accounting direction must be specified")
    for dimension, expected in required.items():
        category = dimensions.get(dimension, {}).get("category", {}).get("index", {})
        if category != {expected: 0}:
            raise EurostatMacroError(f"Eurostat {dimension} identity mismatch")
    times = dimensions.get("time", {}).get("category", {}).get("index")
    if not isinstance(times, dict) or len(times) != shape[-1]:
        raise EurostatMacroError("Missing or ambiguous Eurostat year index")
    if set(times.values()) != set(range(shape[-1])):
        raise EurostatMacroError("Invalid Eurostat observation indexing")
    raw_values = payload.get("value")
    if not isinstance(raw_values, dict):
        raise EurostatMacroError("Missing Eurostat observation values")
    out: dict[date, Decimal] = {}
    for raw_year, position in times.items():
        if not isinstance(raw_year, str) or len(raw_year) != 4 or not raw_year.isdigit():
            raise EurostatMacroError("Invalid annual Eurostat observation year")
        day = date(int(raw_year), 1, 1)
        if day.year > date.today().year or start and day < start:
            continue
        raw = raw_values.get(str(position))
        if raw is None:
            continue
        try:
            value = Decimal(str(raw))
        except (ValueError, InvalidOperation, TypeError) as exc:
            raise EurostatMacroError("Non-numeric Eurostat corporation/GDP observation") from exc
        if not value.is_finite() or value < 0:
            raise EurostatMacroError("Invalid negative or non-finite annual Eurostat flow")
        out[day] = value
    if not out:
        raise EurostatMacroError("No Eurostat annual values in requested window")
    if len(out) > 100:
        raise EurostatMacroError("Unexpected Eurostat annual sample length")
    return dict(sorted(out.items()))


def eu27_corporate_gross_surplus_gdp(
    nonfinancial: dict[date, Decimal],
    financial: dict[date, Decimal],
    nominal_gdp: dict[date, Decimal],
    *,
    start: date | None = None,
) -> dict[date, Decimal]:
    """100*(S11 B2A3G + S12 B2A3G)/(S1 B1GQ) in annual current EUR.

    For S11/S12 sectors, B2A3G denotes gross operating surplus (corporations,
    not household self-employment mixed income). No corporate value-added
    denominator is substituted for *whole EU GDP*.
    """
    common = sorted(set(nonfinancial) & set(financial) & set(nominal_gdp))
    result = {}
    for day in common:
        if start and day < start:
            continue
        amounts = (nonfinancial[day], financial[day], nominal_gdp[day])
        if not all(isinstance(v, Decimal) and v.is_finite() for v in amounts):
            raise EurostatMacroError("Invalid corporate/GDP input")
        if any(v < 0 for v in amounts[:2]) or nominal_gdp[day] <= 0:
            raise EurostatMacroError("Negative corporate surplus or nonpositive GDP")
        share = (amounts[0] + amounts[1]) * Decimal(100) / amounts[2]
        if share < 0 or share > Decimal(100):
            raise EurostatMacroError("EU corporation surplus exceeds economic output")
        result[day] = share
    if not result:
        raise EurostatMacroError("No common S11, S12 and EU27 GDP observations")
    return result
