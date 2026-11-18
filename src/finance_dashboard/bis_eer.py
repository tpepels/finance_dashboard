"""BIS effective exchange rates (dataflow WS_EER): monthly real broad indices.

Key M.R.B.<area>: monthly, real (CPI-deflated), broad basket of 64 economies.
An index (2020 = 100) where a rise is an appreciation of the area's currency.
Gaps (null, NaN) stay absent. Real effective rates are revised when price
indices and trade weights are revised.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Any

from .bis import ProviderError, _dimension_code

BIS_EER_ROOT = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_EER/1.0"
EER_SERIES: dict[str, str] = {
    "fx.us.real_effective_rate.bis": "US",
    "fx.ea.real_effective_rate.bis": "XM",
    "fx.jp.real_effective_rate.bis": "JP",
    "fx.gb.real_effective_rate.bis": "GB",
    "fx.cn.real_effective_rate.bis": "CN",
    "fx.ch.real_effective_rate.bis": "CH",
}


def eer_key(area: str) -> str:
    return f"BIS,WS_EER,1.0/M.R.B.{area}"


def parse_bis_eer(payload: Any, *, area: str, start: date | None = None) -> tuple[dict[date, Decimal], datetime | None]:
    if area not in EER_SERIES.values():
        raise ProviderError("Unregistered BIS effective exchange rate area")
    try:
        block = payload["data"]
        structure = block.get("structure", block.get("structures"))
        if isinstance(structure, list):
            if len(structure) != 1:
                raise ProviderError("BIS EER ambiguous structure")
            structure = structure[0]
        series_dimensions = structure["dimensions"]["series"]
        observation_dimensions = structure["dimensions"]["observation"]
        datasets = block["dataSets"]
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        raise ProviderError("Malformed BIS EER SDMX-JSON response") from exc
    if [d.get("id") for d in series_dimensions] != ["FREQ", "EER_TYPE", "EER_BASKET", "REF_AREA"]:
        raise ProviderError("BIS EER dimensions have changed")
    if [d.get("id") for d in observation_dimensions] != ["TIME_PERIOD"] or not datasets:
        raise ProviderError("BIS EER requires monthly TIME_PERIOD observations")
    values: dict[date, Decimal] = {}
    matched = 0
    for dataset in datasets:
        for series_key, node in dataset.get("series", {}).items():
            if _dimension_code(series_dimensions, series_key) != {
                    "FREQ": "M", "EER_TYPE": "R", "EER_BASKET": "B", "REF_AREA": area}:
                raise ProviderError("BIS EER area, type, basket or frequency mismatch")
            matched += 1
            if matched != 1:
                raise ProviderError("BIS EER ambiguous duplicate series")
            for index, raw in node.get("observations", {}).items():
                period = _dimension_code(observation_dimensions, index)["TIME_PERIOD"]
                if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", period):
                    raise ProviderError("BIS EER period is not monthly")
                day = date(int(period[:4]), int(period[5:]), 1)
                try:
                    observation = raw[0]
                    if observation is None:
                        continue
                    value = Decimal(str(observation))
                except (TypeError, IndexError, InvalidOperation) as exc:
                    raise ProviderError("BIS EER observation is invalid") from exc
                if value.is_nan():
                    continue
                if not value.is_finite() or value <= 0:
                    raise ProviderError("BIS EER index must be positive and finite")
                if day > date.today() or (start is not None and day < start):
                    continue
                if day in values:
                    raise ProviderError("BIS EER duplicate month")
                values[day] = value
    if matched != 1 or not values:
        raise ProviderError("BIS EER has no observations for the requested area")
    stamp = payload.get("meta", {}).get("prepared")
    try:
        prepared = datetime.fromisoformat(stamp.replace("Z", "+00:00")) if stamp else None
    except (TypeError, ValueError, AttributeError) as exc:
        raise ProviderError("BIS EER preparation timestamp is invalid") from exc
    return dict(sorted(values.items())), prepared
