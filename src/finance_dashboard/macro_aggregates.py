"""Publicly published aggregate global equity valuation observations.

Siblis figures are source-published sparse snapshots, not a complete monthly
history. Reuse rights are restricted: an Actions artifact is not public hosting.
Never combine this index P/E with World Bank's different listed equity universe
as though the source constituents or earnings normalization match.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import re

from .remaining_sources import HtmlTables

SIBLIS_WORLD_PE_URL = "https://siblisresearch.com/data/global-markets-pe/"

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
    "oct": 10, "nov": 11, "dec": 12,
}


class AggregateSourceError(ValueError):
    pass


def _month_date(raw: str) -> date | None:
    text = " ".join(raw.strip().replace(",", "").split())
    match = re.fullmatch(r"(\d{4})\s+([A-Za-z]+)|([A-Za-z]+)\s+(\d{4})", text)
    if not match:
        return None
    if match.group(1):
        year, month = int(match.group(1)), match.group(2).lower().rstrip(".")
    else:
        year, month = int(match.group(4)), match.group(3).lower().rstrip(".")
    if month not in MONTHS or not 1970 <= year <= date.today().year:
        raise AggregateSourceError("Invalid published Siblis global P/E month")
    return date(year, MONTHS[month], 1)


def parse_siblis_world_pe(html: str, *, start: date | None = None) -> dict[date, Decimal]:
    """Parse only the official 'Historical trailing P/E' global column.

    The public table contains annual December readings and a recent month.
    Never fill intervening months, infer profits from foreign-universe market
    capitalization, or imply these are a complete subscriber history.
    """
    if not isinstance(html, str) or not html.strip():
        raise AggregateSourceError("Empty published Siblis world equity page")
    if "Global stock market valuations" not in html or "Historical trailing P/E" not in html:
        raise AggregateSourceError("Unexpected Siblis world-market source identity")
    tables = HtmlTables()
    tables.feed(html)
    candidates = []
    for rows in tables.tables:
        if not rows:
            continue
        first = [str(c).strip().lower() for c in rows[0]]
        if len(first) >= 3 and first[0] == "month" and first[1] == "global" and "developed" in first[2]:
            candidates.append(rows)
    if len(candidates) != 1:
        raise AggregateSourceError("Missing or ambiguous global historical trailing P/E table")
    observations: dict[date, Decimal] = {}
    years = set()
    for row in candidates[0][1:]:
        if not row:
            continue
        stamp = _month_date(str(row[0]))
        if stamp is None:
            raise AggregateSourceError("Unrecognized dated global P/E row")
        if len(row) < 2:
            raise AggregateSourceError("Missing global P/E value")
        try:
            value = Decimal(str(row[1]).replace(",", "").strip())
        except InvalidOperation as exc:
            raise AggregateSourceError("Invalid global P/E value") from exc
        if not value.is_finite() or not Decimal("1") <= value <= Decimal("300"):
            raise AggregateSourceError("Impossible world trailing P/E value")
        if stamp in observations:
            raise AggregateSourceError("Duplicate Siblis global P/E month")
        if stamp.month == 12:
            years.add(stamp.year)
        if start is None or stamp >= start:
            observations[stamp] = value
    # Detect a redesigned/truncated source rather than treating a sample
    # or a temporary page error as the complete annual history.
    if len(years) < 9 or min(years) > 2017:
        raise AggregateSourceError("Incomplete published global annual P/E observations")
    if not observations:
        raise AggregateSourceError("No Siblis world P/E in requested period")
    return dict(sorted(observations.items()))


def aggregate_earnings_yield(pe: dict[date, Decimal]) -> dict[date, Decimal]:
    """Siblis-normalized index earnings / index market cap * 100, in percent."""
    if not pe:
        raise AggregateSourceError("Cannot derive earnings yield from empty P/E")
    out: dict[date, Decimal] = {}
    for stamp, value in pe.items():
        if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
            raise AggregateSourceError("Invalid world P/E for earnings yield")
        out[stamp] = Decimal(100) / value
    return dict(sorted(out.items()))


def world_listed_market_cap_gdp(
    cap_usd: dict[date, Decimal],
    gdp_usd: dict[date, Decimal],
    *,
    start: date | None = None,
) -> dict[date, Decimal]:
    """World Bank WLD market cap USD / WLD current-dollar world GDP * 100.

    Both are World Bank WDI aggregates but market-cap coverage differs from
    GDP coverage. This is a published-WLD numerator *derived ratio*, not the
    WDI WLD 'weighted country average' CM.MKT.LCAP.GD.ZS indicator.
    """
    out = {}
    for period in sorted(set(cap_usd) & set(gdp_usd)):
        if start and period < start:
            continue
        c, g = cap_usd[period], gdp_usd[period]
        if not all(isinstance(v, Decimal) and v.is_finite() for v in (c, g)):
            raise AggregateSourceError("Invalid World Bank capitalization or GDP")
        if c < 0 or g <= 0:
            raise AggregateSourceError("Negative world capitalization or nonpositive GDP")
        out[period] = c / g * Decimal(100)
    if not out:
        raise AggregateSourceError("No matched years of world market capitalization and GDP")
    return out
