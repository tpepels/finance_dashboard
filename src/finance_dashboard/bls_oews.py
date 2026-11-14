"""Original BLS OEWS national hourly wages: matched mean/median, separate from CPS.

Only publisher-indexed, annually archived national workbooks are eligible.
Every value comes from the same SOC 00-0000 all-occupations population.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from io import BytesIO
from urllib.parse import urljoin, urlparse
from zipfile import ZipFile, BadZipFile
import re

from .bis import ProviderError, FetchedSeries

INDEX_URL = "https://www.bls.gov/oes/tables.htm"
SOURCE_KEYS = {
    "labour.us.oews_all_mean_hourly": "NATIONAL/ALL_OCCUPATIONS/H_MEAN",
    "labour.us.oews_all_median_hourly": "NATIONAL/ALL_OCCUPATIONS/H_MEDIAN",
}
_LINK = re.compile(r"^/oes/special-requests/oesm(\d{2})nat\.zip$")


class _PublisherLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if isinstance(href, str):
                self.links.append(href)


def published_archives(html: str, *, today: date | None = None) -> list[tuple[int, str]]:
    """No search-engine or external-domain fallbacks if BLS changes its index."""
    current = today or date.today()
    parser = _PublisherLinks()
    parser.feed(html)
    releases = {}
    for href in parser.links:
        url = urljoin(INDEX_URL, href)
        parsed = urlparse(url)
        match = _LINK.fullmatch(parsed.path)
        if parsed.scheme != "https" or parsed.netloc != "www.bls.gov" or not match:
            continue
        if parsed.query or parsed.fragment:
            continue
        year = 2000 + int(match.group(1))
        if 2021 <= year <= current.year:
            if year in releases and releases[year] != url:
                raise ProviderError("BLS OEWS national release index contains conflicting URLs")
            releases[year] = url
    if 2025 not in releases:
        raise ProviderError("BLS OEWS May 2025 national release missing from original index")
    return sorted(releases.items())


def _decimal(cell) -> Decimal:
    if isinstance(cell, bool):
        raise ProviderError("BLS OEWS national wage is not numeric")
    try:
        result = Decimal(str(cell).strip().replace("$", "").replace(",", ""))
    except (ValueError, InvalidOperation):
        raise ProviderError("BLS OEWS national wage is not numeric") from None
    if not result.is_finite() or not Decimal("0") < result < Decimal("200"):
        raise ProviderError("BLS OEWS hourly wage out of source range")
    return result


def parse_national_rows(rows: list, year: int) -> dict[str, Decimal]:
    """Require exactly one total row; an occupation-specific mean is not valid."""
    columns = ("OCC_CODE", "OCC_TITLE", "TOT_EMP", "H_MEAN", "H_MEDIAN")
    headers = []
    for offset, row in enumerate(rows[:25]):
        names = [str(x).strip().upper().replace(" ", "_") for x in row]
        if all(names.count(col) == 1 for col in columns):
            headers.append((offset, {col: names.index(col) for col in columns}))
    if len(headers) != 1:
        raise ProviderError("BLS OEWS original hourly wage header ambiguous or missing")
    offset, positions = headers[0]
    matches = []
    for row in rows[offset + 1:]:
        if len(row) <= max(positions.values()) or str(row[positions["OCC_CODE"]]).strip() != "00-0000":
            continue
        if str(row[positions["OCC_TITLE"]]).strip().lower() != "all occupations":
            raise ProviderError("BLS OEWS all-occupations identity mismatch")
        try:
            population = Decimal(str(row[positions["TOT_EMP"]]).replace(",", ""))
        except InvalidOperation:
            raise ProviderError("BLS OEWS total employment malformed") from None
        if not 50_000_000 < population < 300_000_000:
            raise ProviderError("BLS OEWS all-occupations population invalid")
        mean = _decimal(row[positions["H_MEAN"]])
        median = _decimal(row[positions["H_MEDIAN"]])
        if not Decimal(".33") < mean / median < Decimal("3"):
            raise ProviderError("BLS OEWS original mean/median ratio invalid")
        matches.append({"H_MEAN": mean, "H_MEDIAN": median})
    if len(matches) != 1:
        raise ProviderError(f"BLS OEWS missing or duplicated national total in {year}")
    return matches[0]


def parse_national_zip(payload: bytes, year: int) -> dict[str, Decimal]:
    """Inspect bounded official ZIP and same-year workbook without extraction."""
    if len(payload) > 8_000_000 or not payload.startswith(b"PK\x03\x04"):
        raise ProviderError("BLS OEWS response is not an approved national ZIP")
    name = f"national_M{year}_dl.xlsx"
    try:
        with ZipFile(BytesIO(payload)) as archive:
            infos = [item for item in archive.infolist() if not item.is_dir()]
            if len(infos) != 1 or infos[0].filename != name:
                raise ProviderError("BLS OEWS national workbook year/identity mismatch")
            if infos[0].file_size > 12_000_000:
                raise ProviderError("BLS OEWS source workbook exceeds size bound")
            data = archive.read(name)
    except ProviderError:
        raise
    except (BadZipFile, OSError, RuntimeError, ValueError) as exc:
        raise ProviderError("BLS OEWS ZIP is invalid") from exc
    if len(data) > 12_000_000 or not data.startswith(b"PK\x03\x04"):
        raise ProviderError("BLS OEWS national XLSX is invalid")
    from python_calamine import CalamineWorkbook
    try:
        workbook = CalamineWorkbook.from_filelike(BytesIO(data))
        if len(workbook.sheet_names) != 1:
            raise ProviderError("BLS OEWS national workbook has ambiguous worksheets")
        rows = workbook.get_sheet_by_index(0).to_python()
    except ProviderError:
        raise
    except (OSError, ValueError, RuntimeError, TypeError) as exc:
        raise ProviderError("BLS OEWS national XLSX cannot be parsed") from exc
    return parse_national_rows(rows, year)


def fetch_bls_oews(self, series_id, start, item, key):
    """Called exclusively through the existing governed ProviderRouter."""
    if SOURCE_KEYS.get(series_id) != key:
        raise ProviderError("Unregistered BLS OEWS original wage measure")
    index = self._get_document(INDEX_URL, headers={"Accept": "text/html"})
    releases = published_archives(index.text)
    observations = {}
    for year, url in releases:
        day = date(year, 5, 1)
        if start is not None and day < start:
            continue
        response = self._get_document(url)
        observations[day] = parse_national_zip(response.content, year)[key.rsplit("/", 1)[-1]]
    if not observations:
        raise ProviderError("BLS OEWS original history has no eligible published year")
    return FetchedSeries(series_id, INDEX_URL, None, observations)
