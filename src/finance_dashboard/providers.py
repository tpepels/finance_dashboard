"""Provider-neutral ingestion. Every adapter validates original source identifiers.

A mapped catalog series is fetchable; an unresolved definition must never be
silently replaced with an unrelated proxy. No browser-supplied URLs are fetched.
"""
from __future__ import annotations

import csv
import io
import os
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from .bis import BisPolicyClient, FetchedSeries, ProviderError, COUNTRIES
from .catalog import load_documents

FRED_ROOT = "https://api.stlouisfed.org/fred/series/observations"
FRED_CSV_ROOT = "https://fred.stlouisfed.org/graph/fredgraph.csv"
ECB_ROOT = "https://data-api.ecb.europa.eu/service/data"
WORLD_BANK_ROOT = "https://api.worldbank.org/v2"
IMF_MAPPER_ROOT = "https://www.imf.org/external/datamapper/api/v2"
PROVIDER_CODES = frozenset(("BIS", "FRED", "ECB", "WORLD_BANK", "IMF_DATAMAPPER"))


class SourceUnavailable(ProviderError):
    """Blocked by a missing key, mapping, terms or unavailable official data."""


def _value(raw: Any) -> Decimal | None:
    if raw is None or str(raw).strip() in ("", ".", "NA", "N/A", "null", "NaN"):
        return None
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ProviderError(f"Invalid source numeric value: {str(raw)[:60]!r}") from exc
    if value.is_nan():
        return None
    if not value.is_finite():
        raise ProviderError("Source returned an infinite numeric value")
    return value


def _date(raw: str, frequency: str) -> date:
    try:
        if frequency == "A":
            if not (len(raw) == 4 and raw.isdigit()):
                raise ValueError("not an annual period")
            return date(int(raw), 1, 1)
        if frequency == "M":
            return date.fromisoformat(raw + "-01") if len(raw) == 7 else date.fromisoformat(raw)
        return date.fromisoformat(raw)
    except (ValueError, TypeError) as exc:
        raise ProviderError(f"Invalid observation period: {raw!r}") from exc


def _put(output: dict[date, Decimal], day: date, value: Decimal | None):
    if value is None:
        return
    if day in output:
        if output[day] != value:
            raise ProviderError(f"Conflicting duplicate observation: {day}")
        raise ProviderError(f"Repeated observation: {day}")
    output[day] = value


def parse_fred_csv(csv_text: str, identifier: str, frequency: str) -> dict[date, Decimal]:
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    if not reader.fieldnames or identifier not in reader.fieldnames:
        raise ProviderError(f"Unexpected FRED CSV header: {reader.fieldnames}")
    time_column = "observation_date" if "observation_date" in reader.fieldnames else "DATE"
    if time_column not in reader.fieldnames:
        raise ProviderError("FRED CSV missing date column")
    output = {}
    for row in reader:
        _put(output, _date(row[time_column], frequency), _value(row[identifier]))
    if not output:
        raise ProviderError("FRED CSV contains no usable observations")
    return output


def parse_fred_json(payload: dict, frequency: str) -> dict[date, Decimal]:
    rows = payload.get("observations")
    if not isinstance(rows, list):
        raise ProviderError("FRED observations list missing")
    output = {}
    for row in rows:
        _put(output, _date(row["date"], frequency), _value(row.get("value")))
    if not output:
        raise ProviderError("FRED response contains no usable observations")
    return output


def parse_ecb_csv(csv_text: str, key: str, frequency: str) -> dict[date, Decimal]:
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    required = {"KEY", "TIME_PERIOD", "OBS_VALUE"}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise ProviderError(f"Unexpected ECB CSV columns: {reader.fieldnames}")
    output = {}
    for row in reader:
        if row["KEY"] != key:
            raise ProviderError(f"ECB returned a different series: {row['KEY']}")
        _put(output, _date(row["TIME_PERIOD"], frequency), _value(row["OBS_VALUE"]))
    if not output:
        raise ProviderError("ECB response contains no usable observations")
    return output


def parse_imf_mapper(payload: Any, region: str, indicator: str, start: date | None = None) -> dict[date, Decimal]:
    """Read exactly the published group and indicator; exclude forecast/current year."""
    if not isinstance(payload, dict):
        raise ProviderError("IMF DataMapper returned non-JSON data")
    values = payload.get("values", {}).get(indicator, {})
    if region not in values or not isinstance(values[region], dict):
        raise ProviderError(f"IMF DataMapper region or indicator missing: {region}/{indicator}")
    output: dict[date, Decimal] = {}
    for year, raw_value in values[region].items():
        day = _date(year, "A")
        # DataMapper WEO offers projections without a per-value status flag here.
        # Only previous calendar years are ingested as historical estimates.
        if day.year >= date.today().year or start and day < start:
            continue
        _put(output, day, _value(raw_value))
    if not output:
        raise ProviderError("IMF DataMapper has no historical observations for requested series")
    return output


