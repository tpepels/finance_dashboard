"""Independent change audit of the same approved 35-analysis evidence contract.

Comparisons identify source, role and scientific-gate transitions. A new
pass on a partial gate does not imply original-method acceptance; all
decisions are reproduced from the canonical runtime reports, not recomputed.
"""
from __future__ import annotations

from collections import Counter


READINESS_ORDER = {"blocked": 0, "deferred": 0, "conditional": 1, "accepted": 2, "complete": 2}


def _analyses(report: dict) -> dict:
    data = report["analyses"]
    by_id = {row["id"]: row for row in data}
    if (len(by_id) != len(data)
            or report.get("analysis_count") != len(data)):
        raise ValueError("invalid_research_transition_membership")
    return by_id


def _role_signature(role: dict) -> tuple:
    return role["role"], role["input_type"]


def _checks(role: dict) -> dict:
    values = {item["id"]: item["state"] for item in role["checks"]}
    if len(values) != len(role["checks"]):
        raise ValueError("duplicate_research_gate")
    return values


def research_evidence_transitions(before: dict, after: dict) -> dict:
    """Require the same original source/role matrix and list every transition.

    A pass counts as a scientific gate improvement; blocked->incomplete is
    reported as a state change without asserting that its evidence is now
    satisfactory. Missing/reordered roles or a changed analysis corpus are
    rejected instead of obscuring source upgrades or regressions.
    """
    original = _analyses(before)
    current = _analyses(after)
    if set(original) != set(current):
        raise ValueError("research_transition_analysis_identity_changed")
    transitions = []
    gate_new_passed = Counter()
    gate_lost_passed = Counter()
    gate_state_changes = Counter()
    improvements = []
    regressions = []
    accepted_before = accepted_after = 0
    for aid in sorted(current):
        old, new = original[aid], current[aid]
        if (len(old["requirements"]) != len(new["requirements"])
                or [_role_signature(role) for role in old["requirements"]]
                != [_role_signature(role) for role in new["requirements"]]):
            raise ValueError("research_transition_role_contract_changed")
        old_decision = old["readiness"]["decision"]
        new_decision = new["readiness"]["decision"]
        if old_decision not in READINESS_ORDER or new_decision not in READINESS_ORDER:
            raise ValueError("unrecognized_research_readiness_decision")
        accepted_before += bool(old["acceptance"]["accepted"])
        accepted_after += bool(new["acceptance"]["accepted"])
        changes = []
        for old_role, new_role in zip(
                old["requirements"], new["requirements"], strict=True):
            old_checks, new_checks = _checks(old_role), _checks(new_role)
            if set(old_checks) != set(new_checks):
                raise ValueError("research_transition_gate_identity_changed")
            for gate in sorted(old_checks):
                a, b = old_checks[gate], new_checks[gate]
                if a == b:
                    continue
                gate_state_changes[gate] += 1
                if b == "passed" and a != "passed":
                    gate_new_passed[gate] += 1
                elif a == "passed" and b != "passed":
                    gate_lost_passed[gate] += 1
                changes.append({
                    "role": new_role["role"], "input_type": new_role["input_type"],
                    "gate": gate, "before": a, "after": b,
                    "new_pass": b == "passed" and a != "passed",
                    "lost_pass": a == "passed" and b != "passed",
                })
        if new_decision != old_decision or changes:
            transitions.append({
                "analysis_id": aid,
                "readiness_before": old_decision,
                "readiness_after": new_decision,
                "readiness_direction": (
                    "improved" if READINESS_ORDER[new_decision] >
                    READINESS_ORDER[old_decision] else "regressed"
                    if READINESS_ORDER[new_decision] <
                    READINESS_ORDER[old_decision] else "unchanged"),
                "gate_changes": changes,
                "gate_change_count": len(changes),
                "lost_verified_gate_count": sum(x["lost_pass"] for x in changes),
                "new_verified_gate_count": sum(x["new_pass"] for x in changes),
            })
        if READINESS_ORDER[new_decision] > READINESS_ORDER[old_decision]:
            improvements.append(aid)
        if READINESS_ORDER[new_decision] < READINESS_ORDER[old_decision]:
            regressions.append(aid)
    return {
        "operation": "research_evidence_transitions",
        "analysis_count": len(current),
        "readiness_improvements": improvements,
        "readiness_regressions": regressions,
        "readiness_improvement_count": len(improvements),
        "readiness_regression_count": len(regressions),
        "accepted_before": accepted_before,
        "accepted_after": accepted_after,
        "newly_passed_gates": dict(sorted(gate_new_passed.items())),
        "lost_passed_gates": dict(sorted(gate_lost_passed.items())),
        "gate_state_changes": dict(sorted(gate_state_changes.items())),
        "changed_analyses": transitions,
        "no_evidence_or_certification_created": True,
    }


def compact_research_transitions(report: dict, *, limit: int = 8) -> dict:
    if limit < 0:
        raise ValueError("invalid_transition_limit")
    return {
        key: value for key, value in report.items()
        if key != "changed_analyses"
    } | {
        "changed_analysis_count": len(report["changed_analyses"]),
        "changed_analyses": [{
            "analysis_id": item["analysis_id"],
            "readiness_before": item["readiness_before"],
            "readiness_after": item["readiness_after"],
            "readiness_direction": item["readiness_direction"],
            "new_verified_gate_count": item["new_verified_gate_count"],
            "lost_verified_gate_count": item["lost_verified_gate_count"],
            "changed_gate_ids": sorted(set(
                gate["gate"] for gate in item["gate_changes"])),
        } for item in report["changed_analyses"][:limit]],
        "changed_analyses_omitted": max(
            0, len(report["changed_analyses"]) - limit),
    }
