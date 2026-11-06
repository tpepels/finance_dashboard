#!/usr/bin/env python3
"""Phase 2 full-structured-workstream planning and bounded native collection.

Read-only by default. Live collection is explicit, journaled, governed by the
canonical publisher transport with a global HTTP cap, and independently
rechecked by existing native source readers. Unsupported originals are
reported as manual-source blockers instead of downloaded from guessed URLs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]

from finance_dashboard.phase2_structured_acquisition import (
    CAPABILITIES, collection_plan, collect_structured_original,
    original_artifact_matrix,
)
from finance_dashboard.phase2_sweep_journal import (
    Phase2SweepJournal, sweep_context,
)
from finance_dashboard.phase2_workflow import run_source_acquisition_batch
from finance_dashboard.research_artifacts import research_artifact_evidence
from finance_dashboard.research_corpus import (
    load_research_corpus, validate_research_corpus,
)
from finance_dashboard.catalog import load_documents
from finance_dashboard.source_capture import canonical_bytes
from finance_dashboard.source_policy import managed_client
from finance_dashboard.source_policy_ledger import SourcePolicyGate
from finance_dashboard.source_policy_registry import PolicyRegistry
from finance_dashboard.service import safe_source_failure_code


def structured_operating_plan(document: dict, root: Path, *, holdings: Path | None,
                              kinds: set[str] | None, cvm_year: int | None,
                              agent: str | None, policy: PolicyRegistry,
                              msci_factsheet_url: str | None = None) -> dict:
    originals = research_artifact_evidence(root, holdings_root=holdings,
                                           kinds=kinds)
    matrix = original_artifact_matrix(document, originals, included=kinds)
    plan = collection_plan(
        matrix, registry=policy, cvm_year=cvm_year,
        holdings_dir=holdings, sec_user_agent=agent,
        msci_factsheet_url=msci_factsheet_url)
    by_kind = {row["artifact_id"]: row for row in matrix["artifact_workstreams"]}
    actions = []
    for item in plan["artifacts"]:
        subsources = item.get("subsource_collectors", [])
        if subsources:
            for source in subsources:
                if source["collection_state"] != "original_collection_candidate":
                    continue
                actions.append({
                    "id": item["kind"] + ":" + source["subsource"],
                    "provider": "structured:" + item["kind"],
                    "publisher_policy": source["policy_ids"][0],
                    "publisher_policies": source["policy_ids"],
                    "affected_analyses": item["affected_analyses"],
                    "state": "acquisition_candidate",
                })
            continue
        if item["collection_state"] != "original_collection_candidate":
            continue
        actions.append({
            "id": item["kind"],
            "provider": "structured:" + item["kind"],
            "publisher_policy": item["policy_ids"][0] if item["policy_ids"] else None,
            "publisher_policies": item["policy_ids"],
            "affected_analyses": item["affected_analyses"],
            "state": "acquisition_candidate",
        })
    return {
        "phase": "phase2",
        "operation": "structured_originals_operating_plan",
        "structured_roles": matrix["structured_roles"],
        "roles_with_registered_artifacts": matrix[
            "roles_with_registered_artifacts"],
        "roles_without_registered_artifacts": matrix[
            "roles_without_registered_artifacts"],
        "roles_without_original_adapter": matrix["unassigned_original_roles"],
        "artifact_workstreams": [{
            "artifact_id": row["artifact_id"],
            "collection": row["collection"],
            "role_count": row["role_count"],
            "affected_analyses": row["affected_analyses"],
            "original_proof_state": row["original_proof_state"],
            "full_history_verified": row["full_history_verified"],
            "first_publication_verified": row["first_publication_verified"],
            "collection_state": next(
                (item["collection_state"] for item in plan["artifacts"]
                 if item["kind"] == row["artifact_id"]), "not_required_by_corpus"),
            "subsource_collectors": next(
                (item["subsource_collectors"] for item in plan["artifacts"]
                 if item["kind"] == row["artifact_id"]), []),
        } for row in matrix["artifact_workstreams"]],
        "eligible_original_collectors": len(actions),
        "selected_actions": actions,
        "provenance_is_read_only": True,
        "first_publication_not_inferred": True,
        "scientific_analysis_certified": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--holdings-dir", type=Path)
    parser.add_argument("--artifact", action="append",
                        choices=sorted(CAPABILITIES), help="Repeat to select native workflows")
    parser.add_argument("--cvm-year", type=int)
    parser.add_argument(
        "--msci-factsheet-url",
        help="Direct public MSCI ACWI original PDF URL; classified, bounded and archived")
    parser.add_argument("--acquire", action="store_true")
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-http-requests", type=int, default=30)
    parser.add_argument("--max-tasks", type=int, default=10)
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args(argv)
    if (not 1 <= args.max_http_requests <= 300
            or not 1 <= args.max_tasks <= 15):
        parser.error("HTTP request budget must be 1–300; task budget 1–15")
    if (args.acquire and args.run_dir is None
            or args.run_dir is not None and not args.acquire
            or args.resume and not args.acquire):
        parser.error("Acquisition requires a separate --run-dir; resume requires --acquire")
    if args.artifact is not None and len(set(args.artifact)) != len(args.artifact):
        parser.error("Do not repeat structured artifact identifiers")
    if args.cvm_year is not None and not 2010 <= args.cvm_year <= datetime.now().year:
        parser.error("Invalid CVM annual original year")
    if args.run_dir is not None:
        target = args.run_dir.absolute()
        for folder in (args.evidence_dir, args.holdings_dir):
            if folder is None:
                continue
            original = folder.absolute()
            if target == original or target in original.parents or original in target.parents:
                parser.error("Acquisition journal cannot overlap original source roots")
    try:
        document = load_research_corpus(ROOT)
        catalog = load_documents(ROOT)[0]["series"]
        if validate_research_corpus(document, catalog):
            raise ValueError("invalid_approved_phase2_corpus")
        kinds = set(args.artifact) if args.artifact else set(CAPABILITIES)
        policy = PolicyRegistry()
        agent = os.environ.get("SEC_USER_AGENT")
        plan = structured_operating_plan(
            document, args.evidence_dir,
            holdings=args.holdings_dir, kinds=kinds,
            cvm_year=args.cvm_year, agent=agent, policy=policy,
            msci_factsheet_url=args.msci_factsheet_url)
        if args.acquire:
            contract_digest = sha256(canonical_bytes(document)).hexdigest()
            if args.msci_factsheet_url:
                # Changing a mutable PDF endpoint cannot silently resume a
                # previous immutable acquisition journal.
                contract_digest = sha256(canonical_bytes({
                    "research_contract_sha256": contract_digest,
                    "msci_factsheet_url": args.msci_factsheet_url,
                })).hexdigest()
            context = sweep_context(
                sorted(action["id"] for action in plan["selected_actions"]),
                policy.sha256, contract_digest)
            with Phase2SweepJournal(
                    args.run_dir, context=context,
                    create=not args.resume) as journal:
                gate = SourcePolicyGate(registry=policy)
                with managed_client(
                        timeout=60, follow_redirects=False,
                        headers={"User-Agent": agent or
                                 "finance-dashboard-scientific-research/1.0"},
                        request_budget=args.max_http_requests) as client:
                    def preflight(action):
                        if client._transport.requests_reserved >= args.max_http_requests:
                            return {
                                "state": "deferred",
                                "reason": "invocation_request_budget_exhausted",
                                "retry_at": time.time() + 1,
                            }
                        states = [gate.availability(name) for name in action[
                            "publisher_policies"]]
                        blocked = next(
                            (x for x in states if x["state"] == "blocked"), None)
                        if blocked is not None:
                            return blocked
                        deferred = [x for x in states if x["state"] == "deferred"]
                        if deferred:
                            return {
                                "state": "deferred",
                                "reason": "publisher_budget_deferred",
                                "retry_at": max(x["retry_at"] for x in deferred),
                            }
                        return {"state": "ready"}
                    def refresh(action_id, *, full):
                        if not full:
                            raise ValueError("structured_original_requires_full")
                        kind, _, subsource = action_id.partition(":")
                        outcome = collect_structured_original(
                            kind, root=args.evidence_dir, client=client,
                            subsource=subsource or None,
                            cvm_year=args.cvm_year,
                            holdings_dir=args.holdings_dir,
                            sec_user_agent=agent,
                            msci_factsheet_url=args.msci_factsheet_url,
                            stan_max_requests=max(1, args.max_http_requests -
                                                  client._transport.requests_reserved))
                        return {"status": "success",
                                "series_id": action_id,
                                "received": 1,
                                "versions_added": int(
                                    outcome["state"] == "retained_original")}
                    batch = run_source_acquisition_batch(
                        plan["selected_actions"], refresh,
                        max_attempts=args.max_tasks,
                        stop_scope="publisher", journal=journal,
                        policy_preflight=preflight)
                    requests = client._transport.requests_reserved
                after = structured_operating_plan(
                    document, args.evidence_dir, holdings=args.holdings_dir,
                    kinds=kinds, cvm_year=args.cvm_year, agent=agent,
                    policy=policy, msci_factsheet_url=args.msci_factsheet_url)
                before_by_id = {
                    item["artifact_id"]: item for item in plan["artifact_workstreams"]}
                original_new = [
                    item["artifact_id"] for item in after["artifact_workstreams"]
                    if item["original_proof_state"] == "hash_verified_partial"
                    and before_by_id[item["artifact_id"]][
                        "original_proof_state"] != "hash_verified_partial"
                ]
                plan = after
                plan["acquisition"] = {
                    **{key: val for key, val in batch.items() if key != "results"},
                    "results": batch["results"] if args.details
                               else batch["results"][:13],
                    "actual_managed_http_requests": requests,
                    "newly_hash_verified_artifacts": sorted(original_new),
                    "journal": journal.summary(),
                    "scientific_analysis_certified": False,
                }
        if not args.details:
            plan["roles_without_original_adapter"] = [{
                "analysis_id": role["analysis_id"],
                "role": role["role"],
                "input_type": role["input_type"],
            } for role in plan["roles_without_original_adapter"]]
        print(json.dumps(plan, separators=(",", ":"), allow_nan=False))
        return 0
    except Exception as exc:
        print(json.dumps({
            "phase": "phase2",
            "operation": "structured_originals_operating_plan",
            "status": "blocked",
            "failure_category": safe_source_failure_code(exc),
            "scientific_analysis_certified": False,
        }, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
