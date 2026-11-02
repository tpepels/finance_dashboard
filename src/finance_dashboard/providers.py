"""Provider-neutral ingestion. Every adapter validates original source identifiers.

A mapped catalog series is fetchable; an unresolved definition must never be
silently replaced with an unrelated proxy. No browser-supplied URLs are fetched.
"""
from __future__ import annotations

import csv
import io
import os
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from .bis import BisPolicyClient, FetchedSeries, ProviderError, COUNTRIES, _dimension_code, ACCEPT
from .catalog import load_documents
from .wisesheets import load_sec_profit_snapshot, snapshot_series
from .world_credit import (BIS_COMPOSITE_URL, WORLD_GDP_URL,
    parse_bis_national_credit_gaps, parse_wdi_gdp_all, country_weighted_bis_gap)
from .oecd_corporate import (
    OECD_DATA_URL, OECD_WDI_URL, OECD_WDI_LOCAL_GDP_URL, oecd_annual_data_key,
    parse_oecd_annual_sector_csv, parse_oecd_gdp_weights,
    compute_oecd_corporate_surplus,
)
from .concentration_snapshots import load_msci_concentration_snapshots
from .eurostat_corporate import (
    EUROSTAT_JSON_URL, EUROSTAT_KI_URL, EU27,
    parse_eurostat_annual_series, eu27_corporate_gross_surplus_gdp,
)
from .macro_aggregates import (
    SIBLIS_WORLD_PE_URL, parse_siblis_world_pe, aggregate_earnings_yield,
    world_listed_market_cap_gdp,
)
from .remaining_sources import (
    BEA_Q_URL, MSCI_LEVELS_URL, MSCI_ACWI_INDEX_CODE,
    parse_bea_q1, parse_msci_acwi, gold_acwi_rolling_correlation,
    global_output_to_labour_income_ratio,
)

FRED_ROOT = "https://api.stlouisfed.org/fred/series/observations"
FRED_TABLE_ROOT = "https://fred.stlouisfed.org/data"
FRED_CSV_ROOT = "https://fred.stlouisfed.org/graph/fredgraph.csv"
ECB_ROOT = "https://data-api.ecb.europa.eu/service/data"
WORLD_BANK_ROOT = "https://api.worldbank.org/v2"
SHILLER_HOME = "https://shillerdata.com/"
UN_SDG_ROOT = "https://unstats.un.org/SDGAPI/v1/sdg/Series"
PINK_SHEET_URL = "https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx"
IMF_MAPPER_ROOT = "https://www.imf.org/external/datamapper/api/v2"
BIS_CREDIT_GAP_ROOT = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CREDIT_GAP/1.0"
SIBLIS_FREE_ROOT = "https://siblisresearch.supabase.co/functions/v1/free-data-api/v1"
CORGANO_GOLD_LATEST = "https://goldprice.corgano.com/api/v1/latest"
PROVIDER_CODES = frozenset(("BIS", "FRED", "ECB", "WORLD_BANK", "IMF_DATAMAPPER", "SHILLER", "UN_SDG", "WORLD_BANK_PINK_SHEET", "SIBLIS_FREE", "BIS_CREDIT_GAP", "CORGANO_SPOT", "BEA_Q", "MSCI_NETR", "GOLD_MSCI_CORR", "ILO_LABOUR_PRODUCTIVITY_RATIO", "BIS_WORLD_WEIGHTED", "WISESHEETS_SNAPSHOT", "WORLD_LISTED_CAP_SHARE", "SIBLIS_WORLD_PE", "SIBLIS_WORLD_EARNINGS_YIELD", "MSCI_PUBLISHED_TOP10", "EUROSTAT_CORPORATE_GDP", "EUROSTAT_NFC_PROFIT_GVA", "OECD_CORPORATE_GDPWEIGHTED"))


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
        if frequency == "Q":
            if len(raw) == 10:
                quarter_start = date.fromisoformat(raw)
                if quarter_start.day != 1 or quarter_start.month not in (1, 4, 7, 10):
                    raise ValueError("not a quarterly period start")
                return quarter_start
            import re
            match = re.fullmatch(r"(\d{4})-?Q([1-4])", raw)
            if not match:
                raise ValueError("not a quarter")
            return date(int(match.group(1)), 1 + (int(match.group(2)) - 1) * 3, 1)
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


