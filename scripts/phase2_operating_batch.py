#!/usr/bin/env python3
"""Phase 2 operating batch across all 35 original research contracts.

Default is a fresh, fully read-only assessment of the local history database,
exact source originals, native artifact evidence, and STAN country matrix.
--acquire is explicit and requires verified before/after recoverable backups.
A single concise JSON result replaces giant manual diagnostics copies.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from finance_dashboard.catalog import load_documents
from finance_dashboard.database import make_engine
from finance_dashboard.phase2_workflow import (
    run_source_acquisition_batch, source_acquisition_plan,
)
from finance_dashboard.phase2_role_workplan import (
    phase2_role_workplan, compact_role_workplan,
)
from finance_dashboard.phase2_sweep_journal import (
    Phase2SweepJournal, sweep_context,
)
from finance_dashboard.providers import ProviderRouter
from finance_dashboard.research_corpus import (
    analysis_series_ids, load_research_corpus, validate_research_corpus,
)
from finance_dashboard.research_runtime import evaluate_corpus
from finance_dashboard.service import IngestionService, safe_source_failure_code
from finance_dashboard.source_capture import SourceAcquisition, canonical_bytes
from finance_dashboard.source_policy_registry import PolicyRegistry
from finance_dashboard.source_reconciliation import _readonly_engine
from finance_dashboard.stan_research import summarize_stan_readiness
from scripts.phase2_comparative_corpus import (
    checked_acquisition_target, verified_phase2_snapshot,
)
from scripts.phase2_stan_sources import (
    plan_expansion, resolve_stan_country_selection,
    ordered_stan_acquisition_countries,
)
from finance_dashboard.oecd_corporate import OECD_MEMBER_ISO3


def build_phase2_operating_report(evaluation, document, registry, *,
                                  evidence_root: Path, max_attempts: int = 12,
                                  after_id: str | None = None) -> dict:
    """Derive source-action priority and STAN status from verified local inputs."""
    action = source_acquisition_plan(
        document, registry, evaluation.public_report, evaluation.source_proof,
        limit=max_attempts, after_id=after_id)
    all_countries = tuple(sorted(OECD_MEMBER_ISO3))
    role_work = phase2_role_workplan(evaluation.public_report)
    policy_summary = PolicyRegistry().report()
    missing_direct_ack = sorted(
        p["id"] for p in policy_summary["publishers"]
        if p["require_direct_network_ack"] and not p["operator_acknowledged"]
    )
    native = resolve_stan_country_selection(
        evidence_root, anchor_country="PRT", probe_year=2020,
        explicit_measures=None)
    if native["state"].startswith("blocked_"):
        expansion = {
            "state": native["state"], "blocked_invalid_original_countries": [],
            "pending_countries": [], "verified_countries": [],
            "publisher_requests_made": 0,
        }
    else:
        ordered = ordered_stan_acquisition_countries(
            all_countries, selection=native, anchor_country="PRT")
        expansion = plan_expansion(
            evidence_root, countries=ordered, start_year=1970,
            measures=tuple(native["native_measures"]), max_requests=4)
    readiness = summarize_stan_readiness(
        evidence_root, countries=all_countries)
    return {
        "phase": "phase2", "operation": "integrated_operating_review",
        "status": "scientific_evidence_incomplete",
        "analyses": action["analysis_count"],
        "research_decisions": action["analysis_decisions"],
        "gate_failures": action["gate_failure_counts"],
        "role_resolution": evaluation.public_report["role_resolution_summary"],
        "non_scalar_work": compact_role_workplan(role_work),
        "role_workplan_details": role_work,
        "publisher_policy_preflight": {
            "registry_sha256": policy_summary["registry_sha256"],
            "direct_network_acknowledgement_missing": missing_direct_ack,
            "host_policy_is_enforced_at_request_time": True,
        },
        "source_coverage": {
            "referenced": action["sources_referenced"],
            "verified_original_histories":
                action["sources_with_verified_original_history"],
            "dispositions": action["source_dispositions"],
            "acquisition_candidates": action["source_acquisition_candidates"],
            "selected_actions": action["selected_actions"],
            "deferred_action_count": action["deferred_action_count"],
            "blocked_source_actions": action["blocked_source_actions"],
            "next_cursor": action["next_cursor"],
        },
        "stan": {
            "publisher_metadata": readiness["publisher_measure_metadata"],
            "next_evidence_action": expansion.get(
                "next_evidence_action", "resolve_invalid_evidence"),
            "selection_state": native["state"],
            "native_measures": native["native_measures"],
            "source_proofs": native["source_proofs"][:3],
            "readiness_statuses": readiness["status_counts"],
            "verified_original_countries": readiness["verified_scope_countries"],
            "same_scope_identity_countries": readiness["same_scope_identity_countries"],
            "verified_exact_selection_countries": len(
                expansion["verified_countries"]),
            "exact_scopes_with_each_measure_observed": len(expansion.get(
                "verified_country_scopes_with_each_requested_measure_observed", [])),
            "archived_scopes_missing_numeric_measures": expansion.get(
                "verified_country_scopes_missing_requested_numeric_measures", []),
            "pending_exact_selection_countries": len(
                expansion["pending_countries"]),
            "invalid_original_countries": sorted(set(
                readiness["invalid_original_countries"]) |
                set(expansion["blocked_invalid_original_countries"])),
            "next_bounded_batch": expansion.get(
                "suggested_country_batches", [[]])[0] if expansion.get(
                "suggested_country_batches") else [],
            "coverage_gaps_in_verified_selections": expansion.get(
                "verified_scopes_with_missing_measures", [])[:8],
            "publisher_requests_made": 0,
        },
        "scientific_certification": False,
        "first_publication_verified": False,
        "current_source_reconciliation_checked": True,
        "source_originals_modified": False,
        "publisher_requests_made": 0,
        "analysis_gaps": action["analyses"],
    }


def emit_operating_report(report: dict, *, details: bool = False) -> dict:
    """Bounded diagnostic for copy-paste; optional complete per-analysis gates."""
    public = dict(report)
    if not details:
        public.pop("analysis_gaps", None)
        public.pop("role_workplan_details", None)
        if "source_coverage" in public:
            public["source_coverage"] = dict(public["source_coverage"])
            public["source_coverage"]["selected_actions"] = [
                {"id": item["id"], "provider": item["provider"],
                 "affected_analyses": item["affected_analysis_count"]}
                for item in public["source_coverage"]["selected_actions"][:12]]
            public["source_coverage"]["blocked_source_actions"] = public[
                "source_coverage"]["blocked_source_actions"][:12]
            public["source_coverage"]["blocked_actions_omitted"] = max(
                0, len(report["source_coverage"]["blocked_source_actions"]) - 12)
    if "acquisition" in public:
        public["acquisition"] = dict(public["acquisition"])
        if not details:
            public["acquisition"]["results"] = public[
                "acquisition"]["results"][:12]
    return public


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"),
                        help="Existing finance history database; defaults to DATABASE_URL")
    parser.add_argument("--evidence-dir", type=Path,
                        default=Path(os.environ.get(
                            "FINANCE_SOURCE_EVIDENCE_DIR", "/data/source-evidence")))
    parser.add_argument("--vintage-dir", type=Path,
                        default=Path(os.environ["FINANCE_VINTAGE_DIR"])
                        if os.environ.get("FINANCE_VINTAGE_DIR") else None)
    parser.add_argument("--holdings-dir", type=Path,
                        default=Path(os.environ["FINANCE_HOLDINGS_DIR"])
                        if os.environ.get("FINANCE_HOLDINGS_DIR") else None)
    parser.add_argument("--max-attempts", type=int,
                        help="Maximum source tasks; default 12, or up to 400 with --sweep")
    parser.add_argument("--sweep", action="store_true",
                        help="Plan the full candidate backlog; with --acquire, use a resumable multi-publisher journal")
    parser.add_argument("--run-dir", type=Path,
                        help="Unique out-of-archive acquisition sweep directory; required for --acquire --sweep")
    parser.add_argument("--resume", action="store_true",
                        help="Resume and verify a previous --sweep --run-dir without repeating attempted tasks")
    parser.add_argument("--after-source", help="Resume after this exact canonical source ID")
    parser.add_argument("--acquire", action="store_true",
                        help="Explicit original-source ingestion with verified before/after backups")
    parser.add_argument("--backup-dir", type=Path,
                        help="Existing, separate backup parent; required with --acquire")
    parser.add_argument("--output", type=Path,
                        help="Create one new compact JSON report outside source evidence")
    parser.add_argument("--details", action="store_true",
                        help="Include all 35 per-analysis gate summaries")
    args = parser.parse_args(argv)
    if not args.database_url:
        parser.error("existing --database-url or DATABASE_URL required")
    if args.max_attempts is None:
        args.max_attempts = 200 if args.sweep else 12
    if not 1 <= args.max_attempts <= (400 if args.sweep else 120):
        parser.error("--max-attempts must be 1–120, or 1–400 with --sweep")
    if args.resume and not (args.sweep and args.acquire and args.run_dir):
        parser.error("--resume requires --sweep --acquire --run-dir")
    if args.run_dir and not (args.sweep and args.acquire):
        parser.error("--run-dir requires --sweep --acquire")
    if args.sweep and args.acquire and args.run_dir is None:
        parser.error("--sweep --acquire requires --run-dir")
    if args.sweep and args.after_source:
        parser.error("--after-source is incompatible with journal-based --sweep")
    if args.acquire and args.backup_dir is None:
        parser.error("--acquire requires --backup-dir for verified recoverability")
    if args.backup_dir is not None and not args.acquire:
        parser.error("--backup-dir requires --acquire")
    if args.run_dir is not None:
        target = args.run_dir.absolute()
        for protected in (args.evidence_dir, args.backup_dir):
            if protected is None:
                continue
            protected = protected.absolute()
            if (target == protected or protected in target.parents
                    or target in protected.parents):
                parser.error("--run-dir must be distinct from source originals and backups")
    if args.output is not None:
        if args.output.exists():
            parser.error("--output must not overwrite existing report")
        if args.evidence_dir.resolve() in args.output.resolve().parents:
            parser.error("--output must be outside the original source evidence")

    read_engine = None
    write_engine = None
    try:
        document = load_research_corpus(ROOT)
        registry = load_documents(ROOT)[0]["series"]
        if validate_research_corpus(document, registry):
            raise ValueError("canonical_research_contract_invalid")
        read_engine = _readonly_engine(args.database_url)
        baseline = evaluate_corpus(
            read_engine, registry, document, evidence_root=args.evidence_dir,
            vintage_root=args.vintage_dir, holdings_root=args.holdings_dir)
        report = build_phase2_operating_report(
            baseline, document, registry,
            evidence_root=args.evidence_dir,
            max_attempts=400 if args.sweep else args.max_attempts,
            after_id=args.after_source)
        if args.acquire:
            checked_acquisition_target(args.database_url, args.evidence_dir)
            journal_session = nullcontext(None)
            if args.sweep:
                all_source_ids = sorted({
                    sid for analysis in document["analyses"]
                    for sid in analysis_series_ids(analysis)
                })
                context = sweep_context(
                    all_source_ids, PolicyRegistry().sha256,
                    sha256(canonical_bytes(document)).hexdigest())
                journal_session = Phase2SweepJournal(
                    args.run_dir, context=context, create=not args.resume)

            # Serialize one sweep writer for its entire backup-and-acquisition
            # lifecycle. The before/after snapshots remain independently
            # verified and never overwrite original publisher evidence.
            with journal_session as journal:
                checkpoint = args.backup_dir / (
                    "phase2-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
                before = verified_phase2_snapshot(
                    args.database_url, args.evidence_dir, checkpoint, label="before")
                router = ProviderRouter()
                try:
                    write_engine = make_engine(args.database_url)
                    service = IngestionService(
                        write_engine, SourceAcquisition(router, args.evidence_dir))

                    def progress(index, total, row):
                        print(f"PHASE2 {index}/{total}: {row['series_id']} "
                              f"{row['status']} {row.get('reason', '')}",
                              file=sys.stderr, flush=True)

                    batch = run_source_acquisition_batch(
                        report["source_coverage"]["selected_actions"],
                        service.refresh, max_attempts=args.max_attempts,
                        stop_scope="publisher" if args.sweep else "global",
                        journal=journal, progress=progress)
                finally:
                    router.close()
                    if write_engine is not None:
                        write_engine.dispose()
                        write_engine = None
                after = verified_phase2_snapshot(
                    args.database_url, args.evidence_dir, checkpoint, label="after")
                journal_summary = journal.summary() if journal is not None else None
            refreshed = evaluate_corpus(
                read_engine, registry, document, evidence_root=args.evidence_dir,
                vintage_root=args.vintage_dir, holdings_root=args.holdings_dir)
            report = build_phase2_operating_report(
                refreshed, document, registry,
                evidence_root=args.evidence_dir,
                max_attempts=12)
            # Always show the next default pending actions, including previously
            # failed source histories, separately from this sweep's immutable
            # journal. Success is established only through original proofs.
            archive_changed = (
                before["evidence_archive_sha256"] != after["evidence_archive_sha256"])
            report["source_originals_modified"] = archive_changed
            report["publisher_requests_made"] = None
            report["acquisition"] = batch
            if journal_summary is not None:
                report["sweep_journal"] = journal_summary
                report["next_run_requires_explicit_resume_or_new_journal"] = True
            report["verified_recovery"] = {
                "before_sha256": before["database_sha256"],
                "after_sha256": after["database_sha256"],
                "before_original_archive_sha256": before["evidence_archive_sha256"],
                "after_original_archive_sha256": after["evidence_archive_sha256"],
                "original_archive_changed": archive_changed,
                "backups_verified": True,
            }
        final = emit_operating_report(report, details=args.details)
        if args.output is not None:
            with args.output.open("x", encoding="utf-8") as handle:
                json.dump(final, handle, separators=(",", ":"), allow_nan=False)
                handle.write("\n")
        print(json.dumps(final, separators=(",", ":"), allow_nan=False))
        return 1 if (report["stan"]["invalid_original_countries"]
                     or report.get("acquisition", {}).get("failed", 0)
                     or report.get("acquisition", {}).get("stop_category")) else 0
    except Exception as exc:
        print(json.dumps({
            "phase": "phase2", "operation": "integrated_operating_review",
            "status": "failed",
            "failure_code": safe_source_failure_code(exc),
            "scientific_certification": False,
        }, separators=(",", ":")))
        return 1
    finally:
        if read_engine is not None:
            read_engine.dispose()
        if write_engine is not None:
            write_engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
