"""Evidence-based inventory of data and research limitations.

Read-only: classification never promotes an analysis, refreshes a publisher,
repairs a source, or substitutes expected observations. This is an advisory
assessment of the currently recorded evidence, not a code-completeness proof.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import re

from .engine.acceptance import analysis_phase2
from .engine.analyses import DEFINITIONS
from .engine.limitations import load_register

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
                id=f"research:{aid}:{code}:{len(seen)}",
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
    return questions, findings


def assess_limitations(*, coverage: dict, document: dict,
                       snapshot=None, accounting: dict | None = None,
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
        state = item.get("state")
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
    }
    if snapshot is not None:
        questions, p2_findings = _phase2_findings(snapshot, document)
        findings.extend(p2_findings)
        evaluated = sum(q["state"] != "not_checked" for q in questions)
        assessment = {
            "state": "ready" if evaluated == len(question_ids) else "partial",
            "evaluated_at": snapshot.evaluated_at.isoformat(),
            "question_count": len(question_ids), "evaluated_questions": evaluated,
            "reason": None if evaluated == len(question_ids) else "research_questions_not_all_checked",
        }
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
            findings.append(_finding(
                id="scientific-integrity:icio-accounting",
                category="source_accounting_integrity",
                severity="high", status="needs_evidence",
                title="OECD ICIO native accounting failures require reconciliation",
                detail=(f"{failures} failure equations exported; "
                        f"{len(incomplete)} annual matrices have incomplete failure ledgers."),
                next_action=("Inspect the exact accounting failures in "
                             "diagnostics/icio-accounting-failures.csv; reconcile "
                             "against original matrix definitions before scientific acceptance."),
                analysis_ids=["G06"] if "G06" in question_ids else [],
                provenance="icio_accounting_manifest",
                evidence={"failure_equations_exported": failures,
                          "incomplete_annual_ledgers": len(incomplete)},
            ))
    findings.sort(key=lambda item: (
        {"high": 0, "medium": 1, "information": 2}.get(item["severity"], 3),
        item["category"], item["id"]))
    categories = dict(sorted(Counter(f["category"] for f in findings).items()))
    severity = {key: sum(f["severity"] == key for f in findings)
                for key in ("high", "medium", "information")}
    statuses = dict(sorted(Counter(f["status"] for f in findings).items()))
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
                   "research_questions_evaluated": assessment["evaluated_questions"]},
        "questions": questions,
        "findings": findings,
    }
