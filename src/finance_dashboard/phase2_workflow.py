"""Phase 2 cross-corpus work planning and publisher-neutral acquisition execution.

Every input is derived from canonical scientific roles, catalog definitions and
fresh runtime source reconciliation. A planned task is not source availability
or scientific certification. No alternate provider adapters, rate-limit state,
or parallel scientific readiness registry is maintained here.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import re
import time

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


def independently_reconciled_original(proof: dict | None) -> bool:
    """Exactly the same source-level gate for planning and run comparisons."""
    return bool(
        proof and proof.get("source_values_match") is True
        and proof.get("source_covers_all_stored_periods") is True
        and (proof.get("stored_periods") or 0) > 0
    )


def source_evidence_delta(before: dict, after: dict, batch: dict) -> dict:
    """Compare independently selected original proofs, not ingest statuses."""
    baseline = {row["series_id"]: row for row in before["series"]}
    latest = {row["series_id"]: row for row in after["series"]}
    if len(baseline) != len(before["series"]) or len(latest) != len(after["series"]):
        raise ValueError("duplicate_reconciled_source_id")
    verified_before = {
        sid for sid, row in baseline.items()
        if independently_reconciled_original(row)
    }
    verified_after = {
        sid for sid, row in latest.items()
        if independently_reconciled_original(row)
    }
    success = sorted({
        row["series_id"] for row in batch["results"]
        if row["status"] == "success"
    })
    incomplete = []
    for sid in success:
        proof = latest.get(sid, {})
        if sid in verified_after:
            continue
        incomplete.append({
            "series_id": sid,
            "failure_code": proof.get("failure_code") or
                            "current_original_not_fully_reconciled",
            "original_values_match": proof.get("source_values_match") is True,
            "all_stored_periods_covered":
                proof.get("source_covers_all_stored_periods") is True,
        })
    return {
        "verified_before": len(verified_before),
        "verified_after": len(verified_after),
        "newly_verified": sorted(verified_after - verified_before),
        "newly_verified_count": len(verified_after - verified_before),
        "no_longer_verified": sorted(verified_before - verified_after),
        "no_longer_verified_count": len(verified_before - verified_after),
        "ingestion_success_count": len(success),
        "successful_but_not_verified_count": len(incomplete),
        "successful_but_not_verified": incomplete,
        "proofs_recomputed_from_original_archives": True,
        "first_publication_verified": False,
    }


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
        confirmed = independently_reconciled_original(proof)
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
                                 journal=None, progress=None,
                                 policy_preflight=None, max_wait_seconds: float = 0,
                                 clock=None, sleep=None) -> dict:
    """One canonical coordinator for bounded, policy-respecting source tasks.

    A preflight never authorizes an HTTP request. It only prevents avoidable
    publisher quota failures *before* writing an immutable journal start.
    Optional bounded waits defer other publishers first; the actual HTTP
    policy gateway still reserves and verifies each individual request.
    Neither completed failures nor interrupted journal attempts are retried.
    """
    limit = 400 if stop_scope == "publisher" else 120
    budget = len(selected_actions) if max_attempts is None else max_attempts
    if (type(budget) is not int or budget < 0 or budget > limit
            or stop_scope not in {"global", "publisher"}
            or (journal is not None and stop_scope != "publisher")
            or not isinstance(max_wait_seconds, (int, float))
            or not 0 <= max_wait_seconds <= 14_400
            or (max_wait_seconds and policy_preflight is None)):
        raise ValueError("invalid_phase2_acquisition_budget")
    if len({a["id"] for a in selected_actions}) != len(selected_actions):
        raise ValueError("duplicate_canonical_acquisition_id")
    if any(a.get("state") != "acquisition_candidate" for a in selected_actions):
        raise ValueError("non_acquisition_source_scheduled")
    get_time = clock or time.time
    sleep_for = sleep or time.sleep
    deadline = get_time() + max_wait_seconds
    stopped_policies = {}
    stopped_provider_dependencies = {}
    discovered_upstreams = {}
    global_stop = None
    attempted = 0
    waiting_seconds = 0.0
    rows = {}
    pending = list(enumerate(selected_actions))
    while pending:
        deferred = []
        for index, action in pending:
            sid = action["id"]
            policy_id = action.get("publisher_policy")
            previous = journal.already_attempted(sid) if journal is not None else None
            if previous is not None:
                row = {"series_id": sid, "status": "deferred_prior_attempt",
                       "previous_status": previous["status"],
                       "previous_reason": previous.get("reason")}
                # Legacy completed journal events have only a safe failure
                # code, not a verified actual upstream ID. The HTTP policy
                # gateway, not this inferred catalog ID, guards future work.
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
                availability = (
                    policy_preflight(action) if policy_preflight is not None
                    else {"state": "ready"}
                )
                state = availability["state"]
                if state == "deferred":
                    retry_at = availability.get("retry_at")
                    if not isinstance(retry_at, (float, int)):
                        raise ValueError("invalid_policy_preflight_retry")
                    deferred.append((index, action, retry_at,
                                     availability.get("reason")))
                    continue
                if state == "blocked":
                    row = {"series_id": sid,
                           "status": "deferred_policy_blocked",
                           "reason": availability.get("reason")}
                elif state != "ready":
                    raise ValueError("invalid_policy_preflight_state")
                else:
                    # A durable start must precede the first possible request.
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
                        row = {"series_id": sid, "status": "failed",
                               "reason": reason}
                        if journal is not None:
                            journal.mark_result(sid, status="failed",
                                                reason=reason)
                        stopped = publisher_stop_reason(error)
                        if stopped:
                            if stop_scope == "global":
                                global_stop = stopped
                            else:
                                confirmed = _publisher_interruption_scope(
                                    error, policy_id)
                                if confirmed is None:
                                    global_stop = stopped
                                else:
                                    stopped_policies[confirmed] = stopped
                                    if confirmed != policy_id:
                                        if action.get("provider"):
                                            stopped_provider_dependencies[
                                                action["provider"]] = stopped
                                        discovered_upstreams[sid] = {
                                            "declared_policy": policy_id,
                                            "verified_upstream_policy": confirmed,
                                            "stop_reason": stopped,
                                        }
            rows[index] = row
            if progress is not None and row["status"] in {"success", "failed"}:
                progress(index + 1, len(selected_actions), row)

        if not deferred:
            break
        if global_stop or attempted >= budget:
            for index, action, _, reason in deferred:
                rows[index] = {
                    "series_id": action["id"],
                    "status": "deferred_publisher_stop" if global_stop
                              else "deferred_budget",
                    "reason": global_stop or reason,
                }
            break
        # Freshly visited publishers may have become available while other
        # independent sources were acquired. Re-check them before sleeping.
        retry = min(item[2] for item in deferred)
        remaining = deadline - get_time()
        if max_wait_seconds <= 0 or retry > deadline or remaining <= 0:
            for index, action, when, reason in deferred:
                rows[index] = {
                    "series_id": action["id"],
                    "status": "deferred_policy_preflight",
                    "reason": reason,
                    "retry_at": when,
                }
            break
        seconds = min(max(0.05, retry - get_time()), remaining)
        sleep_for(seconds)
        waiting_seconds += seconds
        pending = [(index, action) for index, action, _, _ in deferred]
    results = [rows[i] for i in range(len(selected_actions))]
    reason = global_stop or (
        next(iter(stopped_policies.values())) if stopped_policies else None)
    preflight_blocked = sum(x["status"] == "deferred_policy_blocked"
                            for x in results)
    preflight_deferred = sum(x["status"] == "deferred_policy_preflight"
                             for x in results)
    return {
        "phase": "phase2", "operation": "bounded_canonical_source_acquisition",
        "selected_sources": len(selected_actions),
        "attempted": attempted,
        "succeeded": sum(x["status"] == "success" for x in results),
        "failed": sum(x["status"] == "failed" for x in results),
        "deferred": sum(x["status"].startswith("deferred_") for x in results),
        "policy_preflight_blocked": preflight_blocked,
        "policy_preflight_deferred": preflight_deferred,
        "policy_wait_seconds": round(waiting_seconds, 3),
        "next_policy_retry_at": min(
            (x["retry_at"] for x in results
             if x["status"] == "deferred_policy_preflight"), default=None),
        "stop_category": reason,
        "global_stop_category": global_stop,
        "publisher_stop_categories": dict(sorted(stopped_policies.items())),
        "publisher_adapter_mismatches": [
            {"series_id": sid, **evidence}
            for sid, evidence in sorted(discovered_upstreams.items())
        ],
        "results": results,
        "no_automatic_failed_source_retries": True,
        "no_automatic_retries": True,
        "publisher_policy_gateway_enforced_by_provider": True,
        "scientific_analysis_certified": False,
    }
