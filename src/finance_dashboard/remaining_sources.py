"""Official BEA replacement-cost Q1, MSCI ACWI NETR and gold/index correlation.

Never substitute a public ETF for a total-return index or index price return
for net total return. Monthly-average gold and monthly-mean ACWI index levels
are aligned in USD; the source gold measure is the World Bank Pink Sheet.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from typing import Any

BEA_Q_URL = "https://apps.bea.gov/scb/issues/2026/05-may/0526-domestic-returns.htm"
MSCI_LEVELS_URL = "https://app2.msci.com/products/service/index/indexmaster/getLevelDataForGraph"
MSCI_ACWI_INDEX_CODE = "892400"
MSCI_VARIANT = "NETR"


class DerivedDataError(ValueError):
    pass


class HtmlTables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = []
        self.table = None
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in ("th", "td") and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("th", "td") and self.cell is not None and self.row is not None:
            self.row.append("".join(self.cell).strip())
            self.cell = None
        elif tag == "tr" and self.table is not None and self.row is not None:
            self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            self.tables.append(self.table)
            self.table = None


def parse_bea_q1(html: str, *, start: date | None = None) -> dict[date, Decimal]:
    """Extract BEA Table E Q1, not Q2/Q3 or the Fed equities/net-worth ratio."""
    if "Q-Type Ratios" not in html or "produced assets" not in html:
        raise DerivedDataError("BEA source does not identify replacement-cost Q ratios")
    parser = HtmlTables()
    parser.feed(html)
    candidates = []
    for table in parser.tables:
        if not table or len(table[0]) < 4:
            continue
        headings = [str(v).upper() for v in table[0]]
        if not headings[1].startswith("Q1") or not headings[2].startswith("Q2") or not headings[3].startswith("Q3"):
            continue
        if not any(row and row[0] == "1960" for row in table[1:]):
            continue
        candidates.append(table)
    if len(candidates) != 1:
        raise DerivedDataError("BEA Table E has missing or ambiguous Q1 columns")
    values = {}
    for row in candidates[0][1:]:
        if len(row) < 4 or not str(row[0]).isdigit() or len(row[0]) != 4:
            raise DerivedDataError("Malformed BEA Table E observation")
        yr = int(row[0])
        day = date(yr, 1, 1)
        try:
            v = Decimal(row[1].replace(",", ""))
            q2 = Decimal(row[2].replace(",", ""))
            q3 = Decimal(row[3].replace(",", ""))
        except InvalidOperation as exc:
            raise DerivedDataError("BEA ratio column is not numeric") from exc
        if not all(q.is_finite() and q > 0 for q in (v, q2, q3)):
            raise DerivedDataError("Nonpositive or nonfinite BEA Tobin Q ratio")
        if day in values:
            raise DerivedDataError("Duplicate BEA Q year")
        if day <= date.today() and (start is None or day >= start):
            values[day] = v
    if not values or (start is None and (date(1960,1,1) not in values or len(values) < 60)):
        raise DerivedDataError("Incomplete BEA historical replacement-cost Q1 series")
    return dict(sorted(values.items()))


def parse_msci_acwi(payload: Any, *, start: date | None = None) -> dict[date, Decimal]:
    """MSCI 892400 NETR USD levels; one observation per actual provider date."""
    if not isinstance(payload, dict) or str(payload.get("msci_index_code")) != MSCI_ACWI_INDEX_CODE:
        raise DerivedDataError("MSCI index identity mismatch")
    if payload.get("index_variant_type") != MSCI_VARIANT or payload.get("ISO_currency_symbol") != "USD":
        raise DerivedDataError("MSCI return method or currency mismatch")
    rows = (payload.get("indexes") or {}).get("INDEX_LEVELS")
    if not isinstance(rows, list):
        raise DerivedDataError("MSCI levels array missing")
    values = {}
    for row in rows:
        try:
            stamp = str(row["calc_date"])
            if len(stamp) != 8 or not stamp.isdigit():
                raise ValueError("Invalid index date")
            day = date(int(stamp[:4]),int(stamp[4:6]),int(stamp[6:8]))
            val = Decimal(str(row["level_eod"]))
        except (KeyError, ValueError, InvalidOperation, TypeError) as exc:
            raise DerivedDataError("Invalid MSCI index observation") from exc
        if not val.is_finite() or val <= 0:
            raise DerivedDataError("Nonpositive MSCI net return level")
        if day > date.today() or (start and day < start):
            continue
        if day in values:
            raise DerivedDataError("Duplicate MSCI index date")
        values[day] = val
    if not values:
        raise DerivedDataError("No MSCI net total-return levels")
    return dict(sorted(values.items()))


def _by_month_average(levels: dict[date, Decimal]) -> dict[date, Decimal]:
    grouped = defaultdict(list)
    for day, value in levels.items():
        grouped[date(day.year,day.month,1)].append(value)
    return {month:sum(vals)/len(vals) for month,vals in grouped.items()}


def _next_month(d: date) -> date:
    return date(d.year+1,1,1) if d.month==12 else date(d.year,d.month+1,1)


def gold_acwi_rolling_correlation(
    gold_monthly_average: dict[date, Decimal],
    acwi_daily_netr: dict[date, Decimal],
    *,
    window: int = 36,
    start: date | None = None,
) -> dict[date, Decimal]:
    """Trailing Pearson on monthly gold and MSCI ACWI NETR *arithmetic returns*.

    Compare monthly averages in both series rather than mixing gold monthly
    average with index month-end close. Full consecutive months are required;
    omit the ongoing calendar month until its end.
    """
    if window < 12 or window > 120:
        raise ValueError("Correlation window must be 12 to 120 months")
    means = _by_month_average(acwi_daily_netr)
    gold = {date(d.year,d.month,1):v for d,v in gold_monthly_average.items()}
    current_month=date.today().replace(day=1)
    common = sorted(d for d in set(gold)&set(means) if d < current_month)
    gold_returns = {}
    equity_returns = {}
    for month in common:
        prev = date(month.year-1,12,1) if month.month==1 else date(month.year,month.month-1,1)
        if prev in gold and prev in means and all(x > 0 for x in (gold[prev],gold[month],means[prev],means[month])):
            gold_returns[month] = gold[month]/gold[prev]-1
            equity_returns[month] = means[month]/means[prev]-1
    months = sorted(set(gold_returns)&set(equity_returns))
    out = {}
    for end in range(window-1,len(months)):
        sample = months[end-window+1:end+1]
        if any(_next_month(a)!=b for a,b in zip(sample,sample[1:])):
            continue
        x = [gold_returns[d] for d in sample]
        y = [equity_returns[d] for d in sample]
        n = Decimal(window)
        mx = sum(x)/n
        my = sum(y)/n
        numerator = sum((a-mx)*(b-my) for a,b in zip(x,y))
        dx = sum((a-mx)**2 for a in x)
        dy = sum((b-my)**2 for b in y)
        if dx <= 0 or dy <= 0:
            continue
        value = numerator / (dx*dy).sqrt()
        if not value.is_finite() or abs(value)>Decimal("1.00000001"):
            raise DerivedDataError("Pearson correlation outside valid range")
        out[sample[-1]] = max(Decimal(-1),min(Decimal(1),value))
    if not out:
        raise DerivedDataError("Insufficient consecutive months for gold/ACWI correlation")
    return dict(sorted((d,v) for d,v in out.items() if start is None or d>=start))


def global_output_to_labour_income_ratio(
    labour_share: dict[date, Decimal], *, start: date | None = None,
) -> dict[date, Decimal]:
    """Ratio (world GDP / total hours) / (world labour income / total hours).

    The same hours denominator cancels; GDP/labour income = 100/ILO SDG
    10.4.1 labour-income share percent. Labour income includes imputed
    self-employment earnings. It is NOT an independently observed hourly
    employee compensation series, and can be interpreted only with this scope.
    """
    result = {}
    for day, share in labour_share.items():
        if not share.is_finite() or share <= 0 or share > 100:
            raise DerivedDataError("Invalid global ILO labour income share")
        if start is None or day >= start:
            result[day] = Decimal(100)/share
    if not result:
        raise DerivedDataError("No world productivity-to-labour-income ratios")
    return dict(sorted(result.items()))