def parse_world_bank(payload: Any, country: str, indicator: str, start: date | None = None):
    if not isinstance(payload, list) or len(payload) != 2:
        raise ProviderError("World Bank response is not a two-part JSON array")
    meta, observations = payload
    if not isinstance(meta, dict) or not isinstance(observations, list):
        raise ProviderError("World Bank response metadata/data malformed")
    if int(meta.get("pages", 0)) != 1:
        raise ProviderError("World Bank returned truncated paginated data")
    output: dict[date, Decimal] = {}
    for row in observations:
        actual_indicator = row.get("indicator", {}).get("id")
        actual_country = row.get("countryiso3code") or row.get("country", {}).get("id")
        if actual_indicator != indicator:
            raise ProviderError(f"World Bank indicator mismatch: {actual_indicator}")
        # World regions (e.g., EMU/WLD) may have an empty countryiso3code.
        if actual_country and actual_country.upper() != country:
            raise ProviderError(f"World Bank geography mismatch: {actual_country}")
        day = _date(row["date"], "A")
        if start and day < start:
            continue
        _put(output, day, _value(row.get("value")))
    if not output:
        raise ProviderError(f"World Bank {country}/{indicator} has no usable data")
    return output


class ProviderRouter:
    """One configured client shared across the run. Explicitly refuse unresolved datasets."""

    def __init__(self, client: httpx.Client | None = None, bis=None):
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(30.0),
            follow_redirects=False,
            headers={"User-Agent": "global-capital-monitor/0.2"},
        )
        self.owns_client = client is None
        self.bis = bis or BisPolicyClient(self.client, retries=1)
        self.definitions = {
            item["id"]: item for item in load_documents()[0]["series"]
        }

    def close(self):
        if self.owns_client:
            self.client.close()

    def supported_ids(self) -> list[str]:
        return sorted(sid for sid, item in self.definitions.items()
                      if item["status"] == "mapped" and item["provider"] in PROVIDER_CODES)

    def blocked(self) -> list[dict]:
        return [{
            "series_id": sid, "provider": item["provider"],
            "reason": "source_mapping_unresolved" if item["status"] != "mapped" else "adapter_unavailable",
            "notes": item["notes"],
        } for sid, item in self.definitions.items()
            if sid not in self.supported_ids()]

    def _get(self, url: str, **kwargs) -> httpx.Response:
        # Up to two attempts for transient upstream failures, no recursive retries.
        import time
        for attempt in range(2):
            try:
                response = self.client.get(url, **kwargs)
                if response.status_code in (429, 500, 502, 503, 504) and attempt == 0:
                    time.sleep(0.5)
                    continue
                response.raise_for_status()
                return response
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt == 1:
                    raise
                time.sleep(0.5)
        raise AssertionError("Unreachable")

    def fetch(self, series_id: str, start: date | None = None) -> FetchedSeries:
        item = self.definitions.get(series_id)
        if item is None:
            raise SourceUnavailable("Unknown catalog series")
        if item["status"] != "mapped":
            raise SourceUnavailable(f"Source mapping unavailable: {series_id}")
        provider, key = item["provider"], item["source_key"]
        if provider == "BIS":
            return self.bis.fetch(series_id, start)
        if provider == "FRED":
            identifier = key
            api_key = os.getenv("FRED_API_KEY")
            if api_key:
                params = {"series_id": identifier, "api_key": api_key, "file_type": "json"}
                if start:
                    params["observation_start"] = start.isoformat()
                response = self._get(FRED_ROOT, params=params)
                observations = parse_fred_json(response.json(), item["frequency"])
            elif os.getenv("FRED_PUBLIC_CSV_FALLBACK") == "1":
                # Explicit opt-in: public CSV can time out or rate-limit in CI.
                params = {"id": identifier}
                if start:
                    params["cosd"] = start.isoformat()
                response = self._get(FRED_CSV_ROOT, params=params)
                observations = parse_fred_csv(response.text, identifier, item["frequency"])
            else:
                raise SourceUnavailable("FRED_API_KEY required (optional public CSV fallback: FRED_PUBLIC_CSV_FALLBACK=1)")
            # Always report a non-secret source URI, even for authenticated requests.
            return FetchedSeries(series_id, f"https://fred.stlouisfed.org/series/{identifier}", None, observations)
        if provider == "ECB":
            if not key.startswith("FM."):
                raise SourceUnavailable(f"Unsupported ECB dataset: {key}")
            url = f"{ECB_ROOT}/FM/{key[3:]}"
            params = {"format": "csvdata"}
            if start:
                params["startPeriod"] = start.isoformat()
            response = self._get(url, params=params)
            observations = parse_ecb_csv(response.text, key, item["frequency"])
            return FetchedSeries(series_id, str(response.request.url), None, observations)
        if provider == "WORLD_BANK":
            country, identifier = key.split("/", 1)
            url = f"{WORLD_BANK_ROOT}/country/{country}/indicator/{identifier}"
            params = {"format": "json", "per_page": 150}
            if start:
                params["date"] = f"{start.year}:{date.today().year}"
            response = self._get(url, params=params)
            observations = parse_world_bank(response.json(), country, identifier, start)
            return FetchedSeries(series_id, str(response.request.url), None, observations)
        if provider == "IMF_DATAMAPPER":
            region, identifier = key.split("/", 1)
            url = f"{IMF_MAPPER_ROOT}/{identifier}/{region}"
            response = self._get(url)
            observations = parse_imf_mapper(response.json(), region, identifier, start)
            return FetchedSeries(series_id, str(response.request.url), None, observations)
        raise SourceUnavailable(f"No validated adapter for provider: {provider}")
