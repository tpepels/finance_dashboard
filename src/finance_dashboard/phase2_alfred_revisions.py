"""Verified observation-level ALFRED real-time original revision windows.

The official output_type=1 API permits observation date and real-time validity
ranges in one (bounded) response. The full pages, not a reconstructed scalar
point estimate, are retained with exact content identity and append-only
retrieval receipts. This proves ALFRED-recorded *availability*, not whether
a different primary publisher disclosed an observation earlier.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

import httpx

from .source_capture import canonical_bytes
from .source_evidence import record_acquisition_receipt, verified_receipted_bundles
from .source_policy import require_managed_client
from .vintage import FRED_OBSERVATIONS, SOURCES, _key_format_ok

MAX_PAGE_ROWS = 10_000
MAX_PAGE_BYTES = 12_000_000
MAX_PAGES_PER_WINDOW = 20
EARLIEST_ALFRED_REALTIME = "1776-07-04"
_RANGE = re.compile(r"window-(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\Z")
_ASOF = re.compile(r"asof-(\d{4}-\d{2}-\d{2})\Z")


def _valid_dates(series_id: str, start: date, end: date, asof: date):
    if (series_id not in SOURCES or not isinstance(start, date)
            or not isinstance(end, date) or not isinstance(asof, date)
            or start > end or end > asof or asof > date.today()
            or start.year < 1900 or (end - start).days > 366):
        raise ValueError("invalid_alfred_original_revision_window")


def _identity(series_id: str, start: date, end: date, asof: date) -> dict:
    _valid_dates(series_id, start, end, asof)
    return {
        "provider": "ALFRED", "endpoint": FRED_OBSERVATIONS,
        "series_id": series_id, "output_type": 1,
        "units": "lin", "observation_start": start.isoformat(),
        "observation_end": end.isoformat(),
        "realtime_start": EARLIEST_ALFRED_REALTIME,
        "realtime_end": asof.isoformat(),
    }


def _parent(root: Path, series_id: str, start: date,
            end: date, asof: date) -> Path:
    _valid_dates(series_id, start, end, asof)
    return (Path(root) / "alfred-original-revisions" / series_id /
            f"window-{start.isoformat()}_{end.isoformat()}" /
            f"asof-{asof.isoformat()}")


def _parse_page(raw: bytes, *, identity: dict, offset: int) -> tuple[int, list[dict]]:
    if (type(offset) is not int or offset < 0
            or not isinstance(raw, bytes) or
            not 1 <= len(raw) <= MAX_PAGE_BYTES):
        raise ValueError("alfred_revision_page_size_or_offset_invalid")
    try:
        doc = json.loads(raw)
        total, returned = doc["count"], doc["offset"]
        rows = doc["observations"]
        if (type(total) is not int or type(returned) is not int
                or total < 0 or returned != offset
                or not isinstance(rows, list) or len(rows) > MAX_PAGE_ROWS
                or offset + len(rows) > total
                or doc.get("output_type", 1) != 1
                or doc.get("units", "lin") != "lin"):
            raise ValueError("alfred_revision_pagination_or_response_invalid")
        for field in ("realtime_start", "realtime_end",
                      "observation_start", "observation_end"):
            if doc.get(field, identity[field]) != identity[field]:
                raise ValueError("alfred_revision_source_query_identity_mismatch")
        start = date.fromisoformat(identity["observation_start"])
        end = date.fromisoformat(identity["observation_end"])
        asof = date.fromisoformat(identity["realtime_end"])
        cleaned = []
        for row in rows:
            observation = date.fromisoformat(row["date"])
            first = date.fromisoformat(row["realtime_start"])
            last = date.fromisoformat(row["realtime_end"])
            if (not start <= observation <= end
                    or not first <= asof or first > last
                    or first < date.fromisoformat(EARLIEST_ALFRED_REALTIME)
                    or first > date.today()):
                raise ValueError("alfred_revision_observation_bounds_invalid")
            original = row["value"]
            if not isinstance(original, str):
                raise ValueError("alfred_revision_native_numeric_type_invalid")
            if original in {".", ""}:
                value = None
            else:
                try:
                    number = Decimal(original)
                except (InvalidOperation, ValueError) as exc:
                    raise ValueError("alfred_revision_number_invalid") from exc
                if not number.is_finite():
                    raise ValueError("alfred_revision_number_nonfinite")
                value = str(number)
            cleaned.append({
                "date": observation.isoformat(),
                "realtime_start": first.isoformat(),
                "realtime_end": last.isoformat(),
                "value": value,
            })
        if not cleaned and total > offset:
            raise ValueError("alfred_revision_truncated_page")
        return total, cleaned
    except (TypeError, KeyError, IndexError, OverflowError,
            json.JSONDecodeError) as exc:
        raise ValueError("alfred_revision_original_schema_invalid") from exc


def _audit(pages: list[bytes], identity: dict) -> dict:
    if not 1 <= len(pages) <= MAX_PAGES_PER_WINDOW:
        raise ValueError("alfred_revision_page_count_invalid")
    offset, total, observations = 0, None, defaultdict(list)
    for raw in pages:
        count, records = _parse_page(raw, identity=identity, offset=offset)
        if total is not None and total != count:
            raise ValueError("alfred_revision_publisher_count_changed_mid_acquisition")
        total = count
        for row in records:
            observations[row["date"]].append(row)
        offset += len(records)
    if total is None or offset != total:
        raise ValueError("alfred_revision_pages_incomplete")
    numeric = missing = revisions = 0
    earliest = []
    for observation, entries in observations.items():
        ordered = sorted(entries, key=lambda r: (
            r["realtime_start"], r["realtime_end"]))
        if len({(r["realtime_start"], r["realtime_end"])
                for r in entries}) != len(entries):
            raise ValueError("alfred_revision_duplicate_realtime_interval")
        for previous, current in zip(ordered, ordered[1:]):
            if previous["realtime_end"] >= current["realtime_start"]:
                raise ValueError("alfred_revision_overlapping_realtime_intervals")
        numeric += sum(r["value"] is not None for r in ordered)
        missing += sum(r["value"] is None for r in ordered)
        revisions += max(0, len(ordered) - 1)
        earliest.append(min(row["realtime_start"] for row in ordered))
    return {
        "rows_in_all_verified_pages": total,
        "observation_dates": len(observations),
        "numeric_source_values": numeric,
        "missing_source_values_not_interpolated": missing,
        "recorded_revision_intervals_after_initial_interval": revisions,
        "earliest_recorded_alfred_revision": min(earliest) if earliest else None,
        "latest_first_recorded_alfred_revision": max(earliest) if earliest else None,
        "all_api_pages_in_window_complete": True,
        "realtime_periods_nonoverlapping_per_observation": True,
        "original_source_numeric_values_not_aggregated": True,
        "original_publisher_first_publication_verified": False,
        "earliest_alfred_record_may_postdate_publisher_release": True,
    }


def read_revision_window(root: Path, series_id: str, start: date,
                         end: date, asof: date) -> dict:
    identity = _identity(series_id, start, end, asof)
    parent = _parent(root, series_id, start, end, asof)
    if not parent.exists() and not parent.is_symlink():
        return {
            "series_id": series_id, "status": "missing_original_revision_window",
            "original_source_hash_verified": False,
            "original_publisher_first_publication_verified": False,
        }
    if any(path.is_symlink() for path in (parent, parent.parent, parent.parent.parent)):
        raise ValueError("alfred_revision_parent_symlink")
    receipts = verified_receipted_bundles(parent, identity)
    versions = {}
    for receipt in receipts:
        digest, folder = receipt["bundle_digest"], receipt["bundle_path"]
        if digest in versions:
            continue
        manifest = receipt["manifest"]
        if (manifest.get("schema_version") != 1
                or manifest.get("source_identity") != identity
                or manifest.get("original_publisher_first_publication_verified") is not False
                or type(manifest.get("pages")) is not list
                or not 1 <= len(manifest["pages"]) <= MAX_PAGES_PER_WINDOW):
            raise ValueError("alfred_revision_manifest_schema_invalid")
        files, content = set(), []
        for index, meta in enumerate(manifest["pages"]):
            name = f"page-{index:04d}.json"
            if (meta.get("file") != name or
                    type(meta.get("bytes")) is not int or
                    not 1 <= meta["bytes"] <= MAX_PAGE_BYTES or
                    type(meta.get("offset")) is not int):
                raise ValueError("alfred_revision_manifest_page_identity_invalid")
            path = folder / name
            if path.is_symlink() or not path.is_file():
                raise ValueError("alfred_revision_page_missing_or_symlink")
            raw = path.read_bytes()
            if len(raw) != meta["bytes"] or sha256(raw).hexdigest() != meta["sha256"]:
                raise ValueError("alfred_revision_original_hash_mismatch")
            files.add(name)
            content.append(raw)
        if set(x.name for x in folder.iterdir()) != files | {"manifest.json"}:
            raise ValueError("alfred_revision_bundle_unexpected_files")
        audit = _audit(content, identity)
        if audit != manifest["native_audit"]:
            raise ValueError("alfred_revision_native_facts_changed")
        page_hashes = [sha256(raw).hexdigest() for raw in content]
        expected = sha256(canonical_bytes({
            "source_identity": identity, "original_page_sha256": page_hashes
        })).hexdigest()
        if expected != digest:
            raise ValueError("alfred_revision_content_address_mismatch")
        if [meta["offset"] for meta in manifest["pages"]] != [
                sum(len(json.loads(raw)["observations"]) for raw in content[:i])
                for i in range(len(content))]:
            raise ValueError("alfred_revision_original_offset_mismatch")
        versions[digest] = audit
    if len({canonical_bytes(item) for item in versions.values()}) > 1 or len(versions) > 1:
        return {
            "series_id": series_id,
            "status": "conflicting_original_revision_versions",
            "source_original_versions": len(versions),
            "source_receipts": len(receipts),
            "original_source_hash_verified": True,
            "original_publisher_first_publication_verified": False,
        }
    return {
        "series_id": series_id, "status": "verified_original_revision_window",
        "window_start": start.isoformat(), "window_end": end.isoformat(),
        "realtime_asof": asof.isoformat(),
        "source_original_versions": len(versions),
        "source_receipts": len(receipts),
        "source_sha256": next(iter(versions)),
        "original_source_hash_verified": True,
        **next(iter(versions.values())),
    }


def capture_revision_window(series_id: str, *, start: date, end: date,
                            asof: date, root: Path, api_key: str,
                            client: httpx.Client, max_pages: int = 10,
                            refresh: bool = False) -> dict:
    """Request a complete paginated original, publish only after full audit."""
    require_managed_client(client)
    identity = _identity(series_id, start, end, asof)
    if not _key_format_ok(api_key):
        raise ValueError("registered_alfred_api_key_required")
    if type(max_pages) is not int or not 1 <= max_pages <= MAX_PAGES_PER_WINDOW:
        raise ValueError("invalid_alfred_revision_page_budget")
    parent = _parent(root, series_id, start, end, asof)
    if parent.exists() and not refresh:
        current = read_revision_window(root, series_id, start, end, asof)
        if current["status"] != "verified_original_revision_window":
            raise ValueError("invalid_existing_revision_original")
        return {**current, "publisher_requests": 0, "cache_hit": True}
    if parent.is_symlink():
        raise ValueError("alfred_revision_parent_symlink")
    pages = []
    expected, offset = None, 0
    while expected is None or offset < expected:
        if len(pages) >= max_pages:
            raise ValueError("alfred_revision_window_exceeds_page_budget")
        response = client.get(FRED_OBSERVATIONS, params={
            "series_id": series_id, "api_key": api_key, "file_type": "json",
            "observation_start": start.isoformat(),
            "observation_end": end.isoformat(),
            "realtime_start": EARLIEST_ALFRED_REALTIME,
            "realtime_end": asof.isoformat(), "output_type": 1,
            "units": "lin", "limit": MAX_PAGE_ROWS, "offset": offset,
            "sort_order": "asc",
        }, timeout=50, follow_redirects=False)
        response.raise_for_status()
        if (response.status_code != 200
                or response.request.url.host != "api.stlouisfed.org"
                or response.request.url.path != httpx.URL(
                    FRED_OBSERVATIONS).path):
            raise ValueError("alfred_revision_publisher_endpoint_changed")
        raw = response.content
        count, records = _parse_page(raw, identity=identity, offset=offset)
        if expected is not None and count != expected:
            raise ValueError("alfred_revision_publisher_count_changed_mid_acquisition")
        expected = count
        pages.append(raw)
        offset += len(records)
    audit = _audit(pages, identity)
    hashes = [sha256(raw).hexdigest() for raw in pages]
    digest = sha256(canonical_bytes({
        "source_identity": identity, "original_page_sha256": hashes
    })).hexdigest()
    parent.mkdir(parents=True, exist_ok=True)
    target, temporary = parent / digest, None
    try:
        if target.exists():
            # A repeated capture must not conceal earlier corrupt originals.
            read_revision_window(root, series_id, start, end, asof)
        else:
            temporary = Path(tempfile.mkdtemp(dir=parent, prefix=".revision-"))
            manifest_pages = []
            offset = 0
            for index, raw in enumerate(pages):
                name = f"page-{index:04d}.json"
                with (temporary / name).open("wb") as out:
                    out.write(raw)
                    out.flush()
                    os.fsync(out.fileno())
                manifest_pages.append({
                    "file": name, "bytes": len(raw),
                    "sha256": hashes[index], "offset": offset,
                })
                offset += len(json.loads(raw)["observations"])
            manifest = {
                "schema_version": 1, "source_identity": identity,
                "pages": manifest_pages, "native_audit": audit,
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "original_publisher_first_publication_verified": False,
                "policy_boundary": "canonical_managed_publisher_http",
                "credential_and_query_url_retained": False,
            }
            (temporary / "manifest.json").write_bytes(canonical_bytes(manifest))
            os.rename(temporary, target)
        record_acquisition_receipt(target, identity)
    finally:
        if temporary is not None and temporary.exists():
            shutil.rmtree(temporary)
    result = read_revision_window(root, series_id, start, end, asof)
    return {**result, "publisher_requests": len(pages), "cache_hit": False}


def revision_inventory(root: Path, series_ids: set[str]) -> dict:
    """Read-only rehashing of all retained official windows and receipts."""
    if series_ids - set(SOURCES):
        raise ValueError("unregistered_alfred_revision_series")
    results = {}
    for sid in sorted(series_ids):
        folder = Path(root) / "alfred-original-revisions" / sid
        windows = []
        if folder.is_symlink():
            windows.append({"status": "invalid_original_revision_archive"})
        elif folder.exists():
            for window in sorted(folder.iterdir()):
                matched = _RANGE.fullmatch(window.name)
                if window.is_symlink() or not window.is_dir() or not matched:
                    windows.append({"status": "invalid_original_revision_archive"})
                    continue
                for asof_dir in sorted(window.iterdir()):
                    match = _ASOF.fullmatch(asof_dir.name)
                    if asof_dir.is_symlink() or not asof_dir.is_dir() or not match:
                        windows.append({"status": "invalid_original_revision_archive"})
                        continue
                    try:
                        item = read_revision_window(
                            root, sid, date.fromisoformat(matched[1]),
                            date.fromisoformat(matched[2]),
                            date.fromisoformat(match[1]))
                    except (OSError, ValueError, KeyError, TypeError):
                        item = {"status": "invalid_original_revision_archive"}
                    windows.append(item)
        results[sid] = {
            "series_id": sid,
            "windows": [{
                "status": x["status"],
                "start": x.get("window_start"),
                "end": x.get("window_end"),
                "asof": x.get("realtime_asof"),
                "revisions": x.get(
                    "recorded_revision_intervals_after_initial_interval"),
                "records": x.get("rows_in_all_verified_pages"),
                "source_sha256": x.get("source_sha256"),
            } for x in windows],
            "verified_windows": sum(
                x["status"] == "verified_original_revision_window"
                for x in windows),
            "invalid_or_conflicting_windows": sum(
                x["status"] != "verified_original_revision_window"
                for x in windows),
            "verified_observation_revision_rows": sum(
                x.get("rows_in_all_verified_pages", 0) for x in windows
                if x["status"] == "verified_original_revision_window"),
            "original_publisher_first_publication_verified": False,
        }
    return {
        "operation": "phase2_alfred_original_revision_inventory",
        "series": results,
        "source_series_checked": len(results),
        "verified_windows": sum(row["verified_windows"]
                                for row in results.values()),
        "invalid_or_conflicting_windows": sum(
            row["invalid_or_conflicting_windows"] for row in results.values()),
        "original_publisher_first_publication_verified": False,
        "current_source_values_not_reinterpreted_as_historical_release": True,
        "scientific_analysis_certified": False,
    }
