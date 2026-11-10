"""Jordà-Schularick-Taylor Macrohistory Database R6: systemic banking crisis start years.

`crisisJST` marks the first year of a systemic financial crisis in 18 advanced
economies, 1870-2020, dated by the authors' published chronology. These dates
are independent of the NBER recession chronology and of market prices, so they
serve as shock context for C05 and P03. Licence: CC BY-NC-SA 4.0 (cite
Jordà, Schularick and Taylor, NBER Macroeconomics Annual 2017).
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import shutil
import tempfile

from python_calamine import CalamineWorkbook

from .bis import ProviderError
from .source_capture import canonical_bytes
from .source_evidence import record_acquisition_receipt

URL = "https://www.macrohistory.net/app/download/9834512569/JSTdatasetR6.xlsx"
FOLDER = "jst-macrohistory"
NAME = "JSTdatasetR6.xlsx"
IDENTITY = {"publisher": "Jordà-Schularick-Taylor Macrohistory Database", "edition": "R6",
            "evidence_type": "jst_macrohistory_dataset"}


def crisis_starts(rows: list[list]) -> dict[str, list[int]]:
    header = [str(cell) for cell in rows[0]]
    if not {"year", "iso", "crisisJST"} <= set(header):
        raise ProviderError("JST dataset layout changed")
    year, iso, crisis = header.index("year"), header.index("iso"), header.index("crisisJST")
    out: dict[str, list[int]] = {}
    for row in rows[1:]:
        if row[crisis] in (1, 1.0, "1"):
            out.setdefault(str(row[iso]), []).append(int(float(row[year])))
    return {country: sorted(years) for country, years in out.items()}


def _rows(raw: bytes) -> list[list]:
    workbook = CalamineWorkbook.from_filelike(io.BytesIO(raw))
    return workbook.get_sheet_by_name(workbook.sheet_names[0]).to_python()


def store(root: Path, raw: bytes) -> Path:
    crisis_starts(_rows(raw))
    content = {"source_identity": IDENTITY, "files": {NAME: {"url": URL, "sha256": sha256(raw).hexdigest(), "bytes": len(raw)}}}
    parent = Path(root) / FOLDER
    parent.mkdir(parents=True, exist_ok=True)
    bundle = parent / sha256(canonical_bytes(content)).hexdigest()
    if not bundle.exists():
        staging = Path(tempfile.mkdtemp(prefix=".jst-", dir=parent))
        try:
            (staging / NAME).write_bytes(raw)
            manifest = {"schema_version": 1, "source_identity": IDENTITY, "content_identity": content,
                        "retrieved_at_utc": datetime.now(timezone.utc).isoformat()}
            (staging / "manifest.json").write_bytes(canonical_bytes(manifest))
            os.rename(staging, bundle)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
    record_acquisition_receipt(bundle, IDENTITY)
    return bundle


_CACHE: dict = {}


def read(root: Path) -> dict:
    from .source_reconciliation import _selected_manifest
    parent = Path(root) / FOLDER
    if not parent.exists():
        raise FileNotFoundError("JST dataset not archived")
    _, manifest_hash, path, manifest, _ = _selected_manifest(parent, IDENTITY)
    if manifest_hash in _CACHE:
        return _CACHE[manifest_hash]
    raw = (path.parent / NAME).read_bytes()
    if sha256(raw).hexdigest() != manifest["content_identity"]["files"][NAME]["sha256"]:
        raise ProviderError("JST dataset differs from its manifest")
    result = {"starts": crisis_starts(_rows(raw)), "source_sha256": sha256(raw).hexdigest(), "url": URL,
              "coverage": "18 advanced economies, 1870-2020"}
    _CACHE[manifest_hash] = result
    return result


def acquire(root: Path) -> Path:
    from .source_policy import managed_client
    with managed_client(timeout=120, follow_redirects=True,
                        headers={"User-Agent": "finance-dashboard-research/0.2 (private research)"}) as client:
        response = client.get(URL)
        if response.status_code != 200 or response.content[:2] != b"PK":
            raise ProviderError("JST dataset request failed")
        return store(root, response.content)


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Archive the Jordà-Schularick-Taylor Macrohistory dataset (R6).")
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps({"bundle": str(acquire(args.evidence_dir))}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
