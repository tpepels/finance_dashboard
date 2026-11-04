"""Reconcile and archive bounded current-source comparisons for approved analyses.

Default execution reads the database and source archive. --acquire explicitly
refreshes complete publisher histories through append-only ingestion first.
No panel certifies first-publication data or closes the 35-analysis gate.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from finance_dashboard.catalog import load_documents
from finance_dashboard.database import make_engine
from finance_dashboard.providers import ProviderRouter
from finance_dashboard.service import IngestionService, safe_source_failure_code
from finance_dashboard.source_capture import CapturedProvider
from finance_dashboard.source_reconciliation import _readonly_engine
from finance_dashboard.research_corpus import load_research_corpus, validate_research_corpus
from finance_dashboard.research_runtime import evaluate_corpus, required_series_ids
from finance_dashboard.comparative_corpus import store_comparative_corpus, compact_comparative_report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--source-evidence-dir", default=os.environ.get("FINANCE_SOURCE_EVIDENCE_DIR", "/data/source-evidence"))
    parser.add_argument("--holdings-dir", default=os.environ.get("FINANCE_HOLDINGS_DIR"),
                        help="Explicit original holdings archive; omitted means holdings are not checked")
    parser.add_argument("--acquire", action="store_true", help="Append complete source histories and preserve original responses")
    parser.add_argument("--only", nargs="+", help="Approved analysis IDs; defaults to all available comparative variants")
    parser.add_argument("--store", action="store_true", help="Archive verified report and exact input/panel rows")
    parser.add_argument("--required-inputs", action="store_true",
                        help="Include every mapped original input role in acquisition and emit per-analysis acceptance diagnostics")
    args = parser.parse_args(argv)
    engine = None
    try:
        document = load_research_corpus(ROOT)
        registry = load_documents(ROOT)[0]["series"]
        if validate_research_corpus(document, registry):
            raise ValueError("source contracts invalid")
        if args.only:
            selected = set(args.only)
            if selected - {item["id"] for item in document["analyses"]}:
                raise ValueError("unknown analysis")
            document = {**document, "analyses": [item for item in document["analyses"] if item["id"] in selected]}
        ids = sorted({sid for item in document["analyses"]
                      for variant in item["comparison_contract"]["variants"] for sid in variant["series_ids"]})
        if args.required_inputs:
            ids = required_series_ids(document)
        if not args.database_url:
            raise ValueError("database required")
        root = Path(args.source_evidence_dir)
        acquisitions = []
        if args.acquire:
            os.environ["FINANCE_SOURCE_EVIDENCE_DIR"] = str(root)
            engine = make_engine(args.database_url)
            router = ProviderRouter()
            try:
                service = IngestionService(engine, CapturedProvider(router, root))
                for sid in ids:
                    try:
                        acquisitions.append(service.refresh(sid, full=True))
                    except Exception as exc:
                        acquisitions.append({"series_id": sid, "status": "failed", "reason": safe_source_failure_code(exc)})
            finally:
                router.close()
        else:
            engine = _readonly_engine(args.database_url)
        evaluation = evaluate_corpus(engine, registry, document, evidence_root=root,
            holdings_root=Path(args.holdings_dir) if args.holdings_dir is not None else None)
        proof = evaluation.source_proof
        report = evaluation.comparative
        receipt = store_comparative_corpus(report, root) if args.store else None
        # Panel rows and publisher outputs stay in the private evidence archive.
        summary = compact_comparative_report(report)
        summary.update(acquisitions=acquisitions, source_reconciliation={
            key: value for key, value in proof.items() if key != "series"},
            source_failures=[{"series_id": item["series_id"], "failure_code": item.get("failure_code", item["evidence_status"])}
                             for item in proof["series"] if not item["source_values_match"]],
            archived_receipt=receipt["receipt_path"] if receipt else None)
        if args.required_inputs:
            acceptance = evaluation.public_report
            summary["acceptance_summary"] = acceptance["acceptance_summary"]
            summary["role_resolution_summary"] = acceptance["role_resolution_summary"]
            summary["readiness_matrix"] = acceptance["readiness_matrix"]
            summary["analysis_acceptance"] = [{"id": item["id"], "acceptance": item["acceptance"],
                "requirements": item["requirements"]} for item in acceptance["analyses"]]
        print(json.dumps(summary, indent=2))
        return 1 if any(item["status"] == "failed" for item in acquisitions) else 0
    except Exception as exc:
        print(json.dumps({"phase": "phase2", "passed": False, "failure_code": safe_source_failure_code(exc),
                          "whole_analysis_validated": False}))
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
