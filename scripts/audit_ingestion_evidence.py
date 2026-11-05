#!/usr/bin/env python3
"""Read-only integrity audit of every linked macro-ingestion original receipt."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from finance_dashboard.database import IngestionRun, make_engine
from finance_dashboard.source_evidence_audit import (
    SourceEvidenceIntegrityError, verify_ingestion_receipt,
)


def audit(root: Path, *, database_url: str | None = None,
          max_failures: int = 8) -> dict:
    engine = make_engine(database_url)
    counts: Counter[str] = Counter()
    failures = []
    try:
        with Session(engine) as session:
            counts["historical_successes_without_evidence"] = session.scalar(
                select(func.count()).select_from(IngestionRun).where(
                    IngestionRun.status == "success",
                    IngestionRun.evidence_kind.is_(None))) or 0
            counts["native_or_local_unlinked"] = session.scalar(
                select(func.count()).select_from(IngestionRun).where(
                    IngestionRun.status == "success",
                    IngestionRun.evidence_kind.is_not(None),
                    IngestionRun.evidence_kind != "response")) or 0
            records = session.execute(select(
                IngestionRun.id, IngestionRun.series_id, IngestionRun.evidence_scope,
                IngestionRun.evidence_bundle_digest, IngestionRun.evidence_receipt_name,
            ).where(IngestionRun.status == "success",
                    IngestionRun.evidence_kind == "response"))
            for run_id, sid, scope, digest, receipt in records:
                counts["linked_original_responses"] += 1
                try:
                    verify_ingestion_receipt(
                        root, series_id=sid, scope=scope,
                        bundle_digest=digest, receipt_name=receipt)
                    counts["verified_original_responses"] += 1
                except (SourceEvidenceIntegrityError, OSError, ValueError,
                        KeyError, TypeError):
                    counts["invalid_original_references"] += 1
                    if len(failures) < max_failures:
                        failures.append({"run_id": run_id, "series_id": sid,
                                         "failure": "source_integrity_invalid"})
    finally:
        engine.dispose()
    return {
        "operation": "audit_ingestion_original_evidence",
        **counts,
        "failed_reference_examples": failures,
        "scientific_analysis_certified": False,
        "publisher_requests": 0,
        "archive_writes": 0,
        "macro_database_writes": 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path,
                        default=Path("/data/source-evidence"))
    parser.add_argument("--brief", action="store_true")
    args = parser.parse_args(argv)
    report = audit(args.evidence_dir)
    print(json.dumps(report, separators=(",", ":") if args.brief else None,
                     indent=None if args.brief else 2))
    return 1 if report.get("invalid_original_references") else 0


if __name__ == "__main__":
    raise SystemExit(main())
