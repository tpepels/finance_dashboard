"""Original academic monthly returns with explicit native conventions.

French market excess and risk-free percentages remain percentages; the named
total series is their same-period sum. Swinkels returns are cached decimal
hypothetical local-currency sovereign estimates, never a global bond index.
"""
from __future__ import annotations

import calendar
import csv
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256, sha1, md5
import io
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urljoin, urlsplit, urlunsplit
import xml.etree.ElementTree as ET
import zipfile

import httpx

from .bis import FetchedSeries, ProviderError
from .source_policy import require_managed_client
from .source_evidence import record_acquisition_receipt

FRENCH_ROOT = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp"
FRENCH_DATASETS = {"developed": "Developed_3_Factors", "emerging": "Emerging_5_Factors"}
FRENCH_SERIES = {
    f"returns.french.{area}.{label}": (dataset, variable)
    for area, dataset in FRENCH_DATASETS.items()
    for label, variable in (("market_excess_usd", "Mkt-RF"), ("risk_free_usd", "RF"),
                            ("market_total_usd", "Mkt-RF+RF"))
}
SWINKELS_DATA_URL = "https://dataverse.nl/api/access/datafile/512630"
SWINKELS_README_URL = "https://dataverse.nl/api/access/datafile/512631"
SWINKELS_METADATA_URL = "https://dataverse.nl/api/datasets/:persistentId/?persistentId=doi:10.34894/YWT2IX"
SWINKELS_ORIGINAL_METADATA_URL = "https://api.figshare.com/v2/articles/8152748/versions/6"
SWINKELS_SHA256 = "90a634328d14dec82bfcbbac83625105c49ff93e9ea2771762c2294d42435847"
SWINKELS_README_SHA256 = "b4c4b95917fbff72d06c8e3be1364d91d87779c3752d06260775ade45fb41072"
_COUNTRIES = (
    ("us", "Improved_US_1947", 4, "USD", "Par yields McCulloch/Kwon 1947–1961; FRED DGS10 from 1962."),
    ("de", "Germany_DE_1972", 2, "domestic_local_currency", "German domestic-currency hypothetical bond; Bundesbank 10-year fitted yields. DEM-era and EUR-era returns are not FX-converted."),
    ("jp", "Japan_JP_1974", 4, "JPY", "Japan Ministry of Finance: 9-year yield proxy until June 1986, then 10-year."),
    ("fr", "France_FR_1987", 2, "domestic_local_currency", "Banque de France Emprunt Phare 10 ans; FRF-era and EUR-era returns are not FX-converted."),
    ("gb", "UK_1970", 4, "GBP", "Bank of England historical long-term rate until December 2011; IUMNPY end-month 10-year nominal par yield from January 2012."),
    ("au", "Australia_AU_1969", 4, "AUD", "RBA 10-year yields: monthly end-month data 1969–1994, daily-file month-end observations from 1995; no monthly-average substitution."),
    ("ca", "Canada_CA_1986", 2, "CAD", "Bank of Canada ZC1000YR 10-year zero-coupon yield used in hypothetical coupon-bond return model."),
    ("no", "Norway_NO_1921", 5, "NOK", "Norges Bank ST10 with documented ST9/ST8/ST7 historical replacements; daily month-end series from December 1989; zero-coupon 10-year yield after June 2021."),
    ("se", "Sweden_SE_1920", 4, "SEK", "Riksbank long-run yields; consols before 1950 proxy a hypothetical 10-year security; separate SE GVB 10Y end-month data from January 1987."),
)
SWINKELS_SERIES = {
    f"returns.swinkels.{country}.sovereign_10y_modelled_local": (sheet, column)
    for country, sheet, column, _currency, _note in _COUNTRIES
}
SWINKELS_SERIES["returns.swinkels.us.sovereign_10y_original_1962_usd"] = ("Original_US_1962", 4)
SWINKELS_METADATA = {
    f"returns.swinkels.{country}.sovereign_10y_modelled_local": {
        "currency": currency, "method_note": note,
        "return_convention": "Publisher yield-modelled hypothetical 10-year sovereign monthly simple total return; improved par-bond revaluation method; native local currency.",
    } for country, _sheet, _column, currency, note in _COUNTRIES
}
SWINKELS_METADATA["returns.swinkels.us.sovereign_10y_original_1962_usd"] = {
    "currency": "USD", "method_note": "Original Swinkels (2019) duration/convexity approximation; distinct from improved US 1947 method.",
    "return_convention": "Publisher yield-modelled hypothetical 10-year US sovereign monthly simple total return; original duration/convexity approximation.",
}
_NS = {"t": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
       "o": "urn:oasis:names:tc:opendocument:xmlns:office:1.0"}
