"""BIS SDMX-JSON 1.0 adapter. Reject ambiguous responses rather than guessing dimensions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import time
from typing import Any

import httpx

API_ROOT = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0"
ACCEPT = "application/vnd.sdmx.data+json;version=1.0.0"
COUNTRIES = {
    "policy_rate.us.bis": "US",
    "policy_rate.ea.bis": "XM",
    "policy_rate.jp.bis": "JP",
}


class ProviderError(ValueError):
    """Invalid/unavailable source data; safe to record without changing observations."""


@dataclass(frozen=True)
class FetchedSeries:
    series_id: str
    request_url: str
    prepared_at: datetime | None
    observations: dict[date, Decimal]


def _dimension_code(dimensions: list[dict[str, Any]], index_key: str) -> dict[str, str]:
    parts = index_key.split(":")
    if len(parts) != len(dimensions):
        raise ProviderError("SDMX dimension index count does not match structure")
    result: dict[str, str] = {}
    for dimension, part in zip(dimensions, parts):
        try:
            item = dimension["values"][int(part)]
            name = dimension["id"]
            code = item["id"]
        except (KeyError, ValueError, TypeError, IndexError) as exc:
            raise ProviderError("Invalid SDMX dimension index") from exc
        if name in result:
            raise ProviderError("Duplicate SDMX dimension")
        result[name] = code
    return result


def parse_bis_json(payload: dict[str, Any], series_id: str) -> tuple[dict[date, Decimal], datetime | None]:
    """Resolve time and country codes through SDMX structures, never positional assumptions."""
    if series_id not in COUNTRIES:
        raise ProviderError("Unsupported BIS policy-rate series")
    try:
        data = payload["data"]
        datasets = data.get("dataSets", data.get("datasets"))
        structures = data.get("structures", data.get("structure", payload.get("structure")))
        if isinstance(structures, list):
            structure = structures[0]
        else:
            structure = structures
        dims = structure["dimensions"]
        series_dimensions = dims["series"]
        observation_dimensions = dims["observation"]
        if len(observation_dimensions) != 1 or observation_dimensions[0]["id"] != "TIME_PERIOD":
            raise ProviderError("Expected exactly one TIME_PERIOD observation dimension")
        if not isinstance(datasets, list) or not datasets:
            raise ProviderError("BIS returned no datasets")
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ProviderError("Malformed BIS SDMX-JSON structure") from exc
    output: dict[date, Decimal] = {}
    matched = 0
    for dataset in datasets:
        for key, node in dataset.get("series", {}).items():
            codes = _dimension_code(series_dimensions, key)
            if codes.get("FREQ") != "D" or codes.get("REF_AREA") != COUNTRIES[series_id]:
                raise ProviderError(f"BIS returned an unexpected series: {codes}")
            matched += 1
            if matched > 1:
                raise ProviderError("BIS returned multiple matching series")
            for observation_index, raw in node.get("observations", {}).items():
                period = _dimension_code(observation_dimensions, observation_index)["TIME_PERIOD"]
                try:
                    day = date.fromisoformat(period)
                    value = Decimal(str(raw[0]))
                except (TypeError, IndexError, ValueError, InvalidOperation) as exc:
                    raise ProviderError(f"Invalid daily observation: {period!r}") from exc
                if not value.is_finite():
                    raise ProviderError("Non-finite BIS observation")
                if day in output:
                    raise ProviderError(f"Duplicate BIS observation: {day}")
                output[day] = value
    if matched != 1 or not output:
        raise ProviderError("No observations for requested BIS series")
    timestamp = payload.get("meta", {}).get("prepared")
    try:
        prepared = datetime.fromisoformat(timestamp.replace("Z", "+00:00")) if timestamp else None
    except (ValueError, TypeError, AttributeError) as exc:
        raise ProviderError("Invalid BIS response preparation timestamp") from exc
    return dict(sorted(output.items())), prepared


class BisPolicyClient:
    """Small bounded, injectable HTTP client; no provider calls in the API process."""

    def __init__(self, client: httpx.Client | None = None, retries: int = 2):
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(30.0), follow_redirects=False,
            headers={"User-Agent": "global-capital-monitor/0.2"}
        )
        self.owns_client = client is None
        self.retries = retries

    def close(self) -> None:
        if self.owns_client:
            self.client.close()

    def fetch(self, series_id: str, start: date | None = None) -> FetchedSeries:
        country = COUNTRIES.get(series_id)
        if country is None:
            raise ProviderError(f"Unsupported BIS series: {series_id}")
        url = f"{API_ROOT}/D.{country}"
        params = {"startPeriod": start.isoformat()} if start else {}
        response = None
        for attempt in range(self.retries + 1):
            try:
                response = self.client.get(url, params=params, headers={"Accept": ACCEPT})
                if response.status_code in (429, 500, 502, 503, 504) and attempt < self.retries:
                    time.sleep(min(2 ** attempt, 3))
                    continue
                response.raise_for_status()
                break
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt == self.retries:
                    raise
                time.sleep(min(2 ** attempt, 3))
        assert response is not None
        if "json" not in response.headers.get("content-type", "").lower():
            raise ProviderError("BIS returned an unexpected content type")
        try:
            raw = response.json()
        except ValueError as exc:
            raise ProviderError("BIS returned invalid JSON") from exc
        values, prepared = parse_bis_json(raw, series_id)
        return FetchedSeries(series_id, str(response.request.url), prepared, values)
