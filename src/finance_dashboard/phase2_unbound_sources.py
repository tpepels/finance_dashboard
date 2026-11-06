"""Evidence-based discovery of every unbound original scalar input.

A reviewed publisher hypothesis and a retained original native observation
are different states. This module cross-checks the actual source selection,
published STAN measure codes, exact country/industry scope and already retained
numeric source rows, without assigning a similarly named scalar history.
"""
from __future__ import annotations

from collections import Counter

# Explicit reviewed source families: original source candidates, not aliases
# for one another or certified scalar-series bindings.
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

# An approved original role can refer to a registered native publication even
# when there is no approved *scalar* catalog binding yet. This never converts
# structured records to a scalar ID or changes the 35-analysis method.
# L07's survey Gini is bound to World Bank PIP survey series since 2026-11-06;
# no role currently needs this path, which remains available for future ones.
DOCUMENTED_NATIVE_DISCOVERY: dict[tuple[str, str], str] = {}

# Nearby, existing real datasets to inspect. All fail at least one of the
# original method's requirements and must never be used as automatic fallbacks.
RELATED_REGISTERED_REFERENCES = {
    ("F01", "nominal_gdp"): (
        ("gdp.nominal_usd.us", "annual_USD_flow_not_quarterly_native_four_quarter_GDP"),),
    ("V03", "regional_trailing_pe"): (
        ("valuation.world.global_trailing_pe", "global_index_not_regional_same_vendor_panel"),),
    ("P03", "benchmark_risk_free"): (
        ("returns.french.developed.risk_free_usd", "fund_factor_proxy_not_named_portfolio_benchmark"),
        ("returns.french.emerging.risk_free_usd", "fund_factor_proxy_not_named_portfolio_benchmark")),
    ("P02", "global_bond_total_return"): (
        ("returns.doeswijk_swinkels.global_multiasset.usd.nominal",
         "multiasset_portfolio_not_global_bond_total_return_index"),),
}


def _stan_candidate_scopes(stan_readiness: dict | None, measures: tuple[str, ...]) -> dict:
    """Original-scope numeric evidence; never join separate publisher calls."""
    if not measures or stan_readiness is None:
        return {
            "verified_numeric_measure_in_original_scopes": False,
            "observed_countries": [],
            "max_numeric_rows_in_one_original_scope": 0,
            "reviewed_original_scopes": [],
            "same_industry_year_alignment_to_other_inputs_verified": False,
        }
    records = []
    for country in stan_readiness.get("country_readiness", []):
        for item in country.get("per_scope_coverage", []):
            present = {
                measure: count for measure, count
                in item.get("measure_observations", {}).items()
                if measure in measures and type(count) is int and count > 0
            }
            if present:
                records.append({
                    "country": country["country"],
                    "scope": item["scope"],
                    "requested_since": item["requested_since"],
                    "source_sha256": item["original_response_sha256"],
                    "numeric_measure_counts": dict(sorted(present.items())),
                    "year_spans_by_measure": {
                        measure: item.get("year_spans_by_measure", {}).get(measure)
                        for measure in sorted(present)
                    },
                    "same_retrieval_verified": True,
                })
    return {
        "verified_numeric_measure_in_original_scopes": bool(records),
        "observed_countries": sorted({row["country"] for row in records}),
        "max_numeric_rows_in_one_original_scope": max((
            max(item["numeric_measure_counts"].values()) for item in records),
            default=0),
        "observed_source_scope_count": len(records),
        "reviewed_original_scopes": records[:8],
        "same_industry_year_alignment_to_other_inputs_verified": False,
        "cross_retrievals_combined": False,
    }