_T, _O = "{" + _NS["t"] + "}", "{" + _NS["o"] + "}"


@dataclass(frozen=True)
class ReturnsBundle:
    observations: dict[str, dict[date, Decimal]]
    metadata: dict


def _number(raw: str) -> Decimal:
    try:
        value = Decimal(raw)
        if not value.is_finite():
            raise InvalidOperation
        return value
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ProviderError("Research return source numeric value invalid") from exc


def _zip_members(raw: bytes, *, maximum: int) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as source:
            names = source.namelist()
            if (len(names) != len(set(names)) or len(names) > 100
                    or sum(x.file_size for x in source.infolist()) > maximum):
                raise ValueError("archive size or duplicate member")
            return {name: source.read(name) for name in names}
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as exc:
        raise ProviderError("Research return original archive invalid") from exc


def parse_french_zip(raw: bytes, *, dataset: str) -> ReturnsBundle:
    """Select source monthly block; annual rows and unrelated missing factors differ."""
    if dataset not in FRENCH_DATASETS.values():
        raise ProviderError("Unregistered French research portfolio")
    members = _zip_members(raw, maximum=5_000_000)
    if set(members) != {dataset + ".csv"}:
        raise ProviderError("French research portfolio archive identity mismatch")
    try:
        body = members[dataset + ".csv"].decode("utf-8-sig")
    except UnicodeError as exc:
        raise ProviderError("French original CSV encoding invalid") from exc
    vintage = re.search(r"^This file was created using the ([0-9]{6}) Bloomberg database\.", body)
    if not vintage or "Missing data are indicated by -99.99." not in body:
        raise ProviderError("French source vintage or missing convention absent")
    try:
        vintage_date = datetime.strptime(vintage[1], "%Y%m").date()
    except ValueError as exc:
        raise ProviderError("French source database vintage invalid") from exc
    expected = ["", "Mkt-RF", "SMB", "HML"] + (["RMW", "CMA"] if dataset == "Emerging_5_Factors" else []) + ["RF"]
    rows = list(csv.reader(io.StringIO(body)))
    headers = [i for i, row in enumerate(rows) if [v.strip() for v in row] == expected]
    if not headers:
        raise ProviderError("French original monthly factor columns mismatch")
    selected = {sid: variable for sid, (name, variable) in FRENCH_SERIES.items() if name == dataset}
    observations = {sid: {} for sid in selected}
    missing = {name: 0 for name in expected[1:]}
    seen = set()
    source_periods = {}
    inputs = {}
    for row in rows[headers[0]+1:]:
        if not row or not any(value.strip() for value in row):
            if seen:
                break
            continue
        period = row[0].strip()
        if not re.fullmatch(r"[0-9]{6}", period) or len(row) != len(expected):
            raise ProviderError("French monthly source period or row invalid")
        try:
            day = datetime.strptime(period, "%Y%m").date()
        except ValueError as exc:
            raise ProviderError("French monthly source period invalid") from exc
        if day > vintage_date or day > date.today() or day in seen:
            raise ProviderError("French duplicate, future or post-vintage month")
        seen.add(day)
        values = {}
        for key, raw_value in zip(expected[1:], row[1:]):
            value = _number(raw_value.strip())
            if value == Decimal("-99.99"):
                missing[key] += 1
                value = None
            values[key] = value
        inputs[day.isoformat()] = {name: str(values[name]) if values[name] is not None else None for name in ("Mkt-RF", "RF")}
        source_periods[day.isoformat()] = date(day.year, day.month, calendar.monthrange(day.year, day.month)[1]).isoformat()
        for sid, variable in selected.items():
            value = (values["Mkt-RF"] + values["RF"] if values["Mkt-RF"] is not None and values["RF"] is not None else None) if variable == "Mkt-RF+RF" else values[variable]
            if value is not None:
                observations[sid][day] = value
    if not seen or any(not values for values in observations.values()):
        raise ProviderError("French research monthly returns absent")
    return ReturnsBundle({sid: dict(sorted(values.items())) for sid, values in observations.items()}, {
        "publisher": "Kenneth French Data Library", "dataset": dataset,
        "source_database_vintage": vintage[1], "native_frequency": "M", "native_unit": "percent",
        "currency": "USD", "original_first_publication_at": None,
        "period_key": "First calendar day labels source YYYYMM; return window is prior month end exclusive to current month end inclusive.",
        "missing_values_by_variable": missing,
        "series": {sid: {"source_variables": ["Mkt-RF", "RF"] if variable == "Mkt-RF+RF" else [variable],
                           "transformation": "Mkt-RF + RF" if variable == "Mkt-RF+RF" else None,
                           "source_periods": source_periods,
                           "return_convention": "Explicit same-period total return" if variable == "Mkt-RF+RF" else "Source excess return" if variable == "Mkt-RF" else "Source risk-free return"}
                   for sid, variable in selected.items()},
        "transformation_inputs": inputs,
        "measurement_note": "Source-defined value-weighted research portfolios; not MSCI ACWI/World or an investable fund. No fee, tax or FX equivalence implied.",
        "rights": "Public no-fee original; explicit redistribution licence unestablished; underlying Bloomberg/IFC inputs not redistributed separately.",
    })


