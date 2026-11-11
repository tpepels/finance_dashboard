"""Append-only receipts for observations of immutable original-source bundles."""
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from uuid import uuid4

from .bis import ProviderError


def record_acquisition_receipt(bundle: Path, source_identity: dict, *,
                               acquisition: dict | None = None) -> Path:
    """Atomically append one receipt after a downloaded source pair is validated.

    A publisher can return an older byte-identical dataset after a revision.
    Receipt time records that new acquisition without changing the old bundle.
    """
    temporary = None
    try:
        if not re.fullmatch(r"[0-9a-f]{64}", bundle.name) or bundle.is_symlink():
            raise ValueError("source bundle identity")
        manifest_hash = sha256((bundle / "manifest.json").read_bytes()).hexdigest()
        observed = datetime.now(timezone.utc)
        receipts = bundle.parent / "retrievals"
        receipts.mkdir(parents=True, exist_ok=True)
        receipt = receipts / (observed.strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex + ".json")
        record = {"schema_version": 1, "observed_at_utc": observed.isoformat(),
                  "bundle_digest": bundle.name, "manifest_sha256": manifest_hash,
                  "source_identity": source_identity}
        if acquisition is not None:
            # Association with a shared original is observed again without
            # claiming a second publisher retrieval took place.
            record["acquisition"] = acquisition
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix=".receipt-",
                                         suffix=".json", dir=receipts, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(record, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        # link publishes a fully written record and refuses to overwrite any
        # existing receipt, unlike replacing a mutable 'latest' pointer.
        os.link(temporary, receipt)
        return receipt
    except (OSError, ValueError) as exc:
        raise ProviderError("Original source acquisition receipt could not be archived") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)



class OriginalReceiptIntegrityError(ValueError):
    """Retained source evidence cannot be independently verified."""


def verified_receipted_bundles(parent: Path, source_identity: dict) -> list[dict]:
    """Verify every immutable manifest referenced by a native source receipt.

    The single shared receipt boundary checks all historical bundle references,
    not just the most recently observed one. It refuses orphaned bundles,
    symlinks, malformed receipts, modified manifests and unexpected identities.
    Caller-specific adapters validate original payload bytes and parsed facts.

    Returns one entry per receipt, sorted by observation time. Identical original
    bytes legitimately have multiple receipts but only one bundle directory.
    Nothing is changed on disk.
    """
    parent = Path(parent)
    receipts = parent / "retrievals"
    try:
        if (parent.is_symlink() or not parent.is_dir() or
                receipts.is_symlink() or not receipts.is_dir()):
            raise OriginalReceiptIntegrityError("original_receipt_directory_invalid")
        entries = []
        bundles = set()
        for receipt_path in sorted(receipts.iterdir()):
            if receipt_path.name.startswith("."):
                continue
            if (receipt_path.is_symlink() or not receipt_path.is_file() or
                    receipt_path.suffix != ".json" or
                    receipt_path.stat().st_size > 32_768):
                raise OriginalReceiptIntegrityError("original_receipt_file_invalid")
            raw = receipt_path.read_bytes()
            record = json.loads(raw)
            observed = datetime.fromisoformat(
                record["observed_at_utc"].replace("Z", "+00:00"))
            bundle_id = record["bundle_digest"]
            manifest_sha = record["manifest_sha256"]
            if (record.get("schema_version") != 1
                    or record.get("source_identity") != source_identity
                    or observed.tzinfo is None
                    or not isinstance(bundle_id, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", bundle_id)
                    or not isinstance(manifest_sha, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", manifest_sha)):
                raise OriginalReceiptIntegrityError("original_receipt_identity_mismatch")
            bundle = parent / bundle_id
            manifest_path = bundle / "manifest.json"
            if (bundle.is_symlink() or not bundle.is_dir()
                    or manifest_path.is_symlink()
                    or not manifest_path.is_file()
                    or manifest_path.stat().st_size > 4_000_000):
                raise OriginalReceiptIntegrityError("original_receipt_manifest_invalid")
            manifest_raw = manifest_path.read_bytes()
            if sha256(manifest_raw).hexdigest() != manifest_sha:
                raise OriginalReceiptIntegrityError("original_receipt_manifest_hash_mismatch")
            manifest = json.loads(manifest_raw)
            if not isinstance(manifest, dict) or manifest.get("source_identity") != source_identity:
                raise OriginalReceiptIntegrityError("original_receipt_source_mismatch")
            bundles.add(bundle_id)
            entries.append({
                "observed_at": observed, "bundle_digest": bundle_id,
                "manifest_sha256": manifest_sha, "manifest": manifest,
                "receipt_sha256": sha256(raw).hexdigest(), "bundle_path": bundle,
            })
        if not entries:
            raise OriginalReceiptIntegrityError("original_receipt_missing")
        actual = set()
        for path in parent.iterdir():
            if path.name == "retrievals" or path.name.startswith("."):
                continue
            if (path.is_symlink() or not path.is_dir()
                    or not re.fullmatch(r"[0-9a-f]{64}", path.name)):
                raise OriginalReceiptIntegrityError("original_bundle_directory_invalid")
            actual.add(path.name)
        if actual != bundles:
            raise OriginalReceiptIntegrityError("unreferenced_or_missing_original_bundle")
        return sorted(entries, key=lambda item: (
            item["observed_at"], item["receipt_sha256"]))
    except OriginalReceiptIntegrityError:
        raise
    except (OSError, KeyError, TypeError, ValueError, OverflowError, json.JSONDecodeError):
        raise OriginalReceiptIntegrityError("original_receipt_invalid") from None
