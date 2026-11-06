"""Deterministic scientific acceptance diagnostics for the original input roles.

Consumes the corpus runtime's validated panel projection, never editable source
certificates. A source binding, a bounded comparison and a complete original
scientific contract have separate gates. No publisher-dimension or observation
first-release verifier exists yet; those gates remain explicitly incomplete.
"""
from __future__ import annotations

from typing import Any

from .source_original_gate import verified_original_rows

PUBLISHER_METADATA_FIELDS = (
    "source_native_unit", "source_native_unit_label", "source_currency", "source_sheet",
    "source_variable", "source_population", "source_price_basis", "source_author_constructed",
    "source_workbook_notes", "source_database_vintage", "source_dataset",
    "source_projection_start_year", "source_metadata_last_modified", "source_publisher_metadata",
)


def _gate(identifier: str, state: str, code: str, series_ids=(), **details) -> dict:
    return {"id": identifier, "state": state, "code": code,
            "series_ids": sorted(series_ids), **details}


def _state(checks: list[dict]) -> str:
    states = {item["state"] for item in checks}
    for state in ("failed", "blocked", "not_checked", "incomplete"):
        if state in states:
            return state
    return "accepted" if states and states.issubset({"passed", "accepted"}) else "not_checked"


def _partial_artifacts(role: dict, evidence: dict) -> list[dict]:
    """Attach verified bounded alternatives without binding an original role.

    Holdings use the existing holdings archive; issuer facts use the existing
    native filing archive. Neither becomes a second scalar ingestion path.
    """
    keys = [key for key in role.get("artifact_ids", []) if key != "icio"]
    return [{"artifact_id": key, "availability": "available_partial", **evidence[key],
             "original_role_satisfied": False,
             "scope": evidence[key].get("scope", "Partial native artifact only; exact population, full history, mapping and publication conditions remain required.")}
            for key in keys if evidence.get(key, {}).get("original_source_hash_verified") is True]


