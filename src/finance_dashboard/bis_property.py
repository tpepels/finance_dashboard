"""BIS original residential and commercial property-price SDMX dataflows.

Selected residential prices are comparatively harmonized original *real*
2010=100 indexes; commercial sources are local property-market measures and
cannot be treated as one internationally comparable universe.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .bis import ProviderError, _dimension_code

BIS_SPP_ROOT = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_SPP/1.0"
BIS_CPP_ROOT = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CPP/1.0"

# Original SDMX key / source frequency / precise statistical interpretation.
PROPERTY_SOURCES: dict[str, tuple[str, str, str]] = {
    "property.us.real_residential.bis": ("SPP", "Q.US.R.628", "Q"),
    "property.de.real_residential.bis": ("SPP", "Q.DE.R.628", "Q"),
    "property.jp.real_residential.bis": ("SPP", "Q.JP.R.628", "Q"),
    "property.pt.real_residential.bis": ("SPP", "Q.PT.R.628", "Q"),
    "property.ea.real_residential.bis": ("SPP", "Q.XM.R.628", "Q"),
    "property.world.real_residential.bis": ("SPP", "Q.XW.R.628", "Q"),
    "property.us.commercial_all.bis": ("CPP", "Q.US.0.A.0.2.6.0", "Q"),
    "property.pt.commercial_all.bis": ("CPP", "A.PT.0.A.0.1.6.0", "A"),
}

DIMENSIONS = {
    "SPP": ("FREQ", "REF_AREA", "VALUE", "UNIT_MEASURE"),
    "CPP": ("FREQ", "REF_AREA", "COVERED_AREA", "RE_TYPE",
            "RE_VINTAGE", "COMPILING_ORG", "PRICED_UNIT", "ADJUST_CODED"),
}


def parse_bis_property(
    payload: Any, *, flow: str, original_key: str,
    start: date | None = None,
) -> tuple[dict[date, Decimal], datetime | None]:
    """Verify the exact original four/eight-dimensional series and native period."""
    expected = DIMENSIONS.get(flow)
    if expected is None or original_key not in {
        item[1] for item in PROPERTY_SOURCES.values() if item[0] == flow
    }:
        raise ProviderError("Unapproved original BIS property-price key")
    key_parts = original_key.split(".")
    if len(key_parts) != len(expected):
        raise ProviderError("BIS property-price source key has incorrect dimensions")
    match = dict(zip(expected, key_parts))
    try:
        block = payload["data"]
        structure = block.get("structure", block.get("structures"))
        if isinstance(structure, list):
            if len(structure) != 1:
                raise ProviderError("Ambiguous BIS property SDMX structure")
            structure = structure[0]
        series_dimensions = structure["dimensions"]["series"]
        obs_dimensions = structure["dimensions"]["observation"]
        datasets = block["dataSets"]
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ProviderError("Malformed BIS property-price SDMX response") from exc
    if (not isinstance(datasets, list) or not datasets
            or len(obs_dimensions) != 1
            or obs_dimensions[0].get("id") != "TIME_PERIOD"
            or tuple(x.get("id") for x in series_dimensions) != expected):
        raise ProviderError("Unexpected BIS property-price SDMX dimensions")
    result: dict[date, Decimal] = {}
    matched = 0
    for dataset in datasets:
        for series_key, series_node in dataset.get("series", {}).items():
            codes = _dimension_code(series_dimensions, series_key)
            if codes != match:
                raise ProviderError("BIS property source geography/measure mismatch")
            matched += 1
            if matched > 1:
                raise ProviderError("Multiple original BIS property series returned")
            for period_index, raw in series_node.get("observations", {}).items():
                period = _dimension_code(obs_dimensions, period_index)["TIME_PERIOD"]
                import re
                if key_parts[0] == "A":
                    if not re.fullmatch(r"\d{4}", period):
                        raise ProviderError("BIS annual property reference period invalid")
                    day = date(int(period), 1, 1)
                else:
                    if not re.fullmatch(r"\d{4}-?Q[1-4]", period):
                        raise ProviderError("BIS quarterly property reference period invalid")
                    day = date(int(period[:4]), 1 + 3 * (int(period[-1]) - 1), 1)
                try:
                    v = raw[0]
                    if v is None:
                        continue
                    value = Decimal(str(v))
                except (IndexError, TypeError, ValueError, InvalidOperation) as exc:
                    raise ProviderError("BIS property-price observation invalid") from exc
                if value.is_nan():
                    continue
                if not value.is_finite() or value <= 0:
                    raise ProviderError("BIS property price index nonpositive or infinite")
                if day > date.today() or start is not None and day < start:
                    continue
                if day in result:
                    raise ProviderError("BIS property duplicate observation period")
                result[day] = value
    if matched != 1 or not result:
        raise ProviderError("No BIS property observations for exact original series")
    prep = payload.get("meta", {}).get("prepared")
    try:
        prepared = datetime.fromisoformat(prep.replace("Z", "+00:00")) if prep else None
    except (ValueError, AttributeError, TypeError) as exc:
        raise ProviderError("BIS property response preparation time invalid") from exc
    return dict(sorted(result.items())), prepared
