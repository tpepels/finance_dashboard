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
    source_evidence_delta,
)
from finance_dashboard.phase2_role_workplan import (
    phase2_role_workplan, compact_role_workplan,
)
from finance_dashboard.phase2_structured_acquisition import (
    original_artifact_matrix, collection_plan,
)
from finance_dashboard.phase2_unbound_sources import (
    unbound_original_source_discovery, concise_unbound_discovery,
)
from finance_dashboard.phase2_accounting_validation import (
    native_accounting_workplan, compact_accounting_workplan,
)
from finance_dashboard.phase2_research_transitions import (
    research_evidence_transitions, compact_research_transitions,
)
from finance_dashboard.phase2_sweep_journal import (
    Phase2SweepJournal, sweep_context,
)
from finance_dashboard.phase2_sweep_revisit import (
    plan_sweep_revisit, REVISIT_MODES,
)
from finance_dashboard.providers import ProviderRouter
from finance_dashboard.research_corpus import (
    analysis_series_ids, load_research_corpus, validate_research_corpus,
)
from finance_dashboard.research_runtime import evaluate_corpus
from finance_dashboard.service import IngestionService, safe_source_failure_code
from finance_dashboard.source_capture import SourceAcquisition, canonical_bytes
from finance_dashboard.source_policy_registry import PolicyRegistry
from finance_dashboard.source_policy_ledger import SourcePolicyGate
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
    structured = original_artifact_matrix(
        document, evaluation.artifact_evidence or {})
    original_uses = collection_plan(
        structured, registry=PolicyRegistry())
    unbound = unbound_original_source_discovery(
        document, registry, evaluation.artifact_evidence or {})
    native_checks = native_accounting_workplan(
        document, evaluation.public_report,
        evaluation.artifact_evidence or {}, readiness)
    return {
        "phase": "phase2", "operation": "integrated_operating_review",
        "status": "scientific_evidence_incomplete",
        "analyses": action["analysis_count"],
        "research_decisions": action["analysis_decisions"],
        "gate_failures": action["gate_failure_counts"],
        "role_resolution": evaluation.public_report["role_resolution_summary"],
        "non_scalar_work": compact_role_workplan(role_work),
        "structured_original_work": {
            "structured_roles": structured["structured_roles"],
            "native_unassigned_role_imports": {
                "roles_available_for_explicit_original_import": (
                    (evaluation.native_role_proof or {}).get(
                        "unbound_structured_roles", 0)),
                "hash_verified_partial_role_imports": (
                    (evaluation.native_role_proof or {}).get(
                        "hash_verified_partial_roles", 0)),
                "invalid_existing_native_originals": (
                    (evaluation.native_role_proof or {}).get(
                        "invalid_archived_roles", [])),
                "imported_data_is_not_original_method_certified": True,
            },
            "roles_without_native_original_artifact":
                structured["roles_without_registered_artifacts"],
            "native_artifacts_with_collectors":
                structured["native_collectors_available"],
            "artifact_states": [{
                "id": item["kind"],
                "roles": item["role_count"],
                "collection_state": item["collection_state"],
                "policies": item["policy_ids"],
            } for item in original_uses["artifacts"]],
            "publisher_requests_made": 0,
            "scientific_certification": False,
        },
        "unbound_original_inputs": concise_unbound_discovery(unbound),
        "native_accounting": compact_accounting_workplan(native_checks),
        "scientific_input_bundle": {
            "analysis_count": native_checks["analyses_checked"],
            "original_roles_checked": native_checks["original_roles_checked"],
            "source_method_and_release_checks_required": True,
            "scientific_analysis_certified": False,
        },
        "unbound_original_details": unbound,
        "native_accounting_details": native_checks,
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
        public.pop("unbound_original_details", None)
        public.pop("native_accounting_details", None)
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
            public["acquisition"]["results_omitted"] = max(
                0, len(report["acquisition"]["results"]) - 12)
    if "research_transitions" in public and not details:
        public["research_transitions"] = compact_research_transitions(
            public["research_transitions"])
    if "source_evidence_delta" in public and not details:
        public["source_evidence_delta"] = dict(public["source_evidence_delta"])
        delta = public["source_evidence_delta"]
        delta["newly_verified_omitted"] = max(0, len(delta["newly_verified"]) - 15)
        delta["newly_verified"] = delta["newly_verified"][:15]
        delta["no_longer_verified_omitted"] = max(
            0, len(delta["no_longer_verified"]) - 15)
        delta["no_longer_verified"] = delta["no_longer_verified"][:15]
        delta["no_longer_verified_diagnoses_omitted"] = max(
            0, len(delta["no_longer_verified_diagnoses"]) - 15)
        delta["no_longer_verified_diagnoses"] = delta[
            "no_longer_verified_diagnoses"][:15]
        delta["unverified_successes_omitted"] = max(
            0, len(delta["successful_but_not_verified"]) - 15)
        delta["successful_but_not_verified"] = delta[
            "successful_but_not_verified"][:15]
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
    parser.add_argument("--max-policy-wait-seconds", type=int, default=0,
                        help="Optional bounded read-only budget preflight waiting in --sweep mode (0–14400 seconds)")
    parser.add_argument("--resume", action="store_true",
                        help="Resume and verify a previous --sweep --run-dir without repeating attempted tasks")
    parser.add_argument("--revisit-from", type=Path,
                        help="Explicitly select previous failed/unverified sources from an independently verified older sweep")
    parser.add_argument("--revisit-mode", choices=sorted(REVISIT_MODES),
                        default="failed",
                        help="Select completed failures, still-unverified successes, or both (default: failed)")
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
    if args.revisit_from and not args.sweep:
        parser.error("--revisit-from requires --sweep")
    if args.revisit_mode != "failed" and not args.revisit_from:
        parser.error("--revisit-mode requires --revisit-from")
    if args.revisit_from and args.resume:
        parser.error("--revisit-from requires a new --run-dir, not --resume")
    if not 0 <= args.max_policy_wait_seconds <= 14_400:
        parser.error("--max-policy-wait-seconds must be 0–14400")
    if args.max_policy_wait_seconds and not (args.sweep and args.acquire):
        parser.error("--max-policy-wait-seconds requires --sweep --acquire")
    if args.acquire and args.backup_dir is None:
        parser.error("--acquire requires --backup-dir for verified recoverability")
    if args.backup_dir is not None and not args.acquire:
        parser.error("--backup-dir requires --acquire")
    if args.run_dir is not None:
        target = args.run_dir.absolute()
        if args.revisit_from is not None:
            prior = args.revisit_from.absolute()
            if target == prior or target in prior.parents or prior in target.parents:
                parser.error("--run-dir must be separate from the older journal")
        for protected in (args.evidence_dir, args.backup_dir):
            if protected is None:
                continue
            protected = protected.absolute()
            if (target == protected or protected in target.parents
                    or target in protected.parents):
                parser.error("--run-dir must be distinct from source originals and backups")
    if args.revisit_from is not None:
        prior = args.revisit_from.absolute()
        for protected in (args.evidence_dir, args.backup_dir):
            if protected is None:
                continue
            protected = protected.absolute()
            if (prior == protected or prior in protected.parents
                    or protected in prior.parents):
                parser.error("--revisit-from must be a separate old journal, outside original archives and backups")
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
        context = None
        revisit = None
        if args.sweep:
            all_source_ids = sorted({
                sid for analysis in document["analyses"]
                for sid in analysis_series_ids(analysis)
            })
            context = sweep_context(
                all_source_ids, PolicyRegistry().sha256,
                sha256(canonical_bytes(document)).hexdigest())
            if args.revisit_from is not None:
                revisit = plan_sweep_revisit(
                    args.revisit_from, context=context,
                    acquisition_candidates=report["source_coverage"][
                        "selected_actions"],
                    mode=args.revisit_mode, max_tasks=400)
                report["source_coverage"]["selected_actions"] = revisit[
                    "selected_actions"]
                report["source_coverage"]["selection_mode"] = "explicit_revisit"
                report["source_coverage"]["selected_revisit_sources"] = revisit[
                    "selected_count"]
                report["revisit_plan"] = {
                    key: value for key, value in revisit.items()
                    if key != "selected_actions"}
        if args.acquire:
            checked_acquisition_target(args.database_url, args.evidence_dir)
            journal_session = nullcontext(None)
            if args.sweep:
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

                    # Operational preflight never reserves a permit or
                    # certifies a descriptive catalogue URL as the real API.
                    # The managed HTTP client enforces exact live requests.
                    budget_gate = SourcePolicyGate(registry=PolicyRegistry())
                    def preflight(action):
                        policy = action.get("publisher_policy")
                        if not policy:
                            return {"state": "ready", "reason": None,
                                    "retry_at": None}
                        return budget_gate.availability(policy)

                    batch = run_source_acquisition_batch(
                        report["source_coverage"]["selected_actions"],
                        service.refresh, max_attempts=args.max_attempts,
                        stop_scope="publisher" if args.sweep else "global",
                        journal=journal, progress=progress,
                        policy_preflight=preflight if args.sweep else None,
                        max_wait_seconds=args.max_policy_wait_seconds)
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
            if revisit is not None:
                report["revisit_plan"] = {
                    key: value for key, value in revisit.items()
                    if key != "selected_actions"}
            report["source_evidence_delta"] = source_evidence_delta(
                baseline.source_proof, refreshed.source_proof, batch)
            report["research_transitions"] = research_evidence_transitions(
                baseline.public_report, refreshed.public_report)
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