class FredTableParser(HTMLParser):
    """Extract actual DATE/VALUE rows from the public FRED observations HTML."""
    def __init__(self):
        super().__init__()
        self.tables = []
        self.table = None
        self.row = None
        self.cell = None
        self.extra = []
        self.in_extra = False

    def handle_starttag(self, tag, attrs):
        if tag == "div" and dict(attrs).get("id") == "extra-rows":
            self.in_extra = True
        if tag == "table":
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.in_extra:
            self.extra.append(data)
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag == "div" and self.in_extra:
            self.in_extra = False
        if tag in ("td","th") and self.cell is not None and self.row is not None:
            self.row.append("".join(self.cell).strip())
            self.cell = None
        elif tag == "tr" and self.table is not None and self.row is not None:
            self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            self.tables.append(self.table)
            self.table = None


def parse_fred_table_html(html: str, identifier: str, frequency: str) -> dict[date, Decimal]:
    """Fails closed if FRED public table layout changes; never guess chart values."""
    if identifier not in html or "Series ID" not in html:
        raise ProviderError("FRED table page does not identify the expected series")
    parser = FredTableParser()
    parser.feed(html)
    valid_tables = []
    for table in parser.tables:
        header_positions = [i for i,row in enumerate(table)
                            if len(row) >= 2 and row[0].upper() == "DATE"
                            and row[1].upper() == "VALUE"]
        if len(header_positions) == 1:
            valid_tables.append(table[header_positions[0]+1:])
    if len(valid_tables) != 1:
        raise ProviderError("FRED public DATE/VALUE table missing or ambiguous")
    result: dict[date, Decimal] = {}
    for row in valid_tables[0]:
        if len(row) != 2:
            raise ProviderError("FRED DATE/VALUE table has an unexpected row")
        _put(result, _date(row[0], frequency), _value(row[1]))
    # FRED HTML renders its first 1,000 observations as table rows.
    # The rest are held as records #YYYY-MM-DD|VALUE in #extra-rows.
    # Parse every record, or fail if a record is malformed; otherwise
    # recent observations silently disappear for long histories.
    extra = "".join(parser.extra)
    if extra.strip():
        for chunk in extra.split("#"):
            if not chunk.strip():
                continue
            fields = chunk.strip().split("|")
            if len(fields) != 2:
                raise ProviderError("Malformed extended FRED observation row")
            _put(result, _date(fields[0].strip(), frequency),
                 _value(fields[1].strip()))
    if not result:
        raise ProviderError("FRED public table contains no usable observations")
    return result


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


def parse_pink_sheet_gold(rows: list[list], start: date | None = None) -> dict[date, Decimal]:
    """World Bank Pink Sheet 'Monthly Prices', nominal Gold ($/troy oz) since 1960."""
    import re
    headers = []
    for index, row in enumerate(rows[:15]):
        columns = [j for j, cell in enumerate(row) if str(cell).strip() == "Gold"]
        if columns:
            headers.append((index, columns[0]))
    if len(headers) != 1:
        raise ProviderError("World Bank workbook must have one Gold column")
    header_row, col = headers[0]
    if header_row + 1 >= len(rows) or col >= len(rows[header_row+1]) or "troy oz" not in str(rows[header_row+1][col]).lower():
        raise ProviderError("World Bank Gold column is not priced per troy ounce")
    output = {}
    for row in rows[header_row+2:]:
        if not row:
            continue
        raw = str(row[0]).strip()
        if not re.fullmatch(r"\d{4}M(0[1-9]|1[0-2])", raw):
            continue
        day = date(int(raw[:4]), int(raw[-2:]), 1)
        if day > date.today() or start and day < start:
            continue
        if col >= len(row):
            continue
        _put(output, day, _value(row[col]))
    if not output:
        raise ProviderError("World Bank Pink Sheet has no usable gold-price months")
    return output


