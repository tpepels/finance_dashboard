"""Reconcile and archive bounded current-source comparisons for approved analyses.

Default execution reads the database and source archive. --acquire explicitly
refreshes complete publisher histories through append-only ingestion first.
No panel certifies first-publication data or closes the 35-analysis gate.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys

from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from finance_dashboard.catalog import load_documents
from finance_dashboard.database import make_engine
from finance_dashboard.providers import ProviderRouter
from finance_dashboard.service import IngestionService, safe_source_failure_code
from finance_dashboard.source_capture import CapturedProvider
from finance_dashboard.source_reconciliation import _readonly_engine, reconcile
from finance_dashboard.research_corpus import load_research_corpus, validate_research_corpus
from finance_dashboard.comparative_corpus import store_comparative_corpus, compact_comparative_report


# Publisher families introduced by the native-source Phase 2 increment. Selection
# derives from canonical source definitions rather than a second ID inventory.
NATIVE_SOURCE_FAMILIES = frozenset({
    "BIS_TOTAL_CREDIT", "BOJ_TSS", "FED_G17_DIFFUSION", "OECD_CLI",
    "OFR_FSI", "IMF_BOP_IIP", "FDIC_BANKFIND",
})


def select_source_ids(registry, *, ids=None, new_sources=False):
    """Resolve an explicit, source-only original capture/reconciliation scope."""
    mapped = {row["id"]: row for row in registry if row["status"] == "mapped"}
    if new_sources:
        selected = sorted(sid for sid, row in mapped.items()
                          if row["provider"] in NATIVE_SOURCE_FAMILIES)
    else:
        selected = sorted(set(ids or ()))
        if len(selected) != len(ids or ()) or any(sid not in mapped for sid in selected):
            raise ValueError("unknown_duplicate_or_unmapped_source_id")
    if not selected:
        raise ValueError("empty_source_selection")
    return selected


def checked_acquisition_target(database_url: str, evidence_root: Path) -> None:
    """Fail before any writes for absent/mistyped database or evidence paths."""
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite":
        database = url.database
        if not database or database == ":memory:" or not Path(database).is_file():
            raise ValueError("existing_persistent_database_required")
    if url.get_backend_name() == "sqlite":
        with Path(url.database).open("rb") as stream:
            if stream.read(16) != b"SQLite format 3\x00":
                raise ValueError("valid_existing_sqlite_database_required")
    if url.get_backend_name() == "sqlite":
        # A valid SQLite header alone does not identify the finance research DB.
        # Fail before creating ingestion rows in an unrelated SQLite database.
        from urllib.parse import quote
        uri = "file:" + quote(str(Path(url.database).resolve()), safe="/") + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=30) as connection:
            actual = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
        if not {"series", "ingestion_runs", "observation_versions"}.issubset(actual):
            raise ValueError("finance_history_schema_required")
    if not evidence_root.is_dir() or evidence_root.is_symlink():
        raise ValueError("existing_source_evidence_directory_required")


def targeted_source_summary(ids, acquisitions, proof):
    """Compact original-versus-stored evidence; no scientific acceptance claim."""
    results = {row["series_id"]: row for row in acquisitions}
    verified = {row["series_id"]: row for row in proof["series"]}
    return {
        "phase": "phase2", "operation": "selected_original_source_reconciliation",
        "scientific_analysis_certified": False,
        "selection_count": len(ids),
        "acquired": sum(row.get("status") == "success" for row in acquisitions),
        "acquisition_failed": sum(row.get("status") == "failed" for row in acquisitions),
        "original_values_matching": proof["matched_series"],
        "full_original_histories_reconciled": proof["fully_reconciled_series"],
        "read_only_reconciliation": True,
        "sources": [
            {
                "id": sid,
                "acquisition": results[sid].get("status") if sid in results else "not_requested",
                "versions_added": results.get(sid, {}).get("versions_added"),
                "acquisition_failure": results.get(sid, {}).get("reason"),
                "source_values_match": verified[sid]["source_values_match"],
                "full_history_reconciled": verified[sid]["source_covers_all_stored_periods"],
                "source_periods": verified[sid]["source_periods"],
                "failure_code": verified[sid].get("failure_code"),
                "original_response_sha256": verified[sid].get("source_sha256"),
                "original_manifest_sha256": verified[sid].get("source_manifest_sha256"),
            }
            for sid in ids
        ],
        "passed": proof["passed"] and proof["all_stored_histories_reconciled"] and not any(row.get("status") == "failed" for row in acquisitions),
        "note": "Current original snapshots only: this does not verify observation first-publication vintages or certify any of the 35 analyses.",
    }



def verified_phase2_snapshot(database_url, evidence_root, backup_dir, *, label):
    """Reuse existing online SQLite backup, including originals, with no pruning.

    A dedicated per-run directory prevents the application's routine backup
    retention from pruning this research checkpoint.
    """
    from finance_dashboard.backup import backup_local, verify_manifest
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        raise ValueError("sqlite_research_backup_required")
    database = Path(url.database).resolve()
    root = database.parent
    output = backup_dir / label
    if backup_dir.is_symlink() or output.exists():
        raise ValueError("unique_backup_directory_required")
    evidence = {
        "source-evidence": evidence_root,
        "vintages": root / "vintages",
        "holdings": root / "holdings",
        "surplus": root / "surplus",
    }
    # Do not archive the backup directory into itself, directly or indirectly.
    location = backup_dir.resolve()
    for source in evidence.values():
        original = source.resolve()
        if location == original or location in original.parents or original in location.parents:
            raise ValueError("backup_location_overlaps_source_archive")
    result = backup_local(output, source_db=database, keep=365, evidence_roots=evidence)
    basename = result["database"]["file"].removesuffix(".sqlite3")
    receipt = output / (basename + ".json")
    verify_manifest(receipt)
    return {
        "manifest": str(receipt),
        "database_sha256": result["database"]["sha256"],
        "evidence_archive_sha256": (
            result["evidence_archive"]["sha256"] if result["evidence_archive"] else None
        ),
    }


def scientific_gap_summary(report, *, source_proof):
    """Describe every remaining failed scientific gate from current runtime evidence."""
    by_analysis = {row["id"]: row for row in report["analyses"]}
    gate_failures = {}
    for analysis in report["analyses"]:
        for role in analysis["requirements"]:
            for check in role["checks"]:
                if check["state"] != "passed":
                    gate_failures[check["id"]] = gate_failures.get(check["id"], 0) + 1
    return {
        "empirical_readiness_evaluated": True,
        "fully_accepted_analyses": report["acceptance_summary"]["fully_accepted_analyses"],
        "failed_or_unverified_gate_counts": dict(sorted(gate_failures.items())),
        "acceptance_summary": report["acceptance_summary"],
        "role_resolution_summary": report["role_resolution_summary"],
        "required_input_source_reconciliation": {
            "checked": source_proof["series_count"],
            "original_values_matching": source_proof["matched_series"],
            "full_original_histories_reconciled": source_proof["fully_reconciled_series"],
            "unverified_source_ids": [
                {"id": row["series_id"], "failure_code": row.get("failure_code")}
                for row in source_proof["series"]
                if not row["source_covers_all_stored_periods"]
            ],
        },
        "analysis_gaps": [
            {
                "id": row["id"],
                "decision": row["decision"],
                "original_decision": row["original"]["decision"],
                "fallback_decision": row["fallback"]["decision"],
                "unverified_roles": row["original"]["missing_or_partial_roles"],
                "blocking_reasons": [item["code"] for item in row["reasons"]],
                "unverified_role_gates": [
                    {
                        "role": role["role"],
                        "input_type": role["input_type"],
                        "failed_or_unverified_checks": [
                            {"id": check["id"], "state": check["state"],
                             "reason": check["code"]}
                            for check in role["checks"] if check["state"] != "passed"
                        ],
                    }
                    for role in by_analysis[row["id"]]["requirements"]
                    if any(check["state"] != "passed" for check in role["checks"])
                ],
            }
            for row in report["readiness_matrix"] if row["decision"] != "complete"
        ],
        "temporal_limitation": (
            "Current original publisher snapshots do not establish each "
            "observation's first publication or historical as-of eligibility."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", help="Explicit database URL; required for acquisition")
    parser.add_argument("--source-evidence-dir", help="Explicit existing source archive; required for acquisition and --store")
    parser.add_argument("--holdings-dir", default=os.environ.get("FINANCE_HOLDINGS_DIR"),
                        help="Explicit original holdings archive; omitted means holdings are not checked")
    parser.add_argument("--acquire", action="store_true", help="Append complete source histories and preserve original responses")
    parser.add_argument("--backup-dir", help="Explicit directory for verified before/after research backups")
    parser.add_argument("--assess-all", action="store_true",
                        help="Evaluate all 35 analyses using current stored data and original evidence")
    parser.add_argument("--only", nargs="+", help="Approved analysis IDs; defaults to all available comparative variants")
    parser.add_argument("--store", action="store_true", help="Archive verified report and exact input/panel rows")
    parser.add_argument("--required-inputs", action="store_true",
                        help="Include every mapped original input role in acquisition and emit per-analysis acceptance diagnostics")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--source-ids", nargs="+",
                           help="Reconcile only these exact canonical scalar source IDs")
    selection.add_argument("--new-sources", action="store_true",
                           help="Reconcile all mapped sources from the seven newly integrated publisher families")
    args = parser.parse_args(argv)
    if args.acquire and (not args.database_url or not args.source_evidence_dir or not args.backup_dir):
        parser.error("--acquire requires explicit --database-url, --source-evidence-dir and --backup-dir")
    if args.store and not args.source_evidence_dir:
        parser.error("--store requires explicit --source-evidence-dir")
    source_only = bool(args.source_ids or args.new_sources)
    if source_only and (args.only or args.required_inputs or (args.store and not args.assess_all)):
        parser.error("--source-ids/--new-sources cannot mix with analysis filters; --store requires --assess-all")
    if args.assess_all and not source_only:
        parser.error("--assess-all is only needed with --source-ids or --new-sources")
    if args.backup_dir and not args.acquire:
        parser.error("--backup-dir is only valid for explicit acquisition")
    database_url = args.database_url or os.environ.get("DATABASE_URL")
    evidence_dir = args.source_evidence_dir or os.environ.get("FINANCE_SOURCE_EVIDENCE_DIR", "/data/source-evidence")
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
        if source_only:
            ids = select_source_ids(registry, ids=args.source_ids, new_sources=args.new_sources)
        else:
            # Only the full 35-analysis evaluation requires original workbook
            # readers. Targeted native-source operations must not import them.
            from finance_dashboard.research_runtime import evaluate_corpus, required_series_ids
            ids = sorted({sid for item in document["analyses"]
                          for variant in item["comparison_contract"]["variants"] for sid in variant["series_ids"]})
            if args.required_inputs:
                ids = required_series_ids(document)
        if not database_url:
            raise ValueError("database required")
        root = Path(evidence_dir)
        acquisitions = []
        backups = {}
        if args.acquire:
            checked_acquisition_target(database_url, root)
            os.environ["FINANCE_SOURCE_EVIDENCE_DIR"] = str(root)
            # Verify a complete original state before any append-only ingestion.
            # A distinct directory retains this research checkpoint indefinitely.
            backup_root = Path(args.backup_dir) / (
                "native-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            )
            backups["before"] = verified_phase2_snapshot(
                database_url, root, backup_root, label="before"
            )
            engine = make_engine(database_url)
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
            # Preserve the acquired originals and append-only observations
            # before any optional expensive research evaluation.
            backups["after"] = verified_phase2_snapshot(
                database_url, root, backup_root, label="after"
            )
        else:
            engine = _readonly_engine(database_url)
        if source_only:
            # Independent selectors check raw publisher response bytes against
            # database observation versions; no alternate reconciliation logic.
            report = targeted_source_summary(ids, acquisitions, reconcile(database_url, root, ids))
            if backups:
                report["verified_research_backups"] = backups
            if args.assess_all:
                from finance_dashboard.research_runtime import evaluate_corpus
                evaluation = evaluate_corpus(engine, registry,
                    load_research_corpus(ROOT), evidence_root=root,
                    holdings_root=Path(args.holdings_dir) if args.holdings_dir else None)
                report["scientific_gaps"] = scientific_gap_summary(
                    evaluation.public_report, source_proof=evaluation.source_proof
                )
                if args.store:
                    report["archived_comparative_receipt"] = store_comparative_corpus(
                        evaluation.comparative, root
                    )["receipt_path"]
            print(json.dumps(report, indent=2))
            return 0 if report["passed"] else 1
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
