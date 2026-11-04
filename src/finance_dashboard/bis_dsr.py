"""BIS original quarterly debt service ratios: rigorously identified SDMX-JSON.

Debt service is a share of the sector's income (percentage). BIS notes that
national changes/within-country deviations are more comparable than national
levels; do not construct a universally ranked cross-country burden score.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .bis import ProviderError, _dimension_code

BIS_DSR_ROOT = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_DSR/1.0"
# Every key below is an original BIS key Q.<country>.<borrowers>, not a
# derived or harmonized private-sector proxy.
DSR_SERIES: dict[str, tuple[str, str]] = {
    "debt_service.us.private.bis": ("US", "P"),
    "debt_service.us.households.bis": ("US", "H"),
    "debt_service.us.corporations.bis": ("US", "N"),
    "debt_service.jp.private.bis": ("JP", "P"),
    "debt_service.de.private.bis": ("DE", "P"),
    "debt_service.cn.private.bis": ("CN", "P"),
    "debt_service.pt.private.bis": ("PT", "P"),
    "debt_service.pt.households.bis": ("PT", "H"),
}
SECTOR_NAMES = {
    "P": "private non-financial sector",
    "H": "households and NPISHs",
    "N": "non-financial corporations",
}


def parse_bis_dsr(
    payload: Any, *, country: str, sector: str, start: date | None = None
) -> tuple[dict[date, Decimal], datetime | None]:
    """Accept exactly one original BIS DSR series by SDMX dimension codes.

    Preserve gaps (null, NaN). Reject wrong countries/sectors, nonquarterly
    series, duplicate dates, malformed structures and nonfinite observations.
    """
    if (country, sector) not in DSR_SERIES.values():
        raise ProviderError("Unregistered BIS DSR sector/country combination")
    try:
        block = payload["data"]
        structure = block.get("structure", block.get("structures"))
        if isinstance(structure, list):
            if len(structure) != 1:
                raise ProviderError("BIS DSR ambiguous structure")
            structure = structure[0]
        dims = structure["dimensions"]
        series_dimensions = dims["series"]
        observation_dimensions = dims["observation"]
        datasets = block["dataSets"]
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        raise ProviderError("Malformed BIS DSR SDMX-JSON response") from exc
    if (len(observation_dimensions) != 1
            or observation_dimensions[0].get("id") != "TIME_PERIOD"
            or not isinstance(datasets, list) or not datasets):
        raise ProviderError("BIS DSR requires quarterly TIME_PERIOD observations")
    if {d.get("id") for d in series_dimensions} != {
        "FREQ", "BORROWERS_CTY", "DSR_BORROWERS"
    } or len(series_dimensions) != 3:
        raise ProviderError("BIS DSR original dimensions have changed")
    observations: dict[date, Decimal] = {}
    matched = 0
    for dataset in datasets:
        for series_key, series_node in dataset.get("series", {}).items():
            codes = _dimension_code(series_dimensions, series_key)
            if codes != {"FREQ": "Q", "BORROWERS_CTY": country,
                         "DSR_BORROWERS": sector}:
                raise ProviderError("BIS DSR country, sector or frequency mismatch")
            matched += 1
            if matched != 1:
                raise ProviderError("BIS DSR ambiguous duplicate source series")
            for time_index, raw in series_node.get("observations", {}).items():
                period = _dimension_code(observation_dimensions, time_index)["TIME_PERIOD"]
                import re
                if not re.fullmatch(r"\d{4}-?Q[1-4]", period):
                    raise ProviderError("BIS DSR invalid quarterly reference period")
                year = int(period[:4])
                quarter = int(period[-1])
                day = date(year, 1 + (quarter - 1) * 3, 1)
                try:
                    observation = raw[0]
                    if observation is None:
                        continue
                    value = Decimal(str(observation))
                except (TypeError, ValueError, IndexError, InvalidOperation) as exc:
                    raise ProviderError("BIS DSR invalid observation value") from exc
                if value.is_nan():
                    continue
                if not value.is_finite() or value < 0:
                    raise ProviderError("BIS DSR nonfinite or negative percentage")
                if day > date.today() or (start is not None and day < start):
                    continue
                if day in observations:
                    raise ProviderError("BIS DSR duplicate reference quarter")
                observations[day] = value
    if matched != 1 or not observations:
        raise ProviderError("BIS DSR has no observations for the requested series")
    timestamp = payload.get("meta", {}).get("prepared")
    try:
        prepared = datetime.fromisoformat(timestamp.replace("Z", "+00:00")) if timestamp else None
    except (ValueError, TypeError, AttributeError) as exc:
        raise ProviderError("BIS DSR invalid response preparation timestamp") from exc
    return dict(sorted(observations.items())), prepared
