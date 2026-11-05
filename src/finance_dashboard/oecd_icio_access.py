"""Retain exact official ICIO download responses, including publisher denials.

Access evidence never certifies a matrix, publication vintage or release match.
The canonical ICIO reader exposes these records beside its original accounting.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

import httpx
from .source_policy import managed_client, require_managed_client

from .source_capture import canonical_bytes
from .source_evidence import record_acquisition_receipt


PUBLISHER_ROOT = "https://webfs-sti.oecd.org/files/STI-PIE/ICIO/2025"
ARCHIVES = ("1995-2000_SML.zip", "2001-2005_SML.zip", "2006-2010_SML.zip",
            "2011-2015_SML.zip", "2016-2022_SML.zip")
PUBLISHER_URLS = {name: f"{PUBLISHER_ROOT}/{name}" for name in
                  (*ARCHIVES, "ReadMe_ICIO_small.xlsx", "ICIO2025annex.pdf")}
ACCESS_IDENTITY = {"publisher": "OECD", "edition": "2025", "table": "regular",
                   "evidence_type": "publisher_download_access_diagnostic"}
SAFE_RESPONSE_HEADERS = frozenset({"content-type", "content-length", "last-modified", "etag",
    "date", "server", "cf-mitigated", "cf-ray", "location"})
MAX_RESPONSE_BYTES = 1_500_000_000


def _hash(path):
    digest = sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _classification(path, source):
    status = source["http_status"]
    if status == 403 and source["headers"].get("cf-mitigated") == "challenge":
        return "http_403_cloudflare_challenge"
    if status != 200:
        return f"http_{status}_download_failed"
    name = source["name"]
    if name.endswith(".zip") and zipfile.is_zipfile(path):
        return "publisher_archive_retained_pending_matrix_validation"
    if name.endswith(".xlsx") and zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            if "xl/workbook.xml" in archive.namelist():
                return "publisher_readme_retained"
    if name.endswith(".pdf"):
        with Path(path).open("rb") as stream:
            if stream.read(5) == b"%PDF-":
                return "publisher_annex_retained"
    return "unexpected_publisher_payload"


def _verify_bundle(folder):
    if folder.is_symlink() or (folder / "manifest.json").is_symlink():
        raise ValueError("icio_publisher_access_identity_invalid")
    manifest = json.loads((folder / "manifest.json").read_bytes())
    sources = manifest["sources"]
    content = {"source_identity": ACCESS_IDENTITY, "sources": sources}
    if (manifest.get("schema_version") != 1 or manifest.get("source_identity") != ACCESS_IDENTITY
            or sha256(canonical_bytes(content)).hexdigest() != folder.name
            or [row["name"] for row in sources] != list(PUBLISHER_URLS)):
        raise ValueError("icio_publisher_access_identity_invalid")
    for source in sources:
        name = source["name"]
        path = folder / (name + ".response")
        if (source["url"] != PUBLISHER_URLS[name] or path.is_symlink()
                or path.stat().st_size != source["bytes"] or _hash(path) != source["sha256"]
                or type(source["http_status"]) is not int
                or not 100 <= source["http_status"] <= 599
                or not set(source["headers"]).issubset(SAFE_RESPONSE_HEADERS)
                or _classification(path, source) != source["classification"]):
            raise ValueError("icio_publisher_access_response_invalid")
    return manifest


def capture_publisher_access(evidence_root: Path, *, client: httpx.Client | None = None) -> Path:
    """GET exact registered official routes once, without challenge handling.

    Preserve whole response bodies and safe transport headers; successful ZIPs
    are retained for inspection and cannot become validated ICIO by this path.
    Transport exceptions fail visibly and never publish an incomplete batch.
    """
    parent = Path(evidence_root) / "icio" / "publisher-access"
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".publisher-access-", dir=parent))
    owned_client = client is None
    client = require_managed_client(client) if client is not None else managed_client(timeout=60, follow_redirects=False)
    try:
        sources = []
        for name, url in PUBLISHER_URLS.items():
            path = staging / (name + ".response")
            with client.stream("GET", url, follow_redirects=False) as response:
                size = 0
                with path.open("wb") as stream:
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > MAX_RESPONSE_BYTES:
                            raise ValueError("icio_publisher_response_size_exceeded")
                        stream.write(chunk)
                    stream.flush()
                    os.fsync(stream.fileno())
                source = {"name": name, "url": url, "request_method": "GET",
                    "http_status": response.status_code, "bytes": size, "sha256": _hash(path),
                    "headers": {key: value for key, value in response.headers.items()
                                if key in SAFE_RESPONSE_HEADERS}}
                source["classification"] = _classification(path, source)
                sources.append(source)
        content = {"source_identity": ACCESS_IDENTITY, "sources": sources}
        folder = parent / sha256(canonical_bytes(content)).hexdigest()
        (staging / "manifest.json").write_bytes(canonical_bytes({"schema_version": 1,
            **content, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "first_publication_verified": False,
            "note": "HTTP dates are retrieval/transport evidence; access denials are not ICIO matrices."}))
        if folder.exists():
            _verify_bundle(folder)
        else:
            os.rename(staging, folder)
        _verify_bundle(folder)
        record_acquisition_receipt(folder, ACCESS_IDENTITY)
        return folder
    finally:
        if owned_client:
            client.close()
        if staging.exists():
            shutil.rmtree(staging)


def read_publisher_access(evidence_root: Path) -> dict:
    """Verify acquisition receipts and exact responses without changing readiness."""
    parent = Path(evidence_root) / "icio" / "publisher-access"
    if not parent.exists():
        return {"status": "publisher_downloads_not_attempted", "response_bytes_verified": False,
                "publisher_archive_acquired": False, "publisher_verified_years": []}
    from .source_reconciliation import _selected_manifest
    observed, manifest_hash, path, _manifest, selection = _selected_manifest(parent, ACCESS_IDENTITY)
    sources = _verify_bundle(path.parent)["sources"]
    archives = [row for row in sources if row["name"] in ARCHIVES]
    blocked = sum(row["http_status"] != 200 for row in archives)
    acquired = sum(row["classification"] == "publisher_archive_retained_pending_matrix_validation"
                   for row in archives)
    readme = next(row for row in sources if row["name"] == "ReadMe_ICIO_small.xlsx")
    definition = {"publisher_readme_identity_verified": False}
    from .icio import README_SHA256, readme_dimensions
    if readme["http_status"] == 200 and readme["sha256"] == README_SHA256:
        dimensions = readme_dimensions((path.parent / (readme["name"] + ".response")).read_bytes())
        areas = list(dict.fromkeys(code.split("_", 1)[0] for code in dimensions["industry_codes"]))
        definition = {"publisher_readme_identity_verified": True, "readme_sha256": README_SHA256,
            "unit": dimensions["unit"], "country_count_including_rest_of_world": dimensions["country_count"],
            "industry_count": dimensions["industry_count"], "industry_nodes": len(dimensions["industry_codes"]),
            "final_demand_columns": len(dimensions["final_demand_codes"]),
            "rest_of_world_included": "ROW" in areas,
            "china_mexico_split_nodes_included": any(area in areas for area in ("CN1", "CN2", "MX1", "MX2")),
            "revision_date_provided_by_readme": False,
            "note": "ReadMe identifies the regular current-price dimensions; transport Last-Modified does not establish the ICIO matrix revision."}
    return {"status": ("publisher_downloads_blocked" if blocked == len(ARCHIVES)
                       else "publisher_downloads_require_matrix_validation"),
        "attempted_archive_years": [1995, 2022], "blocked_archive_count": blocked,
        "retained_archive_count": acquired, "publisher_archive_acquired": acquired > 0,
        "publisher_verified_years": [], "response_bytes_verified": True,
        "responses": sources, "source_manifest_sha256": manifest_hash,
        "bundle_digest": path.parent.name, "acquisition_observed_at_utc": observed.isoformat(),
        "selection_method": selection, "first_publication_verified": False,
        "publisher_revision_match_verified": False,
        "publisher_definition": definition,
        "limitation": "Download responses establish access only. Failed HTML bodies are not matrix evidence; retained ZIPs require full original accounting and edition validation."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--capture", action="store_true", help="Make one exact-route GET attempt per official file")
    args = parser.parse_args()
    if args.capture:
        capture_publisher_access(args.root)
    print(json.dumps(read_publisher_access(args.root), indent=2))


if __name__ == "__main__":
    main()
