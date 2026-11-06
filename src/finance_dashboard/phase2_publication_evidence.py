"""Immutable original publisher-vintage provenance for known ALFRED sources.

An official series' earliest returned ALFRED revision date proves no
observation-specific *first* release. Local fetch times and first populated
snapshots are not historical publication dates. Only publisher bytes and
their immutable receipt are authoritative; a release cannot be asserted
from a user-authored metadata certificate.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from .source_capture import canonical_bytes
from .source_evidence import (
    record_acquisition_receipt, verified_receipted_bundles,
    OriginalReceiptIntegrityError,
)
from .source_policy import require_managed_client
from .vintage import SOURCES, FRED_VINTAGE_DATES, _key_format_ok

MAX_RESPONSE_BYTES = 100_000


def _identity(series_id: str) -> dict:
    if series_id not in SOURCES:
        raise ValueError("unregistered_original_publisher_vintage")
    return {"provider": "ALFRED", "resource": "official_earliest_series_vintage",
            "series_id": series_id, "endpoint": FRED_VINTAGE_DATES}


def _parse(raw: bytes, series_id: str) -> str:
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_RESPONSE_BYTES:
        raise ValueError("publisher_vintage_response_invalid_size")
    try:
        payload = json.loads(raw)
        dates = payload["vintage_dates"]
        if not isinstance(dates, list) or len(dates) != 1:
            raise ValueError("publisher_vintage_expected_one_date")
        first = date.fromisoformat(dates[0])
        if first > date.today() or first.year < 1900:
            raise ValueError("publisher_vintage_date_outside_range")
    except (TypeError, KeyError, ValueError, OverflowError) as exc:
        raise ValueError("publisher_first_series_vintage_invalid") from exc
    return first.isoformat()


def _original_parent(root: Path, series_id: str) -> Path:
    return Path(root) / "alfred-publisher-first-vintage" / series_id


def capture_first_series_vintage(series_id: str, *, root: Path,
                                 api_key: str, client) -> dict:
    """One managed original publisher request; preserve bytes and receipt.

    Already retained and reverified versions are reused rather than refetched.
    Response secrets and query strings are not written to original evidence.
    """
    require_managed_client(client)
    if not _key_format_ok(api_key):
        raise ValueError("invalid_alfred_api_key")
    identity = _identity(series_id)
    parent = _original_parent(root, series_id)
    if parent.exists():
        cached = read_first_series_vintage(root, series_id)
        if cached["status"] != "verified_original_publisher_vintage":
            raise ValueError("invalid_existing_alfred_publisher_original")
        return {**cached, "publisher_requests": 0, "cache_hit": True}
    response = client.get(FRED_VINTAGE_DATES, params={
        "series_id": series_id, "api_key": api_key,
        "file_type": "json", "sort_order": "asc", "limit": 1,
    }, timeout=25, follow_redirects=False)
    response.raise_for_status()
    raw = response.content
    first = _parse(raw, series_id)
    manifest = {
        "schema_version": 1, "source_identity": identity,
        "source_original_sha256": sha256(raw).hexdigest(),
        "source_bytes": len(raw),
        "first_available_alfred_series_vintage": first,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "official_series_first_vintage_not_observation_first_release": True,
        "first_publication_verified": False,
    }
    digest = sha256(canonical_bytes({
        "source_identity": identity, "source_sha256": manifest[
            "source_original_sha256"]})).hexdigest()
    parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(dir=parent, prefix=".publisher-vintage-"))
    try:
        with (stage / "response.json").open("wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        (stage / "manifest.json").write_bytes(canonical_bytes(manifest))
        target = parent / digest
        if not target.exists():
            os.rename(stage, target)
        record_acquisition_receipt(target, identity)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    result = read_first_series_vintage(root, series_id)
    return {**result, "publisher_requests": 1, "cache_hit": False}


def read_first_series_vintage(root: Path, series_id: str) -> dict:
    identity = _identity(series_id)
    parent = _original_parent(root, series_id)
    if not parent.exists():
        return {"series_id": series_id, "status": "missing_original_vintage",
                "first_available_alfred_series_vintage": None,
                "original_source_hash_verified": False,
                "first_publication_verified": False}
    entries = verified_receipted_bundles(parent, identity)
    earliest = []
    for record in entries:
        bundle = record["bundle_path"]
        original = bundle / "response.json"
        if original.is_symlink() or original.stat().st_size > MAX_RESPONSE_BYTES:
            raise ValueError("publisher_vintage_original_file_invalid")
        raw = original.read_bytes()
        meta = record["manifest"]
        if (meta["schema_version"] != 1
                or len(raw) != meta["source_bytes"]
                or sha256(raw).hexdigest() != meta["source_original_sha256"]
                or meta["first_available_alfred_series_vintage"] != _parse(
                    raw, series_id)
                or meta["first_publication_verified"] is not False):
            raise ValueError("publisher_vintage_original_integrity_failed")
        earliest.append(meta["first_available_alfred_series_vintage"])
    # A publisher may revise historical vintage metadata; conflicting
    # independently verified originals are disclosed, never overwritten.
    return {
        "series_id": series_id,
        "status": ("verified_original_publisher_vintage" if len(
            set(earliest)) == 1 else "conflicting_official_vintage_originals"),
        "first_available_alfred_series_vintage":
            earliest[-1] if len(set(earliest)) == 1 else None,
        "all_verified_reported_first_vintages": sorted(set(earliest)),
        "original_versions": len(set(
            entry["bundle_digest"] for entry in entries)),
        "retrieval_receipts": len(entries),
        "original_source_hash_verified": True,
        "first_publication_verified": False,
        "observation_first_release_instants_verified": False,
    }


def publisher_vintage_evidence(root: Path, series_ids: set[str]) -> dict:
    invalid = []
    records = {}
    for sid in sorted(series_ids & set(SOURCES)):
        try:
            record = read_first_series_vintage(root, sid)
        except (OSError, KeyError, ValueError, OriginalReceiptIntegrityError):
            record = {"series_id": sid,
                      "status": "invalid_publisher_vintage_original",
                      "first_publication_verified": False,
                      "original_source_hash_verified": False}
            invalid.append(sid)
        records[sid] = record
    return {
        "operation": "original_publisher_vintage_reconciliation",
        "series": records,
        "verified_series_vintage_sources": sum(
            row["status"] == "verified_original_publisher_vintage"
            for row in records.values()),
        "invalid_original_series": invalid,
        "observation_level_first_publication_verified": False,
        "historical_first_release_assumed_from_http_or_fetch_time": False,
    }
