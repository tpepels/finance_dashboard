"""Phase 2 cross-corpus work planning and publisher-neutral acquisition execution.

Every input is derived from canonical scientific roles, catalog definitions and
fresh runtime source reconciliation. A planned task is not source availability
or scientific certification. No alternate provider adapters, rate-limit state,
or parallel scientific readiness registry is maintained here.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import re

from .provider_registry import get_provider
from .service import safe_source_failure_code
from .source_policy_registry import PolicyRegistry
from .source_policy_types import PolicyDeferred, PolicyViolation


UNVERIFIED_STATES = frozenset({"failed", "blocked", "incomplete", "not_checked"})


def publisher_stop_reason(error: BaseException) -> str | None:
    """Use the existing canonical failure taxonomy, never untrusted messages.

    Downstream adapters may convert an HTTP status into a controlled fixed
    source failure category. The actual transport policy and durable cooldown
    are exclusively owned by the publisher policy gateway.
    """
    if isinstance(error, PolicyDeferred):
        return "source_policy_deferred"
    if isinstance(error, PolicyViolation):
        return "source_policy_denied"
    safe = safe_source_failure_code(error)
    if safe in {"source_policy_deferred", "source_policy_denied"}:
        return safe
    m = re.fullmatch(r"provider_http_([0-9]{3})", safe)
    if m and (int(m.group(1)) in {401, 403, 429}
              or int(m.group(1)) >= 500):
        return safe
    return None


def source_acquisition_plan(document: dict, registry: list[dict],
                            runtime_report: dict, source_proof: dict,
                            *, policy_registry: PolicyRegistry | None = None,
                            limit: int = 12, after_id: str | None = None) -> dict:
    """Prioritize canonical source histories relevant to approved analyses.

    A task is eligible only if its exact catalog adapter is supported and the
    declared source-reference host is governed. Source-reconciled histories
    are never downloaded solely to satisfy publisher-method or temporal gates.
    All analysis references, including contextual mappings, share one source
    ID; duplicates never generate extra publisher requests.
    """
    if not 1 <= limit <= 120:
        raise ValueError("invalid_phase2_source_attempt_limit")
    if (runtime_report.get("analysis_count") != len(document["analyses"])
            or len(runtime_report.get("analyses", [])) != len(document["analyses"])):
        raise ValueError("research_runtime_and_contract_membership_disagree")
    wanted = {item["id"] for item in document["analyses"]}
    observed = {item["id"] for item in runtime_report["analyses"]}
    if len(wanted) != len(document["analyses"]) or wanted != observed:
        raise ValueError("research_runtime_analysis_ids_mismatch")
    if source_proof.get("series") is None:
        raise ValueError("source_reconciliation_missing")

    from .research_corpus import analysis_series_ids
    policy = policy_registry or PolicyRegistry()
    catalog = {item["id"]: item for item in registry}
    if len(catalog) != len(registry):
        raise ValueError("duplicate_source_catalog_id")
    proofs = {item["series_id"]: item for item in source_proof["series"]}
    if len(proofs) != len(source_proof["series"]):
        raise ValueError("duplicate_original_source_proof")

    by_id: dict[str, set[str]] = defaultdict(set)
    for analysis in document["analyses"]:
        for sid in analysis_series_ids(analysis):
            by_id[sid].add(analysis["id"])
    for analysis in runtime_report["analyses"]:
        if {item["series_id"] for item in analysis["linked_sources"]} != {
                sid for sid, analyses in by_id.items() if analysis["id"] in analyses}:
            raise ValueError("research_source_binding_projection_disagrees")

    actions = []
    dispositions = []
    blockers = Counter()
    for sid, analyses in sorted(by_id.items()):
        item = catalog.get(sid)
        if not item:
            raise ValueError("unregistered_research_source")
        proof = proofs.get(sid)
        confirmed = bool(
            proof and proof.get("source_values_match") is True
            and proof.get("source_covers_all_stored_periods") is True
            and (proof.get("stored_periods") or 0) > 0
        )
        provider = get_provider(item["provider"])
        policy_id = None
        policy_blocker = None
        try:
            source_policy = policy.for_url(item["source_url"])
            policy_id = source_policy.id
            if (not source_policy.restrictions["allow_automated_download"]
                    or source_policy.rights["internal_analysis"] !=
                    "allowed_with_attribution"):
                policy_blocker = "publisher_collection_not_cleared"
        except (KeyError, TypeError, PolicyViolation):
            policy_blocker = "publisher_reference_unclassified"
        if confirmed:
            state = "verified_original_history"
        elif item.get("status") != "mapped":
            state = "source_not_mapped"
        elif provider is None or provider.acquisition == "unsupported":
            state = "provider_unavailable"
        elif provider.acquisition == "local":
            state = "local_input_required"
        elif policy_blocker:
            state = policy_blocker
        else:
            state = "acquisition_candidate"
        blockers[state] += 1
        dispositions.append({"id": sid, "state": state,
                             "publisher_policy": policy_id,
                             "affected_analyses": sorted(analyses)})
        if state not in {"verified_original_history", "acquisition_candidate"}:
            continue
        actions.append({
            "id": sid, "publisher_policy": policy_id,
            "provider": item["provider"], "state": state,
            "affected_analyses": sorted(analyses),
            "affected_analysis_count": len(analyses),
            "source_failure_code": (proof or {}).get("failure_code"),
            "stored_periods": (proof or {}).get("stored_periods", 0),
            "historical_completeness_confirmed": confirmed,
        })

    all_unverified = sorted(
        (x for x in actions if x["state"] == "acquisition_candidate"),
        key=lambda x: (-x["affected_analysis_count"], x["id"])
    )
    unverified = all_unverified
    if after_id is not None:
        # Cursor identity remains valid after its own source is acquired and
        # disappears from the candidate list. Priority is stable because it
        # derives from the immutable approved analysis-to-source graph.
        if after_id not in by_id:
            raise ValueError("invalid_phase2_acquisition_cursor")
        rank = (-len(by_id[after_id]), after_id)
        unverified = [
            item for item in unverified
            if (-item["affected_analysis_count"], item["id"]) > rank
        ]
    selected = unverified[:limit]
    deferred = unverified[limit:]
    decisions = Counter(
        a["readiness"]["decision"] for a in runtime_report["analyses"])
    gate_counts = Counter()
    per_analysis = []
    for analysis in runtime_report["analyses"]:
        gate = Counter(check["id"] for role in analysis["requirements"]
                       for check in role["checks"]
                       if check["state"] != "passed")
        gate_counts.update(gate)
        ids = {sid for sid, refs in by_id.items() if analysis["id"] in refs}
        missing = [x["id"] for x in selected if x["id"] in ids]
        per_analysis.append({
            "id": analysis["id"],
            "decision": analysis["readiness"]["decision"],
            "original": analysis["readiness"]["original"]["decision"],
            "unverified_roles": analysis["readiness"]["original"][
                "missing_or_partial_roles"],
            "scientific_failure_count": len(analysis["acceptance"]["scientific_failures"]),
            "gate_counts": dict(sorted(gate.items())),
            "selected_source_actions": missing,
            "first_publication_verified": False,
        })
    return {
        "phase": "phase2", "operation": "canonical_research_action_plan",
        "analysis_count": len(per_analysis),
        "analysis_decisions": dict(sorted(decisions.items())),
        "gate_failure_counts": dict(sorted(gate_counts.items())),
        "source_dispositions": dict(sorted(blockers.items())),
        "sources_referenced": len(by_id),
        "sources_with_verified_original_history": blockers["verified_original_history"],
        "source_acquisition_candidates": len(all_unverified),
        "selected_actions": selected,
        "deferred_action_count": len(deferred),
        "blocked_source_actions": [
            item for item in dispositions
            if item["state"] not in {
                "verified_original_history", "acquisition_candidate"}],
        "analyses": per_analysis,
        "next_cursor": selected[-1]["id"] if selected and deferred else None,
        "publisher_requests_made": 0,
        "source_originals_modified": False,
        "scopes_joined_or_interpolated": False,
        "first_publication_verified": False,
        "scientific_analysis_certified": False,
    }


def run_source_acquisition_batch(selected_actions: list[dict], refresh,
                                 *, max_attempts: int | None = None) -> dict:
    """Execute one bounded publisher-neutral batch against existing service.

    Refresh is the existing IngestionService.refresh interface. No callbacks
    run after publisher access denial, 429/5xx, or policy deferral. The durable
    rate gate remains the only scheduler; this coordinator neither retries nor
    bypasses cooldowns.
    """
    budget = len(selected_actions) if max_attempts is None else max_attempts
    if not isinstance(budget, int) or budget < 0 or budget > 120:
        raise ValueError("invalid_phase2_acquisition_budget")
    if len({a["id"] for a in selected_actions}) != len(selected_actions):
        raise ValueError("duplicate_canonical_acquisition_id")
    results = []
    interrupted = None
    attempts = 0
    for action in selected_actions:
        if action.get("state") != "acquisition_candidate":
            raise ValueError("non_acquisition_source_scheduled")
        if interrupted:
            results.append({"series_id": action["id"], "status": "deferred_publisher_stop",
                            "reason": interrupted})
            continue
        if attempts >= budget:
            results.append({"series_id": action["id"], "status": "deferred_budget"})
            continue
        attempts += 1
        try:
            record = refresh(action["id"], full=True)
            if record.get("status") != "success":
                raise ValueError("unexpected_ingestion_status")
            results.append({"series_id": action["id"], **record})
        except Exception as exc:
            code = safe_source_failure_code(exc)
            results.append({"series_id": action["id"], "status": "failed",
                            "reason": code})
            interrupted = publisher_stop_reason(exc)
    return {
        "phase": "phase2", "operation": "bounded_canonical_source_acquisition",
        "selected_sources": len(selected_actions),
        "attempted": attempts,
        "succeeded": sum(x["status"] == "success" for x in results),
        "failed": sum(x["status"] == "failed" for x in results),
        "deferred": sum(x["status"].startswith("deferred_") for x in results),
        "stop_category": interrupted,
        "results": results,
        "no_automatic_retries": True,
        "publisher_policy_gateway_enforced_by_provider": True,
        "scientific_analysis_certified": False,
    }
