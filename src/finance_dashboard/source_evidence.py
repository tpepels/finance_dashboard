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


def record_acquisition_receipt(bundle: Path, source_identity: dict) -> Path:
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