def parse_corgano_gold(payload: Any, start: date | None = None) -> dict[date, Decimal]:
    """Snapshot the current published spot *quote*, not futures-derived daily history."""
    if not isinstance(payload, dict):
        raise ProviderError("Gold spot response malformed")
    row, meta = payload.get("data"), payload.get("meta")
    if not isinstance(row, dict) or not isinstance(meta, dict):
        raise ProviderError("Gold spot price or metadata unavailable")
    if str(row.get("metal", "")).lower() != "gold" or str(row.get("symbol", "")).upper() not in ("XAU", "XAUUSD"):
        raise ProviderError("Gold spot identity mismatch")
    source = str(meta.get("source", "")).lower()
    if not source or any(x in source for x in ("futures", "comex", "gc=f")):
        raise ProviderError("Gold provider is missing spot provenance or substituted a futures price")
    unit = str(meta.get("unit", "")).strip().lower()
    if "troy ounce" not in unit and "troy oz" not in unit:
        raise ProviderError("Gold price must be quoted per troy ounce")
    try:
        at = datetime.fromisoformat(str(row["as_of"]).replace("Z","+00:00"))
    except (KeyError, ValueError, TypeError) as exc:
        raise ProviderError("Gold spot quote lacks valid timestamp") from exc
    if at.tzinfo is None:
        raise ProviderError("Gold spot quote must carry its timezone")
    from datetime import timezone, timedelta
    if at > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ProviderError("Gold spot quote future-dated")
    day = at.date()
    if start and day < start:
        raise ProviderError("Gold spot quote is older than requested start period")
    usd_prices = row.get("price_usd")
    if not isinstance(usd_prices, dict) or "per_oz" not in usd_prices:
        raise ProviderError("Gold USD quote must contain price_usd.per_oz")
    value = _value(usd_prices["per_oz"])
    if value is None or value <= 0:
        raise ProviderError("Invalid current gold spot price")
    return {day:value}


def parse_un_sdg(payload: Any, series_code: str, area_code: str,
                 start: date | None = None) -> dict[date, Decimal]:
    """UNSD official ILO-custodied global labour share; only unbroken annual global slice."""
    if not isinstance(payload, dict):
        raise ProviderError("UN SDG response malformed")
    if payload.get("series") != series_code or str(payload.get("geoAreaCode")) != area_code:
        raise ProviderError("UN SDG returned a different series or geography")
    rows = payload.get("dimensions")
    if not isinstance(rows, list):
        raise ProviderError("UN SDG missing observation dimensions")
    out: dict[date, Decimal] = {}
    for row in rows:
        expected_age = "15+" if series_code == "SL_EMP_PCAP" else "ALLAGE"
        if row.get("Reporting Type") != "G" or row.get("Age") != expected_age:
            continue
        day = _date(str(row.get("timePeriodStart")), "A")
        if day.year > date.today().year or start and day < start:
            continue
        _put(out, day, _value(row.get("value")))
    if not out:
        raise ProviderError("UN SDG no usable world labour share observations")
    return out


def parse_bis_credit_gap(payload: Any, country: str,
                         start: date | None = None) -> tuple[dict[date, Decimal], datetime | None]:
    """Select *gap* (CG_DTYPE=C), never actual ratio A or HP trend B.

    BIS series: Q.{country}.P.A.C (private nonfinancial borrowers, all lenders,
    actual minus one-sided HP trend). Units: percentage points of GDP.
    """
    try:
        data = payload["data"]
        structure = data["structure"]
        sdims = structure["dimensions"]["series"]
        odims = structure["dimensions"]["observation"]
        datasets = data["dataSets"]
    except (KeyError, TypeError) as exc:
        raise ProviderError("Malformed BIS credit gap SDMX response") from exc
    if len(odims) != 1 or odims[0].get("id") != "TIME_PERIOD":
        raise ProviderError("Expected quarterly TIME_PERIOD observation dimension")
    values: dict[date, Decimal] = {}
    matched = 0
    for dataset in datasets:
        for series_key, series_node in dataset.get("series", {}).items():
            labels = _dimension_code(sdims, series_key)
            if labels.get("FREQ") != "Q" or labels.get("BORROWERS_CTY") != country:
                raise ProviderError("Unexpected BIS credit gap frequency or geography")
            if labels.get("TC_BORROWERS") != "P" or labels.get("TC_LENDERS") != "A":
                raise ProviderError("Unexpected BIS credit borrowers or lenders")
            if labels.get("CG_DTYPE") != "C":
                continue
            matched += 1
            if matched > 1:
                raise ProviderError("Multiple BIS credit-gap series matched")
            for index, row in series_node.get("observations", {}).items():
                label = _dimension_code(odims, index)["TIME_PERIOD"]
                day = _date(label, "Q")
                if start and day < start:
                    continue
                if day > date.today():
                    continue
                _put(values, day, _value(row[0]))
    if matched != 1 or not values:
        raise ProviderError("No actual-minus-trend credit gaps in BIS result")
    prepared_raw = payload.get("meta", {}).get("prepared")
    try:
        prepared = datetime.fromisoformat(prepared_raw.replace("Z", "+00:00")) if prepared_raw else None
    except (ValueError, TypeError, AttributeError) as exc:
        raise ProviderError("Invalid BIS credit gap preparation timestamp") from exc
    return dict(sorted(values.items())), prepared


