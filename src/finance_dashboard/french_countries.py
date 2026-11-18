"""Kenneth French international country portfolios (F-F_International_Countries.zip).

The archive holds one fixed-width ``.Dat`` file per country. Each file has
monthly value-weighted market (``Mkt``) and value/growth portfolio returns in
USD and in local currency (percent), followed by annual blocks, and then the
annual value-weighted average valuation ratios (``Ratios x 100``: B/M, E/P,
CE/P and dividend yield). Every block comes in two universes; only "All 4 Data
Items Not Reqd" (the broader universe) is used. -99.99 and -999 are missing
values. The files carry no database-vintage line; the archive member dates and
the HTTP modification time are recorded instead. Malaysia (ends 2001-10) is
not registered.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import io
import re
import zipfile

from .bis import ProviderError

FRENCH_COUNTRIES_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_International_Countries.zip"
ARCHIVE = "F-F_International_Countries.zip"
# ISO-style code -> archive member
COUNTRY_MEMBERS = {
    "gb": "UK.Dat", "at": "Austria.Dat", "au": "Austrlia.Dat", "be": "Belgium.Dat", "ca": "Canada.Dat",
    "dk": "Denmark.Dat", "fi": "Finland.Dat", "fr": "France.Dat", "de": "Germany.Dat", "hk": "HongKong.Dat",
    "ie": "Ireland.Dat", "it": "Italy.Dat", "jp": "Japan.Dat", "nl": "Nethrlnd.Dat", "nz": "NewZland.Dat",
    "no": "Norway.Dat", "sg": "Singapor.Dat", "es": "Spain.Dat", "se": "Sweden.Dat", "ch": "Swtzrlnd.Dat",
}
ALL_MEMBERS = frozenset(COUNTRY_MEMBERS.values()) | {"Malaysia.Dat"}
# series suffix -> (block, column, frequency)
_MEASURES = {
    "market_usd": ("Dollar", "Mkt", "M"),
    "market_local": ("Local", "Mkt", "M"),
    "book_to_market": ("Ratios", "B/M", "A"),
    "earnings_yield": ("Ratios", "E/P", "A"),
    "dividend_yield": ("Ratios", "Yld", "A"),
}
FRENCH_COUNTRY_SERIES = {
    f"{'returns' if measure.startswith('market') else 'valuation'}.french.country.{code}.{measure}": (code, measure)
    for code in COUNTRY_MEMBERS for measure in _MEASURES
}
_UNIVERSE = "All 4 Data Items Not Reqd"
_RETURN_HEADER = re.compile(r"^\s*Value-Weight (Dollar|Local)\s+Returns\s+(All 4 Data Items (?:Not Reqd|Required))\s*$")
_RETURN_COLUMNS = ["Mkt", "High", "Low", "High", "Low", "High", "Low", "High", "Low", "Zero"]
_RATIO_COLUMNS = ["Firms", "B/M", "E/P", "CE/P", "Yld"]
_MISSING = {Decimal("-99.99"), Decimal("-999")}


def french_country_source_key(series_id: str) -> str:
    code, measure = FRENCH_COUNTRY_SERIES[series_id]
    block, column, _frequency = _MEASURES[measure]
    return f"{ARCHIVE}#{COUNTRY_MEMBERS[code]}:{block}:{column}"


def french_country_frequency(series_id: str) -> str:
    return _MEASURES[FRENCH_COUNTRY_SERIES[series_id][1]][2]


def country_members(raw: bytes) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if (len(names) != len(set(names)) or set(names) != ALL_MEMBERS
                    or sum(info.file_size for info in infos) > 20_000_000):
                raise ValueError("member identity or size")
            return {name: archive.read(name) for name in names}
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        raise ProviderError("French international country archive identity mismatch") from exc


def _number(token: str) -> Decimal | None:
    try:
        value = Decimal(token)
    except InvalidOperation as exc:
        raise ProviderError("French country value is not numeric") from exc
    if not value.is_finite():
        raise ProviderError("French country value is not finite")
    return None if value in _MISSING else value


def parse_country_file(text: str, measure: str) -> dict[date, Decimal]:
    """Read one measure from one country file's "Not Reqd" universe."""
    block, column, frequency = _MEASURES[measure]
    lines = text.replace("\r\n", "\n").split("\n")
    if block == "Ratios":
        starts = [i for i, line in enumerate(lines) if line.strip() == "Average of Annual Value-Weight Averages"]
        starts = [i for i in starts if i + 2 < len(lines) and lines[i + 2].strip() == _UNIVERSE]
        if len(starts) != 1 or not lines[starts[0] + 3].strip().startswith("Ratios x 100"):
            raise ProviderError("French country ratio block missing or ambiguous")
        header = next((i for i in range(starts[0] + 4, min(starts[0] + 8, len(lines))) if lines[i].split() == _RATIO_COLUMNS), None)
        if header is None:
            raise ProviderError("French country ratio columns changed")
        index, row_pattern = _RATIO_COLUMNS.index(column), r"\d{4}"
    else:
        starts = [i for i, line in enumerate(lines)
                  if (m := _RETURN_HEADER.match(line)) and m.group(1) == block and m.group(2) == _UNIVERSE]
        if not starts:
            raise ProviderError("French country return block missing")
        header = starts[0] + 2
        if lines[header].split() != _RETURN_COLUMNS:
            raise ProviderError("French country return columns changed")
        index, row_pattern = _RETURN_COLUMNS.index(column), r"\d{6}"
        first_row = lines[header + 1].split()[:1]
        if not first_row or not re.fullmatch(row_pattern, first_row[0]):
            raise ProviderError("French country monthly block is not first")
    values: dict[date, Decimal] = {}
    for line in lines[header + 1:]:
        tokens = line.split()
        if not tokens:
            if values:
                break
            continue
        if not re.fullmatch(row_pattern, tokens[0]) or len(tokens) != len(_RATIO_COLUMNS if block == "Ratios" else _RETURN_COLUMNS) + 1:
            raise ProviderError("French country row is malformed")
        year = int(tokens[0][:4])
        month = int(tokens[0][4:6]) if frequency == "M" else 1
        if not 1 <= month <= 12:
            raise ProviderError("French country month is invalid")
        day = date(year, month, 1)
        if day in values or day > date.today():
            raise ProviderError("French country period duplicated or in the future")
        value = _number(tokens[index + 1])
        if value is not None:
            values[day] = value
    if not values:
        raise ProviderError("French country measure contains no observations")
    return values


def parse_french_country(raw: bytes, series_id: str, start: date | None = None) -> dict[date, Decimal]:
    if series_id not in FRENCH_COUNTRY_SERIES:
        raise ProviderError("Unregistered French country series")
    code, measure = FRENCH_COUNTRY_SERIES[series_id]
    members = country_members(raw)
    try:
        text = members[COUNTRY_MEMBERS[code]].decode("ascii")
    except UnicodeError as exc:
        raise ProviderError("French country file encoding invalid") from exc
    values = parse_country_file(text, measure)
    return {day: value for day, value in values.items() if start is None or day >= start}
