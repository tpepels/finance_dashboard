"""Scientific input-role work queues derived from the existing 35-analysis gates.

Structured artifacts and unbound scalar roles are tracked separately from
runnable scalar providers. These records are work instructions and never
alter acceptance gates or invent source availability, publisher dimensions or
original publication vintages.
"""
from __future__ import annotations

from collections import Counter


def phase2_role_workplan(public_report: dict) -> dict:
    """Group every original role once; preserve all unresolved gates and scope."""
    by_artifact: dict[str, dict] = {}
    publisher_candidates: dict[tuple[str, str], dict] = {}
    missing_scalar = []
    unassigned_structured = []
    dispositions = Counter()
    all_roles = 0
    counted_structured = 0
    for analysis in public_report["analyses"]:
        for role in analysis["requirements"]:
            all_roles += 1
            input_type = role["input_type"]
            disposition = role.get("resolution", {}).get("classification",
                                                        "unclassified")
            dispositions[disposition] += 1
            missing = sorted({
                check["id"] for check in role["checks"]
                if check["state"] != "passed"})
            if input_type == "scalar_history":
                if not role.get("series_ids"):
                    # Publisher candidates are METHOD hypotheses in the
                    # approved corpus, not scalar dataset bindings or
                    # permission to assign observed values to an original role.
                    candidates = role.get("publisher_candidates", [])
                    missing_scalar.append({
                        "analysis_id": analysis["id"],
                        "role": role["role"],
                        "classification": disposition,
                        "unverified_gates": missing,
                        "publisher_candidate_count": len(candidates),
                        "publisher_candidates": candidates,
                        "requires_original_source_discovery": True,
                    })
                    for candidate in candidates:
                        ident = (candidate["publisher"], candidate["dataset"])
                        record = publisher_candidates.setdefault(ident, {
                            "publisher": candidate["publisher"],
                            "dataset": candidate["dataset"],
                            "source_urls": set(),
                            "roles": [],
                            "analyses": set(),
                            "original_checks": set(),
                            "candidate_states": Counter(),
                        })
                        record["roles"].append({
                            "analysis_id": analysis["id"],
                            "role": role["role"],
                            "potential_original_measure": candidate[
                                "potential_original_measure"],
                            "status": candidate["status"],
                            "required_original_checks": candidate[
                                "required_original_checks"],
                        })
                        record["analyses"].add(analysis["id"])
                        record["source_urls"].add(candidate["source_url"])
                        record["original_checks"].add(candidate[
                            "required_original_checks"])
                        record["candidate_states"][candidate["status"]] += 1
                continue
            counted_structured += 1
            artifacts = sorted(set(role.get("artifact_ids", [])))
            role_entry = {
                "analysis_id": analysis["id"], "role": role["role"],
                "input_type": input_type, "classification": disposition,
                "unverified_gates": missing,
                "partially_verified_artifacts": [
                    item["artifact_id"] for item in
                    role.get("partial_artifact_evidence", [])],
            }
            if not artifacts:
                unassigned_structured.append(role_entry)
            for artifact in artifacts:
                cluster = by_artifact.setdefault(artifact, {
                    "artifact_id": artifact, "roles": [],
                    "analysis_ids": set(), "classifications": Counter(),
                    "missing_gate_counts": Counter(),
                })
                cluster["roles"].append(role_entry)
                cluster["analysis_ids"].add(analysis["id"])
                cluster["classifications"][disposition] += 1
                cluster["missing_gate_counts"].update(missing)
    if public_report.get("role_resolution_summary", {}).get("role_count") != all_roles:
        raise ValueError("scientific_role_report_count_disagrees")
    artifacts = []
    for row in by_artifact.values():
        artifacts.append({
            "artifact_id": row["artifact_id"],
            "role_count": len(row["roles"]),
            "affected_analyses": sorted(row["analysis_ids"]),
            "classification_counts": dict(sorted(row["classifications"].items())),
            "unverified_gate_counts": dict(sorted(row["missing_gate_counts"].items())),
            "roles": row["roles"],
            "evidence_is_partial_not_accepted": True,
        })
    artifacts.sort(key=lambda row: (
        -len(row["affected_analyses"]), -row["role_count"], row["artifact_id"]))
    groups = [{
        "publisher": item["publisher"],
        "dataset": item["dataset"],
        "source_urls": sorted(item["source_urls"]),
        "affected_analyses": sorted(item["analyses"]),
        "unbound_roles": len(item["roles"]),
        "candidate_states": dict(sorted(item["candidate_states"].items())),
        "required_original_checks": sorted(item["original_checks"]),
        "roles": item["roles"],
        "candidate_is_not_verified_source": True,
    } for item in publisher_candidates.values()]
    groups.sort(key=lambda item: (-len(item["affected_analyses"]),
                                  -item["unbound_roles"],
                                  item["publisher"], item["dataset"]))
    return {
        "operation": "phase2_original_role_workplan",
        "total_original_roles": all_roles,
        "structured_roles": counted_structured,
        "unbound_scalar_roles": len(missing_scalar),
        "classification_counts": dict(sorted(dispositions.items())),
        "artifact_workstreams": artifacts,
        "unassigned_structured_roles": unassigned_structured,
        "unbound_scalar_role_discovery": missing_scalar,
        "publisher_original_candidate_groups": groups,
        "unbound_scalar_roles_with_publisher_candidates": sum(
            bool(item["publisher_candidate_count"]) for item in missing_scalar),
        "unbound_scalar_roles_without_publisher_candidates": sum(
            not item["publisher_candidate_count"] for item in missing_scalar),
        "publisher_candidates_require_original_source_validation": True,
        "structured_artifact_acquisition_automated": False,
        "complete_original_release_eligibility_verified": False,
        "scientific_certification": False,
    }


def compact_role_workplan(plan: dict) -> dict:
    """Concise report for copy-paste; details retain full per-role audit."""
    return {
        "structured_roles": plan["structured_roles"],
        "unbound_scalar_roles": plan["unbound_scalar_roles"],
        "classification_counts": plan["classification_counts"],
        "artifact_workstreams": [{
            "artifact_id": item["artifact_id"],
            "role_count": item["role_count"],
            "affected_analyses": len(item["affected_analyses"]),
            "missing_gate_counts": item["unverified_gate_counts"],
        } for item in plan["artifact_workstreams"]],
        "unassigned_structured_roles": len(plan["unassigned_structured_roles"]),
        "unbound_scalar_roles_requiring_discovery": len(
            plan["unbound_scalar_role_discovery"]),
        "unbound_scalar_roles_with_publisher_candidates":
            plan["unbound_scalar_roles_with_publisher_candidates"],
        "unbound_scalar_roles_without_publisher_candidates":
            plan["unbound_scalar_roles_without_publisher_candidates"],
        "publisher_original_candidate_groups": [{
            "publisher": item["publisher"], "dataset": item["dataset"],
            "affected_analyses": item["affected_analyses"],
            "unbound_roles": item["unbound_roles"],
            "candidate_states": item["candidate_states"],
            "candidate_is_not_verified_source": True,
        } for item in plan["publisher_original_candidate_groups"]],
        "scientific_certification": False,
    }
