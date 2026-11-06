"""Immutable originals for approved structured roles without native adapters.

Accept only explicit operator-supplied original CSV/JSON, verify native row
identity, date fields, finite printed numbers and exact approved role contract.
A file hash plus user-declared scope does not establish a publisher's population,
economic meaning, common release, or earliest public disclosure. The original
bytes and every old version/receipt remain recoverable.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from .source_capture import canonical_bytes
from .source_evidence import record_acquisition_receipt, verified_receipted_bundles
from .source_policy_registry import PolicyRegistry

MAX_NATIVE_BYTES = 30_000_000
MAX_NATIVE_ROWS = 100_000
_COLUMN = re.compile(r"[A-Za-z][A-Za-z0-9_ -]{0,79}\Z")
_ID = re.compile(r"[A-Z][0-9]{2}\Z")
_ROLE = re.compile(r"[a-z][a-z0-9_]{0,99}\Z")


def _role(document: dict, analysis_id: str, name: str) -> dict:
    if not _ID.fullmatch(analysis_id) or not _ROLE.fullmatch(name):
        raise ValueError("unregistered_original_role_id")
    analyses = [item for item in document["analyses"] if item["id"] == analysis_id]
    if len(analyses) != 1:
        raise ValueError("unregistered_original_analysis")
    roles = [item for item in analyses[0][
        "comparison_contract"]["original_requirements"]
        if item["role"] == name and
        item["input_type"] != "scalar_history" and
        not item["artifact_ids"]]
    if len(roles) != 1:
        raise ValueError("role_has_separate_original_source_adapter")
    return roles[0]


def _identity(analysis_id: str, name: str) -> dict:
    return {
        "source_family": "phase2_explicit_structured_original",
        "analysis_id": analysis_id, "original_role": name,
    }


def _parent(root: Path, analysis_id: str, name: str) -> Path:
    return Path(root) / "native-role-originals" / analysis_id / name


def _audit(raw: bytes, *, fmt: str, fields: list[str],
           key_fields: list[str], numeric_fields: list[str],
           date_field: str | None) -> dict:
    if (fmt not in {"csv", "json"} or not isinstance(raw, bytes) or
            not 1 <= len(raw) <= MAX_NATIVE_BYTES
            or not fields or len(fields) > 100
            or len(set(fields)) != len(fields)
            or not all(isinstance(f, str) and _COLUMN.fullmatch(f)
                       for f in fields)
            or not key_fields or len(set(key_fields)) != len(key_fields)
            or not set(key_fields) <= set(fields)
            or len(set(numeric_fields)) != len(numeric_fields)
            or not set(numeric_fields) <= set(fields)
            or date_field is not None and date_field not in fields):
        raise ValueError("invalid_original_structured_native_schema")
    try:
        if fmt == "csv":
            reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
            if reader.fieldnames != fields:
                raise ValueError("original_csv_columns_disagree_with_schema")
            rows = list(reader)
        else:
            rows = json.loads(raw)
            if not isinstance(rows, list):
                raise ValueError("original_json_must_be_array")
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("original_structured_content_invalid") from exc
    if not rows or len(rows) > MAX_NATIVE_ROWS:
        raise ValueError("original_native_record_count_invalid")
    seen, missing_numeric, dates, value_count = set(), 0, set(), 0
    for row in rows:
        if (not isinstance(row, dict) or set(row) != set(fields)
                or any(value is not None and not isinstance(value, (str, int, float))
                       for value in row.values())):
            raise ValueError("original_native_row_fields_invalid")
        key = tuple(str(row[field]) if row[field] is not None else ""
                    for field in key_fields)
        if any(not value.strip() for value in key) or key in seen:
            raise ValueError("original_native_record_key_missing_or_duplicated")
        seen.add(key)
        for field in numeric_fields:
            raw_number = row[field]
            if raw_number is None or str(raw_number).strip() in {"", ".", "NA", "N/A"}:
                missing_numeric += 1
                continue
            try:
                value = Decimal(str(raw_number))
            except InvalidOperation as exc:
                raise ValueError("original_native_numeric_value_invalid") from exc
            if not value.is_finite():
                raise ValueError("original_native_numeric_value_nonfinite")
            value_count += 1
        if date_field is not None:
            candidate = str(row[date_field]) if row[date_field] is not None else ""
            try:
                normalized = date.fromisoformat(candidate if len(
                    candidate) != 4 else candidate + "-01-01")
            except ValueError as exc:
                raise ValueError("original_native_date_invalid") from exc
            dates.add(normalized.isoformat())
    return {
        "record_count": len(rows),
        "distinct_original_record_keys": len(seen),
        "numeric_values_reported": value_count,
        "missing_numeric_values_not_imputed": missing_numeric,
        "earliest_record_date": min(dates) if dates else None,
        "latest_record_date": max(dates) if dates else None,
        "numeric_values_not_converted_or_aggregated": True,
        "original_publisher_dimensions_independently_verified": False,
        "observation_first_release_verified": False,
    }


def register_native_role_original(document: dict, *, root: Path,
                                  analysis_id: str, role: str,
                                  original: Path, fields: list[str],
                                  key_fields: list[str],
                                  numeric_fields: list[str] | None = None,
                                  date_field: str | None = None,
                                  origin: str = "user_supplied",
                                  publisher_url: str | None = None) -> dict:
    approved = _role(document, analysis_id, role)
    if (origin not in {"user_supplied", "publisher_original"}
            or origin == "user_supplied" and publisher_url is not None
            or origin == "publisher_original" and not publisher_url):
        raise ValueError("invalid_original_source_origin")
    policy = None
    if publisher_url is not None:
        policy = PolicyRegistry().for_url(publisher_url).id
    path = Path(original)
    if path.is_symlink() or not path.is_file():
        raise ValueError("original_file_missing_or_symlink")
    fmt = path.suffix.lower().lstrip(".")
    raw = path.read_bytes()
    numeric = list(numeric_fields or [])
    facts = _audit(raw, fmt=fmt, fields=fields,
                   key_fields=key_fields, numeric_fields=numeric,
                   date_field=date_field)
    schema = {
        "fields": fields, "key_fields": key_fields,
        "numeric_fields": numeric, "date_field": date_field,
        "format": fmt, "origin": origin,
        "publisher_url": publisher_url, "publisher_policy": policy,
    }
    identity = _identity(analysis_id, role)
    contract_sha = sha256(canonical_bytes(approved)).hexdigest()
    digest = sha256(canonical_bytes({
        "source_identity": identity,
        "original_sha256": sha256(raw).hexdigest(),
        "approved_role_contract_sha256": contract_sha,
        "source_schema": schema,
    })).hexdigest()
    parent = _parent(root, analysis_id, role)
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / digest
    staging = None
    try:
        if target.exists():
            # A retained immutable bundle cannot accept another receipt
            # before every earlier version has passed read-only verification.
            read_native_role_original(
                document, root=root, analysis_id=analysis_id, role=role)
        if not target.exists():
            staging = Path(tempfile.mkdtemp(
                dir=parent, prefix=".native-original-"))
            with (staging / ("original." + fmt)).open("wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            manifest = {
                "schema_version": 1, "source_identity": identity,
                "approved_role_contract_sha256": contract_sha,
                "original_sha256": sha256(raw).hexdigest(),
                "original_bytes": len(raw),
                "source_schema": schema, "native_facts": facts,
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "economic_scope_verified": False,
                "first_publication_verified": False,
            }
            (staging / "manifest.json").write_bytes(canonical_bytes(manifest))
            os.rename(staging, target)
        record_acquisition_receipt(target, identity)
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging)
    return read_native_role_original(document, root=root,
                                     analysis_id=analysis_id, role=role)


def read_native_role_original(document: dict, *, root: Path,
                              analysis_id: str, role: str) -> dict:
    approved = _role(document, analysis_id, role)
    parent = _parent(root, analysis_id, role)
    if not parent.exists():
        return {
            "status": "original_not_registered",
            "original_source_hash_verified": False,
            "original_economic_scope_verified": False,
            "first_publication_verified": False,
        }
    records = verified_receipted_bundles(
        parent, _identity(analysis_id, role))
    versions = set()
    for entry in records:
        manifest = entry["manifest"]
        if (manifest["schema_version"] != 1
                or manifest["approved_role_contract_sha256"] !=
                sha256(canonical_bytes(approved)).hexdigest()
                or manifest["economic_scope_verified"] is not False
                or manifest["first_publication_verified"] is not False):
            raise ValueError("original_role_contract_or_evidence_invalid")
        schema = manifest["source_schema"]
        expected_digest = sha256(canonical_bytes({
            "source_identity": _identity(analysis_id, role),
            "original_sha256": manifest["original_sha256"],
            "approved_role_contract_sha256": manifest[
                "approved_role_contract_sha256"],
            "source_schema": schema,
        })).hexdigest()
        if entry["bundle_digest"] != expected_digest:
            raise ValueError("original_native_bundle_content_identity_mismatch")
        original = entry["bundle_path"] / (
            "original." + schema["format"])
        if (original.is_symlink() or not original.is_file()
                or original.stat().st_size > MAX_NATIVE_BYTES):
            raise ValueError("original_role_file_invalid")
        raw = original.read_bytes()
        if (len(raw) != manifest["original_bytes"]
                or sha256(raw).hexdigest() != manifest["original_sha256"]
                or _audit(raw, fmt=schema["format"],
                          fields=schema["fields"],
                          key_fields=schema["key_fields"],
                          numeric_fields=schema["numeric_fields"],
                          date_field=schema["date_field"]) != manifest[
                              "native_facts"]):
            raise ValueError("original_role_record_or_hash_mismatch")
        versions.add(entry["bundle_digest"])
    last = records[-1]["manifest"]
    return {
        "status": "hash_verified_native_structured_original_partial",
        "original_source_hash_verified": True,
        "original_versions": len(versions),
        "retrieval_receipts": len(records),
        "native_facts": last["native_facts"],
        "origin": last["source_schema"]["origin"],
        "publisher_policy": last["source_schema"]["publisher_policy"],
        "original_economic_scope_verified": False,
        "first_publication_verified": False,
        "original_role_accepted": False,
    }


def native_role_original_evidence(document: dict, root: Path) -> dict:
    collected = {}
    total = 0
    for analysis in document["analyses"]:
        for role in analysis["comparison_contract"]["original_requirements"]:
            if role["input_type"] == "scalar_history" or role["artifact_ids"]:
                continue
            total += 1
            key = analysis["id"] + ":" + role["role"]
            try:
                collected[key] = read_native_role_original(
                    document, root=root, analysis_id=analysis["id"],
                    role=role["role"])
            except (OSError, ValueError, KeyError, TypeError):
                collected[key] = {
                    "status": "invalid_original_role_archive",
                    "original_source_hash_verified": False,
                    "first_publication_verified": False,
                    "original_role_accepted": False,
                }
    return {
        "operation": "phase2_native_role_originals",
        "unbound_structured_roles": total,
        "hash_verified_partial_roles": sum(
            v.get("original_source_hash_verified") is True
            for v in collected.values()),
        "invalid_archived_roles": sorted(k for k, v in collected.items()
                                         if v["status"] ==
                                         "invalid_original_role_archive"),
        "roles": collected,
        "first_publication_verified": False,
        "scientific_analysis_certified": False,
    }
