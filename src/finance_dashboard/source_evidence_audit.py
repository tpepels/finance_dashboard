"""Independent, read-only verification of ingestion-to-source receipt links.

No network access, no macro writes, no import parser dependencies. The original
payload SHA, manifest content identity and receipt are checked separately.
This verifies retained acquisition bytes, not publication-vintage accuracy.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re

from .source_capture import canonical_bytes


class SourceEvidenceIntegrityError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _load(path: Path, *, binary: bool = False):
    if path.is_symlink() or not path.is_file():
        raise SourceEvidenceIntegrityError("missing_or_symlinked_archive_file")
    return path.read_bytes() if binary else json.loads(path.read_bytes())


def verify_ingestion_receipt(root: Path, *, series_id: str, scope: str,
                             bundle_digest: str, receipt_name: str) -> dict:
    """Validate an exact successful HTTP-response acquisition receipt."""
    if (not re.fullmatch(r"[a-zA-Z0-9._-]{1,128}", series_id)
            or not re.fullmatch(r"[a-f0-9]{64}", bundle_digest)
            or not re.fullmatch(r"[0-9TZ-]+[a-f0-9]{32}[.]json", receipt_name)
            or scope not in {"full_source_snapshot", "requested_period_subset"}):
        raise SourceEvidenceIntegrityError("invalid_receipt_reference")
    root = Path(root)
    bundle = root / "responses" / series_id / bundle_digest
    receipt_path = bundle.parent / "retrievals" / receipt_name
    manifest_bytes = _load(bundle / "manifest.json", binary=True)
    try:
        manifest = json.loads(manifest_bytes)
        receipt = _load(receipt_path)
    except (ValueError, UnicodeDecodeError) as exc:
        raise SourceEvidenceIntegrityError("invalid_original_receipt_json") from exc
    if (not isinstance(manifest, dict) or not isinstance(receipt, dict)
            or manifest.get("schema_version") != 1
            or receipt.get("schema_version") != 1
            or manifest.get("series_id") != series_id
            or manifest.get("scope") != scope
            or receipt.get("bundle_digest") != bundle_digest
            or receipt.get("manifest_sha256") != sha256(manifest_bytes).hexdigest()
            or receipt.get("source_identity") != manifest.get("content_identity", {}).get("source_identity")
            or manifest.get("source_contract_sha256") != sha256(
                canonical_bytes(manifest.get("source_contract"))).hexdigest()
            or sha256(canonical_bytes(manifest.get("content_identity"))).hexdigest() != bundle_digest):
        raise SourceEvidenceIntegrityError("source_bundle_or_receipt_identity_mismatch")
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        raise SourceEvidenceIntegrityError("source_response_manifest_empty")
    expected = manifest.get("content_identity", {}).get("responses")
    if not isinstance(expected, list) or len(sources) != len(expected):
        raise SourceEvidenceIntegrityError("source_original_response_list_mismatch")
    verified = []
    for index, (source, selected) in enumerate(zip(sources, expected, strict=True)):
        name = f"response-{index}.bin"
        if (source.get("file") != name or selected.get("file") != name
                or {k: source[k] for k in ("file", "url", "sha256", "bytes")} != selected):
            raise SourceEvidenceIntegrityError("source_original_identity_mismatch")
        raw = _load(bundle / name, binary=True)
        if (len(raw) != source["bytes"]
                or sha256(raw).hexdigest() != source["sha256"]):
            raise SourceEvidenceIntegrityError("source_original_hash_mismatch")
        verified.append(source["sha256"])
    return {
        "status": "verified_immutable_original_response",
        "series_id": series_id, "scope": scope,
        "bundle_digest": bundle_digest,
        "response_sha256": verified,
        "source_receipt_verified": True,
        "first_publication_verified": False,
        "no_archive_writes": True,
    }
