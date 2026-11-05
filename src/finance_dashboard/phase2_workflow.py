"""Phase 2 cross-corpus work planning and publisher-neutral acquisition execution.

Every input is derived from canonical scientific roles, catalog definitions and
fresh runtime source reconciliation. A planned task is not source availability
or scientific certification. No alternate provider adapters, rate-limit state,
or parallel scientific readiness registry is maintained here.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import re

import httpx

from .provider_registry import get_provider
from .service import safe_source_failure_code
from .source_policy_registry import PolicyRegistry
from .source_policy_types import PolicyDeferred, PolicyViolation


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
    if not 1 <= limit <= 400:
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


def _publisher_interruption_scope(error: BaseException, policy_id: str | None,
                                  registry: PolicyRegistry | None = None) -> str | None:
    """Scope a stop to a publisher only when the upstream origin is verified.

    A generic failure string is insufficient to establish which publisher is
    affected. A publisher ID supplied by a policy exception or resolved from
    a verified upstream HTTPS host is canonical, even if the catalog's
    descriptive source URL belongs to a different publisher policy.
    Unknown/unclassified origin still forces a global stop.
    The durable publisher policy ledger remains authoritative.
    """
    actual_id = None
    if isinstance(error, (PolicyDeferred, PolicyViolation)):
        actual_id = error.policy_id
    elif isinstance(error, httpx.HTTPStatusError):
        try:
            actual_id = (registry or PolicyRegistry()).for_url(
                error.request.url).id
        except (PolicyViolation, ValueError, TypeError):
            return None
    else:
        # ProviderRouter emits an app-controlled fixed hostname in this
        # exception category. Never use the rest of exception text or log it.
        match = re.fullmatch(
            r"Provider HTTP [0-9]{3} \(([a-z0-9.-]{1,253})\)", str(error))
        if match:
            try:
                actual_id = (registry or PolicyRegistry()).for_url(
                    "https://" + match.group(1)).id
            except (PolicyViolation, ValueError, TypeError):
                return None
    if actual_id is None:
        return None
    policies = (registry or PolicyRegistry()).by_id
    return actual_id if actual_id in policies else None


def run_source_acquisition_batch(selected_actions: list[dict], refresh,
                                 *, max_attempts: int | None = None,
                                 stop_scope: str = "global",
                                 journal=None, progress=None) -> dict:
    """Execute one bounded policy-compliant batch using canonical ingestion.

    The managed transport is the only actual request quota enforcer. When
    stop_scope='publisher', a publisher-specific stop only allows subsequent
    requests to *verified other publishers*. If the upstream policy origin
    cannot be proven, fail closed and stop the whole batch. Completed/failed
    journal tasks are not retried, and unknown in-flight attempts are held
    for manual verification on resume.
    """
    limit = 400 if stop_scope == "publisher" else 120
    budget = len(selected_actions) if max_attempts is None else max_attempts
    if (not isinstance(budget, int) or budget < 0 or budget > limit
            or stop_scope not in {"global", "publisher"}
            or (journal is not None and stop_scope != "publisher")):
        raise ValueError("invalid_phase2_acquisition_budget")
    if len({a["id"] for a in selected_actions}) != len(selected_actions):
        raise ValueError("duplicate_canonical_acquisition_id")
    if any(a.get("state") != "acquisition_candidate" for a in selected_actions):
        raise ValueError("non_acquisition_source_scheduled")
    results = []
    stopped_policies = {}
    stopped_provider_dependencies = {}
    discovered_upstreams = {}
    global_stop = None
    attempted = 0
    for index, action in enumerate(selected_actions, start=1):
        sid = action["id"]
        policy_id = action.get("publisher_policy")
        previous = journal.already_attempted(sid) if journal is not None else None
        if previous is not None:
            row = {"series_id": sid, "status": "deferred_prior_attempt",
                   "previous_status": previous["status"],
                   "previous_reason": previous.get("reason")}
            # The journal records fixed failure codes but historically did
            # not record verified upstream publisher IDs. Do not guess the
            # affected publisher from a possibly different catalog source URL:
            # the durable transport ledger still enforces its cooldown.
        elif global_stop:
            row = {"series_id": sid, "status": "deferred_publisher_stop",
                   "reason": global_stop}
        elif policy_id in stopped_policies:
            row = {"series_id": sid, "status": "deferred_publisher_stop",
                   "reason": stopped_policies[policy_id]}
        elif action.get("provider") in stopped_provider_dependencies:
            row = {"series_id": sid, "status": "deferred_publisher_stop",
                   "reason": stopped_provider_dependencies[action["provider"]]}
        elif attempted >= budget:
            row = {"series_id": sid, "status": "deferred_budget"}
        else:
            # The start event must be durable before *any* possible request.
            if journal is not None:
                journal.mark_started(sid)
            attempted += 1
            try:
                record = refresh(sid, full=True)
                if record.get("status") != "success":
                    raise ValueError("unexpected_ingestion_status")
                row = {"series_id": sid, "status": "success",
                       "received": record.get("received", 0),
                       "versions_added": record.get("versions_added", 0)}
                if journal is not None:
                    journal.mark_result(
                        sid, status="success", received=row["received"],
                        versions_added=row["versions_added"])
            except Exception as error:
                reason = safe_source_failure_code(error)
                row = {"series_id": sid, "status": "failed", "reason": reason}
                if journal is not None:
                    journal.mark_result(sid, status="failed", reason=reason)
                stopped = publisher_stop_reason(error)
                if stopped:
                    if stop_scope == "global":
                        global_stop = stopped
                    else:
                        confirmed_policy = _publisher_interruption_scope(
                            error, policy_id)
                        if confirmed_policy is None:
                            global_stop = stopped
                        else:
                            stopped_policies[confirmed_policy] = stopped
                            if confirmed_policy != policy_id:
                                # The original catalogue URL describes the
                                # publication, but this adapter uses a verified
                                # different API origin. Avoid repeating the
                                # same denied dependency through this adapter.
                                if action.get("provider"):
                                    stopped_provider_dependencies[
                                        action["provider"]] = stopped
                                discovered_upstreams[sid] = {
                                    "declared_policy": policy_id,
                                    "verified_upstream_policy": confirmed_policy,
                                    "stop_reason": stopped,
                                }
        results.append(row)
        if progress is not None and row["status"] not in {
                "deferred_prior_attempt", "deferred_publisher_stop",
                "deferred_budget"}:
            progress(index, len(selected_actions), row)
    reason = global_stop or (
        next(iter(stopped_policies.values())) if stopped_policies else None)
    return {
        "phase": "phase2", "operation": "bounded_canonical_source_acquisition",
        "selected_sources": len(selected_actions),
        "attempted": attempted,
        "succeeded": sum(x["status"] == "success" for x in results),
        "failed": sum(x["status"] == "failed" for x in results),
        "deferred": sum(x["status"].startswith("deferred_") for x in results),
        "stop_category": reason,
        "global_stop_category": global_stop,
        "publisher_stop_categories": dict(sorted(stopped_policies.items())),
        "publisher_adapter_mismatches": [
            {"series_id": sid, **evidence}
            for sid, evidence in sorted(discovered_upstreams.items())
        ],
        "results": results,
        "no_automatic_retries": True,
        "publisher_policy_gateway_enforced_by_provider": True,
        "scientific_analysis_certified": False,
    }
