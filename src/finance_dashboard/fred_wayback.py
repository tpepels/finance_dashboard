"""FRED's own downloads as archived by the Internet Archive.

Since April 2026 FRED serves only the latest three years of the ICE BofA US
high-yield option-adjusted spread (BAMLH0A0HYM2). FRED's full download from
before that change survives as a raw Internet Archive capture. The capture is
pinned by the archive's CDX digest (base32 SHA-1 of the payload as served),
stored as an immutable bundle with a receipt, and read back verified. Blank
values stay absent. Over 2023-11 to 2025-11 every day agrees exactly with what
FRED serves today (checked at registration and again in Phase 3).
"""
from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import gzip
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from .bis import ProviderError
from .source_capture import canonical_bytes
from .source_evidence import record_acquisition_receipt

FOLDER = "fred-wayback"
IDENTITY = {"publisher": "Federal Reserve Bank of St. Louis (FRED), archived by the Internet Archive",
            "evidence_type": "fred_download_internet_archive_capture"}
CAPTURES = {
    "BAMLH0A0HYM2": {"timestamp": "20251104204105",
                     "original": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2",
                     "cdx_digest": "N7H2CT4SSAXS66QPXVU35STHEOXRP4IH"},
}


def capture_url(code: str) -> str:
    pin = CAPTURES[code]
    return f"https://web.archive.org/web/{pin['timestamp']}id_/{pin['original']}"


def _digest(payload: bytes) -> str:
    from .msci_regional_factsheets import cdx_digest
    return cdx_digest(payload)


def _decoded(payload: bytes) -> str:
    raw = gzip.decompress(payload) if payload[:2] == b"\x1f\x8b" else payload
    return raw.decode("utf-8-sig")


def parse_fred_csv(text: str, code: str) -> dict[date, Decimal]:
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or [cell.strip() for cell in rows[0]] not in (["observation_date", code], ["DATE", code]):
        raise ProviderError("archived FRED download is not the pinned series")
    values: dict[date, Decimal] = {}
    for row in rows[1:]:
        if not row or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row[0]):
            continue
        day = date.fromisoformat(row[0])
        if day in values:
            raise ProviderError("archived FRED download repeats a date")
        raw = row[1].strip() if len(row) > 1 else ""
        if raw in ("", "."):
            continue
        try:
            value = Decimal(raw)
        except InvalidOperation as exc:
            raise ProviderError("archived FRED value is invalid") from exc
        values[day] = value
    if not values:
        raise ProviderError("archived FRED download has no values")
    return values


def store_capture(root: Path, code: str, payload: bytes) -> Path:
    pin = CAPTURES.get(code)
    if pin is None or _digest(payload) != pin["cdx_digest"]:
        raise ProviderError("archived FRED capture differs from the pinned CDX digest")
    parse_fred_csv(_decoded(payload), code)
    content = {"source_identity": IDENTITY, "series": code, "capture_url": capture_url(code),
               "cdx_digest": pin["cdx_digest"], "payload_sha256": sha256(payload).hexdigest()}
    parent = Path(root) / FOLDER / code
    parent.mkdir(parents=True, exist_ok=True)
    bundle = parent / sha256(canonical_bytes(content)).hexdigest()
    if not bundle.exists():
        staging = Path(tempfile.mkdtemp(prefix=".fred-wayback-", dir=parent))
        try:
            (staging / "archived.bin").write_bytes(payload)
            manifest = {"schema_version": 1, "source_identity": IDENTITY, "content_identity": content,
                        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                        "publication_note": "Capture time bounds when FRED served this file; it is not a release date."}
            (staging / "manifest.json").write_bytes(canonical_bytes(manifest))
            os.rename(staging, bundle)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
    record_acquisition_receipt(bundle, IDENTITY)
    return bundle


def read_fred_wayback(root: Path, code: str) -> tuple[dict[date, Decimal], dict]:
    """Values from the verified stored capture, with its proof; FileNotFoundError when not archived."""
    parent = Path(root) / FOLDER / code
    bundles = sorted(p for p in parent.iterdir() if re.fullmatch(r"[0-9a-f]{64}", p.name)) if parent.is_dir() else []
    if not bundles:
        raise FileNotFoundError(f"no archived FRED capture for {code}")
    if len(bundles) != 1:
        raise ProviderError("archived FRED capture is ambiguous")
    manifest = json.loads((bundles[0] / "manifest.json").read_text())
    payload = (bundles[0] / "archived.bin").read_bytes()
    content = manifest["content_identity"]
    if (bundles[0].name != sha256(canonical_bytes(content)).hexdigest() or content["series"] != code
            or _digest(payload) != content["cdx_digest"] or CAPTURES.get(code, {}).get("cdx_digest") != content["cdx_digest"]
            or sha256(payload).hexdigest() != content["payload_sha256"]):
        raise ProviderError("archived FRED capture failed verification")
    values = parse_fred_csv(_decoded(payload), code)
    return values, {"capture_url": content["capture_url"], "cdx_digest": content["cdx_digest"],
                    "payload_sha256": content["payload_sha256"], "manifest_sha256": sha256((bundles[0] / "manifest.json").read_bytes()).hexdigest(),
                    "first": min(values).isoformat(), "last": max(values).isoformat(), "observations": len(values)}


def acquire(root: Path, code: str) -> Path:
    from .source_policy import managed_client
    payload = bytearray()
    with managed_client(timeout=120, follow_redirects=True,
                        headers={"User-Agent": "finance-dashboard-research/0.2 (private research)"}) as client:
        # The CDX digest covers the stored bytes, so the body is read raw (no transfer decoding).
        with client.stream("GET", capture_url(code)) as response:
            if response.status_code != 200:
                raise ProviderError("archived FRED capture request failed")
            for chunk in response.iter_raw():
                payload.extend(chunk)
                if len(payload) > 20_000_000:
                    raise ProviderError("archived FRED capture is unexpectedly large")
    return store_capture(root, code, bytes(payload))


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Archive FRED downloads preserved by the Internet Archive.")
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--series", default="BAMLH0A0HYM2", choices=sorted(CAPTURES))
    args = parser.parse_args(argv)
    print(json.dumps({"bundle": str(acquire(args.evidence_dir, args.series))}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
