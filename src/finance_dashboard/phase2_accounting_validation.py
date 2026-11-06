"""Full Phase 2 native accounting and dimensional readiness inventory.

No cross-vendor economic quantities are pooled unless original publisher
units, populations, definitions, period grids and release vintages have
already passed independent checks. Native matrix/profit/holdings and STAN
source audits retain their own exact accounting evidence; this layer only
projects and joins *diagnostics*, never economic observations.
"""
from __future__ import annotations

from collections import Counter


def native_accounting_workplan(document: dict, runtime_report: dict,
                               artifacts: dict, stan: dict) -> dict:
    analyses = {item["id"]: item for item in runtime_report["analyses"]}
    if len(analyses) != len(document["analyses"]):
        raise ValueError("native_accounting_analysis_membership_inconsistent")
    checks = {}
    for kind, item in sorted(artifacts.items()):
        entry = {
            "artifact": kind, "status": item.get("status", "not_checked"),
            "original_source_hash_verified": item.get(
                "original_source_hash_verified") is True,
            "native_accounting_result": (
                "passed_with_limits" if item.get("accounting_passed") is True
                else "failed" if item.get("accounting_passed") is False
                else "not_checked"),
            "first_publication_verified": item.get(
                "first_publication_verified") is True,
            "full_original_history_verified": item.get(
                "full_history_verified") is True,
            "publisher_population_perimeter_verified": False,
            "same_release_cross_publisher_comparison_verified": False,
        }
        if kind == "icio":
            entry.update({
                "year": item.get("year"),
                "matrix_source_sha256": item.get("matrix_sha256"),
                "historical_coverage": item.get("historical_coverage", {}),
            })
        if kind == "tiva":
            entry.update({
                "selected_country_history_verified": item.get(
                    "selected_country_history_verified") is True,
                "common_release_verified": item.get(
                    "common_release_verified") is True,
                "serialization_diagnostic": item.get("serialization_diagnostic"),
            })
        if kind in {"sec_holdings", "ucits_holdings"}:
            entry.update({
                "reported_position_sources": item.get("source_count", 0),
                "native_accounting_failed_sources": (
                    item.get("fund_accounting_failed_sources") if
                    kind == "sec_holdings" else sum(
                        x.get("nav_accounting_identity_passed") is False
                        for x in item.get("sources", []))),
            })
        checks[kind] = entry
    original_roles = []
    gate_counts = Counter()
    failed = []
    for original in document["analyses"]:
        report = analyses.get(original["id"])
        if report is None:
            raise ValueError("native_accounting_analysis_id_missing")
        expected_roles = {
            r["role"]: r for r in original[
                "comparison_contract"]["original_requirements"]}
        if set(expected_roles) != {
                r["role"] for r in report["requirements"]}:
            raise ValueError("native_accounting_role_membership_changed")
        for role in report["requirements"]:
            gates = {gate["id"]: gate for gate in role["checks"]}
            if len(gates) != len(role["checks"]):
                raise ValueError("native_accounting_duplicate_gate")
            missing = [gate["id"] for gate in gates.values()
                       if gate["state"] != "passed"]
            gate_counts.update(missing)
            linked = role.get("artifact_ids", [])
            originals = {
                artifact: checks.get(artifact, {
                    "status": "no_qualified_original_source_reader",
                    "native_accounting_result": "not_checked",
                    "original_source_hash_verified": False,
                }) for artifact in linked}
            entry = {
                "analysis_id": original["id"], "role": role["role"],
                "input_type": role["input_type"],
                "original_artifact_ids": linked,
                "original_source_gate": gates.get(
                    "original_source_values", {}).get("state"),
                "native_dimension_gate": gates.get(
                    "native_dimensions", {}).get("state"),
                "publisher_dimension_gate": gates.get(
                    "publisher_dimensions", {}).get("state"),
                "matched_period_gate": gates.get(
                    "matched_periods", {}).get("state"),
                "first_release_gate": gates.get(
                    "temporal_evidence", {}).get("state"),
                "missing_scientific_gates": missing,
                "native_artifact_accounting": {
                    key: {
                        "hash_verified": value.get(
                            "original_source_hash_verified") is True,
                        "accounting": value["native_accounting_result"],
                        "publication": value.get(
                            "first_publication_verified", False),
                    } for key, value in originals.items()
                },
                "scientific_original_role_accepted": role["accepted"],
            }
            original_roles.append(entry)
            if any(item["native_accounting_result"] == "failed"
                   for item in originals.values()):
                failed.append({
                    "analysis_id": original["id"], "role": role["role"],
                    "reason": "original_native_accounting_failed",
                })
    stan_status = Counter(
        row["status"] for row in stan.get("country_readiness", []))
    bridge = [{
        "country": row["country"],
        "same_scope_identity_available": row.get(
            "same_scope_identity_observations", False),
        "gross_net_bridge_matched_industry_years_in_one_scope":
            row.get("gross_net_bridge_max_matched_in_single_scope", 0),
        "gross_net_bridge_residuals_outside_printed_precision":
            row.get("gross_net_bridge_residuals_outside_precision", False),
        "source_retrieval_disagreement": row.get(
            "retrieval_scope_disagreements", False),
        "native_status_flags_uninterpreted": row.get(
            "non_A_identity_flags_present", False),
        "country_status": row["status"],
    } for row in stan.get("country_readiness", [])]
    return {
        "phase": "phase2", "operation": "native_source_accounting_and_dimensions",
        "analyses_checked": len(analyses),
        "original_roles_checked": len(original_roles),
        "gate_failures": dict(sorted(gate_counts.items())),
        "native_source_results": checks,
        "native_accounting_failed_role_bindings": failed,
        "stan": {
            "countries_checked": len(bridge),
            "status_counts": dict(sorted(stan_status.items())),
            "gross_net_bridge_matched_countries": sum(
                x["gross_net_bridge_matched_industry_years_in_one_scope"] > 0
                for x in bridge),
            "gross_net_bridge_countries_with_residuals": [
                x["country"] for x in bridge
                if x["gross_net_bridge_residuals_outside_printed_precision"]],
            "official_measure_metadata_status":
                stan.get("publisher_measure_metadata"),
            "country_checks": bridge,
        },
        "original_roles": original_roles,
        "cross_publisher_quantities_joined": False,
        "source_originals_modified": False,
        "historical_release_alignment_certified": False,
        "scientific_analysis_certified": False,
    }


def compact_accounting_workplan(result: dict) -> dict:
    return {
        key: val for key, val in result.items()
        if key not in {"original_roles", "native_source_results"}
    } | {
        "native_source_results": [{
            "artifact": key,
            "original_source_hash_verified": item[
                "original_source_hash_verified"],
            "native_accounting_result": item["native_accounting_result"],
            "full_original_history_verified": item[
                "full_original_history_verified"],
        } for key, item in sorted(result["native_source_results"].items())],
        "original_roles_with_missing_dimensions": sum(
            row["native_dimension_gate"] != "passed" or
            row["publisher_dimension_gate"] != "passed"
            for row in result["original_roles"]),
        "original_roles_with_missing_temporal_eligibility": sum(
            row["first_release_gate"] != "passed"
            for row in result["original_roles"]),
        "stan": {
            key: val for key, val in result["stan"].items()
            if key != "country_checks"
        },
    }
