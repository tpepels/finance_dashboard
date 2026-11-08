"""List every conditional analysis and its limitations from a fresh Phase 2 evaluation.

Read-only. Exits 1 if any limitation code has no register text, naming it.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from .acceptance import AcceptanceSnapshot, snapshot_from_report
from .limitations import UnmappedLimitation
from .runner import conditionals


def _evaluate(args) -> AcceptanceSnapshot:
    from ..catalog import load_documents
    from ..research_corpus import load_research_corpus
    from ..research_runtime import evaluate_corpus
    from ..source_reconciliation import _readonly_engine
    catalog, _ = load_documents()
    engine = _readonly_engine(args.database_url)
    try:
        report = evaluate_corpus(engine, catalog["series"], load_research_corpus(),
                                 evidence_root=args.evidence_dir, vintage_root=args.vintage_dir,
                                 holdings_root=args.holdings_dir).public_report
    finally:
        engine.dispose()
    return snapshot_from_report(report, datetime.now(timezone.utc))


def main(argv=None, snapshot_loader=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--evidence-dir", type=Path,
                        default=Path(os.environ.get("FINANCE_SOURCE_EVIDENCE_DIR", "/data/source-evidence")))
    parser.add_argument("--vintage-dir", type=Path, default=Path(os.environ.get("FINANCE_VINTAGE_DIR", "/data/vintages")))
    parser.add_argument("--holdings-dir", type=Path, default=Path(os.environ.get("FINANCE_HOLDINGS_DIR", "/data/holdings")))
    args = parser.parse_args(argv)
    if snapshot_loader is None and not args.database_url:
        parser.error("existing --database-url or DATABASE_URL required")
    snapshot = (snapshot_loader or _evaluate)(args)
    try:
        listing = conditionals(snapshot)
    except UnmappedLimitation as error:
        print(json.dumps({"error": "limitation code without register text", "code": error.args[0]}))
        return 1
    print(json.dumps(listing, indent=1))
    return 0
