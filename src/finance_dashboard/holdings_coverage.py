"""Field coverage of original fund holdings, weighted by position value.

Coverage is the share of a fund's security positions, by absolute reported
value, whose original row reports a field. Cash, FX, futures and other
derivative rows are not securities; their count is reported separately.
Nothing is inferred: a field counts only where the publisher's row has it.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re

FIELDS = ("security_identifier", "issuer_identifier", "holding_name", "country", "sector")
_NOT_REPORTED = {"", "N/A", "NA", "-", "NONE", "NOT AVAILABLE", "00000000000000000000"}
# Native iShares/Vanguard asset classes that are not security positions.
NON_SECURITY_CLASSES = frozenset({"Cash", "FX", "Futures", "Forwards", "Swaps", "Options",
                                  "Money Market", "Cash Collateral and Margins"})
_LEI = re.compile(r"[A-Z0-9]{20}")
_ISO2 = re.compile(r"[A-Z]{2}")
_PRECISION = Decimal("0.000001")


def reported(value) -> bool:
    return isinstance(value, str) and value.strip().upper() not in _NOT_REPORTED


def _amount(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return abs(Decimal(str(value).replace(",", "")))
    except InvalidOperation:
        return None


def _lei(value) -> bool:
    return isinstance(value, str) and bool(_LEI.fullmatch(value)) and value != "0" * 20


def field_weight_coverage(rows) -> dict:
    """``rows`` yields ``(value, {field: bool})`` for security positions only."""
    total = Decimal(0)
    covered = dict.fromkeys(FIELDS, Decimal(0))
    counted = unvalued = 0
    for value, fields in rows:
        if value is None:
            unvalued += 1
            continue
        counted += 1
        total += value
        for field in FIELDS:
            if fields.get(field):
                covered[field] += value
    return {"security_positions": counted, "unvalued_security_positions": unvalued,
            "security_value": str(total),
            "fields": {field: str((covered[field] / total).quantize(_PRECISION)) if total > 0 else None
                       for field in FIELDS},
            "weighting": "Absolute reported position value of security rows; cash, FX and derivative rows excluded."}


def sec_coverage(positions) -> dict:
    """N-PORT Part C rows; derivative contracts are not security positions."""
    def rows():
        for p in positions:
            if p.get("is_derivative"):
                continue
            yield _amount(p.get("value_usd")), {
                "security_identifier": reported(p.get("cusip")) or any(
                    reported(i.get("value")) for i in p.get("security_identifiers", [])),
                "issuer_identifier": _lei(p.get("lei")),
                "holding_name": reported(p.get("name")),
                "country": isinstance(p.get("issuer_country"), str)
                           and bool(_ISO2.fullmatch(p["issuer_country"])),
                "sector": False}
    return field_weight_coverage(rows())


def ucits_coverage(positions) -> dict:
    """iShares CSV/annual-report and Vanguard report rows, as natively labelled."""
    def rows():
        for p in positions:
            if p.get("asset_class") in NON_SECURITY_CLASSES:
                continue
            value = next((p[key] for key in ("market_value", "value_usd", "value_usd_thousands")
                          if p.get(key) is not None), None)
            yield _amount(value), {
                "security_identifier": reported(p.get("isin")) or reported(p.get("cusip")),
                "issuer_identifier": _lei(p.get("lei")),
                "holding_name": reported(p.get("name")),
                "country": reported(p.get("reported_location")) or reported(p.get("reported_country_label")),
                "sector": reported(p.get("sector"))}
    return field_weight_coverage(rows())
