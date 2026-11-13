"""Original WID income/wealth shares with immutable source-pair evidence.

National and world estimates retain their different publisher variable codes and
vintages. Shares remain source fractions; neither gaps nor publication dates are
invented. A per-client area cache avoids downloading each bulk file per group.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import shutil
import tempfile

import httpx

from .bis import FetchedSeries, ProviderError
from .source_policy import require_managed_client
from .source_policy_types import PolicyDeferred
from .source_evidence import record_acquisition_receipt

WID_ROOT = "https://wid.world/bulk_download"
WID_SERIES = {
    f"inequality.{label}.{concept}.{group}": (
        area, stem + ("j992" if area == "WO" else "992j"), percentile)
    for label, area in (("us", "US"), ("fr", "FR"), ("pt", "PT"),
                        ("cn", "CN"), ("in", "IN"), ("world", "WO"))
    for concept, stem in (("pretax_income", "sptinc"),
                          ("net_personal_wealth", "shweal"))
    for group, percentile in ((("top10", "p90p100"), ("bottom50", "p0p50"))
                              + ((("top1", "p99p100"),) if concept == "pretax_income" else ()))
}
_CONCEPTS = {"sptinc": "Pre-tax national income", "shweal": "Net personal wealth"}


@dataclass(frozen=True)
class WidBundle:
    observations: dict[tuple[str, str], dict[date, Decimal]]
    metadata: dict[str, dict[str, str]]
    quality: dict[tuple[str, str], dict[date, str | None]]


def _reader(text: str, required: set[str]) -> csv.DictReader:
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")), delimiter=";")
    if (not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames)
            or not required.issubset(reader.fieldnames)):
        raise ProviderError("WID original CSV schema is missing or ambiguous")
    return reader


def parse_wid_bundle(data_text: str, metadata_text: str, *, area: str) -> WidBundle:
    """Validate original source identity and select registered native area shares."""
    keys = {(variable, percentile) for registered_area, variable, percentile
            in WID_SERIES.values() if registered_area == area}
    if not keys:
        raise ProviderError("Unregistered WID reference area")
    expected_variables = {key[0] for key in keys}
    metadata = {}
    reader = _reader(metadata_text, {"country", "variable", "age", "pop", "shortname",
                                    "shorttype", "shortpop", "shortage", "unit",
                                    "source", "method"})
    try:
        for row in reader:
            if row.get("country") != area:
                raise ProviderError("WID metadata reference area mismatch")
            variable = row.get("variable")
            if variable not in expected_variables:
                continue
            if variable in metadata:
                raise ProviderError("WID duplicate variable metadata")
            if (row.get("age") != "992" or row.get("pop") != "j"
                    or row.get("unit") != "share" or row.get("shorttype") != "Share"
                    or row.get("shortpop") != "equal-split adults"
                    or row.get("shortage") != "Adults"
                    or (row.get("shortname") or "").strip() != _CONCEPTS[variable[:6]]
                    or not (row.get("source") or "").strip()
                    or not (row.get("method") or "").strip()):
                raise ProviderError("WID concept, population, unit or source metadata mismatch")
            metadata[variable] = dict(row)
        if set(metadata) != expected_variables:
            raise ProviderError("WID exact variable metadata missing")
        observations = {key: {} for key in keys}
        quality = {key: {} for key in keys}
        reader = _reader(data_text, {"country", "variable", "percentile", "year",
                                     "value", "age", "pop"})
        for row in reader:
            if row.get("country") != area:
                raise ProviderError("WID observation reference area mismatch")
            key = row.get("variable"), row.get("percentile")
            if key not in keys:
                continue
            if row.get("age") != "992" or row.get("pop") != "j":
                raise ProviderError("WID observation age or population mismatch")
            raw_year = row.get("year") or ""
            if len(raw_year) != 4 or not raw_year.isdigit():
                raise ProviderError("WID invalid annual observation year")
            day = date(int(raw_year), 1, 1)
            if day.year > date.today().year:
                raise ProviderError("WID future observation year")
            raw = row.get("value")
            if raw in (None, "", "NA", "N/A", "NaN"):
                continue
            try:
                value = Decimal(raw)
            except InvalidOperation as exc:
                raise ProviderError("WID invalid numeric source share") from exc
            if not value.is_finite():
                raise ProviderError("WID nonfinite source share")
            # Net wealth group shares can be negative or greater than one.
            # Preserve them; source-defined wealth is assets minus debts.
            if day in observations[key]:
                raise ProviderError("WID duplicate annual share observation")
            observations[key][day] = value
            quality[key][day] = row.get("data_quality") or None
    except (csv.Error, TypeError, ValueError) as exc:
        if isinstance(exc, ProviderError):
            raise
        raise ProviderError("Malformed WID original CSV record") from exc
    if any(not values for values in observations.values()):
        raise ProviderError("WID selected original share has no observations")
    return WidBundle({key: dict(sorted(values.items())) for key, values in observations.items()},
                     metadata, quality)


def _source_record(response: httpx.Response, filename: str) -> dict:
    return {"file": filename, "url": str(response.request.url),
            "bytes": len(response.content), "sha256": sha256(response.content).hexdigest(),
            "last_modified": response.headers.get("last-modified"),
            "etag": response.headers.get("etag"),
            "content_type": response.headers.get("content-type")}


def _verify_archive(folder: Path, area: str, sources: dict, bundle: WidBundle) -> None:
    try:
        record = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        if (record.get("schema_version") != 1 or record.get("publisher") != "WID.world"
                or record.get("area") != area
                or record.get("original_first_publication_at") is not None
                or not record.get("retrieved_at_utc")
                or record.get("variables") != bundle.metadata):
            raise ValueError("source manifest identity")
        # The manifest records the selection made at acquisition. Additional
        # registered percentiles can be independently selected from the same
        # immutable original CSV without rewriting that historical manifest.
        actual_quality = {
            variable + "/" + percentile: {day.isoformat(): value for day, value in values.items()}
            for (variable, percentile), values in bundle.quality.items()}
        stored_quality = record.get("observation_quality")
        baseline = {variable + "/" + percentile for variable in bundle.metadata
                    for percentile in ("p90p100", "p0p50")}
        if (not isinstance(stored_quality, dict) or not baseline.issubset(stored_quality)
                or any(key not in actual_quality or value != actual_quality[key]
                       for key, value in stored_quality.items())):
            raise ValueError("source manifest selected quality mismatch")
        for kind, source in sources.items():
            stored = record["sources"][kind]
            if any(stored.get(key) != source[key] for key in ("file", "url", "bytes", "sha256")):
                raise ValueError("source manifest hash mismatch")
            original = folder / source["file"]
            if original.is_symlink() or sha256(original.read_bytes()).hexdigest() != source["sha256"]:
                raise ValueError("source evidence content mismatch")
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ProviderError("WID immutable source evidence is inconsistent") from exc


def _archive_bundle(root: Path, area: str, data: httpx.Response,
                    metadata: httpx.Response, bundle: WidBundle) -> Path:
    sources = {"data": _source_record(data, f"WID_data_{area}.csv"),
               "metadata": _source_record(metadata, f"WID_metadata_{area}.csv")}
    digest = sha256((sources["data"]["sha256"] + ":" +
                     sources["metadata"]["sha256"]).encode("ascii")).hexdigest()
    parent = Path(root) / "wid" / area
    folder = parent / digest
    temporary = None
    try:
        parent.mkdir(parents=True, exist_ok=True)
        if folder.exists():
            _verify_archive(folder, area, sources, bundle)
            return folder
        temporary = Path(tempfile.mkdtemp(prefix=".wid-", dir=parent))
        for kind, response in (("data", data), ("metadata", metadata)):
            with (temporary / sources[kind]["file"]).open("wb") as handle:
                handle.write(response.content)
                handle.flush()
                os.fsync(handle.fileno())
        manifest = {
            "schema_version": 1, "publisher": "WID.world", "area": area,
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "original_first_publication_at": None,
            "publication_note": "HTTP Last-Modified is a bulk-file modification time, not original first publication.",
            "source_class": "original_publisher_current_bulk_snapshot",
            "sources": sources, "variables": bundle.metadata,
            "observation_quality": {
                variable + "/" + percentile: {day.isoformat(): value for day, value in values.items()}
                for (variable, percentile), values in bundle.quality.items()},
        }
        with (temporary / "manifest.json").open("w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.rename(temporary, folder)
        except OSError:
            # Another collector can atomically publish the same hash first.
            if not folder.exists():
                raise
        _verify_archive(folder, area, sources, bundle)
        return folder
    except OSError as exc:
        raise ProviderError("WID original source evidence could not be archived") from exc
    finally:
        if temporary is not None and temporary.exists():
            shutil.rmtree(temporary)


# A publisher policy may defer the second original of the data/metadata
# pair for many minutes. Until both are validated, the first response MUST
# remain quarantined, not published as a certified WID source receipt. A
# bounded, hash-verifiable staging file lets later scheduled runs resume.
_PENDING_LIMIT = 250_000_000
_PENDING_MAX_AGE = timedelta(days=2)


def _pending_root(root: Path, area: str) -> Path:
    if area not in {reference for reference, _, _ in WID_SERIES.values()}:
        raise ProviderError("WID staging area unregistered")
    return Path(root) / "wid-pending" / area


def _stage_pending_data(root: Path, area: str, response: httpx.Response) -> None:
    """Persist non-certifying data original after metadata is policy deferred."""
    url = f"{WID_ROOT}/WID_data_{area}.csv"
    body = response.content
    if (response.status_code != 200 or str(response.request.url) != url
            or not body or len(body) > _PENDING_LIMIT):
        raise ProviderError("WID pending original identity or size mismatch")
    digest = sha256(body).hexdigest()
    parent = _pending_root(root, area)
    folder = parent / digest
    temporary = None
    try:
        parent.mkdir(parents=True, exist_ok=True)
        if folder.exists():
            _read_pending_data(root, area, folder)
            return
        temporary = Path(tempfile.mkdtemp(prefix=".wid-pending-", dir=parent))
        with (temporary / "data.csv").open("wb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        manifest = {
            "schema_version": 1, "kind": "unvalidated_wid_data_pending_metadata",
            "publisher": "WID.world", "area": area,
            "original_url": url, "sha256": digest, "bytes": len(body),
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "headers": {key: response.headers[key] for key in
                        ("content-type", "etag", "last-modified")
                        if key in response.headers},
            "certified": False, "receipt": None,
        }
        with (temporary / "manifest.json").open("w", encoding="utf-8") as stream:
            json.dump(manifest, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.rename(temporary, folder)
            temporary = None
        except FileExistsError:
            _read_pending_data(root, area, folder)
    except OSError as exc:
        raise ProviderError("WID pending data could not be staged") from exc
    finally:
        if temporary is not None and temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)


def _read_pending_data(root: Path, area: str, folder: Path) -> tuple[httpx.Response, datetime]:
    url = f"{WID_ROOT}/WID_data_{area}.csv"
    try:
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError("pending path")
        document = folder / "manifest.json"
        payload = folder / "data.csv"
        if document.is_symlink() or payload.is_symlink():
            raise ValueError("pending symlink")
        manifest = json.loads(document.read_text(encoding="utf-8"))
        if (manifest.get("schema_version") != 1
                or manifest.get("kind") != "unvalidated_wid_data_pending_metadata"
                or manifest.get("publisher") != "WID.world"
                or manifest.get("area") != area
                or manifest.get("original_url") != url
                or manifest.get("sha256") != folder.name
                or manifest.get("certified") is not False
                or manifest.get("receipt") is not None
                or type(manifest.get("bytes")) is not int
                or not 0 < manifest["bytes"] <= _PENDING_LIMIT):
            raise ValueError("pending identity")
        if payload.stat().st_size != manifest["bytes"]:
            raise ValueError("pending length")
        body = payload.read_bytes()
        if sha256(body).hexdigest() != manifest["sha256"]:
            raise ValueError("pending hash")
        headers = manifest.get("headers")
        if (not isinstance(headers, dict) or any(key not in (
                "content-type", "etag", "last-modified") or
                not isinstance(value, str) or len(value) > 1000
                for key, value in headers.items())):
            raise ValueError("pending response headers")
        retrieved_at = datetime.fromisoformat(manifest["retrieved_at_utc"])
        if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
            raise ValueError("pending retrieval time")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ProviderError("WID pending original hash or identity invalid") from exc
    return (httpx.Response(200, content=body, headers=headers,
                           request=httpx.Request("GET", url)), retrieved_at)


def _resumable_pending_data(root: Path, area: str) -> httpx.Response | None:
    parent = _pending_root(root, area)
    latest = None
    for folder in sorted(parent.iterdir()) if parent.is_dir() else []:
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        response, retrieved = _read_pending_data(root, area, folder)
        age = datetime.now(timezone.utc) - retrieved.astimezone(timezone.utc)
        if timedelta(0) <= age < _PENDING_MAX_AGE:
            if latest is None or retrieved > latest[1]:
                latest = response, retrieved
    return latest[0] if latest else None


class WidClient:
    """One original CSV and metadata pair per area per collector lifetime.

    Pass archive_dir in production to require evidence persistence before any
    observations are returned. No network URL is derived from an arbitrary ID.
    """
    def __init__(self, client: httpx.Client, *, archive_dir: Path | None = None):
        self.client = require_managed_client(client)
        self.archive_dir = Path(archive_dir) if archive_dir is not None else None
        self._areas: dict[str, WidBundle] = {}

    def fetch(self, series_id: str, start: date | None = None) -> FetchedSeries:
        selected = WID_SERIES.get(series_id)
        if selected is None:
            raise ProviderError("Unregistered WID original share source")
        area, variable, percentile = selected
        data_url = f"{WID_ROOT}/WID_data_{area}.csv"
        metadata_url = f"{WID_ROOT}/WID_metadata_{area}.csv"
        if area not in self._areas:
            data = (_resumable_pending_data(self.archive_dir, area)
                    if self.archive_dir is not None else None)
            try:
                if data is None:
                    data = self.client.get(data_url, follow_redirects=False)
                    data.raise_for_status()
                try:
                    metadata = self.client.get(metadata_url, follow_redirects=False)
                    metadata.raise_for_status()
                except PolicyDeferred:
                    # The managed rate ledger did not emit the metadata GET.
                    # Persist only the first original so that a later normal
                    # run can request metadata under the same publisher rules.
                    # This staging is not an accepted/receipted source pair.
                    if self.archive_dir is not None:
                        _stage_pending_data(self.archive_dir, area, data)
                    raise
            except httpx.HTTPError as exc:
                raise ProviderError("WID original data or metadata request failed") from exc
            if (data.status_code != 200 or metadata.status_code != 200
                    or str(data.request.url) != data_url
                    or str(metadata.request.url) != metadata_url
                    or len(data.content) > 250_000_000 or len(metadata.content) > 20_000_000):
                raise ProviderError("WID response identity or size mismatch")
            try:
                bundle = parse_wid_bundle(data.content.decode("utf-8-sig"),
                                          metadata.content.decode("utf-8-sig"), area=area)
            except UnicodeError as exc:
                raise ProviderError("WID original CSV encoding is invalid") from exc
            if self.archive_dir is not None:
                archived = _archive_bundle(self.archive_dir, area, data, metadata, bundle)
                record_acquisition_receipt(archived, {"publisher": "WID.world", "area": area})
                # The full validated original pair now has its own immutable
                # archive. Clear only temporary non-certifying staging, so
                # the next normal refresh can detect genuine source revisions.
                pending = _pending_root(self.archive_dir, area)
                if pending.exists():
                    shutil.rmtree(pending)
            self._areas[area] = bundle
        values = self._areas[area].observations[(variable, percentile)]
        observations = {day: value for day, value in values.items()
                        if start is None or day >= start}
        if not observations:
            raise ProviderError("WID original share has no observations in requested period")
        return FetchedSeries(series_id, data_url + " + " + metadata_url, None, observations)
