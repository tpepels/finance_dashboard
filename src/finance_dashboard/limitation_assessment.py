"""Evidence-based inventory of data and research limitations.

Read-only: classification never promotes an analysis, refreshes a publisher,
repairs a source, or substitutes expected observations. This is an advisory
assessment of the currently recorded evidence, not a code-completeness proof.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import re

from .engine.acceptance import UnacceptedInput, analysis_phase2, input_provenance
from .engine.analyses import DEFINITIONS
from .engine.limitations import UnmappedLimitation, load_register

_SOURCE_ATTENTION = frozenset({
    "stale", "collection_disabled", "not_ingested", "collection_failed",
    "collection_deferred", "refresh_deferred_with_data",
    "refresh_failed_with_data", "source_unresolved",
})
_MISSING_STATES = frozenset({
    "collection_disabled", "not_ingested", "collection_failed",
    "collection_deferred", "source_unresolved",
})
_SOURCE_CHECKED = "source_checked_no_newer_data"
_RESEARCH_BLOCKED = frozenset({"deferred", "incomplete", "not_checked", "failed"})
# A fixed date in a maintained prose statement is a review candidate, not proof
# that newer publisher observations exist. No dates or findings are fabricated.
_FIXED_CURRENCY = re.compile(
    r"\b(?:currently\s+ends?|ending|ends?)\s+(?:in\s+)?20\d{2}\b",
    re.IGNORECASE)
_RESEARCH_GAP_CODES = frozenset({
    "exact_original_inputs_missing_or_partial", "original_comparison_open",
    "original_scientific_failure", "deferred_research_extension",
    "exact_source_unavailable_fallback_used",
})
_METHOD_SCOPE_CODES = frozenset({
    "role_descoped_by_phase1_revision", "io_input_origin_share_author_published",
})
_REMEDIATION = {
    "stale": "Verify the newest publisher observation for this exact series, then import it if available.",
    "collection_failed": "Inspect the last provider error and retry the governed collector.",
    "refresh_failed_with_data": "Investigate the failed source refresh without discarding retained observations.",
    "refresh_deferred_with_data": "Respect the publisher retry policy, then verify whether a newer observation exists.",
    "collection_deferred": "Resume source acquisition when the publisher policy allows.",
    "collection_disabled": "Enable or implement the approved canonical source collector.",
    "not_ingested": "Acquire, validate and ingest the registered original evidence.",
    "source_unresolved": "Resolve the documented source mapping and original identity.",
    _SOURCE_CHECKED: "Recheck the complete publisher original when the verified check expires.",
}


def _finding(*, id: str, category: str, severity: str, status: str,
             title: str, detail: str, next_action: str, analysis_ids=(),
             source_ids=(), provenance: str, evidence: dict | None = None) -> dict:
    return {
        "id": id, "category": category, "severity": severity, "status": status,
        "title": title, "detail": detail, "next_action": next_action,
        "analysis_ids": sorted(set(analysis_ids)),
        "source_ids": sorted(set(source_ids)),
        "provenance": provenance, "evidence": evidence or {},
    }


def _phase2_findings(snapshot, document: dict) -> tuple[list[dict], list[dict]]:
    """Inventories Phase 2 limits AND role-only limits; do not require figure runs."""
    questions, findings = [], []
    for row in document["analyses"]:
        aid = row["id"]
        state = analysis_phase2(snapshot, aid)
        recorded = snapshot.analyses.get(aid) or {}
        questions.append({
            "analysis_id": aid, "question": row.get("title"),
            "state": state["state"], "evaluated_at": state["evaluated_at"],
            "open_gates": list(state.get("open_gates") or []),
            "limitation_codes": sorted({
                limit["code"] for limit in state["limitations"]
            }),
        })
        if state["state"] != "accepted":
            findings.append(_finding(
                id=f"research:{aid}:acceptance_state",
                category="research_acceptance_state",
                severity="medium" if state["state"] == "conditional" else "high",
                status="needs_review" if state["state"] == "conditional" else "needs_evidence",
                title=f"{aid}: research state is {state['state']}",
                detail=("This question's original-method scientific acceptance is not "
                        "unconditionally accepted; its evidence gates and limitations "
                        "must be examined before interpreting results."),
                next_action=("Inspect the question's original roles, verified alternative "
                             "scope and open gates. Reassess after new evidence arrives."),
                analysis_ids=[aid], provenance="phase2_acceptance",
                evidence={"state": state["state"],
                          "open_gates": list(state["open_gates"])},
            ))
        for role in recorded.get("requirements", []):
            if (role.get("requirement_class") == "supplemental"
                    and role.get("state") != "accepted"):
                findings.append(_finding(
                    id=f"research:{aid}:{role['role']}:supplemental_unavailable",
                    category="supplemental_source_pending",
                    severity="information", status="monitor",
                    title=f"{aid}: optional source {role['role']} remains unverified",
                    detail=("This country's supplemental comparison is withheld "
                            "until the exact original is accepted. Core results "
                            "can remain available from their verified inputs."),
                    next_action=("Allow the governed scheduled collector to import "
                                 "and validate this original; investigate only if "
                                 "source health reports a persistent failure."),
                    analysis_ids=[aid], source_ids=role.get("series_ids") or [],
                    provenance="phase2_acceptance",
                    evidence={"role": role["role"], "role_state": role.get("state")},
                ))
        seen: set[tuple[str, str | None]] = set()
        # Analysis-level and per-role limitations can overlap. De-duplicate
        # by exact (code, detail) while retaining affected source identities.
        grouped_items = list(state["limitations"])
        for role in recorded.get("requirements", []):
            from .engine.acceptance import grouped
            grouped_items.extend(grouped(role.get("limitations") or []))
        for limit in grouped_items:
            code, detail = limit["code"], limit.get("detail")
            signature = (code, str(detail) if detail is not None else None)
            if signature in seen:
                continue
            seen.add(signature)
            impacted = set(limit.get("series_ids") or [])
            for item in limit.get("items") or []:
                if item.get("series_id"):
                    impacted.add(item["series_id"])
                impacted.update(item.get("fallback_series_ids") or [])
            gap = code in _RESEARCH_GAP_CODES
            scope = code in _METHOD_SCOPE_CODES
            category = ("research_evidence_gap" if gap else
                        "declared_scope_constraint" if scope else "research_evidence_caveat")
            severity = ("high" if gap and state["state"] in _RESEARCH_BLOCKED
                        else "medium" if gap else "information")
            findings.append(_finding(
                id=f"research:{aid}:{code}:{sha256(str(detail).encode('utf-8')).hexdigest()[:10]}",
                category=category, severity=severity,
                status="needs_evidence" if gap else "documented",
                title=f"{aid}: {code.replace('_', ' ')}",
                detail=(limit.get("text") or code) +
                    ((" Detail: " + str(detail)) if detail else ""),
                next_action=("Obtain and validate the specified original-role evidence; rerun scientific acceptance."
                             if gap else "Retain this caveat in the research question and review whether its stated scope still applies."),
                analysis_ids=[aid], source_ids=impacted,
                provenance="phase2_acceptance",
                evidence={"analysis_state": state["state"], "code": code,
                          "open_gates": list(state.get("open_gates") or [])},
            ))
        if state["open_gates"] and not any(f["analysis_ids"] == [aid] and
                f["category"] == "research_evidence_gap" for f in findings):
            findings.append(_finding(
                id=f"research:{aid}:open_gates", category="research_evidence_gap",
                severity="high", status="needs_evidence",
                title=f"{aid}: research inputs remain unaccepted",
                detail="The scientific acceptance evaluation reports open original-method gates.",
                next_action="Inspect the named roles and complete their original-evidence checks.",
                analysis_ids=[aid], provenance="phase2_acceptance",
                evidence={"analysis_state": state["state"],
                          "open_gates": list(state["open_gates"])},
            ))
    # Bundles may display a limitation inherited from another question's
    # accepted role. Attribute that warning to the borrowing question too,
    # just as engine.bundle.shown_limitations does.
    for row in document["analyses"]:
        aid = row["id"]
        definition = DEFINITIONS.get(aid)
        if definition is None:
            continue
        for role, sid in definition.inputs.items():
            try:
                provenance = input_provenance(snapshot, aid, sid)
            except UnacceptedInput:
                continue
            lender = provenance["accepted_under"]
            if lender["analysis_id"] == aid:
                continue
            for limit in provenance.get("limitations") or []:
                code = limit["code"]
                detail = limit.get("detail")
                findings.append(_finding(
                    id=(f"borrowed:{aid}:{sid}:{code}:"
                        f"{sha256(str(detail).encode('utf-8')).hexdigest()[:10]}"),
                    category="borrowed_input_limitation",
                    severity="information", status="documented",
                    title=f"{aid}: inherited input limitation ({code.replace('_', ' ')})",
                    detail=(limit.get("text") or code) +
                        ((" Detail: " + str(detail)) if detail else ""),
                    next_action=("Review the cited lending analysis and source role "
                                 "before interpreting the borrowed input."),
                    analysis_ids=[aid], source_ids=[sid],
                    provenance="accepted_borrowed_input",
                    evidence={"code": code, "input_role": role,
                              "accepted_under": lender},
                ))
    return questions, findings


def assess_limitations(*, coverage: dict, document: dict,
                       snapshot=None, accounting: dict | None = None,
                       icio_dependencies: dict | None = None,
                       release: dict | None = None) -> dict:
    """Build the complete observable register without running analyses or downloads.

    A missing acceptance assessment is explicitly UNKNOWN; never infer zero
    research limitations. Sources and static method limits remain inspectable.
    """
    findings = []
    series = coverage.get("items") or []
    question_ids = [row["id"] for row in document.get("analyses", [])]
    for item in series:
        sid = item.get("id")
        state = item.get("state") or "unknown"
        refreshed = item.get("refresh_state")
        if not sid:
            continue
        if state in _SOURCE_ATTENTION:
            category = "source_missing" if state in _MISSING_STATES else "source_freshness"
            severity = "high" if item.get("stored_periods", 0) == 0 else "medium"
            status = "needs_evidence"
            action = _REMEDIATION.get(state, "Investigate the registered source.")
        elif state == _SOURCE_CHECKED:
            category, severity, status = "source_freshness", "information", "monitor"
            action = _REMEDIATION[state]
        elif refreshed == "deferred":
            category, severity, status = "source_refresh_deferred", "information", "monitor"
            action = ("An attempted refresh was deferred. Monitor publisher policy "
                      "and the next scheduled source acquisition.")
        else:
            continue
        findings.append(_finding(
            id=f"source:{item.get('family', 'other')}:{sid}:{state if state != 'available' else 'deferred'}",
            category=category, severity=severity, status=status,
            title=f"{sid}: {state.replace('_', ' ')}",
            detail=item.get("next_action") or action, next_action=action,
            source_ids=[sid], analysis_ids=item.get("research_questions") or [],
            provenance="source_coverage",
            evidence={key: item.get(key) for key in (
                "provider", "frequency", "state", "observation_state",
                "latest_source_date", "published_through", "days_since_latest_observation",
                "expected_lag_days", "stored_periods", "last_attempt_state",
                "last_failure_code", "refresh_state", "freshness_basis",
                "source_checked_through_utc")},
        ))
    register = load_register()
    methods = register.get("method") or {}
    questions = []
    assessment = {
        "state": "unavailable", "evaluated_at": None,
        "question_count": len(question_ids), "evaluated_questions": 0,
        "reason": "scientific_acceptance_snapshot_unavailable",
        "source_evidence_revalidated_by_this_audit": False,
    }
    if snapshot is not None:
        try:
            questions, p2_findings = _phase2_findings(snapshot, document)
        except (UnmappedLimitation, KeyError, TypeError, ValueError, AttributeError) as error:
            # Do not suppress the bug or allow an optional audit to destroy
            # the diagnostic ZIP needed to investigate it.
            reason = "acceptance_limitation_register_invalid:" + type(error).__name__
            findings.append(_finding(
                id="assessment:research_limitations_invalid",
                category="limitation_assessment_failure",
                severity="high", status="needs_review",
                title="Research limitation assessment could not be completed",
                detail="The registered acceptance limitations could not be reconciled.",
                next_action="Investigate the limitation register and acceptance role output.",
                provenance="limitation_audit",
                evidence={"error_class": type(error).__name__},
            ))
            assessment = {
                "state": "failed", "evaluated_at": snapshot.evaluated_at.isoformat(),
                "question_count": len(question_ids), "evaluated_questions": 0,
                "reason": reason,
                "source_evidence_revalidated_by_this_audit": False,
            }
        else:
            findings.extend(p2_findings)
            evaluated = sum(q["state"] != "not_checked" for q in questions)
            assessment = {
                "state": "ready" if evaluated == len(question_ids) else "partial",
                "evaluated_at": snapshot.evaluated_at.isoformat(),
                "question_count": len(question_ids), "evaluated_questions": evaluated,
                "reason": None if evaluated == len(question_ids) else "research_questions_not_all_checked",
                "source_evidence_revalidated_by_this_audit": False,
            }
    for aid in sorted(question_ids):
        if aid not in DEFINITIONS:
            findings.append(_finding(
                id=f"implementation:{aid}:missing_engine",
                category="analysis_implementation_missing",
                severity="high", status="needs_review",
                title=f"{aid}: research question has no computing engine",
                detail="The research catalogue declares the question, but the engine "
                       "definition is missing. Its fallback computation returns no values.",
                next_action="Implement the canonical analysis definition and integrate its acceptance and tests.",
                analysis_ids=[aid], provenance="engine_definitions",
            ))
    for aid in sorted(set(methods) - set(question_ids)):
        findings.append(_finding(
            id=f"implementation:{aid}:orphaned_method_limits",
            category="unmapped_limitation_register",
            severity="medium", status="needs_review",
            title=f"{aid}: registered method constraints have no research question",
            detail="Method-limit text exists without a matching analysis in the research corpus.",
            next_action="Reconcile the method register with the actual research catalogue.",
            analysis_ids=[aid], provenance="registered_method_limitation",
        ))
    # The method register is explicit application code, and always inspectable
    # even before the first/next scientific acceptance has finished.
    for aid in sorted(question_ids):
        for code, explanation in (methods.get(aid) or {}).items():
            findings.append(_finding(
                id=f"method:{aid}:{code}", category="documented_method_constraint",
                severity="information", status="documented",
                title=f"{aid}: {code.replace('_', ' ')}",
                detail=explanation,
                next_action="Keep this assumption visible with the affected analysis; review if the method or inputs change.",
                analysis_ids=[aid], provenance="registered_method_limitation",
                evidence={"code": code},
            ))
            if _FIXED_CURRENCY.search(explanation):
                findings.append(_finding(
                    id=f"review:{aid}:{code}:fixed_date",
                    category="potentially_outdated_hardcoded_statement",
                    severity="medium", status="needs_review",
                    title=f"{aid}: fixed source date in method limitation",
                    detail=explanation,
                    next_action=("Compare this fixed date with the latest verified publisher "
                                 "release and stored series. Update the text only when verified."),
                    analysis_ids=[aid], provenance="registered_method_limitation",
                    evidence={"code": code, "automatic_outdatedness_confirmed": False},
                ))
    if accounting is not None:
        failures = int(accounting.get("failure_equations_exported") or 0)
        incomplete = accounting.get("annual_matrices_without_complete_failure_ledger") or []
        if failures or incomplete:
            # Archive-level failed equations do not identify an analytic
            # consumer. The separate dependency audit checks the pinned
            # source-member SHA; only its *exact* failing matches may be
            # attributed to L04. G06 reads a different published TiVA source.
            dependencies = icio_dependencies if isinstance(icio_dependencies, dict) else {}
            counts = dependencies.get("counts") or {}
            matching_failures = int(counts.get("failing_exact_consumer_matrices") or 0)
            other_failures = int(counts.get("failing_other_matrices") or 0)
            matching_origins = int(counts.get("consumer_exact_hash_match") or 0)
            consumer_matched = matching_failures > 0
            linked = ["L04"] if consumer_matched and "L04" in question_ids else []
            if not dependencies:
                scope = "not_evaluated"
            elif consumer_matched:
                scope = "failing_exact_consumer_hash"
            else:
                scope = "no_failing_exact_consumer_hash_in_archive_inventory"
            findings.append(_finding(
                id="scientific-integrity:icio-accounting",
                category="source_accounting_integrity",
                severity="high", status="needs_evidence",
                title=("OECD ICIO source-accounting failures in archived matrices"
                       if not consumer_matched else
                       "OECD ICIO accounting failures affect an exact L04 consumer source"),
                detail=(f"{failures} failure equations exported; "
                        f"{len(incomplete)} annual matrices have incomplete failure ledgers. "
                        + ("Source-consumer identity not assessed in this report."
                           if not dependencies else
                           f"{matching_failures} failed exact-consumer matrices; "
                           f"{other_failures} failed other-edition matrices. "
                           "Nonmatching archives cannot be attributed to G06 or L04; "
                           "unmatched consumer originals are not independently validated.")),
                next_action=("Inspect diagnostics/icio-accounting-failures.csv alongside "
                             "diagnostics/icio-consumer-dependencies.json. Reconcile original "
                             "archive definitions and verify consumer member SHA before "
                             "granting any source-accounting scientific acceptance."),
                analysis_ids=linked,
                provenance="icio_accounting_manifest_and_consumer_scope",
                evidence={"failure_equations_exported": failures,
                          "incomplete_annual_ledgers": len(incomplete),
                          "consumer_scope_state": scope,
                          "failed_exact_consumer_matrices": matching_failures,
                          "failed_other_matrices": other_failures,
                          "exact_consumer_origin_matches": matching_origins,
                          "complete_publisher_reader_audit":
                              dependencies.get("complete_publisher_reader_audit") is True},
            ))
    findings.sort(key=lambda item: (
        {"high": 0, "medium": 1, "information": 2}.get(item["severity"], 3),
        item["category"], item["id"]))
    categories = dict(sorted(Counter(f["category"] for f in findings).items()))
    severity = {key: sum(f["severity"] == key for f in findings)
                for key in ("high", "medium", "information")}
    statuses = dict(sorted(Counter(f["status"] for f in findings).items()))
    research_states = dict(sorted(Counter(q["state"] for q in questions).items()))
    registered = {a for a in methods if a not in question_ids}
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "release": release,
        "scientific_acceptance": assessment,
        "data_coverage": {
            "state": "ready" if isinstance(coverage.get("items"), list) else "unavailable",
            "asof": coverage.get("asof"),
            "registered_series": len(series),
        },
        "method_register": {
            "state": "ready", "analyses_registered": len(methods),
            "unmatched_analysis_ids": sorted(registered),
        },
        "scope": ("Read-only inventory of canonical source health, recorded Phase 2 "
                  "acceptance/role caveats, registered method limitations, fixed-date "
                  "wording needing review and exported ICIO accounting results. "
                  "Not a proof of absence of bugs, source updates or new-method validity."),
        "counts": {"total": len(findings), "by_category": categories,
                   "by_severity": severity, "by_status": statuses,
                   "research_questions": len(question_ids),
                   "research_questions_evaluated": assessment["evaluated_questions"],
                   "research_by_state": research_states},
        "questions": questions,
        "findings": findings,
    }