def _row_cells(row) -> list:
    """Expand only columns used here; ODS empty-repeat tails can be enormous."""
    cells = []
    for cell in row:
        if cell.tag not in (_T + "table-cell", _T + "covered-table-cell"):
            continue
        try:
            repeat = int(cell.get(_T + "number-columns-repeated", "1"))
            if repeat < 1:
                raise ValueError("repeat")
        except ValueError as exc:
            raise ProviderError("Swinkels invalid repeated source cell") from exc
        cells.extend([cell] * min(repeat, 12-len(cells)))
        if len(cells) == 12:
            break
    return cells


def parse_swinkels_ods(raw: bytes) -> ReturnsBundle:
    """Read original cached decimal results, retaining published formulas verbatim.

    This parser does not evaluate spreadsheet formula code. The acquisition
    client separately pins the exact original v6 byte identity.
    """
    members = _zip_members(raw, maximum=30_000_000)
    if members.get("mimetype") != b"application/vnd.oasis.opendocument.spreadsheet" or "content.xml" not in members:
        raise ProviderError("Swinkels original ODS identity mismatch")
    content = members["content.xml"]
    if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
        raise ProviderError("Swinkels original XML declarations invalid")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ProviderError("Swinkels original ODS XML invalid") from exc
    wanted = {sheet: (sid, column) for sid, (sheet, column) in SWINKELS_SERIES.items()}
    observations, metadata, source_notes, matched = {}, {}, [], set()
    for table in root.findall(".//t:table", _NS):
        name = table.get(_T + "name")
        if name == "Data_Sources":
            source_notes = [" ".join("".join(cell.itertext()).split()) for cell in table.findall(".//t:table-cell", _NS) if "".join(cell.itertext()).strip()]
        if name not in wanted:
            continue
        if name in matched:
            raise ProviderError("Swinkels duplicate original method sheet")
        matched.add(name)
        sid, column = wanted[name]
        rows = table.findall("t:table-row", _NS)
        if not rows:
            raise ProviderError("Swinkels original sheet rows absent")
        headers = _row_cells(rows[0])
        if (len(headers) <= column or "".join(headers[0].itertext()).strip() != "observation_date"
                or "".join(headers[column].itertext()).strip() != "Return M"):
            raise ProviderError("Swinkels original monthly return header mismatch")
        values, periods, formulas = {}, {}, {}
        previous = None
        for row in rows[1:]:
            cells = _row_cells(row)
            if not cells or cells[0].get(_O + "value-type") != "date":
                continue
            try:
                original = date.fromisoformat((cells[0].get(_O + "date-value") or "")[:10])
                repeated = int(row.get(_T + "number-rows-repeated", "1"))
            except ValueError as exc:
                raise ProviderError("Swinkels source month invalid") from exc
            if (original.day != calendar.monthrange(original.year, original.month)[1]
                    or original > date.today() or repeated != 1
                    or (previous is not None and original <= previous)):
                raise ProviderError("Swinkels duplicate, unordered or invalid month end")
            if previous is not None and (original.year*12+original.month) - (previous.year*12+previous.month) != 1:
                raise ProviderError("Swinkels monthly source window has a gap")
            previous = original
            cell = cells[column] if len(cells) > column else None
            if cell is None or cell.get(_O + "value") is None:
                if values:
                    raise ProviderError("Swinkels cached monthly return missing")
                continue  # Original first dated row is a yield/wealth baseline.
            if cell.get(_O + "value-type") != "percentage" or not cell.get(_T + "formula"):
                raise ProviderError("Swinkels cached return type or formula invalid")
            value = _number(cell.get(_O + "value"))
            day = original.replace(day=1)
            values[day] = value
            periods[day.isoformat()] = original.isoformat()
            formulas[day.isoformat()] = cell.get(_T + "formula")
        if not values:
            raise ProviderError("Swinkels original monthly returns absent")
        observations[sid] = values
        metadata[sid] = {**SWINKELS_METADATA[sid], "source_sheet": name,
                         "return_column_zero_based": column, "source_periods": periods,
                         "source_formulas": formulas, "first_original_period_end": periods[min(values).isoformat()],
                         "last_original_period_end": periods[max(values).isoformat()]}
    if matched != set(wanted) or not source_notes:
        raise ProviderError("Swinkels original country/method sheets or source notes absent")
    return ReturnsBundle(observations, {"publisher": "Laurens Swinkels / Erasmus University Rotterdam",
        "dataset_doi": "10.25397/eur.8152748.v6", "dataset_version": 6,
        "dataset_release_at": "2023-01-10T08:58:37Z", "original_first_publication_at": None,
        "native_frequency": "M", "native_unit": "ratio", "series": metadata,
        "period_key": "First calendar day labels return ending original month end; window is prior month end exclusive to current month end inclusive.",
        "source_notes": source_notes, "rights": "CC BY 4.0",
        "measurement_note": "Publisher yield-modelled hypothetical national sovereign returns; no global aggregation or FX conversion. Original and improved US methods remain separate.",
        "citation": "Swinkels, L. (2023), Historical Data: International monthly government bond returns, doi:10.25397/eur.8152748.v6; method: Swinkels (2019), doi:10.3390/data4030091.",
    })


