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
from pathlib import Path
from typing import Any

import httpx
from .source_policy import managed_client, require_managed_client

from .bis import BisPolicyClient, FetchedSeries, ProviderError, COUNTRIES, _dimension_code, ACCEPT
from .bis_credit import BIS_TC_ROOT, TC_SERIES, tc_key, parse_bis_total_credit
from .bis_dsr import BIS_DSR_ROOT, DSR_SERIES, parse_bis_dsr
from .bis_property import PROPERTY_SOURCES, BIS_SPP_ROOT, BIS_CPP_ROOT, parse_bis_property
from .boj_call_rates import BOJ_SERIES, boj_url, parse_boj_csv
from .fdic_banks import FDIC_FINANCIALS_URL, FDIC_QUERY, FDIC_SERIES, parse_fdic_aggregates
from .fed_g17 import G17_DIFFUSION_SERIES, G17_DIFFUSION_URL, parse_g17_diffusion
from .imf_external import IMF_SDMX_ROOT, IMF_SERIES, imf_key, parse_imf_bop_iip
from .oecd_cli import OECD_CLI_FLOW, OECD_CLI_ROOT, OECD_CLI_SERIES, oecd_cli_key, parse_oecd_cli_csv
from .ofr_fsi import OFR_FSI_SERIES, OFR_FSI_URL, parse_ofr_fsi
from .wid import WID_SERIES, WidClient
from .oecd_tiva import TIVA_SERIES, TivaClient
from .research_returns import FRENCH_SERIES, SWINKELS_SERIES, ResearchReturnsClient
from .global_market_returns import GLOBAL_MARKET_SERIES
from .catalog import load_documents
from .wisesheets import load_sec_profit_snapshot, snapshot_series
from .world_credit import (BIS_COMPOSITE_URL, WORLD_GDP_URL,
    parse_bis_national_credit_gaps, parse_wdi_gdp_all, country_weighted_bis_gap)
from .oecd_corporate import (
    OECD_DATA_URL, OECD_WDI_URL, OECD_WDI_LOCAL_GDP_URL, oecd_annual_data_key,
    parse_oecd_annual_sector_csv, parse_oecd_gdp_weights,
    compute_oecd_corporate_surplus,
)
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
    parse_bea_q1, parse_bea_q_table, parse_msci_acwi, gold_acwi_rolling_correlation,
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
from .provider_registry import PROVIDER_CODES, get_provider


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
            # FRED annual observations are ISO dates (YYYY-01-01); other
            # providers may use the calendar-year label YYYY.
            if len(raw) == 4 and raw.isdigit():
                return date(int(raw), 1, 1)
            observed = date.fromisoformat(raw)
            if observed.month != 1 or observed.day != 1:
                raise ValueError("annual observation must begin on January 1")
            return observed
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


def parse_pink_sheet_price(rows: list[list], variable: str, start: date | None = None) -> dict[date, Decimal]:
    """Select one named original nominal USD benchmark; never fill missing months."""
    import re
    units = {"Gold": "troy oz", "Crude oil, Brent": "bbl",
             "Natural gas, US": "mmbtu", "Maize": "mt"}
    if variable not in units:
        raise ProviderError("Unapproved World Bank Pink Sheet commodity")
    headers = [(i, j) for i, row in enumerate(rows[:15])
               for j, cell in enumerate(row)
               if str(cell).strip() == variable]
    if len(headers) != 1:
        raise ProviderError("World Bank Pink Sheet commodity column missing or ambiguous")
    header_row, column = headers[0]
    if header_row+1 >= len(rows) or column >= len(rows[header_row+1]):
        raise ProviderError("World Bank commodity source unit row missing")
    if str(rows[header_row+1][column]).strip().lower() != f"($/{units[variable]})":
        denominators = {"Gold": "troy ounce", "Crude oil, Brent": "barrel",
                        "Natural gas, US": "million Btu", "Maize": "metric ton"}
        raise ProviderError(f"World Bank {variable} must be priced per {denominators[variable]} in nominal USD")
    output: dict[date, Decimal] = {}
    for row in rows[header_row+2:]:
        if not row:
            continue
        period = str(row[0]).strip()
        if not re.fullmatch(r"\d{4}M(0[1-9]|1[0-2])", period):
            continue
        day = date(int(period[:4]), int(period[-2:]), 1)
        if day > date.today() or (start is not None and day < start):
            continue
        if column >= len(row):
            continue
        value = _value(row[column])
        if value is not None and value <= 0:
            raise ProviderError("World Bank commodity price must be positive")
        _put(output, day, value)
    if not output:
        raise ProviderError("World Bank Pink Sheet has no commodity price observations")
    return dict(sorted(output.items()))


def parse_pink_sheet_gold(rows: list[list], start: date | None = None) -> dict[date, Decimal]:
    return parse_pink_sheet_price(rows, "Gold", start)


def parse_pink_sheet_brent(rows: list[list], start: date | None = None) -> dict[date, Decimal]:
    return parse_pink_sheet_price(rows, "Crude oil, Brent", start)


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
                         start: date | None = None, dtype: str = "C") -> tuple[dict[date, Decimal], datetime | None]:
    """Select exactly one CG_DTYPE: C gap (default, actual minus one-sided HP trend) or B trend.

    BIS series: Q.{country}.P.A.{dtype} (private nonfinancial borrowers, all
    lenders). The gap is percentage points of GDP; the trend is percent of GDP.
    The actual ratio (A) is carried by WS_TC and is never selected here.
    """
    if dtype not in ("B", "C"):
        raise ProviderError("Unsupported BIS credit-gap data type")
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
            if labels.get("CG_DTYPE") != dtype:
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
        raise ProviderError("No selected BIS credit-gap or trend series in BIS result")
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


