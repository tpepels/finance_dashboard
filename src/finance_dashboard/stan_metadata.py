"""Read-only discovery of exact OECD STAN 2025 MEASURE codes from SDMX structure.

Publisher metadata is not itself proof that an individual country/period
contains observations. Never infer numeric values or amend archived responses.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import os
import shutil
import tempfile
import xml.etree.ElementTree as ET

from .source_capture import canonical_bytes
from .source_evidence import record_acquisition_receipt, verified_receipted_bundles
from .source_reconciliation import EvidenceError, _original_file
from .bis import ProviderError

from .stan_originals import STAN_FLOW

MAX_STRUCTURE_BYTES = 20_000_000
STRUCTURE_URL = ("https://sdmx.oecd.org/public/rest/dataflow/"
                 "OECD.STI.PIE/DSD_STAN@DF_STAN_2025/1.0")
STRUCTURE_PARAMS = {"references": "all"}
STRUCTURE_ACCEPT = "application/vnd.sdmx.structure+xml;version=2.1"


def local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def parse_stan_measure_structure(raw: bytes) -> dict:
    """Extract the exact referenced MEASURE codelist from SDMX-ML metadata.

    Fail closed when the dataflow, measure dimension or codelist is absent.
    """
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_STRUCTURE_BYTES:
        raise ValueError("invalid_stan_structure_response_size")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError("invalid_stan_structure_xml") from exc
    flows = [x for x in root.iter() if local_name(x) == "Dataflow"
             and x.get("id") == "DSD_STAN@DF_STAN_2025"
             and x.get("agencyID") == "OECD.STI.PIE"]
    if len(flows) != 1:
        raise ValueError("publisher_stan_2025_dataflow_missing_or_ambiguous")
    dimensions = [x for x in root.iter()
                  if local_name(x) in ("Dimension", "MeasureDimension")
                  and x.get("id") == "MEASURE"]
    if len(dimensions) != 1:
        raise ValueError("publisher_measure_dimension_missing_or_ambiguous")
    dimension_refs = [x.get("id") for x in dimensions[0].iter()
                      if local_name(x) == "Ref" and x.get("id")]
    if len(dimension_refs) != 1:
        raise ValueError("publisher_measure_codelist_ref_missing_or_ambiguous")
    candidates = [x for x in root.iter()
                  if local_name(x) == "Codelist"
                  and x.get("id") == dimension_refs[0]]
    if len(candidates) != 1:
        raise ValueError("publisher_measure_codelist_missing_or_ambiguous")
    codelist = candidates[0]
    measures = []
    for code in codelist:
        if local_name(code) != "Code":
            continue
        code_id = code.get("id")
        names = [n for n in code if local_name(n) == "Name"]
        english = next(
            (n.text or "" for n in names
             if n.get("{http://www.w3.org/XML/1998/namespace}lang") == "en"), None)
        label = english if english is not None else (
            (names[0].text or "") if names else "")
        if not code_id:
            raise ValueError("publisher_measure_code_without_id")
        measures.append({"id": code_id, "label": label})
    if not measures or len({m["id"] for m in measures}) != len(measures):
        raise ValueError("publisher_measure_code_set_invalid")
    income = [m for m in measures
              if "surplus" in m["label"].lower() or "mixed income" in m["label"].lower()]
    return {
        "dataflow": STAN_FLOW,
        "measure_codelist_id": codelist.get("id"),
        "codelist_agency": codelist.get("agencyID"),
        "measure_code_count": len(measures),
        "surplus_measures": income,
        "historical_candidates_present": [
            m["id"] for m in measures
            if m["id"] in ("B2N_B3_N", "B2N_B3N", "B2G_B3G", "B2N", "B2G")
        ],
        "source_sha256": sha256(raw).hexdigest(),
        "publisher_values_acquired": False,
        "country_coverage_verified": False,
    }



# Metadata is a native source original with its own immutable receipt chain.
# Do not place it in the scalar macro response gateway or STAN country scopes.
STRUCTURE_IDENTITY = {
    "provider": "OECD_STAN_METADATA",
    "source_key": STRUCTURE_URL,
    "query": STRUCTURE_PARAMS,
    "requested_accept": STRUCTURE_ACCEPT,
}


def _structure_parent(root: Path) -> Path:
    return Path(root) / "stan-2025" / "publisher-structure"


def _validate_structure_bundle(bundle: Path) -> dict:
    """Independently verify the original XML, manifest and extracted codelist."""
    if bundle.is_symlink() or not bundle.is_dir():
        raise EvidenceError("publisher_structure_bundle_invalid")
    manifest_path = bundle / "manifest.json"
    if manifest_path.is_symlink():
        raise EvidenceError("publisher_structure_manifest_invalid")
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    raw, digest = _original_file(
        bundle, manifest["original"], "structure.xml", binary=True)
    parsed = parse_stan_measure_structure(raw)
    content = manifest["content_identity"]
    if (manifest.get("schema_version") != 1
            or manifest.get("source_identity") != STRUCTURE_IDENTITY
            or manifest.get("source_url") != STRUCTURE_URL
            or manifest.get("source_request_parameters") != STRUCTURE_PARAMS
            or manifest.get("source_accept") != STRUCTURE_ACCEPT
            or manifest.get("parsed_structure") != parsed
            or content.get("source_identity") != STRUCTURE_IDENTITY
            or content.get("original_sha256") != digest
            or content.get("original_bytes") != len(raw)
            or content.get("parsed_sha256") != sha256(canonical_bytes(parsed)).hexdigest()
            or sha256(canonical_bytes(content)).hexdigest() != bundle.name):
        raise EvidenceError("publisher_structure_identity_mismatch")
    return {"bundle_digest": bundle.name, "parsed": parsed}


def read_stan_structure(root: Path) -> dict:
    """Independently verify all archived publisher-structure source versions.

    Receipt, manifest, bundle and orphan integrity rules are shared with every
    versioned native original. A current codelist never certifies historical
    country observations or source publication vintages.
    """
    parent = _structure_parent(root)
    if not parent.exists() and not parent.is_symlink():
        return {"status": "metadata_not_acquired", "originals_verified": 0,
                "publisher_requests": 0, "no_archive_writes": True}
    try:
        if Path(root).is_symlink() or parent.parent.is_symlink():
            raise EvidenceError("publisher_structure_path_invalid")
        receipts = verified_receipted_bundles(parent, STRUCTURE_IDENTITY)
        verified = {}
        for receipt in receipts:
            digest = receipt["bundle_digest"]
            if digest not in verified:
                verified[digest] = _validate_structure_bundle(receipt["bundle_path"])
        selected = receipts[-1]
        parsed = verified[selected["bundle_digest"]]["parsed"]
        return {
            "status": "verified_publisher_structure",
            "originals_verified": len(verified),
            "retrieval_receipts_verified": len(receipts),
            "bundle_digest": selected["bundle_digest"],
            "latest_retrieval_time": selected["observed_at"].isoformat(),
            **parsed,
            "publisher_requests": 0, "no_archive_writes": True,
        }
    except (EvidenceError, ProviderError, OSError, KeyError, TypeError,
            ValueError, UnicodeError, json.JSONDecodeError):
        return {"status": "invalid_metadata_original_or_receipt",
                "originals_verified": 0, "publisher_requests": 0,
                "no_archive_writes": True}


def store_stan_structure(raw: bytes, *, root: Path) -> dict:
    """Preserve an official publisher SDMX structure byte-for-byte, append-only."""
    parsed = parse_stan_measure_structure(raw)
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        raise ProviderError("Existing source-evidence root required")
    previous = read_stan_structure(root)
    if previous["status"] == "invalid_metadata_original_or_receipt":
        raise ProviderError("Existing STAN structure evidence is invalid")
    parent = _structure_parent(root)
    if parent.is_symlink() or parent.parent.is_symlink():
        raise ProviderError("STAN metadata evidence directory is a symbolic link")
    parent.mkdir(parents=True, exist_ok=True)
    original_digest = sha256(raw).hexdigest()
    content = {
        "source_identity": STRUCTURE_IDENTITY,
        "original_sha256": original_digest,
        "original_bytes": len(raw),
        "parsed_sha256": sha256(canonical_bytes(parsed)).hexdigest(),
    }
    bundle_digest = sha256(canonical_bytes(content)).hexdigest()
    bundle = parent / bundle_digest
    staged = None
    try:
        if bundle.exists():
            _validate_structure_bundle(bundle)
            original = bundle / "structure.xml"
            if original.is_symlink() or original.read_bytes() != raw:
                raise EvidenceError("publisher_structure_original_changed")
        else:
            staged = Path(tempfile.mkdtemp(prefix=".structure-", dir=parent))
            (staged / "structure.xml").write_bytes(raw)
            manifest = {
                "schema_version": 1,
                "source_identity": STRUCTURE_IDENTITY,
                "content_identity": content,
                "source_url": STRUCTURE_URL,
                "source_request_parameters": STRUCTURE_PARAMS,
                "source_accept": STRUCTURE_ACCEPT,
                "scope": "official_dataflow_structure_all_referenced_measures",
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "original": {"file": "structure.xml",
                             "sha256": original_digest, "bytes": len(raw)},
                "parsed_structure": parsed,
                "country_coverage_verified": False,
                "first_publication_verified": False,
            }
            (staged / "manifest.json").write_bytes(canonical_bytes(manifest))
            os.rename(staged, bundle)
            staged = None
        receipt = record_acquisition_receipt(bundle, STRUCTURE_IDENTITY)
        return {
            "status": "original_publisher_structure_retained",
            "bundle_digest": bundle_digest,
            "source_sha256": original_digest,
            "receipt_sha256": sha256(receipt.read_bytes()).hexdigest(),
            "country_coverage_verified": False,
        }
    except (EvidenceError, OSError, KeyError, TypeError, ValueError) as exc:
        raise ProviderError("Publisher structure source could not be archived") from exc
    finally:
        if staged is not None:
            shutil.rmtree(staged)
