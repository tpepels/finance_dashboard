"""Approved original-method source discovery for all unbound scalar roles.

Never auto-binds a similar generic series, converts the units, or asserts an
unknown publisher code. An exact source is a *candidate* until its original
publisher dimensions, observation history, same-release perimeter and
publication evidence are independently checked.
"""
from __future__ import annotations

from collections import Counter

from .phase2_structured_acquisition import CAPABILITIES


_APPROVED_NATIVE_CANDIDATES = {
    "OECD_STAN_2025": {
        "artifact": "stan",
        "roles": {
            "employee_compensation": ("D1",),
            "consumption_fixed_capital": ("P51C",),
            "net_production_taxes": ("D29X39",),
            "gross_value_added": ("B1G",),
            "net_operating_surplus": ("B2N", "B2N_B3_N"),
            "net_fixed_capital": (),
            "oecd_matched_value_added": ("B1G",),
            "oecd_matched_hours": (),
            "oecd_matched_output_deflator": (),
        },
    },
}


def unbound_original_source_discovery(document: dict, catalog: list[dict],
                                      native_evidence: dict) -> dict:
    """Classify the 21 unbound scalar roles against reviewed source families.

    STAN code selection is a native *search plan*: B2N_B3_N explicitly
    combines surplus and mixed income, so it is not an approved replacement
    for pure B2N or a Marxian surplus/profit-rate numerator.
    """
    declared_ids = {item["id"] for item in catalog}
    if len(declared_ids) != len(catalog):
        raise ValueError("duplicate_source_catalog_id")
    rows = []
    candidate_states = Counter()
    for analysis in document["analyses"]:
        for role in analysis["comparison_contract"]["original_requirements"]:
            if role["input_type"] != "scalar_history" or role["series_ids"]:
                continue
            reviewed = []
            for candidate in role.get("publisher_candidates", []):
                dataset = candidate["dataset"]
                native = _APPROVED_NATIVE_CANDIDATES.get(dataset)
                artifact = native["artifact"] if native else None
                evidence = native_evidence.get(artifact, {}) if artifact else {}
                codes = native["roles"].get(role["role"], ()) if native else ()
                supported = bool(evidence.get("original_source_hash_verified"))
                state = (
                    "original_candidate_requires_exact_dimension_reconciliation"
                    if supported and codes else
                    "reviewed_publisher_source_not_verified_for_this_role"
                    if supported else
                    "publisher_original_not_acquired"
                )
                candidate_states[state] += 1
                reviewed.append({
                    "publisher": candidate["publisher"],
                    "dataset": dataset,
                    "publisher_source_url": candidate["source_url"],
                    "potential_original_measure":
                        candidate["potential_original_measure"],
                    "candidate_native_codes": list(codes),
                    "native_artifact_id": artifact,
                    "source_original_hash_verified": supported,
                    "candidate_status": state,
                    "candidate_is_not_exact_role_binding": True,
                    "original_required_checks":
                        candidate["required_original_checks"],
                    "underlying_surplus_contains_mixed_income": (
                        role["role"] == "net_operating_surplus" and
                        dataset == "OECD_STAN_2025"),
                    "official_source_measure_verified_for_role": False,
                    "same_scope_dimensions_verified": False,
                    "first_publication_verified": False,
                })
            rows.append({
                "analysis_id": analysis["id"], "role": role["role"],
                "expected": role["expected"],
                "publisher_candidates": reviewed,
                "reviewed_publisher_candidate_count": len(reviewed),
                "source_discovery_state": (
                    "reviewed_candidates_require_original_verification"
                    if reviewed else "publisher_source_identity_to_research"),
                "exact_scalar_series_bound": False,
                "manual_original_research_required": not reviewed,
            })
    return {
        "operation": "phase2_unbound_original_source_discovery",
        "unbound_scalar_roles": len(rows),
        "roles_with_reviewed_publisher_candidates": sum(
            bool(x["publisher_candidates"]) for x in rows),
        "roles_requiring_new_publisher_discovery": sum(
            not x["publisher_candidates"] for x in rows),
        "source_candidate_states": dict(sorted(candidate_states.items())),
        "role_candidates": rows,
        "automatically_bound_scalar_series": 0,
        "publishers_with_original_data_not_assumed_correct": True,
        "no_missing_observations_interpolated": True,
        "first_publication_verified": False,
        "scientific_analysis_certified": False,
    }


def concise_unbound_discovery(report: dict) -> dict:
    return {
        "unbound_scalar_roles": report["unbound_scalar_roles"],
        "roles_with_reviewed_publisher_candidates":
            report["roles_with_reviewed_publisher_candidates"],
        "roles_requiring_new_publisher_discovery":
            report["roles_requiring_new_publisher_discovery"],
        "source_candidate_states": report["source_candidate_states"],
        "outstanding_roles": [{
            "analysis_id": row["analysis_id"],
            "role": row["role"],
            "publisher_candidate_count": row["reviewed_publisher_candidate_count"],
            "next_action": row["source_discovery_state"],
        } for row in report["role_candidates"]],
        "automatically_bound_scalar_series": 0,
        "scientific_analysis_certified": False,
    }
