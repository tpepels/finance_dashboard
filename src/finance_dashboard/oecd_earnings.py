"""OECD full-time employee earnings-dispersion and minimum-to-median originals.

The published DSD_EARNINGS flows contain relative distribution indicators,
not median earning levels. Their population and interpretation differ from
BLS CPS full-time wage/salary workers and nonfarm-business compensation.
"""
from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal, InvalidOperation
import io
import re

from .bis import ProviderError

ROOT = "https://sdmx.oecd.org/public/rest/data"
AGENCY = "OECD.ELS.SAE"
FLOWS = {"decile":"DSD_EARNINGS@DEC_I", "minimum":"DSD_EARNINGS@MIN2AVE"}
VERSION = "1.0"
AREAS = {"us":"USA","de":"DEU","fr":"FRA","pt":"PRT","jp":"JPN"}
KINDS = {"p90_p10":"D9_1", "p90_p50":"D9_5", "p50_p10":"D5_1",
         "minimum_median":"MEDIAN"}
OECD_EARNINGS_SERIES = {
    f"labour.{country}.oecd_{kind}": ("decile" if kind != "minimum_median" else "minimum", area, code)
    for country,area in AREAS.items()
    for kind,code in KINDS.items()
}


def source_key(flow: str, area: str, operation: str) -> str:
    if flow not in FLOWS or area not in AREAS.values() or operation not in KINDS.values():
        raise ProviderError("Unregistered OECD earnings data dimensions")
    if (flow == "minimum") != (operation == "MEDIAN"):
        raise ProviderError("OECD earnings flow/measure mismatch")
    lookup = f"{area}.....{operation}." + ("_T" if flow == "decile" else "")
    return f"{AGENCY},{FLOWS[flow]},{VERSION}/{lookup}"


def parse_oecd_earnings_csv(text: str, flow: str, area: str, operation: str,
                           start: date | None = None) -> dict[date, Decimal]:
    """Require exact publisher flow, place, aggregation, total-sex and annual dates.

    CSV names follow the OECD SDMX CSV file export. Data are intentionally
    withheld if publisher dimensions change; changing a flow is not a licence
    to reinterpret values under a different national earnings definition.
    """
    expected = f"{AGENCY}:{FLOWS[flow]}({VERSION})"
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    required = {"DATAFLOW","REF_AREA","AGGREGATION_OPERATION",
                "TIME_PERIOD","OBS_VALUE","OBS_STATUS","UNIT_MULT"}
    if flow == "decile":
        required |= {"SEX","UNIT_MEASURE"}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise ProviderError("OECD earnings CSV schema missing required dimensions")
    ratios = {"D9_1":"FCTR_D1", "D9_5":"FCTR_D5", "D5_1":"FCTR_D1"}
    observations:dict[date,Decimal] = {}
    seen:set[str] = set()
    for row in reader:
        if (row.get("DATAFLOW") != expected
                or row.get("REF_AREA") != area
                or row.get("AGGREGATION_OPERATION") != operation
                or row.get("UNIT_MULT") != "0"):
            raise ProviderError("OECD earnings dataset, place or calculation differs")
        if flow == "decile" and (
                row.get("SEX") != "_T"
                or row.get("UNIT_MEASURE") != ratios[operation]):
            raise ProviderError("OECD earnings source population or ratio unit differs")
        period = row.get("TIME_PERIOD") or ""
        if not re.fullmatch(r"\d{4}",period) or period in seen:
            raise ProviderError("OECD earnings annual period malformed or duplicated")
        seen.add(period)
        if row.get("OBS_STATUS") not in ("A",""):
            # Data which are suppressed, estimates of different status, or
            # absent must not be treated as ordinary original observations.
            continue
        raw = row.get("OBS_VALUE")
        if raw in (None,"","NA","NaN"):
            continue
        try:
            value = Decimal(raw)
        except InvalidOperation as exc:
            raise ProviderError("OECD earnings observation invalid") from exc
        if not value.is_finite() or value <= 0 or (
            flow == "decile" and value < 1) or (
            flow == "minimum" and value > 200):
            raise ProviderError("OECD earnings observation has impossible magnitude")
        day = date(int(period),1,1)
        if day > date.today():
            continue
        if start is None or day >= start:
            observations[day]=value
    if not observations:
        raise ProviderError("OECD earnings source has no qualifying observations")
    return dict(sorted(observations.items()))
