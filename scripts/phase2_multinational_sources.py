"""Acquire or import original AMNE/MEIP bundles into canonical source evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx

from finance_dashboard.multinational_sources import (
    SOURCE_FILES, collect_multinational_source, read_multinational_evidence,
    store_multinational_source,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-evidence-dir", required=True, type=Path)
    parser.add_argument("--only", nargs="+", choices=sorted(SOURCE_FILES), default=sorted(SOURCE_FILES))
    parser.add_argument("--import-directory", type=Path,
                        help="Import retained publisher originals instead of downloading again")
    parser.add_argument("--output", type=Path, help="Create a new JSON audit file; existing files are preserved")
    args = parser.parse_args(argv)
    reports = {}
    with httpx.Client(timeout=120, headers={"User-Agent": "GlobalCapitalMonitor/0.2 original-source-research"}) as client:
        for kind in dict.fromkeys(args.only):
            if args.import_directory is None:
                collect_multinational_source(kind, root=args.source_evidence_dir, client=client)
            else:
                payloads = {name: (args.import_directory / name).read_bytes() for name in SOURCE_FILES[kind]}
                # An import without publisher HTTP receipts remains explicitly
                # marked imported_original_bytes by the canonical store.
                store_multinational_source(kind, payloads, root=args.source_evidence_dir)
            reports[kind] = read_multinational_evidence(args.source_evidence_dir, kind)
    report = {"schema_version": 1, "database_writes": 0, "artifacts": reports}
    if args.output is not None:
        with args.output.open("x") as handle:
            json.dump(report, handle, indent=2); handle.write("\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
