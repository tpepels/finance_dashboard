"""OECD member-country corporate gross operating surplus / GDP, 2026 membership.

Source: official OECD annual sector accounts, DSD_NASEC10@DF_TABLE14 v1.1.
For each member/year:
  corporate surplus = S11 D B2G + S12 D B2G (nominal local currency)
  nominal GDP = S1 D B1G + S1 C D21X31 (same currency / year).
The ratio is weighted using same-year WDI nominal USD GDP (country weights).
Annual GDP-based source coverage and participating-member counts are separate
series. The result is an OECD-membership-weighted composite, NOT the OECD's own
published group aggregate, nor global listed-company profits.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import csv
import io
from typing import Any

OECD_DATA_URL = ("https://sdmx.oecd.org/public/rest/data/"
                 "OECD.SDD.NAD,DSD_NASEC10@DF_TABLE14,1.1")
OECD_WDI_URL = "https://api.worldbank.org/v2/country/all/indicator/NY.GDP.MKTP.CD"
OECD_WDI_LOCAL_GDP_URL = "https://api.worldbank.org/v2/country/all/indicator/NY.GDP.MKTP.CN"
# Only stable, explicitly matched LCU currency pairs with sector totals but
# missing OECD product tax balance; no generalized mixed-currency fallback.
LOCAL_GDP_FALLBACK = {"USA": "USD", "JPN": "JPY", "CAN": "CAD"}
OECD_MEMBER_ISO3 = frozenset(
    "AUS AUT BEL CAN CHL COL CRI CZE DNK EST FIN FRA DEU GRC HUN ISL "
    "IRL ISR ITA JPN KOR LVA LTU LUX MEX NLD NZL NOR POL PRT SVK SVN "
    "ESP SWE CHE TUR GBR USA".split())
assert len(OECD_MEMBER_ISO3) == 38
SECTOR_KEYS = {
    ("S11", "D", "B2G"): "nfc",
    ("S12", "D", "B2G"): "fc",
    ("S1", "D", "B1G"): "gva",
    ("S1", "C", "D21X31"): "net_product_taxes",
}
REQUIRED_COLUMNS = {
    "DATAFLOW", "FREQ", "REF_AREA", "SECTOR", "COUNTERPART_SECTOR",
    "ACCOUNTING_ENTRY", "TRANSACTION", "INSTR_ASSET", "EXPENDITURE",
    "UNIT_MEASURE", "VALUATION", "PRICE_BASE", "TRANSFORMATION",
    "TABLE_IDENTIFIER", "TIME_PERIOD", "OBS_VALUE", "UNIT_MULT", "CURRENCY",
}
MIN_GDP_WEIGHT_COVERAGE = Decimal("0.80")
MIN_MEMBERS_WITH_WDI = 35
MIN_OBSERVED_MEMBER_COUNT = 29


class OecdSectorError(ValueError):
    pass


def oecd_annual_data_key() -> str:
    members = "+".join(sorted(OECD_MEMBER_ISO3))
    return (f"A.{members}.S11+S12+S1.S1.C+D.B2G+B1G+D21X31."
            "_Z._Z.XDC.S.V.N.T0800")


def _dec(value: Any, *, positive: bool = False) -> Decimal:
    try:
        result = Decimal(str(value))
    except (ValueError, InvalidOperation, TypeError) as exc:
        raise OecdSectorError("Invalid macroeconomic numerical observation") from exc
    if not result.is_finite() or (positive and result <= 0):
        raise OecdSectorError("Invalid non-finite or nonpositive OECD/WDI observation")
    return result


def parse_oecd_annual_sector_csv(raw: str) -> dict[int, dict[str, dict[str, Decimal]]]:
    if not isinstance(raw, str) or len(raw) > 18_000_000:
        raise OecdSectorError("Invalid or oversized OECD annual CSV")
    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames or not REQUIRED_COLUMNS.issubset(reader.fieldnames):
        raise OecdSectorError("OECD dataflow CSV dimensions changed")
    data: dict[int, dict[str, dict[str, Decimal]]] = {}
    currencies: dict[tuple[int, str], str] = {}
    accepted = 0
    for row in reader:
        if row.get("DATAFLOW") != "OECD.SDD.NAD:DSD_NASEC10@DF_TABLE14(1.1)":
            raise OecdSectorError("OECD annual dataflow identity mismatch")
        if (row.get("FREQ") != "A" or row.get("REF_AREA") not in OECD_MEMBER_ISO3
            or row.get("COUNTERPART_SECTOR") != "S1"
            or row.get("INSTR_ASSET") != "_Z"
            or row.get("EXPENDITURE") != "_Z"
            or row.get("UNIT_MEASURE") != "XDC"
            or row.get("VALUATION") != "S"
            or row.get("PRICE_BASE") != "V"
            or row.get("TRANSFORMATION") != "N"
            or row.get("TABLE_IDENTIFIER") != "T0800"
            or row.get("UNIT_MULT") != "6"):
            raise OecdSectorError("OECD country, units or price/frequency identity mismatch")
        year_string = row.get("TIME_PERIOD", "")
        if len(year_string) != 4 or not year_string.isdigit():
            raise OecdSectorError("Invalid OECD annual period")
        year = int(year_string)
        if not 1950 <= year <= date.today().year:
            raise OecdSectorError("Future or implausible OECD annual period")
        currency = row.get("CURRENCY")
        if not currency or len(currency) != 3 or not currency.isalpha():
            raise OecdSectorError("Missing source-reported OECD local currency")
        ckey = (year, row["REF_AREA"])
        old_currency = currencies.setdefault(ckey, currency)
        if old_currency != currency:
            raise OecdSectorError("Country-year accounting components use different currencies")
        component = SECTOR_KEYS.get((
            row.get("SECTOR"), row.get("ACCOUNTING_ENTRY"), row.get("TRANSACTION")))
        if component is None or row.get("OBS_VALUE") in (None, ""):
            continue
        amount = _dec(row["OBS_VALUE"])
        if component != "net_product_taxes" and amount < 0:
            raise OecdSectorError("Negative corporate surplus or gross value added")
        target = data.setdefault(year, {}).setdefault(row["REF_AREA"], {})
        target["currency"] = currency
        if component in target and target[component] != amount:
            raise OecdSectorError("Conflicting duplicate OECD accounting observations")
        target[component] = amount
        accepted += 1
    if accepted < 20 or len(data) < 1:
        raise OecdSectorError("Insufficient verified OECD sector-account observations")
    return data


def parse_oecd_gdp_weights(payload: Any, *, indicator: str = "NY.GDP.MKTP.CD") -> dict[int, dict[str, Decimal]]:
    if indicator not in ("NY.GDP.MKTP.CD", "NY.GDP.MKTP.CN"):
        raise OecdSectorError("Unsupported WDI GDP weight or local GDP indicator")
    if (not isinstance(payload, list) or len(payload) != 2
        or not isinstance(payload[0], dict) or payload[0].get("pages") != 1
        or not isinstance(payload[1], list)):
        raise OecdSectorError("Invalid or paginated WDI GDP response")
    data: dict[int, dict[str, Decimal]] = {}
    for row in payload[1]:
        if row.get("indicator", {}).get("id") != indicator:
            raise OecdSectorError("World Bank GDP weights have wrong indicator")
        code = row.get("countryiso3code")
        if code not in OECD_MEMBER_ISO3 or row.get("value") is None:
            continue
        yr = row.get("date")
        if not isinstance(yr, str) or len(yr) != 4 or not yr.isdigit():
            raise OecdSectorError("Invalid World Bank country GDP period")
        year = int(yr)
        if year > date.today().year:
            continue
        amount = _dec(row["value"], positive=True)
        bucket = data.setdefault(year, {})
        if code in bucket:
            raise OecdSectorError("Duplicate WDI national GDP weights")
        bucket[code] = amount
    if not data:
        raise OecdSectorError("Missing OECD member nominal USD GDP weights")
    return data


def compute_oecd_corporate_surplus(
    corporate: dict[int, dict[str, dict[str, Decimal]]],
    nominal_gdp_usd: dict[int, dict[str, Decimal]],
    *,
    nominal_gdp_lcu: dict[int, dict[str, Decimal]] | None = None,
    start: date | None = None,
    coverage_floor: Decimal = MIN_GDP_WEIGHT_COVERAGE,
) -> tuple[dict[date, Decimal], dict[date, Decimal], dict[date, Decimal]]:
    """Return GDP-weighted share %, reporting GDP coverage %, and member count.

    Fixed 2026 OECD membership is applied retrospectively. Report only
    years with >=35/38 WDI GDP weights, >=29 contributing companies, and
     >=80% OECD-known GDP weight coverage. Explicit WDI local-GDP fallback only for USD/JPY/CAD stable-currency countries when OECD product taxes are missing. Do not fill missing years.
    """
    shares, coverage, member_counts = {}, {}, {}
    for year in sorted(set(corporate) & set(nominal_gdp_usd)):
        period = date(year, 1, 1)
        if start and period < start:
            continue
        weights = nominal_gdp_usd[year]
        if len(weights) < MIN_MEMBERS_WITH_WDI:
            continue
        total_oecd_weight = sum(weights.values(), Decimal(0))
        if total_oecd_weight <= 0:
            raise OecdSectorError("OECD WDI GDP weight denominator zero")
        eligible = []
        for country, components in corporate[year].items():
            if country not in weights or not {"nfc","fc","gva"}.issubset(components):
                continue
            nfc = components["nfc"]
            fc = components["fc"]
            if "net_product_taxes" in components:
                gdp = components["gva"] + components["net_product_taxes"]
            elif (country in LOCAL_GDP_FALLBACK
                  and components.get("currency") == LOCAL_GDP_FALLBACK[country]
                  and nominal_gdp_lcu and country in nominal_gdp_lcu.get(year, {})):
                # OECD sector GOS / WDI local-currency GDP for exactly USA,
                # JPN and CAN, whose currency did not change over this period.
                # Value in WDI LCU divided by 10^6 matches OECD unit multiplier 6.
                gdp = nominal_gdp_lcu[year][country] / Decimal(1_000_000)
                if not components["gva"] * Decimal("0.90") <= gdp <= components["gva"] * Decimal("1.35"):
                    raise OecdSectorError("Incompatible OECD GVA vs WDI local GDP magnitude")
            else:
                continue
            if gdp <= 0:
                raise OecdSectorError("Nonpositive OECD derived GDP denominator")
            national_ratio = (nfc + fc) / gdp
            if national_ratio < 0 or national_ratio > 1:
                raise OecdSectorError("Corporate surplus exceeds national GDP")
            eligible.append((weights[country], national_ratio))
        if len(eligible) < MIN_OBSERVED_MEMBER_COUNT:
            continue
        included_gdp = sum((w for w, _ in eligible), Decimal(0))
        fraction = included_gdp / total_oecd_weight
        if fraction > Decimal("1.0000001"):
            raise OecdSectorError("Reported countries exceed OECD GDP weights")
        if fraction < coverage_floor:
            continue
        shares[period] = sum((w * ratio for w, ratio in eligible), Decimal(0)) / included_gdp * 100
        coverage[period] = fraction * 100
        member_counts[period] = Decimal(len(eligible))
    if not shares:
        raise OecdSectorError("No OECD annual observations meet member/GDP coverage threshold")
    return shares, coverage, member_counts