def parse_siblis_cape(payload: Any, ticker: str, start: date | None = None) -> dict[date, Decimal]:
    """Preserve exact sparse month-end snapshots; not interpolated monthly history.

    Siblis free API is proprietary and its returned observations must not be
    redistributed via a public/static site without a separate licence.
    """
    if not isinstance(payload, dict) or payload.get("ticker") != ticker or payload.get("ratio") != "cape":
        raise ProviderError("Siblis CAPE identity mismatch")
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ProviderError("Siblis response lacks data array")
    output = {}
    for row in rows:
        day = _date(row.get("trading_day (EOD)"), "M")
        if day > date.today() or (start and day < start):
            continue
        value = _value(row.get("value"))
        if value is not None and value <= 0:
            raise ProviderError("Non-positive CAPE is not a meaningful valuation ratio")
        _put(output, day, value)
    if not output:
        raise ProviderError("No historical Siblis CAPE snapshots in requested window")
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


class ShillerDownloadLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        url = dict(attrs).get("href", "")
        if urlparse(url).path.lower().endswith("/ie_data.xls"):
            self.links.append(url)


def parse_shiller_sheet(sheet) -> dict[date, Decimal]:
    """Shiller workbook has prose above the Date/CAPE header and Excel year.month dates."""
    header_row = None
    date_col = cape_col = None
    for row in range(min(60, sheet.nrows)):
        cells = [str(sheet.cell_value(row, col)).strip().upper() for col in range(sheet.ncols)]
        if "DATE" in cells and "CAPE" in cells:
            header_row = row
            date_col, cape_col = cells.index("DATE"), cells.index("CAPE")
            break
    if header_row is None:
        raise ProviderError("Shiller workbook does not contain recognizable DATE/CAPE columns")
    output = {}
    for row in range(header_row + 1, sheet.nrows):
        raw_date = sheet.cell_value(row, date_col)
        try:
            num = Decimal(str(raw_date))
            year = int(num)
            month = int((num - year) * 100 + Decimal("0.5"))
            if year < 1871 or month < 1 or month > 12:
                continue
            day = date(year, month, 1)
        except (TypeError, ValueError, InvalidOperation):
            continue
        _put(output, day, _value(sheet.cell_value(row, cape_col)))
    if not output:
        raise ProviderError("Shiller workbook contains no CAPE observations")
    return output


