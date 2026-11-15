"""Three official-source adapters using the existing managed HTTP router and response archive.

No alternative HTTP client, background job or persistence path is created here.
The SEC series are bounded N-MFP3 observations from the exact publisher files,
not a claim that a reporting-fund sample covers every US cash-equivalent.
"""
from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from io import BytesIO, StringIO
import re
from urllib.parse import urljoin, urlparse
from zipfile import BadZipFile, ZipFile

from .bis import FetchedSeries, ProviderError
from .provider_parsers import parse_ecb_csv

DWA_BASE = "https://data-api.ecb.europa.eu/service/data/DWA/"
EUROSTAT_HPI_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hpi_q"
SEC_NMFP_INDEX = "https://www.sec.gov/data-research/sec-markets-data/dera-form-n-mfp-data-sets"
SEC_NMFP_ROOT = "https://www.sec.gov/files/dera/data/form-n-mfp-data-sets/"
DWA_AREAS = ("PT", "DE", "FR", "I9")
DWA_GROUPS = ("T10", "B50")
HPI_AREAS = ("PT", "DE", "FR", "EA20", "EU27_2020")
HPI_PURCHASES = ("TOTAL", "DW_NEW", "DW_EXST")
SEC_METRICS = ("NET_ASSETS_MUSD", "WAM_DAYS", "WAL_DAYS", "WEEKLY_LIQUIDITY_PCT")
_SEC_FILE = re.compile(r"/files/dera/data/form-n-mfp-data-sets/(\d{8})-(\d{8})_nmfp\.zip", re.I)
_MONTHS = ("January","February","March","April","May","June","July","August",
           "September","October","November","December")


def _number(raw, label: str, *, maximum=Decimal("1E20")) -> Decimal:
    try:
        value = Decimal(str(raw).strip().replace(",", ""))
    except (InvalidOperation, TypeError, ValueError):
        raise ProviderError(f"{label} has an invalid original numeric value") from None
    if not value.is_finite() or value < 0 or value > maximum:
        raise ProviderError(f"{label} is outside the original numeric bounds")
    return value


def fetch_ecb_dwa(self, sid, start, item, key):
    """Only source-verified net-household-wealth shares; no inferred middle group."""
    parts = key.split(".")
    if (len(parts) != 11 or parts[0] != "DWA" or parts[1] != "Q"
            or parts[2] not in DWA_AREAS or parts[3:7] != ["S14","_Z","_Z","NWA"]
            or parts[7] not in DWA_GROUPS or parts[8:] != ["PT","S","N"]):
        raise ProviderError("Unapproved ECB DWA household distribution key")
    if item["geography"] != ("EA" if parts[2] == "I9" else parts[2]):
        raise ProviderError("ECB DWA series geography mismatch")
    url = DWA_BASE + ".".join(parts[1:])
    params = {"format":"csvdata"}
    if start is not None:
        params["startPeriod"] = f"{start.year}-Q{(start.month-1)//3+1}"
    response = self._get_document(url, params=params)
    observations = parse_ecb_csv(response.text, key, "Q")
    if any(value < 0 or value > 100 for value in observations.values()):
        raise ProviderError("ECB DWA percentage share outside 0 to 100")
    return FetchedSeries(sid, str(response.request.url), None, observations)


