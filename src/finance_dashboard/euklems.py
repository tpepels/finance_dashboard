"""EU KLEMS & INTANProd 2025 per-country workbooks (Luiss Lab of European Economics).

Matched-scope industry inputs for L01: value added at current prices (VA_CP),
its price index (VA_PI, 2015=100) and hours worked by persons engaged
(H_EMP) from the national-accounts workbook; labour compensation including
the imputed self-employed share (LAB) from the growth-accounts workbook.
Files are the publisher's own Dropbox shares, read from Dropbox's direct
content host so no redirect leaves the governed route.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import io

from python_calamine import CalamineWorkbook

from .bis import ProviderError

EUKLEMS_ROOT = "https://dl.dropboxusercontent.com/"
DOWNLOAD_PAGE = "https://euklems-intanprod-llee.luiss.it/download/"
# Publisher geo codes; the UK is "UK", not ISO "GB".
EUKLEMS_FILES = {
    "US": {"national": "s/bvnqzfet1sixenz/US_national%20accounts.xlsx",
           "growth": "s/bvv0nzietfbrrrq/US_growth%20accounts.xlsx"},
    "DE": {"national": "s/v3zx4ypon254g6g/DE_national%20accounts.xlsx",
           "growth": "s/juj6ac3bku25qki/DE_growth%20accounts.xlsx"},
    "FR": {"national": "s/6yj0d4qzvzp46hl/FR_national%20accounts.xlsx",
           "growth": "s/9nboo27zfp89lia/FR_growth%20accounts.xlsx"},
    "PT": {"national": "s/inbjn5c6a2094p5/PT_national%20accounts.xlsx",
           "growth": "s/0n5fxqi92iwyylw/PT_growth%20accounts.xlsx"},
    "UK": {"national": "s/kao3sofun6nhxag/UK_national%20accounts.xlsx",
           "growth": "s/i9nfi5mvn313vwx/UK_growth%20accounts.xlsx"},
    "IT": {"national": "s/izfljd8d1l5d2f0/IT_national%20accounts.xlsx",
           "growth": "s/4g5ncbd8mnfkrwp/IT_growth%20accounts.xlsx"},
    "ES": {"national": "s/vv4otmgaqxr1cqk/ES_national%20accounts.xlsx",
           "growth": "s/99elo7bm2fvmrjk/ES_growth%20accounts.xlsx"},
    "NL": {"national": "s/k34sqtsg9ywxtvz/NL_national%20accounts.xlsx",
           "growth": "s/z6tzbjyp5o2626v/NL_growth%20accounts.xlsx"},
}
EUKLEMS_VARIABLES = {"VA_CP": "national", "VA_PI": "national", "H_EMP": "national", "LAB": "growth"}
EUKLEMS_INDUSTRIES = frozenset({"TOT"})


def euklems_url(key: str) -> str:
    """``US/TOT/VA_CP`` -> the pinned workbook that publishes that variable."""
    geo, industry, variable = key.split("/")
    if geo not in EUKLEMS_FILES or industry not in EUKLEMS_INDUSTRIES or variable not in EUKLEMS_VARIABLES:
        raise ValueError("unapproved_euklems_series")
    return EUKLEMS_ROOT + EUKLEMS_FILES[geo][EUKLEMS_VARIABLES[variable]]


def _number(value) -> Decimal | None:
    if value in (None, "", "NA"):
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise ProviderError("EU KLEMS cell is not numeric") from None
    if not number.is_finite():
        raise ProviderError("EU KLEMS cell is not finite")
    return number


def parse_euklems_workbook(raw: bytes, key: str, start: date | None = None) -> dict[date, Decimal]:
    geo, industry, variable = key.split("/")
    workbook = CalamineWorkbook.from_filelike(io.BytesIO(raw))
    if variable not in workbook.sheet_names:
        raise ProviderError("EU KLEMS workbook lacks the variable sheet")
    rows = workbook.get_sheet_by_name(variable).to_python()
    header = [str(cell).strip() for cell in rows[0]]
    for name in ("nace_r2_code", "geo_code", "var"):
        if header.count(name) != 1:
            raise ProviderError("EU KLEMS sheet header differs from the published layout")
    years = {index: int(float(cell)) for index, cell in enumerate(header)
             if cell.replace(".0", "").isdigit() and len(cell.replace(".0", "")) == 4}
    matches = [row for row in rows[1:] if str(row[header.index("nace_r2_code")]).strip() == industry]
    if (len(matches) != 1 or str(matches[0][header.index("geo_code")]).strip() != geo
            or str(matches[0][header.index("var")]).strip() != variable or not years):
        raise ProviderError("EU KLEMS returned a different series")
    out = {}
    for index, year in sorted(years.items(), key=lambda item: item[1]):
        value = _number(matches[0][index] if index < len(matches[0]) else None)
        if value is not None and (start is None or year >= start.year):
            out[date(year, 1, 1)] = value
    if not out:
        raise ProviderError("EU KLEMS series has no observations")
    return out
