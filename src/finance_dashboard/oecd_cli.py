"""OECD composite leading indicators (DSD_STES@DF_CLI 4.1), original monthly SDMX CSV.

AA is the amplitude-adjusted headline CLI (index, long-term average 100); TR is
the same indicator with the reference-series trend restored. They are separate
published concepts and only the identity checked below may enter a series.
CLI describes direction and turning points, not growth rates or probabilities.
"""
from __future__ import annotations

import csv
from datetime import date
from decimal import Decimal, InvalidOperation
import io

from .bis import ProviderError

OECD_CLI_ROOT = "https://sdmx.oecd.org/public/rest/data"
OECD_CLI_FLOW = "OECD.SDD.STES,DSD_STES@DF_CLI,4.1"
OECD_CLI_DATAFLOW_ID = "OECD.SDD.STES:DSD_STES@DF_CLI(4.1)"
AREAS = {"us": "USA", "jp": "JPN", "de": "DEU", "fr": "FRA", "gb": "GBR", "cn": "CHN", "in": "IND",
         "g7": "G7", "g20": "G20"}
OECD_CLI_SERIES = {
    **{f"activity.{label}.oecd_cli": (area, "AA") for label, area in AREAS.items()},
    "activity.us.oecd_cli_trend_restored": ("USA", "TR"),
    "activity.jp.oecd_cli_trend_restored": ("JPN", "TR"),
}


def oecd_cli_key(area: str, adjustment: str) -> str:
    return f"{area}.M.LI.IX._Z.{adjustment}.IX._Z.H"


def parse_oecd_cli_csv(text: str, area: str, adjustment: str, start: date | None = None) -> dict[date, Decimal]:
    expected = {"DATAFLOW": OECD_CLI_DATAFLOW_ID, "REF_AREA": area, "FREQ": "M", "MEASURE": "LI",
                "UNIT_MEASURE": "IX", "ACTIVITY": "_Z", "ADJUSTMENT": adjustment, "TRANSFORMATION": "IX",
                "TIME_HORIZ": "_Z", "METHODOLOGY": "H", "UNIT_MULT": "0"}
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    if not reader.fieldnames or not {*expected, "TIME_PERIOD", "OBS_VALUE", "OBS_STATUS"} <= set(reader.fieldnames):
        raise ProviderError("OECD CLI CSV schema changed")
    values: dict[date, Decimal] = {}
    seen: set[str] = set()
    for row in reader:
        if any(row.get(name) != value for name, value in expected.items()):
            raise ProviderError("OECD CLI dataflow, area, adjustment, unit or methodology mismatch")
        label = row["TIME_PERIOD"]
        if len(label) != 7 or label[4] != "-" or label in seen:
            raise ProviderError("OECD CLI monthly period is invalid or duplicated")
        seen.add(label)
        if row["OBS_STATUS"] != "A":
            raise ProviderError("OECD CLI observation status is not a normal value")
        try:
            day, value = date.fromisoformat(label + "-01"), Decimal(row["OBS_VALUE"])
        except (ValueError, InvalidOperation) as exc:
            raise ProviderError("OECD CLI observation is invalid") from exc
        if not value.is_finite() or value <= 0 or day > date.today():
            raise ProviderError("OECD CLI value is nonpositive or the period is in the future")
        if start is None or day >= start:
            values[day] = value
    if not values:
        raise ProviderError("OECD CLI has no observations in the requested period")
    return dict(sorted(values.items()))
