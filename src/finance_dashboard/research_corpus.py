"""Phase 2: read-only research-source inventory and conservative evidence status.

A registered series, an implemented adapter, and a verified economic comparison
are three different claims. Never treat an existing code reference as evidence
that the source measurements, historical vintages, or complete analysis exist.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from .catalog import DEFAULT_ROOT
from .comparative_corpus import CHECK_IDS
from .research_readiness import ARTIFACT_IDS, INPUT_TYPES, role_resolution, readiness_decision, resolution_summary

FAMILIES = {"C": 6, "M": 3, "F": 7, "V": 4, "L": 7, "G": 5, "P": 7}
# Owner-approved baseline (35 + P06/P07 from November 6) and the
# November 14 research expansion (L08/C07). Keep exact membership strict:
# family totals alone do not catch a wrong replacement.
APPROVED_ANALYSIS_IDS = frozenset((
    "C01", "C02", "C03", "C05", "C06", "C07",
    "M01", "M02", "M04",
    "F01", "F02", "F03", "F04", "F05", "F06", "F07",
    "V01", "V02", "V03", "V05",
    "L01", "L02", "L03", "L04", "L05", "L07", "L08",
    "G01", "G02", "G03", "G05", "G06",
    "P01", "P02", "P03", "P04", "P05", "P06", "P07",
))  # P06/P07: EUR investor decision layer, Phase 1 revision 2026-11-06
SUPPORTING_METHODS = {"C04", "M03", "V04", "L06", "G04"}
TEMPORAL_REQUIREMENTS = {"current_source_snapshot", "source_asof", "first_publication", "latest_revised"}
# Owner parameters and owner-curated sourced registers (e.g. shock events).
USER_SUPPLY_INPUT_TYPES = {"allocation", "policy", "scenario_parameter", "positions", "entity_mapping", "events"}
# Only reviewed catalogue metadata and safe census fields enter the API.
# Ingestion request URLs and upstream error text may contain credentials.
SOURCE_CONTRACT_FIELDS = (
    "name", "provider", "source_key", "source_url", "geography", "frequency",
    "unit", "measurement", "revision_policy", "rights", "notes", "status",
)
OBSERVATION_COVERAGE_FIELDS = (
    "frequency", "state", "collection_enabled", "mapped", "stored_periods",
    "oldest_source_date", "latest_source_date", "days_since_latest_observation",
    "stored_versions", "additional_revisions", "unobserved_internal_periods",
    "regular_cadence_assumed", "published_through", "published_release",
    "published_release_date", "complete_for_pinned_release", "last_attempt_utc",
    "last_attempt_state", "last_success_utc", "last_failure_code",
)


def load_research_corpus(root: Path = DEFAULT_ROOT) -> dict[str, Any]:
    source = Path(root) / "definitions" / "phase2_research_corpus.json"
    with source.open(encoding="utf-8") as handle:
        return json.load(handle)


def analysis_series_ids(analysis: dict) -> list[str]:
    """Canonical input union, retaining explicitly separate contextual sources.

    A role's cited fallback is an input too: it must be acquired, reconciled
    and gated like any other source before it can resolve the role.
    """
    contract = analysis["comparison_contract"]
    fallbacks = {
        sid for role in contract["original_requirements"]
        if isinstance(role.get("verified_unavailability"), dict)
        and isinstance(role["verified_unavailability"].get("fallback"), dict)
        for sid in role["verified_unavailability"]["fallback"].get("series_ids", [])}
    return sorted(set(analysis.get("context_series_ids", [])) | fallbacks | {
        sid for binding in contract["original_requirements"] + contract["variants"]
        for sid in binding["series_ids"]})


def _validate_phase1_revision(ident: str, row: dict) -> list[str]:
    """Phase 1 revision (owner decision 2026-11-06): evidence tier, decision
    informed, scope and descoped roles are explicit for every analysis."""
    from .research_acceptance import EVIDENCE_TIERS, PHASE2_SCOPES
    errors = []
    tier = row.get("evidence_tier")
    if tier not in EVIDENCE_TIERS:
        errors.append(f"{ident}: evidence_tier must be descriptive or predictive")
    if not isinstance(row.get("decision_informed"), str) or not row["decision_informed"].strip():
        errors.append(f"{ident}: decision_informed must name the decision the analysis supports")
    scope = row.get("phase2_scope")
    if scope not in PHASE2_SCOPES:
        errors.append(f"{ident}: phase2_scope must be active or deferred_extension")
    if scope == "deferred_extension" and not str(row.get("deferral_reason", "")).strip():
        errors.append(f"{ident}: deferred analyses must state a deferral_reason")
    descoped = row.get("descoped_roles", [])
    if (not isinstance(descoped, list) or any(
            not isinstance(item, dict) or set(item) != {"role", "reason"}
            or not all(isinstance(item[k], str) and item[k].strip() for k in item) for item in descoped)):
        errors.append(f"{ident}: descoped_roles must list role and reason")
    contract = row.get("comparison_contract") or {}
    roles = [r for r in contract.get("original_requirements") or [] if isinstance(r, dict)]
    active = {r.get("role") for r in roles}
    if isinstance(descoped, list) and any(isinstance(item, dict) and item.get("role") in active for item in descoped):
        errors.append(f"{ident}: a descoped role cannot remain in original_requirements")
    for role in roles:
        if "supply" in role and (role["supply"] != "user" or role.get("series_ids")
                                 or role.get("input_type") not in USER_SUPPLY_INPUT_TYPES):
            errors.append(f"{ident}: only unbound owner parameters may be supply=user")
        if role.get("supply") == "user" or role.get("input_type") != "scalar_history":
            continue
        expected = "first_publication" if tier == "predictive" else "latest_revised"
        if role.get("temporal_requirement") not in (expected, "source_asof"):
            errors.append(f"{ident}: {tier} scalar roles require {expected} temporal evidence")
    return errors


def _validate_comparison_contract(ident: str, contract: Any, registry: dict) -> list[str]:
    errors = []
    if not isinstance(contract, dict) or contract.get("version") != 1:
        return [f"{ident}: comparison requirement contract version 1 required"]
    if not str(contract.get("specification", "")).startswith("docs/PHASE1_ANALYSIS_SPECIFICATIONS.md#"):
        errors.append(f"{ident}: approved scientific specification anchor required")
    requirements = contract.get("original_requirements")
    variants = contract.get("variants")
    if not isinstance(requirements, list) or not requirements or not isinstance(variants, list):
        return errors + [f"{ident}: original requirements and variants must be arrays"]
    roles = set()
    for requirement in requirements:
        if not isinstance(requirement, dict):
            errors.append(f"{ident}: malformed original requirement")
            continue
        role = requirement.get("role")
        if not isinstance(role, str) or not role.strip() or role in roles:
            errors.append(f"{ident}: unique named requirement roles required")
        else:
            roles.add(role)
        if not str(requirement.get("description", "")).strip():
            errors.append(f"{ident}: requirement source definition required")
        if requirement.get("requirement_class", "required") not in ("required", "supplemental"):
            errors.append(f"{ident}: requirement_class must be required or supplemental")
        if requirement.get("requirement_class") == "supplemental" and (
                requirement.get("input_type") != "scalar_history"
                or requirement.get("supply") == "user"):
            errors.append(f"{ident}: only publisher scalar histories may be supplemental")
        if requirement.get("input_type") not in INPUT_TYPES:
            errors.append(f"{ident}: explicit input representation required")
        artifacts = requirement.get("artifact_ids")
        if (not isinstance(artifacts, list) or len(artifacts) != len(set(artifacts))
                or any(key not in ARTIFACT_IDS for key in artifacts)):
            errors.append(f"{ident}: unknown/duplicate original artifact binding")
        if requirement.get("input_type") == "scalar_history" and artifacts:
            errors.append(f"{ident}: scalar role cannot substitute an artifact for original scalar values")
        for candidate in requirement.get("source_candidates", []):
            if (candidate.get("artifact_id") not in ARTIFACT_IDS or candidate.get("source_id") not in registry
                    or not all(isinstance(candidate.get(key), str) and candidate[key].strip() for key in ("measure", "sector", "condition"))):
                errors.append(f"{ident}: invalid native source candidate reference")
        if "verified_unavailability" in requirement:
            from .research_acceptance import valid_unavailability
            unavailability = requirement["verified_unavailability"]
            if not valid_unavailability(unavailability):
                errors.append(f"{ident}: invalid verified_unavailability declaration")
            elif any(sid not in registry for sid in unavailability["fallback"].get("series_ids", [])):
                errors.append(f"{ident}: verified_unavailability fallback references unknown series")
        if "holdings_contract" in requirement:
            from .holdings_acceptance import valid_holdings_contract
            contract = requirement["holdings_contract"]
            if (not valid_holdings_contract(contract) or requirement.get("series_ids")
                    or any(item["artifact_id"] not in requirement.get("artifact_ids", [])
                           for item in contract["funds"])):
                errors.append(f"{ident}: invalid holdings contract")
        publisher_candidates = requirement.get("publisher_candidates", [])
        if (not isinstance(publisher_candidates, list)
                or (publisher_candidates and
                    (requirement.get("input_type") != "scalar_history" or requirement.get("series_ids")))):
            errors.append(f"{ident}: unverified publisher candidates cannot replace original bindings")
        elif any(not isinstance(candidate, dict)
                 or set(candidate) != {"publisher", "dataset", "source_url",
                                       "potential_original_measure", "status", "required_original_checks"}
                 or candidate.get("status") != "unverified_candidate"
                 or not all(isinstance(candidate.get(key), str) and candidate[key].strip()
                     for key in ("publisher", "dataset", "source_url",
                                 "potential_original_measure", "required_original_checks"))
                 or not candidate.get("source_url", "").startswith("https://")
                 for candidate in publisher_candidates):
            errors.append(f"{ident}: unverified publisher candidate schema invalid")
        ids = requirement.get("series_ids")
        if not isinstance(ids, list) or any(not isinstance(sid, str) for sid in ids):
            errors.append(f"{ident}: requirement source bindings must be an array")
            continue
        if len(ids) != len(set(ids)) or any(sid not in registry for sid in ids):
            errors.append(f"{ident}: unknown/duplicate requirement source")
        if "requirement_status" in requirement:
            errors.append(f"{ident}: derived requirement status must not be stored")
        if requirement.get("temporal_requirement") not in TEMPORAL_REQUIREMENTS:
            errors.append(f"{ident}: explicit temporal evidence requirement required")
        expected = requirement.get("expected")
        if not isinstance(expected, dict):
            errors.append(f"{ident}: expected source dimensions required")
            continue
        for sid in ids:
            if sid not in registry:
                continue
            for field in ("frequency", "unit"):
                if expected.get(field) != registry[sid].get(field):
                    errors.append(f"{ident}: requirement native {field} mismatch for {sid}")
            if not isinstance(expected.get("geography"), list) or registry[sid].get("geography") not in expected["geography"]:
                errors.append(f"{ident}: requirement native geography mismatch for {sid}")
        if any(key in requirement for key in ("evidence_status", "coverage", "accepted")):
            errors.append(f"{ident}: editable evidence certificate forbidden in requirement")
    seen = set()
    for variant in variants:
        if not isinstance(variant, dict):
            errors.append(f"{ident}: malformed comparison variant")
            continue
        variant_id = variant.get("id")
        if not isinstance(variant_id, str) or not variant_id.strip() or variant_id in seen:
            errors.append(f"{ident}: unique comparison variant ID required")
        else:
            seen.add(variant_id)
        if any(not isinstance(variant.get(field), str) or not variant[field].strip() for field in ("label", "scope")):
            errors.append(f"{ident}: named comparison scope required")
        if variant.get("kind") not in {"original_scope", "approved_narrower", "approved_fallback"}:
            errors.append(f"{ident}: approved variant kind required")
        if (variant.get("frequency") not in {"D", "W", "M", "Q", "A"}
                or variant.get("end") != "latest_common"
                or variant.get("join") != "exact_period_intersection"
                or variant.get("missingness") != "no_fill"
                or variant.get("temporal_mode") != "current_source_snapshot"):
            errors.append(f"{ident}: explicit native-frequency no-fill snapshot join required")
        try:
            date.fromisoformat(variant["start"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"{ident}: valid requested comparison start date required")
        ids = variant.get("series_ids")
        if not isinstance(ids, list) or not ids or any(not isinstance(sid, str) for sid in ids):
            errors.append(f"{ident}: comparison source bindings required")
            ids = []
        if len(ids) != len(set(ids)) or any(sid not in registry for sid in ids):
            errors.append(f"{ident}: unknown/duplicate comparison source")
        for sid in ids:
            if sid in registry and registry[sid].get("frequency") != variant.get("frequency"):
                errors.append(f"{ident}: comparison native frequency mismatch for {sid}")
        checks = variant.get("checks")
        if not isinstance(checks, list) or any(not isinstance(check, str) or check not in CHECK_IDS for check in checks):
            errors.append(f"{ident}: unknown comparison consistency check")
        if not isinstance(variant.get("limitations"), list) or not variant["limitations"] or any(not isinstance(limit, str) or not limit.strip() for limit in variant["limitations"]):
            errors.append(f"{ident}: comparison limitations required")
        if type(variant.get("satisfies_original_method")) is not bool:
            errors.append(f"{ident}: native input scope declaration must be boolean")
        if variant.get("satisfies_original_method") is True and variant.get("kind") != "original_scope":
            errors.append(f"{ident}: alternate scope cannot satisfy original native input scope")
        if any(key in variant for key in ("evidence_status", "coverage", "fully_validated", "full_analysis_accepted")):
            errors.append(f"{ident}: editable evidence certificate forbidden in variant")
    return errors


def validate_research_corpus(
    document: dict[str, Any],
    known_series: list[dict[str, Any]],
) -> list[str]:
    """Full-membership and proof contract: no fabricated validated state."""
    errors: list[str] = []
    if document.get("schema_version") != 4:
        errors.append("corpus: unsupported schema_version")
    if document.get("approved_phase1_version") != "2026-11-03":
        errors.append("corpus: wrong approved Phase 1 contract version")
    sources = document.get("original_sources")
    analyses = document.get("analyses")
    if not isinstance(sources, list) or not isinstance(analyses, list):
        return errors + ["corpus: sources and analyses must be arrays"]

    source_ids: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            errors.append("corpus: malformed original source")
            continue
        identifier = source.get("id")
        if not isinstance(identifier, str) or not identifier.startswith("S"):
            errors.append("corpus: invalid source identifier")
            continue
        if identifier in source_ids:
            errors.append(f"{identifier}: duplicate original source")
        source_ids.add(identifier)
        if not str(source.get("url", "")).startswith("https://"):
            errors.append(f"{identifier}: source URL must be HTTPS")
        if not str(source.get("label", "")).strip():
            errors.append(f"{identifier}: missing source identification")
    # The original S01-S49 charter is immutable, but registered
    # publisher additions may extend the sequential source inventory.
    expected = {f"S{i:02d}" for i in range(1, max(49, len(source_ids)) + 1)}
    if source_ids != expected:
        errors.append("corpus: original source IDs must form a complete S01+ sequence")

    registry = {item["id"]: item for item in known_series if isinstance(item, dict)
                and isinstance(item.get("id"), str)}
    registered = set(registry)
    seen: set[str] = set()
    counts = {prefix: 0 for prefix in FAMILIES}
    for row in analyses:
        if not isinstance(row, dict):
            errors.append("corpus: malformed analysis")
            continue
        ident = row.get("id")
        if not isinstance(ident, str) or len(ident) != 3:
            errors.append("corpus: invalid analysis identifier")
            continue
        if ident in seen:
            errors.append(f"{ident}: duplicate analysis")
        seen.add(ident)
        if ident in SUPPORTING_METHODS:
            errors.append(f"{ident}: supporting method cannot masquerade as first-class")
        if ident[:1] not in counts:
            errors.append(f"{ident}: unknown domain")
        else:
            counts[ident[0]] += 1
        if not str(row.get("title", "")).strip():
            errors.append(f"{ident}: question title required")
        refs = row.get("primary_method_sources")
        if not isinstance(refs, list) or not refs:
            errors.append(f"{ident}: primary methodological source required")
        elif len(refs) != len(set(refs)) or any(x not in source_ids for x in refs):
            errors.append(f"{ident}: duplicate or unknown source reference")
        if any(field in row for field in ("existing_series_references", "existing_adapter_references")):
            errors.append(f"{ident}: legacy source inventory forbidden; canonical bindings required")
        artifact_context = row.get("context_artifact_ids")
        if not isinstance(artifact_context, list) or any(key not in ARTIFACT_IDS for key in artifact_context):
            errors.append(f"{ident}: explicit known contextual artifact bindings required")
        context = row.get("context_series_ids")
        if not isinstance(context, list) or any(not isinstance(sid, str) for sid in context):
            errors.append(f"{ident}: context source bindings must be an array of IDs")
        else:
            if len(context) != len(set(context)) or any(sid not in registered for sid in context):
                errors.append(f"{ident}: unknown/duplicate context source")
            contract = row.get("comparison_contract", {})
            bound = {sid for field in ("original_requirements", "variants")
                     for binding in (contract.get(field) or []) if isinstance(binding, dict)
                     and isinstance(binding.get("series_ids"), list)
                     for sid in binding.get("series_ids", []) if isinstance(sid, str)} if isinstance(contract, dict) else set()
            if set(context) & bound:
                errors.append(f"{ident}: context source duplicates a canonical role or variant binding")
        if not str(row.get("outstanding_evidence", "")).strip():
            errors.append(f"{ident}: evidence gap must be documented")
        if any(field in row for field in ("evidence_status", "coverage", "comparative_corpus_validated")):
            errors.append(f"{ident}: editable evidence certificate forbidden; runtime evidence required")
        errors.extend(_validate_comparison_contract(ident, row.get("comparison_contract"), registry))
        errors.extend(_validate_phase1_revision(ident, row))
        fallbacks = row.get("fallback_options")
        if not isinstance(fallbacks, list):
            errors.append(f"{ident}: fallback_options must be an array")
        else:
            for fallback in fallbacks:
                if not isinstance(fallback, dict) or not all(
                    str(fallback.get(field, "")).strip()
                    for field in ("tier", "label", "valid_concept", "reference", "frequency")
                ):
                    errors.append(f"{ident}: fallback must disclose its actual economic concept")
                elif fallback["reference"] != "docs/PHASE1_FALLBACK_SOURCE_MATRIX.md":
                    errors.append(f"{ident}: fallback must refer to approved method contract")
                if fallback.get("data_verified") is True:
                    errors.append(f"{ident}: fallback verification cannot be inferred from old code")
    if (len(analyses) != len(APPROVED_ANALYSIS_IDS)
            or seen != APPROVED_ANALYSIS_IDS
            or any(counts[p] != n for p, n in FAMILIES.items())):
        missing = sorted(APPROVED_ANALYSIS_IDS - seen)
        unexpected = sorted(seen - APPROVED_ANALYSIS_IDS)
        errors.append(
            f"corpus: expected all {len(APPROVED_ANALYSIS_IDS)} approved scientific question IDs by domain"
            f" (missing={missing}, unexpected={unexpected})"
        )
    if not {"G01", "G03", "P01", "P02"}.issubset(seen):
        errors.append("corpus: four hard historical-data target contracts missing")
    for row in analyses:
        if isinstance(row, dict) and row.get("id") in {"G01", "G03", "P01", "P02"}:
            if not row.get("fallback_options"):
                errors.append(f"{row['id']}: approved fallback hierarchy missing")
    return errors


def research_corpus_report(
    document: dict[str, Any],
    observations: dict[str, Any] | None = None,
    *,
    vintages: dict[str, Any] | None = None,
    series_registry: list[dict[str, Any]] | None = None,
    comparative_evidence: dict[str, Any] | None = None,
    source_reconciliation: dict[str, Any] | None = None,
    artifact_evidence: dict[str, Any] | None = None,
    publisher_vintage_proof: dict[str, Any] | None = None,
    native_role_evidence: dict[str, Any] | None = None,
    alfred_revision_proof: dict[str, Any] | None = None,
    unbound_source_evidence: dict[str, Any] | None = None,
    owner_supply: dict[tuple[str, str], dict] | None = None,
) -> dict[str, Any]:
    """Join runtime evidence; declarations and source counts cannot grant approval."""
    from .comparative_corpus import comparative_evidence_summary
    from .research_acceptance import analysis_acceptance, acceptance_summary
    comparative = comparative_evidence_summary(comparative_evidence, series_registry or [], document)
    counts = {item["id"]: item for item in (observations or {}).get("items", [])
              if item.get("family") == "macro"}
    # ALFRED true source publication-as-of data is keyed by FRED series ID,
    # not by our app's observation-series ID or ingestion timestamp.
    original_by_local_id = {
        item["id"]: item for item in (series_registry or [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    vintage_by_id = {
        item["series_id"]: item for item in (vintages or {}).get("series", [])
        if isinstance(item, dict) and isinstance(item.get("series_id"), str)
    }
    method_source_by_id = {item["id"]: item for item in document["original_sources"]}
    verified_publisher_releases = (
        (publisher_vintage_proof or {}).get("series") or {})
    revision_originals = (
        (alfred_revision_proof or {}).get("series") or {})
    analyses: list[dict[str, Any]] = []
    for row in document["analyses"]:
        links = []
        for series_id in analysis_series_ids(row):
            source = counts.get(series_id)
            original = original_by_local_id.get(series_id, {})
            original_fred_id = (original.get("source_key")
                                if original.get("provider") == "FRED" else None)
            source_vintages = vintage_by_id.get(original_fred_id) if original_fred_id else None
            publication = {
                "original_fred_id": original_fred_id,
                "checked": source_vintages is not None,
                "asof_snapshot_files": source_vintages.get("count", 0)
                    if source_vintages is not None else None,
                "populated_asof_snapshots": source_vintages.get("populated_vintage_count", 0)
                    if source_vintages is not None else None,
                "first_populated_asof": source_vintages.get("first_populated_asof")
                    if source_vintages else None,
                "last_populated_asof": source_vintages.get("last_populated_asof")
                    if source_vintages else None,
                "source_publication_vintage_verified": bool(
                    source_vintages and source_vintages.get("populated_vintage_count", 0) > 0
                ),
                # A populated ALFRED snapshot proves values known on its as-of
                # date, not the earliest public release of each observation.
                "first_publication_vintage_verified": False,
                "official_revision_windows_verified": (
                    revision_originals.get(
                        original_fred_id, {}).get("verified_windows", 0)),
                "official_revision_rows_verified": (
                    revision_originals.get(original_fred_id, {}).get(
                        "verified_observation_revision_rows", 0)),
                "revision_original_archives_invalid_or_conflicting": (
                    revision_originals.get(original_fred_id, {}).get(
                        "invalid_or_conflicting_windows", 0)),
                "observation_specific_first_publisher_release_verified": False,
                "original_publisher_first_series_vintage": (
                    verified_publisher_releases.get(
                        original_fred_id, {}).get(
                            "first_available_alfred_series_vintage")
                    if verified_publisher_releases.get(
                        original_fred_id, {}).get("status") ==
                    "verified_original_publisher_vintage" else None),
                "publisher_vintage_original_status": (
                    verified_publisher_releases.get(
                        original_fred_id, {}).get("status", "not_checked")),
                "publication_semantics": (
                    "Stored ALFRED information available on selected as-of dates; "
                    "first populated as-of is not the first publication date."
                ),
            } if original_fred_id else None
            links.append({
                "series_id": series_id,
                "source_contract": {
                    field: original.get(field) for field in SOURCE_CONTRACT_FIELDS
                } if original else None,
                "observation_coverage": {
                    field: source.get(field) for field in OBSERVATION_COVERAGE_FIELDS
                } if source is not None else None,
                "original_source_asof": publication,
                "stored_periods": source.get("stored_periods", 0) if source else None,
                "oldest_source_date": source.get("oldest_source_date") if source else None,
                "latest_source_date": source.get("latest_source_date") if source else None,
                "source_state": source.get("state") if source else "not_checked",
                "stored_versions": source.get("stored_versions") if source else None,
            })
        observed = sum((p["stored_periods"] or 0) > 0 for p in links)
        panel_evidence = [panel for panel in comparative["panels"] if panel["analysis_id"] == row["id"]]
        bounded_verified = any(panel["state"] == "bounded_current_vintage_verified" for panel in panel_evidence)
        acceptance = analysis_acceptance(row, original_by_local_id, counts, panel_evidence,
            observations_checked=observations is not None, source_proof=source_reconciliation,
            artifact_evidence=artifact_evidence,
            publisher_vintage_proof=publisher_vintage_proof,
            native_role_evidence=native_role_evidence,
            alfred_revision_proof=alfred_revision_proof,
            unbound_source_evidence=unbound_source_evidence,
            owner_supply=owner_supply)
        external_coverage = {item["id"]: item for item in (observations or {}).get("items", []) if item.get("family") == "fx"}
        requirements = []
        for role in acceptance.pop("requirements"):
            role["resolution"] = role_resolution(role, counts, original_by_local_id, external_coverage=external_coverage,
                                                  artifact_evidence=artifact_evidence)
            role["requirement_status"] = ("mapped" if role["series_ids"] else "missing_scalar" if role["input_type"] == "scalar_history"
                else "structured_partial" if role["resolution"]["availability"] == "available_partial" else "structured_required")
            requirements.append(role)
        readiness = readiness_decision(row, requirements, acceptance, panel_evidence)
        analyses.append({
            "id": row["id"], "title": row["title"],
            "evidence_status": "verified_source_data" if bounded_verified else "not_empirically_verified_for_phase2",
            "source_reference_count": len(links),
            "source_references_with_observations": observed,
            "linked_sources": links,
            "method_source_ids": row["primary_method_sources"],
            "method_sources": [
                {field: method_source_by_id[source_id].get(field)
                 for field in ("id", "label", "url")}
                for source_id in row["primary_method_sources"]
            ],
            "outstanding_evidence": row["outstanding_evidence"],
            "fallbacks": [{**fallback, "data_verified": False} for fallback in row["fallback_options"]],
            "requirements": requirements,
            "acceptance": acceptance,
            "readiness": readiness,
            "context_artifacts": {key: (artifact_evidence or {}).get(key, {"status": "not_checked"})
                                  for key in row["context_artifact_ids"]},
            "comparison_variants": row["comparison_contract"]["variants"],
            "comparison_evidence": panel_evidence,
            "has_bounded_current_vintage_panel": bounded_verified,
            "comparative_corpus_validated": acceptance["accepted"],
        })
    return {
        "phase": "phase2", "status": "active_not_complete",
        "analysis_count": len(analyses),
        "method_source_count": len(document["original_sources"]),
        "fully_validated_analysis_count": sum(x["comparative_corpus_validated"] for x in analyses),
        "acceptance_summary": acceptance_summary(analyses),
        "role_resolution_summary": resolution_summary(analyses),
        "readiness_matrix": [analysis["readiness"] for analysis in analyses],
        "bounded_current_vintage_panel_count": comparative["bounded_current_vintage_panel_count"],
        "analyses_with_bounded_current_vintage_panels": sum(x["has_bounded_current_vintage_panel"] for x in analyses),
        "comparative_evidence_checked": comparative["checked"],
        "comparative_evidence_valid": comparative["valid"],
        "comparative_evidence_failure_codes": comparative["failure_codes"],
        "comparative_evidence_asof": comparative.get("checked_at_utc"),
        "comparative_report_sha256": comparative.get("report_sha256"),
        "analyses_with_source_references": sum(x["source_reference_count"] > 0 for x in analyses),
        "analysis_with_any_stored_macro_observations": sum(x["source_references_with_observations"] > 0 for x in analyses),
        "observations_checked": observations is not None,
        "observation_evidence_asof": observations.get("asof")
            if observations is not None else None,
        "alfred_publication_vintages_checked": vintages is not None,
        "publisher_original_first_series_vintages_checked":
            publisher_vintage_proof is not None,
        "verified_official_series_vintage_origins": (
            publisher_vintage_proof.get("verified_series_vintage_sources", 0)
            if publisher_vintage_proof is not None else None),
        "observation_level_first_release_verified": False,
        "alfred_original_revision_inventory_checked":
            alfred_revision_proof is not None,
        "unbound_source_scopes_checked":
            unbound_source_evidence is not None,
        "original_unbound_roles_checked": (
            unbound_source_evidence.get("unbound_scalar_roles", 0)
            if unbound_source_evidence is not None else None),
        "alfred_verified_source_revision_windows": (
            alfred_revision_proof.get("verified_windows", 0)
            if alfred_revision_proof is not None else None),
        "alfred_invalid_original_revision_windows": (
            alfred_revision_proof.get(
                "invalid_or_conflicting_windows", 0)
            if alfred_revision_proof is not None else None),
        "structured_native_role_originals_checked":
            native_role_evidence is not None,
        "structured_native_roles_with_hash_verified_partial_originals": (
            native_role_evidence.get("hash_verified_partial_roles", 0)
            if native_role_evidence is not None else None),
        "alfred_sources_with_populated_asof": sum(
            item.get("populated_vintage_count", 0) > 0
            for item in vintage_by_id.values()
        ) if vintages is not None else None,
        "interpretation": (
            "Source bindings and stored historical source periods are not proof of "
            "complete matched economic comparisons or original release-time vintage. "
            "Missing sources and declared fallbacks remain visible; no synthetic data."
        ),
        "analyses": analyses,
    }
