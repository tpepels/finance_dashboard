"""Original Federal Reserve G.17 industrial-production diffusion history.

The published index is the percentage of G.17 series that increased over the
stated span plus one-half of those unchanged (release Table 6 note). It is not
an analyst-constructed sector share, an NBER classification or a forecast.
The file is fixed-width: month m ends at column 33 + 10 (m - 1), and blank
cells are genuinely missing months that must not be shifted left.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import re

from .bis import ProviderError

G17_DIFFUSION_URL = "https://www.federalreserve.gov/Releases/G17/Current/ipdisk/diff_sa.txt"
G17_DIFFUSION_SERIES = {
    "activity.us.industrial_production_diffusion_1m": ("DIFFUSION_1", "one month earlier"),
    "activity.us.industrial_production_diffusion_3m": ("DIFFUSION_3", "three months earlier"),
    "activity.us.industrial_production_diffusion_6m": ("DIFFUSION_6", "six months earlier"),
}
FIRST_MONTH_END_COLUMN = 33
COLUMN_WIDTH = 10


def parse_g17_diffusion(text: str, *, block: str, span: str, start: date | None = None) -> dict[date, Decimal]:
    """Accept exactly one named block of year-by-month rows; reject any other layout."""
    lines = text.lstrip("\ufeff").splitlines()
    header = f'"{block}: Diffusion index of industrial production, {span}"'
    positions = [index for index, line in enumerate(lines) if line.strip() == header]
    if len(positions) != 1:
        raise ProviderError("G.17 diffusion block identity or span changed")
    values: dict[date, Decimal] = {}
    previous_year = None
    rows = 0
    for line in lines[positions[0] + 1:]:
        if not line.strip():
            continue
        if re.match(r'^"DIFFUSION_\d+:', line.strip()):
            break
        cells = [(m.start(), m.end(), m.group()) for m in re.finditer(r"\S+", line)]
        if len(cells) < 3 or cells[0][2] != f'"{block}"' or not re.fullmatch(r"\d{4}", cells[1][2]):
            raise ProviderError("G.17 diffusion row identity or year is malformed")
        year = int(cells[1][2])
        if previous_year is not None and year != previous_year + 1:
            raise ProviderError("G.17 diffusion years are not consecutive")
        previous_year = year
        rows += 1
        for _begin, end, raw in cells[2:]:
            offset, remainder = divmod(end - FIRST_MONTH_END_COLUMN, COLUMN_WIDTH)
            if remainder or not 0 <= offset <= 11:
                raise ProviderError("G.17 diffusion value is outside the fixed monthly columns")
            try:
                value = Decimal(raw)
            except InvalidOperation as exc:
                raise ProviderError("G.17 diffusion value is not numeric") from exc
            if not value.is_finite() or not 0 <= value <= 100:
                raise ProviderError("G.17 diffusion index is outside its 0-100 percentage domain")
            day = date(year, offset + 1, 1)
            if day > date.today() or day in values:
                raise ProviderError("G.17 diffusion contains a future or duplicated period")
            if start is None or day >= start:
                values[day] = value
    if not rows or not values:
        raise ProviderError("G.17 diffusion has no observations in the requested period")
    return values
