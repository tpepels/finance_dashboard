"""Immutable, receipt-backed publisher evidence for exact-year STAN measure probes.

A single-year, total-activity probe is not historical industry coverage. The
original cannot enter the country-wide STAN evidence directory or a macro table.
Every retained revision is verified; previously archived bytes are never edited.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile

from .bis import ProviderError
from .source_capture import canonical_bytes
from .source_evidence import record_acquisition_receipt, verified_receipted_bundles
from .source_reconciliation import EvidenceError, _original_file
from .stan_originals import (
    STAN_SURPLUS_CANDIDATES, parse_stan_original_csv, stan_source_request,
)


MAX_PROBE_BYTES = 2_000_000
PROBE_SCOPE = "total_activity_one_exact_year_noncertifying"


def _probe_identity(country: str, year: int, measure: str) -> tuple[dict, str, dict]:
    if measure not in STAN_SURPLUS_CANDIDATES:
        raise ValueError("not_a_known_stan_surplus_probe_measure")
    url, params = stan_source_request(
        country, year, measures=(measure,), activity="_T", end_year=year)
    request = {**params, "format": "csvfile"}
    identity = {
        "provider": "OECD_STAN_EXACT_YEAR_PROBE",
        "country": country, "probe_year": year, "activity": "_T",
        "native_measure": measure, "source_key": url.split("/rest/data/", 1)[-1],
        "request_parameters": request,
    }
    return identity, url, request


def _probe_parent(root: Path, country: str, year: int, measure: str) -> Path:
    _probe_identity(country, year, measure)
    return Path(root) / "stan-2025" / "native-probes" / country / str(year) / (
        "measure-" + measure)


def _probe_facts(raw: bytes, country: str, year: int, measure: str) -> dict:
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_PROBE_BYTES:
        raise ProviderError("Invalid bounded STAN publisher probe size")
    facts = parse_stan_original_csv(
        raw, country=country, start_year=year, end_year=year,
        expected_measures=(measure,), expected_activity="_T")
    if (not facts["source_dataflow_field_verified"]
            or facts["native_measure_observation_counts"].get(measure, 0) < 1):
        raise ProviderError("STAN probe lacks publisher-native measure evidence")
    return facts


def _verified_probe_versions(root: Path, country: str, year: int,
                             measure: str) -> dict:
    identity, url, query = _probe_identity(country, year, measure)
    parent = _probe_parent(root, country, year, measure)
    receipts = verified_receipted_bundles(parent, identity)
    versions = {}
    for receipt in receipts:
        digest = receipt["bundle_digest"]
        if digest in versions:
            continue
        manifest = receipt["manifest"]
        if (manifest.get("schema_version") != 1
                or manifest.get("source_identity") != identity
                or manifest.get("source_url") != url
                or manifest.get("source_request_parameters") != query
                or manifest.get("scope") != PROBE_SCOPE
                or manifest.get("country_coverage_verified") is not False
                or manifest.get("first_publication_verified") is not False):
            raise EvidenceError("original_stan_probe_identity_invalid")
        raw, original_hash = _original_file(
            receipt["bundle_path"], manifest["original"],
            "original.csv", binary=True)
        facts = _probe_facts(raw, country, year, measure)
        content = manifest["content_identity"]
        if (manifest.get("facts") != facts
                or content.get("source_identity") != identity
                or content.get("original_sha256") != original_hash
                or content.get("original_bytes") != len(raw)
                or content.get("facts_sha256") != sha256(canonical_bytes(facts)).hexdigest()
                or sha256(canonical_bytes(content)).hexdigest() != digest):
            raise EvidenceError("original_stan_probe_values_invalid")
        versions[digest] = {
            "bundle_digest": digest,
            "original_sha256": original_hash,
            "numeric_observations": facts["numeric_observations"],
            "original_source_hash_verified": True,
        }
    selected = receipts[-1]
    return {
        "state": "verified_native_csv",
        "country": country, "year": year, "measure": measure,
        **versions[selected["bundle_digest"]],
        "original_versions_verified": len(versions),
        "verified_bundle_digests": sorted(versions),
        "retrieval_receipts_verified": len(receipts),
        "latest_observed_at_utc": selected["observed_at"].isoformat(),
        "publisher_requests": 0, "historical_country_coverage_verified": False,
        "scientific_analysis_certified": False,
    }


def read_stan_probe_evidence(root: Path, *, country: str, year: int,
                             measures: tuple[str, ...]) -> dict:
    """Read-only bounded selection: every prior original must verify.

    Corruption blocks further acquisition; it is never mistaken for a missing
    cached probe. A missing exact-year probe cannot imply measure unavailability.
    """
    selected = tuple(measures)
    if not selected or len(set(selected)) != len(selected):
        raise ValueError("invalid_stan_probe_selection")
    result = []
    for measure in selected:
        folder = _probe_parent(root, country, year, measure)
        if not folder.exists() and not folder.is_symlink():
            result.append({"measure": measure, "state": "not_probed"})
            continue
        try:
            verified = _verified_probe_versions(root, country, year, measure)
            result.append(verified)
        except (EvidenceError, ProviderError, OSError, KeyError, TypeError,
                ValueError, UnicodeError, json.JSONDecodeError):
            result.append({"measure": measure, "state": "invalid_original_probe"})
    return {
        "operation": "stan_exact_year_probe_evidence",
        "country": country, "probe_year": year, "measures": result,
        "verified_measures": [
            item["measure"] for item in result
            if item["state"] == "verified_native_csv"],
        "invalid_measures": [
            item["measure"] for item in result
            if item["state"] == "invalid_original_probe"],
        "publisher_requests": 0, "no_archive_writes": True,
        "country_coverage_verified": False, "scientific_analysis_certified": False,
    }


def store_stan_probe_original(raw: bytes, *, country: str, year: int,
                              measure: str, root: Path) -> dict:
    """Validate and append exactly one publisher response, retaining all vintages."""
    identity, url, params = _probe_identity(country, year, measure)
    facts = _probe_facts(raw, country, year, measure)
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        raise ProviderError("Existing original-evidence root required")
    inspected = read_stan_probe_evidence(
        root, country=country, year=year, measures=(measure,))
    if inspected["invalid_measures"]:
        raise ProviderError("Original STAN probe integrity failure")
    parent = _probe_parent(root, country, year, measure)
    for directory in (parent, parent.parent, parent.parent.parent,
                      parent.parent.parent.parent):
        if directory.is_symlink():
            raise ProviderError("STAN probe directory symlink forbidden")
    parent.mkdir(parents=True, exist_ok=True)
    raw_digest = sha256(raw).hexdigest()
    content = {
        "source_identity": identity, "original_sha256": raw_digest,
        "original_bytes": len(raw),
        "facts_sha256": sha256(canonical_bytes(facts)).hexdigest(),
    }
    bundle_digest = sha256(canonical_bytes(content)).hexdigest()
    bundle = parent / bundle_digest
    staged = None
    try:
        if bundle.exists():
            # Independently verify old bytes before appending a new receipt.
            verified = _verified_probe_versions(root, country, year, measure)
            if (bundle.is_symlink() or
                    bundle_digest not in verified["verified_bundle_digests"]):
                raise EvidenceError("original_probe_bundle_not_verified")
        else:
            staged = Path(tempfile.mkdtemp(prefix=".stan-probe-", dir=parent))
            (staged / "original.csv").write_bytes(raw)
            manifest = {
                "schema_version": 1,
                "source_identity": identity,
                "content_identity": content,
                "source_url": url,
                "source_request_parameters": params,
                "scope": PROBE_SCOPE,
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "original": {"file": "original.csv",
                             "sha256": raw_digest, "bytes": len(raw)},
                "facts": facts,
                "country_coverage_verified": False,
                "first_publication_verified": False,
            }
            (staged / "manifest.json").write_bytes(canonical_bytes(manifest))
            os.rename(staged, bundle)
            staged = None
        receipt = record_acquisition_receipt(bundle, identity)
        return {
            "status": "original_probe_retained",
            "measure": measure, "country": country, "year": year,
            "original_sha256": raw_digest,
            "bundle_digest": bundle_digest,
            "receipt_sha256": sha256(receipt.read_bytes()).hexdigest(),
            "numeric_observations": facts["numeric_observations"],
            "historical_country_coverage_verified": False,
        }
    except (EvidenceError, OSError, KeyError, TypeError, ValueError) as exc:
        raise ProviderError("Original STAN probe could not be preserved") from exc
    finally:
        if staged is not None:
            shutil.rmtree(staged)