def unbound_original_source_discovery(document: dict, catalog: list[dict],
                                      native_evidence: dict,
                                      *, stan_readiness: dict | None = None,
                                      stan_structure: dict | None = None) -> dict:
    """Evaluate all unbound source hypotheses against retained originals.

    Even a matching native code can be a combined gross/net mixed-income
    measure, a divergent publication vintage or a different industry-sector
    concept. Publisher metadata is not country-year observation coverage.
    """
    declared = {item["id"]: item for item in catalog}
    if len(declared) != len(catalog):
        raise ValueError("duplicate_source_catalog_id")
    stan_codes = set((stan_structure or {}).get(
        "historical_candidates_present", []))
    metadata_ok = (stan_structure or {}).get("status") == (
        "verified_publisher_structure")
    rows = []
    states = Counter()
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
                original = bool(evidence.get(
                    "original_source_hash_verified"))
                observed = _stan_candidate_scopes(
                    stan_readiness, codes) if artifact == "stan" else {}
                has_observation = observed.get(
                    "verified_numeric_measure_in_original_scopes", False)
                if has_observation:
                    state = "original_observed_requires_economic_identity_and_same_release"
                elif original:
                    state = "original_available_measure_or_same_scope_missing"
                else:
                    state = "publisher_original_not_acquired"
                states[state] += 1
                mixed = (role["role"] == "net_operating_surplus"
                         and "B2N_B3_N" in codes)
                reviewed.append({
                    "publisher": candidate["publisher"],
                    "dataset": dataset,
                    "publisher_source_url": candidate["source_url"],
                    "potential_original_measure":
                        candidate["potential_original_measure"],
                    "candidate_native_codes": list(codes),
                    "native_artifact_id": artifact,
                    "source_original_hash_verified": original,
                    "candidate_status": state,
                    "candidate_is_not_exact_role_binding": True,
                    "original_required_checks":
                        candidate["required_original_checks"],
                    "underlying_surplus_contains_mixed_income": mixed,
                    "mixed_income_separation_unverified": mixed,
                    "official_structure_acquired": metadata_ok
                        if artifact == "stan" else False,
                    "publisher_structure_candidates_present": sorted(
                        stan_codes & set(codes)) if artifact == "stan" else [],
                    "official_source_measure_verified_for_role": False,
                    "original_numeric_scope_evidence": observed,
                    "same_scope_dimensions_verified": False,
                    "first_publication_verified": False,
                })
            key = (analysis["id"], role["role"])
            linked = DOCUMENTED_NATIVE_DISCOVERY.get(key)
            linked_original = native_evidence.get(linked, {}) if linked else {}
            related = [{
                "series_id": sid,
                "provider": declared[sid]["provider"],
                "source_key": declared[sid]["source_key"],
                "original_method_mismatch": reason,
                "rejected_as_direct_original_role_binding": True,
            } for sid, reason in RELATED_REGISTERED_REFERENCES.get(key, ())
                if sid in declared]
            rows.append({
                "analysis_id": analysis["id"], "role": role["role"],
                "expected": role["expected"],
                "publisher_candidates": reviewed,
                "reviewed_publisher_candidate_count": len(reviewed),
                "documented_native_artifact": linked,
                "documented_artifact_original_hash_verified":
                    linked_original.get("original_source_hash_verified") is True,
                "related_existing_catalog_inputs_not_equivalent": related,
                "source_discovery_state": (
                    "reviewed_native_source_observed_needs_economic_method_validation"
                    if any(c["original_numeric_scope_evidence"].get(
                        "verified_numeric_measure_in_original_scopes")
                           for c in reviewed) else
                    "reviewed_candidates_require_original_verification"
                    if reviewed else
                    "documented_original_artifact_requires_original_method"
                    if linked else "publisher_source_identity_to_research"),
                "exact_scalar_series_bound": False,
                "manual_original_research_required": not reviewed,
            })
    return {
        "operation": "phase2_unbound_original_source_discovery",
        "unbound_scalar_roles": len(rows),
        "roles_with_reviewed_publisher_candidates": sum(
            bool(x["publisher_candidates"]) for x in rows),
        "roles_requiring_new_publisher_discovery": sum(
            not x["publisher_candidates"] and
            x["documented_native_artifact"] is None for x in rows),
        "roles_with_named_native_original_artifact": sum(
            x["documented_native_artifact"] is not None for x in rows),
        "source_candidate_states": dict(sorted(states.items())),
        "role_candidates": rows,
        "automatically_bound_scalar_series": 0,
        "publishers_with_original_data_not_assumed_correct": True,
        "same_retrieval_measure_availability_not_economic_comparability": True,
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
        "roles_with_named_native_original_artifact":
            report["roles_with_named_native_original_artifact"],
        "source_candidate_states": report["source_candidate_states"],
        "outstanding_roles": [{
            "analysis_id": row["analysis_id"],
            "role": row["role"],
            "publisher_candidate_count": row["reviewed_publisher_candidate_count"],
            "original_native_observed_scope_count": sum(
                item["original_numeric_scope_evidence"].get(
                    "observed_source_scope_count", 0)
                for item in row["publisher_candidates"]),
            "documented_original_artifact": row["documented_native_artifact"],
            "nearby_catalog_not_original": [
                item["series_id"] for item in row[
                    "related_existing_catalog_inputs_not_equivalent"]],
            "next_action": row["source_discovery_state"],
        } for row in report["role_candidates"]],
        "automatically_bound_scalar_series": 0,
        "scientific_analysis_certified": False,
    }