def parse_shiller_sheet(sheet, *, variable: str = "CAPE") -> dict[date, Decimal]:
    """Read a named authored monthly series, including split multi-row headers.

    Strictly identify ordinary CAPE rather than the separate total-return CAPE.
    A partial source file must never replace a known historical series.
    """
    if isinstance(sheet, list):
        nrows = len(sheet)
        ncols = max((len(row) for row in sheet), default=0)

        def cell(row, col):
            return sheet[row][col] if col < len(sheet[row]) else ""
    else:
        nrows, ncols = sheet.nrows, sheet.ncols
        cell = sheet.cell_value

    # Shiller's original Data worksheet uses seven header rows and two
    # spacer columns. The Date Fraction, TR CAPE, and Excess CAPE Yield
    # columns may each contain an independent "Date" or "CAPE" label.
    # Select by the complete column heading, not by an isolated cell.
    header_rows = min(8, nrows)
    headings = {}
    last_header_row = {}
    for col in range(ncols):
        parts = []
        last = 0
        for row in range(header_rows):
            raw = cell(row, col)
            # Do not count numeric data rows as further header rows.
            # This also accommodates short fixture sheets with data at row 2.
            if not isinstance(raw, str) or not any(ch.isalpha() for ch in raw):
                continue
            label = raw.strip().upper()
            if label and label not in ("NA", "N/A", "NULL"):
                parts.append(label)
                last = row
        headings[col] = " ".join(parts)
        last_header_row[col] = last

    dates = [col for col, label in headings.items()
             if "DATE" in label.split() and "FRACTION" not in label]
    def ordinary_cape(label: str) -> bool:
        return ("CAPE" in label.split() and
                not any(forbidden in label for forbidden in
                        ("TOTAL RETURN", "TR CAPE", "EXCESS CAPE")))

    capes = [col for col, label in headings.items()
             if ordinary_cape(label)]
    strong = [col for col in capes
              if "CYCLICALLY ADJUSTED" in headings[col]]
    if len(strong) == 1:
        capes = strong
    if variable != "CAPE":
        labels = {"P": "S&P COMP. P", "D": "DIVIDEND D", "E": "EARNINGS E",
                  "CPI": "CONSUMER PRICE INDEX CPI", "REAL_TR_PRICE": "REAL TOTAL RETURN PRICE"}
        if variable not in labels:
            raise ProviderError("Unapproved Shiller workbook variable")
        capes = [col for col, label in headings.items() if label == labels[variable]]
    if len(dates) != 1 or len(capes) != 1:
        raise ProviderError("Shiller workbook does not contain recognizable DATE/CAPE columns")
    date_col, cape_col = dates[0], capes[0]
    if date_col == cape_col:
        raise ProviderError("Shiller workbook has ambiguous DATE/CAPE columns")
    date_header_row = last_header_row[date_col]
    cape_header_row = last_header_row[cape_col]
    output = {}
    for row in range(max(date_header_row, cape_header_row) + 1, nrows):
        try:
            num = Decimal(str(cell(row, date_col)))
            year = int(num)
            month = int((num - year) * 100 + Decimal("0.5"))
            if year < 1871 or month < 1 or month > 12:
                continue
            day = date(year, month, 1)
        except (TypeError, ValueError, InvalidOperation):
            continue
        _put(output, day, _value(cell(row, cape_col)))
    if not output:
        raise ProviderError("Shiller workbook contains no CAPE observations")
    first, last = min(output), max(output)
    expected_months = (last.year-first.year)*12 + last.month-first.month + 1
    if (first > date(1882, 1, 1) or
            (expected_months >= 120 and len(output) < int(expected_months*0.90))):
            raise ProviderError(f"Shiller source workbook has incomplete monthly {variable} history")
    return output


class ProviderRouter:
    """One configured client shared across the run. Explicitly refuse unresolved datasets."""

    def __init__(self, client: httpx.Client | None = None, bis=None):
        self.client = require_managed_client(client) if client is not None else managed_client(
            timeout=httpx.Timeout(30.0),
            follow_redirects=False,
        )
        self.owns_client = client is None
        self.bis = bis or BisPolicyClient(self.client)
        self._wid = None
        self._tiva = None
        self._research_returns = None
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
        # Policy-controlled transport owns request pacing and durable backoff.
        # An unsuccessful response remains a distinct failure; scheduled
        # refresh may try again after the canonical publisher cooldown.
        response = self.client.get(url, **kwargs)
        if response.status_code >= 400:
            # Avoid embedding FRED API keys or signed URLs in errors/logs.
            raise SourceUnavailable(
                f"Provider HTTP {response.status_code} ({response.request.url.host})")
        return response

    def fetch(self, series_id: str, start: date | None = None) -> FetchedSeries:
        item = self.definitions.get(series_id)
        if item is None:
            raise SourceUnavailable("Unknown catalog series")
        if item["status"] != "mapped":
            raise SourceUnavailable(f"Source mapping unavailable: {series_id}")
        provider, key = item["provider"], item["source_key"]
        spec = get_provider(provider)
        if spec is None:
            raise SourceUnavailable(f"No validated adapter for provider: {provider}")
        from .provider_adapters import HANDLERS
        return HANDLERS[provider](self, series_id, start, item, key)