def parse_eurostat_hpi(payload: dict, *, area: str, purchase: str) -> dict[date, Decimal]:
    """Decode the publisher's JSON-stat 2 multidimensional coordinates exactly."""
    if area not in HPI_AREAS or purchase not in HPI_PURCHASES:
        raise ProviderError("Unapproved Eurostat HPI scope")
    if not isinstance(payload, dict) or payload.get("class") != "dataset":
        raise ProviderError("Eurostat HPI response is not a JSON-stat dataset")
    dims, sizes = payload.get("id"), payload.get("size")
    if (not isinstance(dims, list) or not isinstance(sizes, list)
            or len(dims) != len(sizes) or len(dims) != 5
            or set(dims) != {"freq","purchase","unit","geo","time"}):
        raise ProviderError("Eurostat HPI dimensions differ from approved dataset")
    wanted = {"freq":"Q","purchase":purchase,"unit":"I15_Q","geo":area}
    dimension = payload.get("dimension")
    if not isinstance(dimension, dict):
        raise ProviderError("Eurostat HPI dimension metadata missing")
    indexes = {}
    for dimension_id in dims:
        meta = dimension.get(dimension_id, {})
        category = meta.get("category", {}) if isinstance(meta, dict) else {}
        index = category.get("index")
        if not isinstance(index, dict) or len(index) != sizes[dims.index(dimension_id)]:
            raise ProviderError("Eurostat HPI category positions inconsistent")
        indexes[dimension_id] = index
        if dimension_id in wanted and wanted[dimension_id] not in index:
            raise ProviderError("Eurostat HPI returned a different series")
    # All non-time coordinates are explicitly constrained; disallow a response
    # that contains multiple series so a broad dataset cannot masquerade as one.
    if any(sizes[dims.index(dimension_id)] != 1 for dimension_id in wanted):
        raise ProviderError("Eurostat HPI must contain exactly one selected series")
    values = payload.get("value")
    if not isinstance(values, dict):
        raise ProviderError("Eurostat HPI observations object missing")
    reverse_time = {position:label for label,position in indexes["time"].items()}
    output = {}
    for flat_position, raw in values.items():
        try:
            offset = int(flat_position)
        except (ValueError, TypeError):
            raise ProviderError("Eurostat HPI observation index invalid") from None
        if str(offset) != str(flat_position) or offset < 0:
            raise ProviderError("Eurostat HPI observation index invalid")
        coordinates = {}
        remaining = offset
        for dimension_id, length in reversed(list(zip(dims,sizes))):
            coordinates[dimension_id] = remaining % length
            remaining //= length
        if remaining or any(coordinates[dim] != indexes[dim][value] for dim,value in wanted.items()):
            raise ProviderError("Eurostat HPI observation belongs to another scope")
        stamp = reverse_time.get(coordinates["time"])
        if not isinstance(stamp, str) or not re.fullmatch(r"\d{4}-Q[1-4]", stamp):
            raise ProviderError("Eurostat HPI quarter label invalid")
        year, quarter = int(stamp[:4]), int(stamp[-1])
        day = date(year,(quarter-1)*3+1,1)
        if day in output:
            raise ProviderError("Eurostat HPI repeated original quarter")
        value = _number(raw,"Eurostat HPI index",maximum=Decimal("1E6"))
        if value <= 0:
            raise ProviderError("Eurostat HPI price index must be positive")
        output[day] = value
    if not output:
        raise ProviderError("Eurostat HPI contains no observations for the selected series")
    return dict(sorted(output.items()))


def fetch_eurostat_hpi(self, sid, start, item, key):
    parts = key.split("/")
    if (len(parts) != 4 or parts[0] != "prc_hpi_q"
            or parts[1] not in HPI_AREAS or parts[2] not in HPI_PURCHASES
            or parts[3] != "I15_Q"):
        raise ProviderError("Unapproved Eurostat quarterly house-price series")
    area, purchase = parts[1:3]
    if item["geography"] != ("EA" if area == "EA20" else "EU" if area == "EU27_2020" else area):
        raise ProviderError("Eurostat HPI geography mismatch")
    params = {"freq":"Q","geo":area,"purchase":purchase,"unit":"I15_Q"}
    if start:
        params["sinceTimePeriod"] = f"{start.year}-Q{(start.month-1)//3+1}"
    response = self._get_document(EUROSTAT_HPI_URL, params=params)
    return FetchedSeries(sid,str(response.request.url),None,
                         parse_eurostat_hpi(response.json(),area=area,purchase=purchase))


class _SecLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.href = None
        self.found = []
        self.label = ""
    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self.href = dict(attrs).get("href")
            self.label = ""
    def handle_data(self, data):
        if self.href is not None:
            self.label += data
    def handle_endtag(self, tag):
        if tag.lower() == "a":
            if self.href:
                self.found.append((self.href,self.label))
            self.href = None
            self.label = ""