def analysis_acceptance(analysis: dict, registry: dict, counts: dict, panels: list[dict], *,
                        observations_checked: bool, source_proof: dict | None = None,
                        artifact_evidence: dict | None = None,
                        publisher_vintage_proof: dict | None = None,
                        native_role_evidence: dict | None = None) -> dict[str, Any]:
    """Evaluate all original roles using the current, independently checked inputs.

    `panels` must come from comparative_evidence_summary, which reconstructs
    their joins, contracts, hashes and scientific checks. `source_proof` is the
    fresh reconcile_session result from this read, never an imported JSON
    certificate or request parameter. It also covers inputs outside panels.
    Narrower variants can
    prove their native source values, but cannot certify the original analysis.
    """
    requirements = []
    # One shared, contract/hash/history-bound proof gate for scientific
    # acceptance, acquisition planning and full-corpus diagnostics.
    originals = verified_original_rows(source_proof, registry, counts)
    matrix = (artifact_evidence or {}).get("icio", {}) if analysis["id"] == "G06" else {}
    matrix_available = (matrix.get("original_source_hash_verified") is True
                        and type(matrix.get("year")) is int and 1995 <= matrix["year"] <= 2022
                        and type(matrix.get("accounting_passed")) is bool)
    for role in analysis["comparison_contract"]["original_requirements"]:
        ids = role["series_ids"]
        expected = role["expected"]
        checks = [_gate("source_binding", "passed" if ids else "blocked",
                        "source_binding_present" if ids else "source_binding_missing", ids)]
        mismatches = []
        unknown = []
        for sid in ids:
            source = registry.get(sid)
            if source is None:
                unknown.append(sid)
                continue
            if (any(field in expected and expected[field] != source.get(field)
                    for field in ("frequency", "unit"))
                    or "geography" in expected and source.get("geography") not in expected["geography"]):
                mismatches.append(sid)
        checks.append(_gate("native_dimensions",
            "failed" if mismatches else "not_checked" if unknown or not ids else "passed",
            "native_dimensions_mismatch" if mismatches else "source_contract_not_checked" if unknown or not ids
            else "canonical_native_dimensions_match", mismatches or unknown,
            scope="Canonical declarations only; original publisher population, currency and price basis are separate."))
        stored = [sid for sid in ids if (counts.get(sid, {}).get("stored_periods") or 0) > 0]
        missing = set(ids) - set(stored)
        checks.append(_gate("stored_history",
            "not_checked" if not observations_checked else "blocked" if missing or not ids else "passed",
            "source_history_not_checked" if not observations_checked else
            "source_history_missing" if missing or not ids else "stored_histories_present", missing))
        reconciled = set(originals) | {sid for panel in panels if panel.get("source_reconciled") is True
                                       for sid in panel["series_ids"]}
        unproved = set(ids) - reconciled
        checks.append(_gate("original_source_values", "passed" if ids and not unproved else "incomplete",
            "independent_original_values_match" if ids and not unproved else "independent_original_values_unverified",
            unproved, scope="Current-source numeric fidelity only; publication vintage is separate."))
        covering = [p for p in panels if ids and set(ids).issubset(p["series_ids"])
                    and p.get("matched_period_count", 0) > 0]
        complete = [p for p in covering if p.get("requested_coverage_complete") is True]
        checks.append(_gate("matched_periods", "passed" if complete else "incomplete",
            "requested_periods_exactly_matched" if complete else "requested_period_coverage_incomplete",
            ids, variants=[p["variant_id"] for p in covering],
            scope="Exact native-period joins; no fill. Daily calendars require independent evidence."))
        checks.append(_gate("publisher_dimensions", "incomplete", "publisher_dimensions_unverified", ids,
            required_evidence=["population", "currency_and_quote", "price_basis_and_index_base", "common_release"],
            expected=expected,
            original_metadata=[{"series_id": sid, "source_sha256": originals[sid]["source_sha256"],
                **{key: originals[sid][key] for key in PUBLISHER_METADATA_FIELDS if key in originals[sid]}}
                for sid in ids if sid in originals],
            scope="Independently selected original metadata and author estimation notes are disclosed. Complete publisher population/base and common-release eligibility are not inferred from numeric fidelity."))
        # Independently verified original publisher-vintage dates add
        # provenance to the role, without inventing first-release dates for
        # individual observations or assuming synchronized source versions.
        published = (publisher_vintage_proof or {}).get("series", {})
        release_originals = [{
            "series_id": sid,
            "publisher_series": registry[sid]["source_key"],
            "official_first_series_vintage": published[
                registry[sid]["source_key"]]["first_available_alfred_series_vintage"],
            "publisher_original_receipts_verified": True,
            "observation_first_publication_verified": False,
        } for sid in ids if sid in registry and
            registry[sid].get("provider") == "FRED" and
            published.get(registry[sid]["source_key"], {}).get("status") ==
            "verified_original_publisher_vintage"]
        checks.append(_gate(
            "temporal_evidence", "incomplete",
            "observation_release_eligibility_unverified", ids,
            required_mode=role["temporal_requirement"],
            verified_official_series_vintages=release_originals,
            original_publisher_series_vintage_count=len(release_originals),
            observation_first_release_dates_verified=0,
            scope="Official first ALFRED series vintage is not the first published date of each observation. Original release synchronization and eligibility remain separate. Receipt time and current-source observations cannot certify them."))
        artifact = None
        if "icio" in role.get("artifact_ids", []) and matrix_available:
            artifact = {key: matrix.get(key) for key in (
                "status", "year", "edition", "matrix_sha256", "package_sha256", "readme_sha256",
                "source_manifest_sha256", "bundle_digest", "industry_nodes", "accounting_passed")}
            history = matrix.get("historical_coverage", {})
            years = sorted(set(history.get("verified_years", [matrix["year"]])))
            artifact.update(availability="available_partial", full_history_verified=False,
                            first_publication_verified=False, available_years=years,
                            replica_only_years=history.get("replica_only_years", []),
                            common_update_verified=history.get("common_update_verified") is True)
            checks[0] = _gate("source_binding", "incomplete", "original_artifact_partial_history",
                               scope="Hash-verified original matrices are partially available; the full 1995–2022 common-edition corpus remains incomplete.")
            checks[1] = _gate("native_dimensions", "passed", "original_artifact_dimensions_verified",
                scope="Pinned regular-matrix country/industry/final-demand codes match publisher ReadMe; native current USD millions. Historical publisher update is separately unverified.")
            checks[2] = _gate("stored_history", "incomplete", "original_artifact_partial_history",
                               available_years=years,
                               missing_years=sorted(set(range(1995, 2023)) - set(years)))
            checks[3] = _gate("original_source_values", "passed", "original_artifact_hashes_verified",
                scope="Original matrix bytes match the pinned replica ledger. Accounting validity is a separate failed check.")
        partial = _partial_artifacts(role, artifact_evidence or {})
        if not ids and partial:
            checks[0] = _gate("source_binding", "incomplete", "original_artifact_partial_scope",
                scope="Verified structured originals are connected; complete original scope/history remains unverified.")
            checks[2] = _gate("stored_history", "incomplete", "original_artifact_partial_history",
                artifact_ids=[item["artifact_id"] for item in partial])
            if checks[1]["state"] == "not_checked":
                checks[1] = _gate("native_dimensions", "incomplete", "original_artifact_partial_dimensions",
                    scope="Native artifact scope is disclosed; it does not establish the complete original population/mapping.")
        # The 28 operator-originated structured roles can retain exact
        # immutable native files without pretending that declared columns
        # prove the economic method, complete history or first release.
        attached = (native_role_evidence or {}).get("roles", {}).get(
            analysis["id"] + ":" + role["role"])
        if (attached and attached.get("original_source_hash_verified") is True
                and not ids and not role.get("artifact_ids")):
            checks[0] = _gate(
                "source_binding", "incomplete", "exact_native_original_file_attached",
                scope="Archived original source bytes are linked to this approved role; publisher population and method remain unverified.")
            checks[2] = _gate(
                "stored_history", "incomplete", "original_native_partial_history",
                native_records=attached["native_facts"]["record_count"],
                first_record=attached["native_facts"]["earliest_record_date"],
                last_record=attached["native_facts"]["latest_record_date"])
            checks[3] = _gate(
                "original_source_values", "incomplete",
                "original_native_source_file_hash_verified_but_method_unreconciled",
                original_versions=attached["original_versions"])
        state = _state(checks)
        result = {**role, "state": state, "accepted": state == "accepted",
            "sources_checked": observations_checked, "mapped_source_count": len(ids),
            "sources_with_observations": len(stored), "first_publication_verified": False,
            "source_asof_verified": False, "checks": checks,
            "blocking_checks": [item["id"] for item in checks if item["state"] != "passed"]}
        if artifact is not None:
            result["original_artifact_evidence"] = artifact
        if partial:
            result["partial_artifact_evidence"] = partial
        if attached and attached.get("original_source_hash_verified") is True:
            result["attached_native_original"] = {
                "status": attached["status"],
                "original_source_hash_verified": True,
                "native_facts": attached["native_facts"],
                "origin": attached["origin"],
                "first_publication_verified": False,
                "original_economic_scope_verified": False,
            }
        requirements.append(result)
    scientific_failures = [{"variant_id": panel["variant_id"], "panel_sha256": panel.get("panel_sha256"),
                            "check": check}
        for panel in panels for check in panel.get("checks", []) if check.get("passed") is False]
    if matrix_available and matrix.get("accounting_passed") is False:
        scientific_failures.append({"artifact": f"OECD_ICIO_2025_REGULAR_{matrix['year']}",
            "matrix_sha256": matrix.get("matrix_sha256"),
            "check": {"id": "original_matrix_accounting", "passed": False,
                **{key: matrix.get(key) for key in ("row_accounting_failures", "column_accounting_failures",
                    "maximum_row_residual", "maximum_column_residual", "identities")}}})
    # Historical replicas and published TiVA levels/shares retain their own
    # accounting results even when a scalar panel has not been assembled.
    if analysis["id"] == "G06":
        for item in matrix.get("historical_matrices", []):
            if item.get("original_source_hash_verified") is True and item.get("accounting_passed") is False:
                scientific_failures.append({"artifact": f"OECD_ICIO_2025_REGULAR_{item['year']}_REPLICA",
                    "matrix_sha256": item.get("matrix_sha256"),
                    "check": {"id": "original_matrix_accounting", "passed": False,
                        **{key: item.get(key) for key in ("row_accounting_failures", "column_accounting_failures",
                            "maximum_row_residual", "maximum_column_residual", "identities")}}})
        tiva = (artifact_evidence or {}).get("tiva", {})
        if tiva.get("original_source_hash_verified") is True and tiva.get("accounting_passed") is False:
            scientific_failures.append({"artifact": "OECD_TIVA_2025_ORIGINAL_LEVELS_SHARES",
                "source_hashes": tiva.get("source_hashes"),
                "check": {"id": "original_tiva_serialization", "passed": False,
                          "serialization_diagnostic": tiva.get("serialization_diagnostic")}})
    originals = [panel for panel in panels if panel.get("kind") == "original_scope"
                 and panel.get("native_input_scope_matches_original_method") is True
                 and panel.get("requested_coverage_complete") is True
                 and panel.get("state") == "bounded_current_vintage_verified"]
    # Input acquisition can use several native-frequency panels. Requiring
    # every role in one panel made mixed-frequency specifications impossible;
    # converting their values here would prematurely implement Phase 3.
    covered = {role["role"] for role in requirements if role["series_ids"]
        and set(role["series_ids"]).issubset({sid for panel in originals for sid in panel["series_ids"]})}
    uncovered = sorted(role["role"] for role in requirements if role["role"] not in covered)
    comparison = _gate("original_comparison", "passed" if not uncovered else "incomplete",
        "original_native_input_bundle_verified" if not uncovered else "complete_original_comparison_outstanding",
        variants=sorted(p["variant_id"] for p in originals),
        covered_roles=sorted(covered), uncovered_roles=uncovered,
        scope="Original native input bundle only; temporal transformations and methodological alignment belong to Phase 3.")
    checks = [{"state": r["state"]} for r in requirements] + [comparison]
    if scientific_failures:
        checks.append({"state": "failed"})
    state = _state(checks)
    result = {"contract_version": 1, "specification": analysis["comparison_contract"]["specification"],
        "state": state, "accepted": state == "accepted", "required_input_roles": len(requirements),
        "accepted_input_roles": sum(r["accepted"] for r in requirements),
        "requirements": requirements, "comparison": comparison, "scientific_failures": scientific_failures,
        "blocking_roles": [r["role"] for r in requirements if not r["accepted"]],
        "interpretation": "Original analysis acceptance requires every role and original comparison gate. Bounded native alternatives remain separately labelled."}
    fallbacks = analysis.get("fallback_options", [])
    if analysis["id"] == "G06":
        result["source_investigations"] = {key: matrix[key] for key in ("publisher_acquisition", "release_comparison") if key in matrix}
    policy = "docs/PHASE1_FALLBACK_SOURCE_MATRIX.md"
    if fallbacks and all(option.get("reference") == policy for option in fallbacks):
        result["source_resolution"] = {
            "classification": "certified" if result["accepted"] else "conditional",
            "policy_reference": policy,
            "phase2_resolved": result["accepted"],
            "unmet_original_roles": result["blocking_roles"],
            "comparison_outstanding": comparison["state"] != "passed",
            "scientific_failure_count": len(scientific_failures),
            "verified_native_alternative_variants": sorted(p["variant_id"] for p in panels
                if p.get("kind") in {"approved_narrower", "approved_fallback"}
                and p.get("state") == "bounded_current_vintage_verified"),
            "partial_artifact_ids": sorted({artifact["artifact_id"] for role in requirements
                for artifact in role.get("partial_artifact_evidence", [])}),
            "conditions": "Exact source identity, historical coverage, publisher dimensions and temporal eligibility remain required. Named alternatives retain their own populations; missing implementation or evidence is not an unavailable-source finding.",
        }
    return result


def acceptance_summary(analyses: list[dict]) -> dict:
    return {"analysis_count": len(analyses),
        "required_input_roles": sum(row["acceptance"]["required_input_roles"] for row in analyses),
        "accepted_input_roles": sum(row["acceptance"]["accepted_input_roles"] for row in analyses),
        "fully_accepted_analyses": sum(row["acceptance"]["accepted"] for row in analyses),
        "analysis_states": {state: sum(row["acceptance"]["state"] == state for row in analyses)
                            for state in ("accepted", "failed", "blocked", "incomplete", "not_checked")},
        "role_states": {state: sum(role["state"] == state for row in analyses for role in row["requirements"])
                        for state in ("accepted", "failed", "blocked", "incomplete", "not_checked")}}
