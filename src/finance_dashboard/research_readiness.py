"""Evidence-derived input triage and complete/conditional/blocked decisions.

Representations belong to the scientific contract. Availability and readiness
are computed from the current read, never editable certificates in the registry.
"""

INPUT_TYPES = frozenset({"scalar_history", "matrix", "positions", "entity_mapping", "filing_panel",
                        "events", "allocation", "policy", "fx_history", "accounting_panel", "scenario_parameter"})


def role_resolution(role, counts, registry, *, external_coverage=None, artifact_evidence=None):
    ids = role["series_ids"]
    if ids:
        missing = [sid for sid in ids if not counts.get(sid, {}).get("stored_periods")]
        return {"category": 2 if missing else 1,
            "classification": "supported_source_not_acquired" if missing else "existing_source_connected",
            "connected": True, "availability": "missing_or_partial" if missing else "stored",
            "missing_series_ids": missing,
            "reason": "Bindings are exact declared scalar inputs; numeric, dimension and publication gates remain independent."}
    if role.get("derivation"):
        return {"category": 4, "classification": "derived_variable", "connected": False,
            "availability": "prerequisites_unverified", "derivation": role["derivation"],
            "reason": "The conversion needs validated native currency/quote inputs and a dated policy; no values are invented."}
    candidates = []
    for candidate in role.get("source_candidates", []):
        artifact = (artifact_evidence or {}).get(candidate["artifact_id"], {})
        coverage = artifact.get("required_variable_coverage", {}).get(candidate["measure"], {}).get(
            "source_coverage", {}).get(candidate["source_id"], {}).get(candidate["sector"], {})
        if artifact.get("original_source_hash_verified") is True and (coverage.get("country_year_pairs") or 0) > 0:
            candidates.append({**candidate, "coverage": coverage})
    if candidates:
        return {"category": 1, "classification": "existing_source_unconnected", "connected": False,
            "availability": "matched_perimeter_unverified", "exact_role_satisfied": False,
            "source_candidates": candidates,
            "reason": "A genuine retained sector component exists. Select and verify the common NOS/capital/CE/CFC currency, year and accounting perimeter before exact binding."}
    external = role.get("external_sources", [])
    available = [sid for sid in external if (external_coverage or {}).get(sid, {}).get("stored_periods")]
    if available:
        return {"category": 1, "classification": "existing_source_unconnected", "connected": False,
            "availability": "partial_reference_quotes", "external_sources": available,
            "reason": "Existing EUR-base reference FX histories are stored. Required pair, fixing/execution policy, original fidelity and missing currencies still need verification; these do not establish issuer fiscal FX or portfolio execution."}
    if role["input_type"] != "scalar_history":
        artifacts = role.get("partial_artifact_evidence", [])
        original = role.get("original_artifact_evidence")
        return {"category": 3, "classification": "structured_original", "connected": bool(artifacts or original),
            "availability": "available_partial" if artifacts or original else "missing_original_or_declaration",
            "artifact_ids": role.get("artifact_ids", []),
            "reason": role.get("input_requirement", "Native structured records are required; an empty macro-series list is not a missing scalar history.")}
    return {"category": 5, "classification": "targeted_original_discovery", "connected": False,
        "availability": "missing_exact_original", "reason": role["description"],
        "scope": "A related source or supported generic provider does not establish this exact population/measure. No unavailable-source finding is inferred."}


def readiness_decision(analysis, requirements, acceptance, panels):
    missing = [role["role"] for role in requirements
               if any(check["state"] != "passed" for check in role["checks"]
                      if check["id"] in {"source_binding", "stored_history", "original_source_values", "native_dimensions"})]
    failures = acceptance["scientific_failures"]
    original = "complete" if acceptance["accepted"] else "blocked" if missing or failures else "conditional"
    alternatives = [p for p in panels if p.get("kind") in {"approved_narrower", "approved_fallback"}
                    and p.get("state") == "bounded_current_vintage_verified"]
    # A narrower native panel is evidence, not automatically a completed
    # approved fallback. All temporal/population/method conditions stay open.
    approved_alternatives = [p for p in alternatives if analysis.get("fallback_options") or p.get("kind") == "approved_fallback"]
    artifacts = {item["artifact_id"]: item for role in requirements for item in role.get("partial_artifact_evidence", [])}
    structured = sorted({key for option in analysis.get("fallback_options", [])
        for key in option.get("artifact_ids", []) if artifacts.get(key, {}).get("bounded_data_verified") is True})
    fallback_defined = analysis.get("fallback_options") or any(p.get("kind") == "approved_fallback" for p in analysis["comparison_contract"]["variants"])
    fallback = "conditional" if approved_alternatives or structured else "blocked" if fallback_defined else "not_applicable"
    decision = "complete" if original == "complete" else "conditional" if original == "conditional" or fallback == "conditional" else "blocked"
    reasons = []
    if missing:
        reasons.append({"code": "exact_original_inputs_missing_or_partial", "roles": missing})
    if failures:
        reasons.append({"code": "original_scientific_failure", "count": len(failures)})
    if not acceptance["accepted"]:
        reasons.append({"code": "publisher_and_release_eligibility_incomplete",
                        "detail": "Complete population/price-basis/common-release and observation first-publication eligibility remain unverified."})
    return {"id": analysis["id"], "decision": decision,
        "original": {"decision": original, "scalar_bound_roles": sum(bool(r["series_ids"]) for r in requirements),
                     "required_roles": len(requirements), "missing_or_partial_roles": missing,
                     "missing_scalar_roles": [r["role"] for r in requirements if r["role"] in missing and r["input_type"] == "scalar_history"],
                     "missing_structured_roles": [r["role"] for r in requirements if r["role"] in missing and r["input_type"] != "scalar_history"],
                     "accepted": acceptance["accepted"]},
        "fallback": {"decision": fallback, "policy_reference": "docs/PHASE1_FALLBACK_SOURCE_MATRIX.md" if analysis.get("fallback_options") else None,
                     "verified_native_variants": [p["variant_id"] for p in approved_alternatives],
                     "verified_structured_alternatives": structured,
                     "limitations": "Native alternative coverage is bounded; no alternative silently satisfies the original method or first-release contract."},
        "reasons": reasons, "production_integration_ready": acceptance["accepted"]}


def resolution_summary(analyses):
    roles = [r for a in analyses for r in a["requirements"]]
    scalar = [r for r in roles if r["input_type"] == "scalar_history"]
    remaining = [r for r in roles if not r["series_ids"]]
    return {"role_count": len(roles), "scalar_roles": len(scalar), "structured_roles": len(roles)-len(scalar),
        "scalar_bound_roles": sum(bool(r["series_ids"]) for r in scalar),
        "unbound_scalar_roles": sum(not r["series_ids"] for r in scalar),
        "roles_without_scalar_bindings": len(remaining),
        "remaining_role_categories": {str(category): sum(r["resolution"]["category"] == category for r in remaining) for category in range(1, 7)},
        "unavailability_policy": "Category 6 requires verified exact-source unavailability and a satisfied approved fallback. Neither missing implementation nor one blocked route establishes it; no such finding is currently verified.",
        "interpretation": "Structured originals, policy declarations and derived conversions are not missing scalar series. Representation or partial availability never certifies a role."}