def nmfp_archives(index: str) -> list[tuple[date,str]]:
    """Read only monthly named official downloads, beginning with N-MFP3-era files."""
    links = _SecLinks()
    links.feed(index)
    result = {}
    for href,label in links.found:
        match = re.fullmatch(r"20(2[5-9])\s+("+"|".join(_MONTHS)+r")\s+NMFP", label.strip(), re.I)
        url = urljoin(SEC_NMFP_INDEX,href)
        parsed = urlparse(url)
        file_match = _SEC_FILE.fullmatch(parsed.path)
        if not (match and file_match and parsed.scheme == "https"
                and parsed.netloc == "www.sec.gov" and not parsed.query and not parsed.fragment):
            continue
        period = date(2000+int(match.group(1)),_MONTHS.index(match.group(2).capitalize())+1,1)
        if period < date(2025,7,1):
            continue
        if period in result and result[period] != url:
            raise ProviderError("SEC N-MFP monthly publisher links conflict")
        result[period] = url
    if not result:
        raise ProviderError("SEC N-MFP3 monthly publisher downloads unavailable")
    return sorted(result.items())


def _tsv(archive: ZipFile, table: str) -> list[dict]:
    names = {f"NMFP_{table.upper()}.TSV", f"{table.upper()}.TSV"}
    matches = [entry for entry in archive.infolist()
               if not entry.is_dir()
               and entry.filename.rsplit("/", 1)[-1].upper() in names]
    if len(matches) != 1:
        raise ProviderError(f"SEC N-MFP {table} data table missing or ambiguous")
    member = matches[0]
    if (".." in member.filename.split("/") or member.file_size > 35_000_000
            or member.file_size <= 0):
        raise ProviderError("SEC N-MFP selected table exceeds verified boundaries")
    try:
        raw = archive.read(member)
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(StringIO(text), delimiter="\t")
        if not reader.fieldnames or "ACCESSION_NUMBER" not in reader.fieldnames:
            raise ProviderError("SEC N-MFP table header invalid")
        rows = list(reader)
        if any(None in row for row in rows):
            raise ProviderError("SEC N-MFP tab-delimited row malformed")
        return rows
    except (UnicodeError, csv.Error) as exc:
        raise ProviderError("SEC N-MFP table encoding invalid") from exc


def _sec_date(value):
    for fmt in ("%Y-%m-%d","%m/%d/%Y","%d-%b-%Y"):
        try:
            return datetime.strptime(str(value).strip(),fmt).date()
        except (ValueError, TypeError):
            pass
    raise ProviderError("SEC N-MFP original date invalid")