def _source_record(response: httpx.Response, filename: str, requested_url: str) -> dict:
    # Signed object-store query strings are transport credentials, never evidence.
    resolved = urlsplit(str(response.request.url))
    return {"file": filename, "url": requested_url,
            "resolved_url_without_query": urlunsplit((resolved.scheme, resolved.netloc, resolved.path, "", "")),
            "bytes": len(response.content), "sha256": sha256(response.content).hexdigest(),
            "last_modified": response.headers.get("last-modified"), "etag": response.headers.get("etag"),
            "content_type": response.headers.get("content-type")}


def _archive(root: Path, area: str, responses: dict, bundle: ReturnsBundle, extra: dict) -> Path:
    sources = {kind: _source_record(response, filename, url) for kind, (response, filename, url) in responses.items()}
    digest = sha256(json.dumps({key: value["sha256"] for key, value in sources.items()}, sort_keys=True).encode()).hexdigest()
    parent = Path(root) / "research-returns" / area
    folder = parent / digest
    temporary = None
    def verify():
        try:
            if folder.is_symlink() or (folder / "manifest.json").is_symlink():
                raise ValueError("symlink")
            manifest = json.loads((folder / "manifest.json").read_text())
            if (manifest.get("schema_version") != 1 or manifest.get("source_identity") != extra["source_identity"]
                    or manifest.get("data_metadata") != bundle.metadata):
                raise ValueError("manifest identity")
            for kind, source in sources.items():
                recorded = manifest["sources"][kind]
                if any(recorded.get(key) != source[key] for key in ("file", "url", "bytes", "sha256")):
                    raise ValueError("manifest hash")
                path = folder / source["file"]
                if path.is_symlink() or sha256(path.read_bytes()).hexdigest() != source["sha256"]:
                    raise ValueError("source hash")
        except (OSError, KeyError, ValueError, TypeError) as exc:
            raise ProviderError("Research returns immutable original evidence inconsistent") from exc
    try:
        parent.mkdir(parents=True, exist_ok=True)
        if not folder.exists():
            temporary = Path(tempfile.mkdtemp(prefix=".returns-", dir=parent))
            for kind, (response, _name, _url) in responses.items():
                with (temporary / sources[kind]["file"]).open("wb") as handle:
                    handle.write(response.content); handle.flush(); os.fsync(handle.fileno())
            manifest = {"schema_version": 1, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                        "original_first_publication_at": None, "publication_note": "Dataset/repository release, database vintage, HTTP modification and local acquisition are distinct; individual observation first publication is unknown.",
                        "sources": sources, "data_metadata": bundle.metadata, **extra}
            with (temporary / "manifest.json").open("w", encoding="utf-8") as handle:
                json.dump(manifest, handle, ensure_ascii=False, indent=2); handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
            try:
                os.rename(temporary, folder)
            except OSError:
                if not folder.exists():
                    raise
        verify()
        record_acquisition_receipt(folder, extra["source_identity"])
        return folder
    except OSError as exc:
        raise ProviderError("Research return original evidence could not be archived") from exc
    finally:
        if temporary is not None and temporary.exists():
            shutil.rmtree(temporary)


