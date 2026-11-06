"""Canonical provider adapters. One registered callable per provider family.

Parser definitions live in provider_parsers.py; this module is loaded only on a
validated fetch. It holds no parallel fallback dispatcher.
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


from .provider_parsers import (
    SourceUnavailable,
    parse_fred_csv,
    parse_fred_table_html,
    parse_fred_json,
    parse_ecb_csv,
    parse_pink_sheet_price,
    parse_corgano_gold,
    parse_un_sdg,
    parse_bis_credit_gap,
    parse_siblis_cape,
    parse_imf_mapper,
    parse_world_bank,
    ShillerDownloadLinks,
    parse_shiller_sheet,
    FRED_ROOT,
    FRED_TABLE_ROOT,
    FRED_CSV_ROOT,
    ECB_ROOT,
    WORLD_BANK_ROOT,
    SHILLER_HOME,
    UN_SDG_ROOT,
    PINK_SHEET_URL,
    IMF_MAPPER_ROOT,
    BIS_CREDIT_GAP_ROOT,
    SIBLIS_FREE_ROOT,
    CORGANO_GOLD_LATEST,
)

def fetch_bis(self, series_id, start, item, key):
    """Validate and fetch native data for BIS."""
    provider = item["provider"]
    return self.bis.fetch(series_id, start)


def fetch_wid(self, series_id, start, item, key):
    """Validate and fetch native data for WID."""
    provider = item["provider"]
    expected = WID_SERIES.get(series_id)
    if expected is None or key != "/".join(expected):
        raise SourceUnavailable("WID original variable or population mapping changed")
    if self._wid is None:
        self._wid = WidClient(self.client, archive_dir=Path(os.environ.get(
            "FINANCE_SOURCE_EVIDENCE_DIR", "/data/source-evidence")))
    return self._wid.fetch(series_id, start)


def fetch_oecd_tiva(self, series_id, start, item, key):
    """Validate and fetch native data for OECD_TIVA."""
    provider = item["provider"]
    expected = TIVA_SERIES.get(series_id)
    if expected is None:
        raise SourceUnavailable("Unregistered OECD TiVA original source")
    flow, measure, area, activity, counterpart, unit, freq = expected
    exact_key = f"OECD.STI.PIE,{flow},1.1/{measure}.{area}.{activity}.{counterpart}.{unit}.{freq}"
    if key != exact_key:
        raise SourceUnavailable("OECD TiVA original dimensions or unit mapping changed")
    if self._tiva is None:
        self._tiva = TivaClient(self.client, archive_dir=Path(os.environ.get(
            "FINANCE_SOURCE_EVIDENCE_DIR", "/data/source-evidence")))
    return self._tiva.fetch(series_id, start)


def fetch_french_returns(self, series_id, start, item, key):
    """Validate and fetch native data for FRENCH_RETURNS, SWINKELS_RETURNS, GLOBAL_MARKET_RETURNS."""
    provider = item["provider"]
    if provider == "FRENCH_RETURNS":
        expected = FRENCH_SERIES.get(series_id)
        exact_key = "/".join(expected) if expected else None
    elif provider == "SWINKELS_RETURNS":
        expected = SWINKELS_SERIES.get(series_id)
        exact_key = f"{expected[0]}/column:{expected[1]}/cached_decimal_return" if expected else None
    else:
        expected = GLOBAL_MARKET_SERIES.get(series_id)
        exact_key = f"GMP JIMF/{expected[0]}/{expected[1]}/cached_percent_return" if expected else None
    if expected is None or key != exact_key:
        raise SourceUnavailable("Original research return source identity or convention changed")
    if provider == "GLOBAL_MARKET_RETURNS" and (
            item.get("unit") != "percent" or item.get("frequency") != "M"
            or item.get("currency") != expected[0]):
        raise SourceUnavailable("Global multiasset native frequency, currency or percent unit changed")
    if self._research_returns is None:
        self._research_returns = ResearchReturnsClient(self.client, archive_dir=Path(os.environ.get(
            "FINANCE_SOURCE_EVIDENCE_DIR", "/data/source-evidence")))
    return self._research_returns.fetch(series_id, start)


def fetch_fred(self, series_id, start, item, key):
    """Validate and fetch native data for FRED."""
    provider = item["provider"]
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
    # FRED may include older full-history observations in an overlap
    # request. Apply the requested source-date boundary locally for all
    # three FRED transports; the ingestion service keeps its strict
    # rejection of unfiltered out-of-window data from other providers.
    if start is not None:
        observations = {day: value for day, value in observations.items()
                        if day >= start}
    if not observations:
        raise ProviderError("FRED source has no observations in requested window")
    # Always report a non-secret source URI, even for authenticated requests.
    return FetchedSeries(series_id, f"https://fred.stlouisfed.org/series/{identifier}", None, observations)


def fetch_ecb(self, series_id, start, item, key):
    """Validate and fetch native data for ECB."""
    provider = item["provider"]
    from .captured_sources import _ECB_SERIES
    if key not in _ECB_SERIES:
        raise SourceUnavailable(f"Unsupported ECB series: {key}")
    dataset = _ECB_SERIES[key][0]
    url = f"{ECB_ROOT}/{dataset}/{key[len(dataset) + 1:]}"
    params = {"format": "csvdata"}
    if start:
        params["startPeriod"] = start.isoformat()
    response = self._get(url, params=params)
    observations = parse_ecb_csv(response.text, key, item["frequency"])
    return FetchedSeries(series_id, str(response.request.url), None, observations)


def fetch_world_bank(self, series_id, start, item, key):
    """Validate and fetch native data for WORLD_BANK."""
    provider = item["provider"]
    country, identifier = key.split("/", 1)
    url = f"{WORLD_BANK_ROOT}/country/{country}/indicator/{identifier}"
    params = {"format": "json", "per_page": 150}
    if start:
        params["date"] = f"{start.year}:{date.today().year}"
    response = self._get(url, params=params)
    observations = parse_world_bank(response.json(), country, identifier, start)
    return FetchedSeries(series_id, str(response.request.url), None, observations)


def fetch_world_listed_cap_share(self, series_id, start, item, key):
    """Validate and fetch native data for WORLD_LISTED_CAP_SHARE."""
    provider = item["provider"]
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


def fetch_siblis_world_pe(self, series_id, start, item, key):
    """Validate and fetch native data for SIBLIS_WORLD_PE, SIBLIS_WORLD_EARNINGS_YIELD."""
    provider = item["provider"]
    if key != "GLOBAL/PT12M":
        raise SourceUnavailable("Unapproved Siblis global valuation source key")
    response = self._get(SIBLIS_WORLD_PE_URL)
    observations = parse_siblis_world_pe(response.text, start=start)
    if provider == "SIBLIS_WORLD_EARNINGS_YIELD":
        observations = aggregate_earnings_yield(observations)
    return FetchedSeries(series_id, SIBLIS_WORLD_PE_URL, None, observations)


def fetch_msci_published_top10(self, series_id, start, item, key):
    """Validate and fetch native data for MSCI_PUBLISHED_TOP10."""
    provider = item["provider"]
    if key not in {"892400/TOP10/PUBLISHED_SPARSE_SNAPSHOTS", "892400/COUNT/PUBLISHED_SPARSE_SNAPSHOTS"}:
        raise SourceUnavailable("Wrong index, statistic or historical method")
    from .msci_concentration_originals import read_msci_concentration_originals
    values, _evidence = read_msci_concentration_originals(Path(os.environ.get(
        "FINANCE_SOURCE_EVIDENCE_DIR", "/data/source-evidence")))
    if key == "892400/COUNT/PUBLISHED_SPARSE_SNAPSHOTS":
        values = {date.fromisoformat(period): Decimal(count) for period, count in _evidence["constituent_count_values"].items()}
    values = {day: value for day, value in values.items() if start is None or day >= start}
    if not values:
        raise ProviderError("Original MSCI factsheets have no selected values in requested period")
    return FetchedSeries(series_id,
        "https://www.msci.com/indexes/index/892400/msci-acwi-index",
        None, values)


def fetch_oecd_corporate_gdpweighted(self, series_id, start, item, key):
    """Validate and fetch native data for OECD_CORPORATE_GDPWEIGHTED."""
    provider = item["provider"]
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


def fetch_eurostat_corporate_gdp(self, series_id, start, item, key):
    """Validate and fetch native data for EUROSTAT_CORPORATE_GDP."""
    provider = item["provider"]
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


def fetch_eurostat_nfc_profit_gva(self, series_id, start, item, key):
    """Validate and fetch native data for EUROSTAT_NFC_PROFIT_GVA."""
    provider = item["provider"]
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


def fetch_bis_world_weighted(self, series_id, start, item, key):
    """Validate and fetch native data for BIS_WORLD_WEIGHTED."""
    provider = item["provider"]
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


def fetch_ilo_labour_productivity_ratio(self, series_id, start, item, key):
    """Validate and fetch native data for ILO_LABOUR_PRODUCTIVITY_RATIO."""
    provider = item["provider"]
    if key != "UN_SDG_SL_EMP_GTOTL_WORLD_100_OVER_SHARE":
        raise SourceUnavailable("Unknown global productivity/pay methodology")
    labour_income = self.fetch("labour.world.income_share")
    observations = global_output_to_labour_income_ratio(
        labour_income.observations, start=start)
    return FetchedSeries(series_id,
        "https://unstats.un.org/SDGAPI/v1/sdg/Series/SL_EMP_GTOTL/GeoArea/1/DataSlice",
        None, observations)


def fetch_wisesheets_snapshot(self, series_id, start, item, key):
    """Validate and fetch native data for WISESHEETS_SNAPSHOT."""
    provider = item["provider"]
    snapshot = load_sec_profit_snapshot()
    if snapshot is None:
        raise SourceUnavailable("Monthly SEC annual earnings snapshot not collected")
    observations = snapshot_series(snapshot, key, start=start)
    return FetchedSeries(
        series_id, "https://www.wisesheets.io/api/docs", None, observations)


def fetch_bea_q(self, series_id, start, item, key):
    """Validate and fetch native data for BEA_Q."""
    provider = item["provider"]
    approved = {
        "BEA_2026_TABLE_E_Q1": "Q1",
        "BEA_2026_TABLE_E_Q2": "Q2",
        "BEA_2026_TABLE_E_Q3": "Q3",
    }
    if key not in approved:
        raise SourceUnavailable("Unknown BEA Q table/version")
    response = self._get(BEA_Q_URL)
    observations = parse_bea_q_table(response.text, approved[key], start=start)
    return FetchedSeries(series_id, BEA_Q_URL, None, observations)


def fetch_msci_netr(self, series_id, start, item, key):
    """Validate and fetch native data for MSCI_NETR."""
    provider = item["provider"]
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


def fetch_gold_msci_corr(self, series_id, start, item, key):
    """Validate and fetch native data for GOLD_MSCI_CORR."""
    provider = item["provider"]
    if key != "36M/PINK_SHEET_GOLD/MSCI_892400_NETR_USD":
        raise SourceUnavailable("Unsupported gold/index correlation convention")
    gold = self.fetch("gold.usd.monthly_average")
    index = self.fetch("equity.world.msci_acwi_netr_usd")
    observations = gold_acwi_rolling_correlation(
        gold.observations, index.observations, window=36, start=start)
    return FetchedSeries(series_id,
        "https://www.msci.com/indexes/index/892400/msci-acwi-index",
        None, observations)


def fetch_corgano_spot(self, series_id, start, item, key):
    """Validate and fetch native data for CORGANO_SPOT."""
    provider = item["provider"]
    response = self._get(CORGANO_GOLD_LATEST)
    observations = parse_corgano_gold(response.json(), start)
    return FetchedSeries(series_id, CORGANO_GOLD_LATEST, None, observations)


def fetch_bis_property(self, series_id, start, item, key):
    """Validate and fetch native data for BIS_PROPERTY."""
    provider = item["provider"]
    registered = PROPERTY_SOURCES.get(series_id)
    if registered is None:
        raise SourceUnavailable("Unregistered BIS property series")
    flow, original_key, native_frequency = registered
    if key != f"BIS,WS_{flow},1.0/{original_key}":
        raise SourceUnavailable("BIS property source key changed or is unapproved")
    start_period = (str(start.year) if native_frequency == "A"
                    else f"{start.year}-Q{(start.month - 1)//3 + 1}") if start else None
    response = self._get(
        f"{BIS_SPP_ROOT if flow == 'SPP' else BIS_CPP_ROOT}/{original_key}",
        params={"startPeriod":start_period} if start_period else {},
        headers={"Accept": ACCEPT})
    values, prepared = parse_bis_property(
        response.json(), flow=flow, original_key=original_key, start=start)
    return FetchedSeries(series_id, str(response.request.url), prepared, values)


def fetch_bis_dsr(self, series_id, start, item, key):
    """Validate and fetch native data for BIS_DSR."""
    provider = item["provider"]
    exact = DSR_SERIES.get(series_id)
    if exact is None:
        raise SourceUnavailable("Unregistered BIS DSR data series")
    country, sector = exact
    if key != f"BIS,WS_DSR,1.0/Q.{country}.{sector}":
        raise SourceUnavailable("BIS DSR source key differs from approved country/sector")
    response = self._get(
        f"{BIS_DSR_ROOT}/Q.{country}.{sector}",
        params={"startPeriod": f"{start.year}-Q{(start.month - 1)//3 + 1}"} if start else {},
        headers={"Accept": ACCEPT})
    values, prepared = parse_bis_dsr(
        response.json(), country=country, sector=sector, start=start)
    return FetchedSeries(series_id, str(response.request.url), prepared, values)


def fetch_bis_credit_gap(self, series_id, start, item, key):
    """Validate and fetch native data for BIS_CREDIT_GAP."""
    provider = item["provider"]
    # The API is queried with a country code then exact dimensions
    # are selected from the SDMX structure, not assumed by series position.
    parts = key.split("/")[1].split(".")
    country, dtype = parts[1], parts[-1]
    if country not in {"US", "JP", "XM", "DE", "CN", "PT"} or key != f"BIS,WS_CREDIT_GAP,1.0/Q.{country}.P.A.{dtype}":
        raise SourceUnavailable("Unsupported BIS credit-gap country or data type")
    url = f"{BIS_CREDIT_GAP_ROOT}/Q.{country}"
    response = self._get(url, params={"startPeriod": f"{start.year}-Q1"} if start else {},
                         headers={"Accept": ACCEPT})
    observations, prepared = parse_bis_credit_gap(response.json(), country, start, dtype)
    return FetchedSeries(series_id, str(response.request.url), prepared, observations)


def fetch_bis_total_credit(self, series_id, start, item, key):
    """Validate and fetch native data for BIS_TOTAL_CREDIT."""
    provider = item["provider"]
    exact = TC_SERIES.get(series_id)
    if exact is None or key != f"BIS,WS_TC,2.0/{tc_key(*exact[:3])}":
        raise SourceUnavailable("BIS total-credit source key differs from the approved country/sector/unit")
    response = self._get(f"{BIS_TC_ROOT}/{tc_key(*exact[:3])}", headers={"Accept": ACCEPT})
    values, prepared = parse_bis_total_credit(response.json(), series_id, start)
    return FetchedSeries(series_id, str(response.request.url), prepared, values)


def fetch_fed_g17_diffusion(self, series_id, start, item, key):
    """Validate and fetch native data for FED_G17_DIFFUSION."""
    provider = item["provider"]
    exact = G17_DIFFUSION_SERIES.get(series_id)
    if exact is None or key != f"diff_sa.txt#{exact[0]}":
        raise SourceUnavailable("G.17 diffusion span or block identity differs from the approved definition")
    response = self._get(G17_DIFFUSION_URL)
    return FetchedSeries(series_id, G17_DIFFUSION_URL, None,
                         parse_g17_diffusion(response.text, block=exact[0], span=exact[1], start=start))


def fetch_ofr_fsi(self, series_id, start, item, key):
    """Validate and fetch native data for OFR_FSI."""
    provider = item["provider"]
    column = OFR_FSI_SERIES.get(series_id)
    if column is None or key != f"fsi.csv#{column}":
        raise SourceUnavailable("OFR FSI column identity differs from the approved definition")
    response = self._get(OFR_FSI_URL, headers={"Accept": "text/csv"})
    return FetchedSeries(series_id, OFR_FSI_URL, None, parse_ofr_fsi(response.text, column, start))


def fetch_boj_tss(self, series_id, start, item, key):
    """Validate and fetch native data for BOJ_TSS."""
    provider = item["provider"]
    exact = BOJ_SERIES.get(series_id)
    if exact is None or key != exact[1]:
        raise SourceUnavailable("BOJ series code differs from the approved daily/monthly definition")
    response = self._get(boj_url(exact[0]), headers={"Accept": "text/csv"})
    return FetchedSeries(series_id, boj_url(exact[0]), None, parse_boj_csv(response.text, series_id, start))


def fetch_oecd_cli(self, series_id, start, item, key):
    """Validate and fetch native data for OECD_CLI."""
    provider = item["provider"]
    exact = OECD_CLI_SERIES.get(series_id)
    if exact is None or key != f"{OECD_CLI_FLOW}/{oecd_cli_key(*exact)}":
        raise SourceUnavailable("OECD CLI area or adjustment differs from the approved definition")
    response = self._get(f"{OECD_CLI_ROOT}/{OECD_CLI_FLOW}/{oecd_cli_key(*exact)}",
                         params={"format": "csvfile"}, headers={"Accept": "text/csv"})
    return FetchedSeries(series_id, str(response.request.url), None,
                         parse_oecd_cli_csv(response.text, *exact, start=start))


def fetch_imf_bop_iip(self, series_id, start, item, key):
    """Validate and fetch native data for IMF_BOP_IIP."""
    provider = item["provider"]
    exact = IMF_SERIES.get(series_id)
    if exact is None or key != imf_key(exact[0], exact[1], exact[2], exact[3]):
        raise SourceUnavailable("IMF BOP/IIP key differs from the approved country and indicator")
    response = self._get(f"{IMF_SDMX_ROOT}/IMF.STA,{exact[0]},{exact[1]}/{exact[2]}..{exact[3]}.USD.A",
                         headers={"Accept": "application/xml"})
    return FetchedSeries(series_id, str(response.request.url), None,
                         parse_imf_bop_iip(response.content, series_id, start))


def fetch_fdic_bankfind(self, series_id, start, item, key):
    """Validate and fetch native data for FDIC_BANKFIND."""
    provider = item["provider"]
    field = FDIC_SERIES.get(series_id)
    if field is None or key != f"financials?agg_by=REPDTE#{field}":
        raise SourceUnavailable("FDIC aggregate field differs from the approved definition")
    response = self._get(FDIC_FINANCIALS_URL, params=FDIC_QUERY)
    return FetchedSeries(series_id, str(response.request.url), None,
                         parse_fdic_aggregates(response.json(), series_id, start))


def fetch_siblis_free(self, series_id, start, item, key):
    """Validate and fetch native data for SIBLIS_FREE."""
    provider = item["provider"]
    ticker, ratio = key.split("/", 1)
    if ticker not in {"ACWI"} or ratio != "cape":
        raise SourceUnavailable("Siblis API ticker/metric not approved by catalog")
    url = f"{SIBLIS_FREE_ROOT}/{ticker}/{ratio}"
    response = self._get(url)
    observations = parse_siblis_cape(response.json(), ticker, start)
    return FetchedSeries(series_id, url, None, observations)


def fetch_world_bank_pink_sheet(self, series_id, start, item, key):
    """Validate and fetch native data for WORLD_BANK_PINK_SHEET."""
    provider = item["provider"]
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
    prefix = "CMO-Historical-Data-Monthly.xlsx#Monthly Prices:"
    if not key.startswith(prefix):
        raise SourceUnavailable("Unapproved World Bank Pink Sheet commodity")
    observations = parse_pink_sheet_price(rows, key[len(prefix):], start)
    return FetchedSeries(series_id, PINK_SHEET_URL, None, observations)


def fetch_un_sdg(self, series_id, start, item, key):
    """Validate and fetch native data for UN_SDG."""
    provider = item["provider"]
    code, area = key.split("/", 1)
    url = f"{UN_SDG_ROOT}/{code}/GeoArea/{area}/DataSlice"
    response = self._get(url)
    observations = parse_un_sdg(response.json(), code, area, start)
    return FetchedSeries(series_id, str(response.request.url), None, observations)


def fetch_shiller(self, series_id, start, item, key):
    """Validate and fetch native data for SHILLER."""
    provider = item["provider"]
    from io import BytesIO
    from python_calamine import CalamineWorkbook
    homepage = self._get(SHILLER_HOME, follow_redirects=True)
    parser = ShillerDownloadLinks()
    parser.feed(homepage.text)
    if len(parser.links) != 1:
        raise ProviderError("Cannot identify a unique Shiller ie_data.xls download")
    url = urljoin(SHILLER_HOME, parser.links[0])
    if urlparse(url).hostname not in ("img1.wsimg.com", "shillerdata.com", "www.econ.yale.edu"):
        raise ProviderError("Shiller workbook link points to an unapproved host")
    response = self._get(url, follow_redirects=True)
    data = response.content
    if len(data) > 15_000_000:
        raise ProviderError("Shiller workbook exceeds safe size limit")
    if not (data.startswith(bytes.fromhex("D0CF11E0A1B11AE1"))
            or data.startswith(b"PK\x03\x04")):
        raise ProviderError("Shiller download is not an Excel workbook")
    try:
        workbook = CalamineWorkbook.from_filelike(BytesIO(data))
        rows = workbook.get_sheet_by_name("Data").to_python()
    except Exception as exc:
        # Never expose remote response bodies or arbitrary parser errors.
        raise ProviderError("Invalid Shiller Excel workbook or Data sheet") from exc
    # Parse separately: ProviderError subclasses ValueError and must not
    # be converted into the generic workbook-invalid diagnostic.
    prefix = "ie_data.xls#Data:"
    if not key.startswith(prefix):
        raise SourceUnavailable("Unapproved Shiller workbook variable")
    values = parse_shiller_sheet(rows, variable=key[len(prefix):])
    observations = {day: value for day, value in values.items()
                    if day <= date.today() and (start is None or day >= start)}
    if not observations:
        raise ProviderError("Shiller workbook has no values within requested period")
    return FetchedSeries(series_id, SHILLER_HOME, None, observations)


def fetch_imf_datamapper(self, series_id, start, item, key):
    """Validate and fetch native data for IMF_DATAMAPPER."""
    provider = item["provider"]
    region, identifier = key.split("/", 1)
    url = f"{IMF_MAPPER_ROOT}/{identifier}"
    response = self._get(url)
    observations = parse_imf_mapper(response.json(), region, identifier, start)
    return FetchedSeries(series_id, str(response.request.url), None, observations)