def parse_nmfp_month(raw: bytes, report_month: date) -> dict[str, Decimal]:
    """As-filed N-MFP3; choose latest filing per series/month, reject duplicate rows.

    Only non-feeder money-market fund series are counted. Liquidity is the
    final disclosed day of each fund in the report month. The weighted mean
    is conditional on funds with a usable corresponding filing; do not impute
    missing percentages or treat it as a fund-run probability.
    """
    if len(raw) > 50_000_000 or not raw.startswith(b"PK\x03\x04"):
        raise ProviderError("SEC N-MFP response is not a bounded publisher ZIP")
    try:
        with ZipFile(BytesIO(raw)) as archive:
            files = _tsv(archive,"SUBMISSION")
            series = _tsv(archive,"SERIESLEVELINFO")
            liquid = _tsv(archive,"LIQUIDASSETSDETAILS")
    except (BadZipFile, OSError, RuntimeError, ValueError) as exc:
        raise ProviderError("SEC N-MFP original ZIP could not be parsed") from exc
    submissions = {}
    for row in files:
        accession = row["ACCESSION_NUMBER"]
        if accession in submissions:
            raise ProviderError("SEC N-MFP duplicated submission accession")
        kind = row.get("SUBMISSIONTYPE","").upper()
        if kind not in ("N-MFP3","N-MFP3/A"):
            continue
        day = _sec_date(row.get("REPORTDATE"))
        if (day.year,day.month) != (report_month.year,report_month.month):
            continue
        submissions[accession] = (_sec_date(row.get("FILING_DATE")),row.get("SERIESID",""))
    if not submissions:
        raise ProviderError("SEC N-MFP has no N-MFP3 filings for the declared report month")
    source_rows = {}
    for row in series:
        accession = row.get("ACCESSION_NUMBER","")
        if accession in submissions:
            if accession in source_rows:
                raise ProviderError("SEC N-MFP repeated series filing")
            source_rows[accession] = row
    latest = {}
    for accession,(filing,series_id) in submissions.items():
        if not series_id or accession not in source_rows:
            continue
        key = series_id
        rank = (filing,accession)
        if key not in latest or rank > latest[key][0]:
            latest[key] = (rank,accession)
    eligible = {}
    for _, accession in latest.values():
        row = source_rows[accession]
        if row.get("FEEDERFUNDFLAG","").strip().upper() == "Y":
            continue
        size = _number(row.get("NETASSETSOFSERIES",""),"SEC N-MFP net assets")
        if size > 0:
            eligible[accession] = (size,row)
    if not eligible:
        raise ProviderError("SEC N-MFP original contains no eligible non-feeder funds")
    assets = sum((v[0] for v in eligible.values()),Decimal(0))
    def weighted(field):
        components = [(size,_number(row[field],field,maximum=Decimal("1000")))
                      for size,row in eligible.values() if row.get(field,"").strip()]
        if not components:
            return None
        return sum((size*v for size,v in components),Decimal(0)) / sum((size for size,_ in components),Decimal(0))
    result = {"NET_ASSETS_MUSD": assets / Decimal("1000000"),
              "WAM_DAYS": weighted("AVERAGEPORTFOLIOMATURITY"),
              "WAL_DAYS": weighted("AVERAGELIFEMATURITY")}
    last_liquid = {}
    for row in liquid:
        accession = row.get("ACCESSION_NUMBER","")
        if accession not in eligible or not row.get("PCTWEEKLYLIQUIDASSETS","").strip():
            continue
        day = _sec_date(row.get("TOTLIQUIDASSETSNEARPCTDATE"))
        if (day.year,day.month) != (report_month.year,report_month.month):
            continue
        value = _number(row["PCTWEEKLYLIQUIDASSETS"],"SEC N-MFP weekly liquidity",
                        maximum=Decimal(100))
        # N-MFP3 discloses proportions on a 0..1 scale. Do not guess
        # whether an out-of-range original used a different convention.
        if value > 1:
            raise ProviderError("SEC N-MFP weekly liquidity fraction exceeds one")
        value *= 100
        if accession in last_liquid and day == last_liquid[accession][0]:
            raise ProviderError("SEC N-MFP repeated fund/date liquidity observation")
        if accession not in last_liquid or day > last_liquid[accession][0]:
            last_liquid[accession] = (day,value)
    if last_liquid:
        weight = sum((eligible[a][0] for a in last_liquid),Decimal(0))
        result["WEEKLY_LIQUIDITY_PCT"] = sum((eligible[a][0]*row[1] for a,row in last_liquid.items()),Decimal(0))/weight
    return {key:value for key,value in result.items() if value is not None}


def fetch_sec_nmfp(self, sid, start, item, key):
    if key not in SEC_METRICS or sid != "funding.us.sec_nmfp_"+key.lower():
        raise ProviderError("Unapproved SEC N-MFP3 source metric")
    import os
    agent = os.environ.get("SEC_USER_AGENT","").strip()
    if not agent or not ("@" in agent or "https://" in agent):
        raise ProviderError("SEC N-MFP collection requires SEC_USER_AGENT with operator contact")
    headers = {"User-Agent":agent}
    index = self._get_document(SEC_NMFP_INDEX,headers=headers)
    downloads = nmfp_archives(index.text)
    # Preserve the source's monthly history. Later refresh windows request only
    # new/overlapping releases, with the prior verified database retained.
    observations = {}
    for period,url in downloads:
        if start is not None and period < date(start.year,start.month,1):
            continue
        response = self._get_document(url,headers=headers)
        result = parse_nmfp_month(response.content,period)
        if key in result:
            observations[period] = result[key]
    if not observations:
        raise ProviderError("SEC N-MFP has no accepted monthly observations for this measure")
    return FetchedSeries(sid, SEC_NMFP_INDEX, None, observations)