class ProviderRouter:
    """One configured client shared across the run. Explicitly refuse unresolved datasets."""

    def __init__(self, client: httpx.Client | None = None, bis=None):
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(30.0),
            follow_redirects=False,
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
                if response.status_code >= 400:
                    # Avoid embedding FRED API keys or signed URLs in errors/logs.
                    raise SourceUnavailable(f"Provider HTTP {response.status_code} ({response.request.url.host})")
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
                # Public FRED DATE/VALUE table. No API key; exact series identity,
                # unit/frequency and row structure are validated before ingestion.
                # FRED and underlying data rights still govern redistribution.
                response = self._get(f"{FRED_TABLE_ROOT}/{identifier}")
                rows = parse_fred_table_html(response.text, identifier, item["frequency"])
                observations = {day: val for day, val in rows.items()
                                if start is None or day >= start}
                if not observations:
                    raise ProviderError("FRED table has no observations in requested window")
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
        if provider == "WORLD_LISTED_CAP_SHARE":
            if key != "WLD/CM.MKT.LCAP.CD:WLD/NY.GDP.MKTP.CD":
                raise SourceUnavailable("Unapproved world-listed capitalization formula")
            cap_url = f"{WORLD_BANK_ROOT}/country/WLD/indicator/CM.MKT.LCAP.CD"
            gdp_url = f"{WORLD_BANK_ROOT}/country/WLD/indicator/NY.GDP.MKTP.CD"
            params = {"format": "json", "per_page": 150}
            if start:
                params["date"] = f"{start.year}:{date.today().year}"
            cap_response = self._get(cap_url, params=params)
            gdp_response = self._get(gdp_url, params=params)
            cap = parse_world_bank(cap_response.json(), "WLD", "CM.MKT.LCAP.CD", start)
            gdp = parse_world_bank(gdp_response.json(), "WLD", "NY.GDP.MKTP.CD", start)
            observations = world_listed_market_cap_gdp(cap, gdp, start=start)
            return FetchedSeries(series_id, str(cap_response.request.url) + " + " +
                                 str(gdp_response.request.url), None, observations)
        if provider in ("SIBLIS_WORLD_PE", "SIBLIS_WORLD_EARNINGS_YIELD"):
            if key != "GLOBAL/PT12M":
                raise SourceUnavailable("Unapproved Siblis global valuation source key")
            response = self._get(SIBLIS_WORLD_PE_URL)
            observations = parse_siblis_world_pe(response.text, start=start)
            if provider == "SIBLIS_WORLD_EARNINGS_YIELD":
                observations = aggregate_earnings_yield(observations)
            return FetchedSeries(series_id, SIBLIS_WORLD_PE_URL, None, observations)
        if provider == "MSCI_PUBLISHED_TOP10":
            if key != "892400/TOP10/PUBLISHED_SPARSE_SNAPSHOTS":
                raise SourceUnavailable("Wrong index, statistic or historical method")
            values = load_msci_concentration_snapshots(start=start)
            return FetchedSeries(series_id,
                "https://www.msci.com/indexes/index/892400/msci-acwi-index",
                None, values)
        if provider == "OECD_CORPORATE_GDPWEIGHTED":
            lookup = {
                "RATIO/OECD38_S11_S12_B2G_GDP_WDIWEIGHT": 0,
                "COVERAGE/OECD38_S11_S12_B2G_GDP_WDIWEIGHT": 1,
                "COUNT/OECD38_S11_S12_B2G_GDP_WDIWEIGHT": 2,
            }
            if key not in lookup:
                raise SourceUnavailable("Unapproved OECD composite or coverage source key")
            first_year = max(1990, start.year) if start else 1990
            oecd_response = self._get(
                f"{OECD_DATA_URL}/{oecd_annual_data_key()}",
                params={"format": "csvfile", "startPeriod": str(first_year)},
                headers={"Accept": "*/*"})
            sectors = parse_oecd_annual_sector_csv(oecd_response.text)
            wdi_response = self._get(
                OECD_WDI_URL,
                params={"format": "json", "per_page": 20000,
                        "date": f"{first_year}:{date.today().year}"})
            nominal_usd = parse_oecd_gdp_weights(wdi_response.json())
            local_response = self._get(
                OECD_WDI_LOCAL_GDP_URL,
                params={"format":"json", "per_page":20000,
                        "date": f"{first_year}:{date.today().year}"})
            nominal_local = parse_oecd_gdp_weights(
                local_response.json(), indicator="NY.GDP.MKTP.CN")
            sets = compute_oecd_corporate_surplus(
                sectors, nominal_usd, nominal_gdp_lcu=nominal_local, start=start)
            return FetchedSeries(
                series_id, str(oecd_response.request.url) + " + " +
                str(wdi_response.request.url) + " + " +
                str(local_response.request.url), None, sets[lookup[key]])
        if provider == "EUROSTAT_CORPORATE_GDP":
            if key != "nasa_10_nf_tr/EU27_2020/S11+S12_B2A3G/S1_B1GQ":
                raise SourceUnavailable("Invalid Eurostat corporation GDP methodology")
            sources = {}
            source_urls = []
            for sector, na_item in (("S11", "B2A3G"), ("S12", "B2A3G"), ("S1", "B1GQ")):
                params = {"freq": "A", "unit": "CP_MEUR", "direct": "RECV",
                          "sector": sector, "na_item": na_item, "geo": EU27}
                if start:
                    params["sinceTimePeriod"] = str(start.year)
                result = self._get(EUROSTAT_JSON_URL, params=params)
                sources[sector] = parse_eurostat_annual_series(
                    result.json(), dataset="nasa_10_nf_tr", sector=sector,
                    na_item=na_item, unit="CP_MEUR", direct="RECV", start=start)
                source_urls.append(str(result.request.url))
            values = eu27_corporate_gross_surplus_gdp(
                sources["S11"], sources["S12"], sources["S1"], start=start)
            return FetchedSeries(series_id, " + ".join(source_urls), None, values)
        if provider == "EUROSTAT_NFC_PROFIT_GVA":
            if key != "nasa_10_ki/EU27_2020/S11/B2G_B3G_RAT_S11":
                raise SourceUnavailable("Invalid Eurostat NFC gross profit share source key")
            params = {"freq": "A", "unit": "PC", "sector": "S11",
                      "geo": EU27, "na_item": "B2G_B3G_RAT_S11"}
            if start:
                params["sinceTimePeriod"] = str(start.year)
            response = self._get(EUROSTAT_KI_URL, params=params)
            values = parse_eurostat_annual_series(
                response.json(), dataset="nasa_10_ki",
                sector="S11", na_item="B2G_B3G_RAT_S11",
                unit="PC", start=start)
            if any(v > 100 for v in values.values()):
                raise ProviderError("Non-financial corporation gross profit share >100% of GVA")
            return FetchedSeries(series_id, str(response.request.url), None, values)
        if provider == "BIS_WORLD_WEIGHTED":
            if key not in ("GAP/43_COUNTRIES_PRIOR_YEAR_GDP_80PCT",
                           "COVERAGE/43_COUNTRIES_PRIOR_YEAR_GDP_80PCT"):
                raise SourceUnavailable("Unrecognized BIS country-gap global methodology")
            bis_params = {"startPeriod":f"{max(1960, start.year-1)}-Q1"} if start else {}
            bis = self._get(BIS_COMPOSITE_URL, params=bis_params,
                            headers={"Accept": ACCEPT})
            countries = parse_bis_national_credit_gaps(bis.json())
            gdp_params={"format":"json", "per_page":20000,
                        "date":f"{max(1960,start.year-1) if start else 1960}:{date.today().year}"}
            gdp_response=self._get(WORLD_GDP_URL,params=gdp_params)
            gdp_by_year, world_gdp = parse_wdi_gdp_all(gdp_response.json())
            gap, coverage = country_weighted_bis_gap(countries,gdp_by_year,world_gdp,start=start)
            values = gap if key.startswith("GAP/") else coverage
            return FetchedSeries(series_id, BIS_COMPOSITE_URL, None, values)
        if provider == "ILO_LABOUR_PRODUCTIVITY_RATIO":
            if key != "UN_SDG_SL_EMP_GTOTL_WORLD_100_OVER_SHARE":
                raise SourceUnavailable("Unknown global productivity/pay methodology")
            labour_income = self.fetch("labour.world.income_share")
            observations = global_output_to_labour_income_ratio(
                labour_income.observations, start=start)
            return FetchedSeries(series_id,
                "https://unstats.un.org/SDGAPI/v1/sdg/Series/SL_EMP_GTOTL/GeoArea/1/DataSlice",
                None, observations)
        if provider == "WISESHEETS_SNAPSHOT":
            snapshot = load_sec_profit_snapshot()
            if snapshot is None:
                raise SourceUnavailable("Monthly SEC annual earnings snapshot not collected")
            observations = snapshot_series(snapshot, key, start=start)
            return FetchedSeries(
                series_id, "https://www.wisesheets.io/api/docs", None, observations)
        if provider == "BEA_Q":
            if key != "BEA_2026_TABLE_E_Q1":
                raise SourceUnavailable("Unknown BEA Q table/version")
            response = self._get(BEA_Q_URL)
            observations = parse_bea_q1(response.text, start=start)
            return FetchedSeries(series_id, BEA_Q_URL, None, observations)
        if provider == "MSCI_NETR":
            if key != "892400/NETR/USD":
                raise SourceUnavailable("MSCI index, variant or currency unspecified")
            response = self._get(MSCI_LEVELS_URL, params={
                "index_codes": MSCI_ACWI_INDEX_CODE,
                "currency_symbol": "USD",
                "index_variant": "NETR",
                "data_frequency": "DAILY",
                "start_date": (start or date(2000, 1, 1)).strftime("%Y%m%d"),
                "end_date": date.today().strftime("%Y%m%d"),
            }, headers={"User-Agent": "Mozilla/5.0",
                        "Referer": "https://www.msci.com/",
                        "Accept": "application/json"})
            observations = parse_msci_acwi(response.json(), start=start)
            return FetchedSeries(series_id,
                "https://www.msci.com/indexes/index/892400/msci-acwi-index",
                None, observations)
        if provider == "GOLD_MSCI_CORR":
            if key != "36M/PINK_SHEET_GOLD/MSCI_892400_NETR_USD":
                raise SourceUnavailable("Unsupported gold/index correlation convention")
            gold = self.fetch("gold.usd.monthly_average")
            index = self.fetch("equity.world.msci_acwi_netr_usd")
            observations = gold_acwi_rolling_correlation(
                gold.observations, index.observations, window=36, start=start)
            return FetchedSeries(series_id,
                "https://www.msci.com/indexes/index/892400/msci-acwi-index",
                None, observations)
        if provider == "CORGANO_SPOT":
            response = self._get(CORGANO_GOLD_LATEST)
            observations = parse_corgano_gold(response.json(), start)
            return FetchedSeries(series_id, CORGANO_GOLD_LATEST, None, observations)
        if provider == "BIS_CREDIT_GAP":
            # The API is queried with a country code then exact dimensions
            # are selected from the SDMX structure, not assumed by series position.
            country = key.split("/")[1].split(".")[1]
            if country not in {"US", "JP", "XM"}:
                raise SourceUnavailable("Unsupported BIS credit-gap country")
            url = f"{BIS_CREDIT_GAP_ROOT}/Q.{country}"
            response = self._get(url, params={"startPeriod": f"{start.year}-Q1"} if start else {},
                                 headers={"Accept": ACCEPT})
            observations, prepared = parse_bis_credit_gap(response.json(), country, start)
            return FetchedSeries(series_id, str(response.request.url), prepared, observations)
        if provider == "SIBLIS_FREE":
            ticker, ratio = key.split("/", 1)
            if ticker not in {"ACWI"} or ratio != "cape":
                raise SourceUnavailable("Siblis API ticker/metric not approved by catalog")
            url = f"{SIBLIS_FREE_ROOT}/{ticker}/{ratio}"
            response = self._get(url)
            observations = parse_siblis_cape(response.json(), ticker, start)
            return FetchedSeries(series_id, url, None, observations)
        if provider == "WORLD_BANK_PINK_SHEET":
            from io import BytesIO
            from python_calamine import CalamineWorkbook
            response = self._get(PINK_SHEET_URL, follow_redirects=True)
            if len(response.content) > 15_000_000:
                raise ProviderError("World Bank workbook exceeds safe size limit")
            try:
                workbook = CalamineWorkbook.from_filelike(BytesIO(response.content))
                rows = workbook.get_sheet_by_name("Monthly Prices").to_python()
            except (ValueError, RuntimeError) as exc:
                raise ProviderError("World Bank monthly workbook is invalid") from exc
            observations = parse_pink_sheet_gold(rows, start)
            return FetchedSeries(series_id, PINK_SHEET_URL, None, observations)
        if provider == "UN_SDG":
            code, area = key.split("/", 1)
            url = f"{UN_SDG_ROOT}/{code}/GeoArea/{area}/DataSlice"
            response = self._get(url)
            observations = parse_un_sdg(response.json(), code, area, start)
            return FetchedSeries(series_id, str(response.request.url), None, observations)
        if provider == "SHILLER":
            import xlrd
            homepage = self._get(SHILLER_HOME, follow_redirects=True)
            parser = ShillerDownloadLinks()
            parser.feed(homepage.text)
            if len(parser.links) != 1:
                raise ProviderError("Cannot identify a unique Shiller ie_data.xls download")
            url = urljoin(SHILLER_HOME, parser.links[0])
            if urlparse(url).hostname not in ("img1.wsimg.com", "shillerdata.com", "www.econ.yale.edu"):
                raise ProviderError("Shiller workbook link points to an unapproved host")
            response = self._get(url, follow_redirects=True)
            try:
                workbook = xlrd.open_workbook(file_contents=response.content)
                values = parse_shiller_sheet(workbook.sheet_by_name("Data"))
            except (xlrd.XLRDError, ValueError, IndexError) as exc:
                raise ProviderError("Invalid Shiller Excel workbook or Data sheet") from exc
            observations = {day: value for day, value in values.items()
                            if day <= date.today() and (start is None or day >= start)}
            if not observations:
                raise ProviderError("Shiller workbook has no values within requested period")
            return FetchedSeries(series_id, SHILLER_HOME, None, observations)
        if provider == "IMF_DATAMAPPER":
            region, identifier = key.split("/", 1)
            url = f"{IMF_MAPPER_ROOT}/{identifier}"
            response = self._get(url)
            observations = parse_imf_mapper(response.json(), region, identifier, start)
            return FetchedSeries(series_id, str(response.request.url), None, observations)
        raise SourceUnavailable(f"No validated adapter for provider: {provider}")
