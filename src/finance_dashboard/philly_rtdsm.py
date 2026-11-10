"""Philadelphia Fed Real-Time Data Set for Macroeconomists: civilian unemployment rate vintages (RUC).

Each quarterly vintage column holds the monthly unemployment rates as the
Bureau of Labor Statistics had published them by the middle of the quarter's
second month, collected by the Philadelphia Fed from the original releases.
From each vintage's own data the Sahm rule is recomputed for its latest month:
the three-month average less the lowest three-month average of the prior
twelve months. Comparing that with FRED's real-time Sahm series checks FRED's
ALFRED-based values against the agency's releases.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from python_calamine import CalamineWorkbook

from .bis import ProviderError
from .source_capture import canonical_bytes
from .source_evidence import record_acquisition_receipt

URL = ("https://www.philadelphiafed.org/-/media/frbp/assets/surveys-and-data/real-time-data/data-files/xlsx/rucQvMd.xlsx")
FOLDER = "philly-rtdsm"
NAME = "rucQvMd.xlsx"
IDENTITY = {"publisher": "Federal Reserve Bank of Philadelphia, Real-Time Data Set for Macroeconomists",
            "evidence_type": "rtdsm_unemployment_rate_quarterly_vintages"}


def parse_vintages(rows: list[list]) -> dict[str, dict[str, float]]:
    """{'1965Q4': {'1947-01': 3.4, ...}, ...}; '#N/A' cells (not yet published in that vintage) are absent."""
    header = [str(cell) for cell in rows[0]]
    if header[0] != "DATE" or not all(re.fullmatch(r"RUC\d{2}Q[1-4]", h) for h in header[1:]):
        raise ProviderError("RTDSM unemployment workbook layout changed")
    out: dict[str, dict[str, float]] = {}
    for j, code in enumerate(header[1:], start=1):
        year = int(code[3:5])
        vintage = f"{1900 + year if year >= 65 else 2000 + year}Q{code[-1]}"
        column = {}
        for row in rows[1:]:
            label, value = str(row[0]), row[j] if j < len(row) else None
            if not re.fullmatch(r"\d{4}:\d{2}", label) or value in (None, "", "#N/A"):
                continue
            column[label.replace(":", "-")] = float(value)
        out[vintage] = column
    return out


def realtime_sahm(vintages: dict[str, dict[str, float]]) -> list[dict]:
    """The Sahm rule for each vintage's latest month, from that vintage's own data only."""
    points = []
    for vintage in sorted(vintages):
        values = vintages[vintage]
        months = sorted(values)
        if len(months) < 15:
            continue
        average = lambda i: sum(values[months[k]] for k in range(i - 2, i + 1)) / 3
        last = len(months) - 1
        value = average(last) - min(average(i) for i in range(last - 12, last))
        points.append({"vintage": vintage, "month": months[last], "value": round(value, 10)})
    return points


def store(root: Path, raw: bytes) -> Path:
    rows = CalamineWorkbook.from_filelike(io.BytesIO(raw)).get_sheet_by_name("ruc").to_python()
    parse_vintages(rows)
    content = {"source_identity": IDENTITY, "files": {NAME: {"url": URL, "sha256": sha256(raw).hexdigest(), "bytes": len(raw)}}}
    parent = Path(root) / FOLDER
    parent.mkdir(parents=True, exist_ok=True)
    bundle = parent / sha256(canonical_bytes(content)).hexdigest()
    if not bundle.exists():
        staging = Path(tempfile.mkdtemp(prefix=".rtdsm-", dir=parent))
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


def read(root: Path) -> dict:
    """The latest acquired, hash-verified vintage workbook as real-time Sahm points."""
    from .source_reconciliation import _selected_manifest
    parent = Path(root) / FOLDER
    if not parent.exists():
        raise FileNotFoundError("RTDSM unemployment vintages not archived")
    _, manifest_hash, path, manifest, _ = _selected_manifest(parent, IDENTITY)
    raw = (path.parent / NAME).read_bytes()
    if sha256(raw).hexdigest() != manifest["content_identity"]["files"][NAME]["sha256"]:
        raise ProviderError("RTDSM workbook differs from its manifest")
    rows = CalamineWorkbook.from_filelike(io.BytesIO(raw)).get_sheet_by_name("ruc").to_python()
    return {"points": realtime_sahm(parse_vintages(rows)), "source_sha256": sha256(raw).hexdigest(),
            "manifest_sha256": manifest_hash, "retrieved_at_utc": manifest["retrieved_at_utc"], "url": URL}


def acquire(root: Path) -> Path:
    from .source_policy import managed_client
    with managed_client(timeout=120, follow_redirects=True,
                        headers={"User-Agent": "finance-dashboard-research/0.2 (private research)"}) as client:
        response = client.get(URL)
        if response.status_code != 200 or response.content[:2] != b"PK":
            raise ProviderError("RTDSM unemployment workbook request failed")
        return store(root, response.content)


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Archive the Philadelphia Fed unemployment-rate vintages.")
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps({"bundle": str(acquire(args.evidence_dir))}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