class ResearchReturnsClient:
    """Cache complete originals per collection lifetime; archive before returning."""
    def __init__(self, client: httpx.Client, *, archive_dir: Path | None = None):
        self.client = require_managed_client(client)
        self.archive_dir = Path(archive_dir) if archive_dir is not None else None
        self._bundles: dict[str, ReturnsBundle] = {}

    def _get(self, url: str, maximum: int) -> httpx.Response:
        current = url
        for _ in range(4):
            response = self.client.get(current, follow_redirects=False)
            response.raise_for_status() if response.status_code >= 400 else None
            if response.status_code in (301, 302, 303, 307, 308):
                redirect = urljoin(current, response.headers.get("location", ""))
                parsed = urlsplit(redirect)
                if (urlsplit(url).hostname != "dataverse.nl" or parsed.scheme != "https"
                        or parsed.hostname != "objectstore.surf.nl" or parsed.username or parsed.password
                        or not parsed.path.startswith("/store/10.34894/YWT2IX/")):
                    raise ProviderError("Research return source redirect identity unapproved")
                current = redirect
                continue
            if response.status_code != 200 or len(response.content) > maximum:
                raise ProviderError("Research return source response size or status invalid")
            return response
        raise ProviderError("Research return source redirect limit exceeded")

    def fetch(self, series_id: str, start: date | None = None) -> FetchedSeries:
        from .global_market_returns import (GLOBAL_MARKET_SERIES, SOURCE_IDENTITY,
            SOURCE_URL as GLOBAL_MARKET_URL, parse_global_market_workbook)
        if series_id in FRENCH_SERIES:
            dataset, _variable = FRENCH_SERIES[series_id]
            area = next(label for label, name in FRENCH_DATASETS.items() if name == dataset)
            cache_key, url = "french/" + area, f"{FRENCH_ROOT}/{dataset}_CSV.zip"
            if cache_key not in self._bundles:
                response = self._get(url, 5_000_000)
                bundle = parse_french_zip(response.content, dataset=dataset)
                if self.archive_dir is not None:
                    _archive(self.archive_dir, cache_key, {"data": (response, "source.zip", url)}, bundle,
                             {"source_identity": {"publisher": "Kenneth French Data Library", "dataset": dataset}})
                self._bundles[cache_key] = bundle
        elif series_id in SWINKELS_SERIES:
            cache_key, url = "swinkels", SWINKELS_DATA_URL
            if cache_key not in self._bundles:
                data = self._get(url, 5_000_000)
                if sha256(data.content).hexdigest() != SWINKELS_SHA256:
                    raise ProviderError("Swinkels original v6 workbook hash mismatch")
                repository = self._get(SWINKELS_METADATA_URL, 2_000_000)
                original = self._get(SWINKELS_ORIGINAL_METADATA_URL, 2_000_000)
                readme = self._get(SWINKELS_README_URL, 2_000_000)
                try:
                    source_meta = original.json()
                    repo_meta = repository.json()["data"]["latestVersion"]
                    repo_file = next(x["dataFile"] for x in repo_meta["files"] if x["dataFile"]["id"] == 512630)
                    original_file = next(x for x in source_meta["files"] if x["name"].endswith(".ods"))
                    if (source_meta["doi"] != "10.25397/eur.8152748.v6" or source_meta["version"] != 6
                            or source_meta["published_date"] != "2023-01-10T08:58:37Z"
                            or source_meta["license"]["name"] != "CC BY 4.0"
                            or original_file["computed_md5"] != md5(data.content).hexdigest()
                            or repo_meta["datasetPersistentId"] != "doi:10.34894/YWT2IX"
                            or repo_meta["license"]["name"] != "CC-BY-4.0"
                            or repo_file["checksum"]["type"] != "SHA-1"
                            or repo_file["checksum"]["value"] != sha1(data.content).hexdigest()
                            or sha256(readme.content).hexdigest() != SWINKELS_README_SHA256):
                        raise ValueError("publisher identity")
                except (KeyError, TypeError, ValueError, StopIteration) as exc:
                    raise ProviderError("Swinkels original method or publisher metadata mismatch") from exc
                bundle = parse_swinkels_ods(data.content)
                if self.archive_dir is not None:
                    _archive(self.archive_dir, cache_key, {
                        "data": (data, "source.ods", url),
                        "readme": (readme, "readme.pdf", SWINKELS_README_URL),
                        "repository_metadata": (repository, "repository_metadata.json", SWINKELS_METADATA_URL),
                        "original_metadata": (original, "original_v6_metadata.json", SWINKELS_ORIGINAL_METADATA_URL)}, bundle,
                        {"source_identity": {"publisher": "Laurens Swinkels", "doi": "10.25397/eur.8152748.v6", "version": 6},
                         "repository_release_at": repo_meta["releaseTime"],
                         "original_dataset_modified_at": source_meta["modified_date"]})
                self._bundles[cache_key] = bundle
        elif series_id in GLOBAL_MARKET_SERIES:
            cache_key,url="doeswijk-swinkels/global-multiasset",GLOBAL_MARKET_URL
            if cache_key not in self._bundles:
                response=self._get(url,5_000_000)
                bundle=parse_global_market_workbook(response.content)
                if self.archive_dir is not None:
                    _archive(self.archive_dir,cache_key,{"data":(response,"source.xlsx",url)},bundle,
                             {"source_identity":SOURCE_IDENTITY})
                self._bundles[cache_key]=bundle
        else:
            raise ProviderError("Unregistered original academic return series")
        values = {day: value for day, value in self._bundles[cache_key].observations[series_id].items() if start is None or day >= start}
        if not values:
            raise ProviderError("Research return source has no observations in requested period")
        return FetchedSeries(series_id, url, None, values)
