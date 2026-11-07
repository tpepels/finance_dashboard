"""Deterministic scientific acceptance diagnostics for the original input roles.

Consumes the corpus runtime's validated panel projection, never editable source
certificates. A source binding, a bounded comparison and a complete original
scientific contract have separate gates.

Phase 2 evidenced end states (owner decision 2026-11-06): a role is
``accepted`` only when every gate passes. Publisher dimensions pass from a
cited per-series ``publisher_dimensions`` review that no archived original or
role expectation contradicts. Temporal evidence passes from verified ALFRED
real-time windows, or from a cited ``not_published_by_publisher`` finding that
is carried as an explicit role limitation, or (``source_asof`` roles) from a
verified original. A role whose exact source is verified unavailable resolves
as ``unavailable_with_fallback`` only when its approved fallback passes the
same gates; analyses using one are ``conditional``, never ``accepted``.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .source_original_gate import verified_original_rows
from .holdings_acceptance import holdings_role_checks, load_holdings_sources, valid_holdings_contract
from .chronology_acceptance import nber_announcement_checks
from .phase2_unbound_sources import DOCUMENTED_NATIVE_DISCOVERY

PUBLISHER_METADATA_FIELDS = (
    "source_native_unit", "source_native_unit_label", "source_currency", "source_sheet",
    "source_variable", "source_population", "source_price_basis", "source_author_constructed",
    "source_workbook_notes", "source_database_vintage", "source_dataset",
    "source_projection_start_year", "source_metadata_last_modified", "source_publisher_metadata",
)


FALLBACK_POLICY = "docs/PHASE1_FALLBACK_SOURCE_MATRIX.md"
RELEASE_DATING_MODES = ("alfred_real_time", "not_published_by_publisher", "publisher_vintage_archive",
                        "unrevised_market_observation")
DIMENSION_FIELDS = ("population", "currency", "price_basis", "index_base")
RESOLVED_ROLE_STATES = ("accepted", "unavailable_with_fallback", "user_input")
EVIDENCE_TIERS = ("descriptive", "predictive")
PHASE2_SCOPES = ("active", "deferred_extension")


def _iso_date(value) -> bool:
    try:
        return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _cited(declaration) -> bool:
    return (isinstance(declaration, dict)
            and isinstance(declaration.get("evidence_url"), str)
            and declaration["evidence_url"].startswith("https://")
            and _iso_date(declaration.get("reviewed_on")))


def valid_publisher_dimensions(declaration) -> bool:
    """A cited review; every field is explicit (null means not applicable)."""
    return (_cited(declaration)
            and isinstance(declaration.get("population"), str) and declaration["population"].strip() != ""
            and all(field in declaration and (declaration[field] is None or (
                isinstance(declaration[field], str) and declaration[field].strip()))
                for field in DIMENSION_FIELDS))


def valid_release_dating(declaration) -> bool:
    return _cited(declaration) and declaration.get("mode") in RELEASE_DATING_MODES


def valid_unavailability(declaration) -> bool:
    fallback = declaration.get("fallback") if isinstance(declaration, dict) else None
    return (isinstance(declaration, dict) and _iso_date(declaration.get("reviewed_on"))
            and isinstance(declaration.get("reason"), str) and declaration["reason"].strip() != ""
            and isinstance(declaration.get("evidence_urls"), list) and declaration["evidence_urls"]
            and all(isinstance(url, str) and url.startswith("https://") for url in declaration["evidence_urls"])
            and isinstance(fallback, dict) and fallback.get("reference") == FALLBACK_POLICY
            and isinstance(fallback.get("series_ids", []), list)
            and all(isinstance(sid, str) for sid in fallback.get("series_ids", []))
            # A fallback is either scalar series or a holdings contract, never both.
            and (bool(fallback.get("series_ids")) != ("holdings_contract" in fallback))
            and ("holdings_contract" not in fallback or valid_holdings_contract(fallback["holdings_contract"]))
            and isinstance(fallback.get("expected"), dict)
            and isinstance(fallback.get("population_difference"), str)
            and fallback["population_difference"].strip() != "")


def _publisher_dimensions_gate(ids, expected, registry, originals) -> dict:
    missing, unverified, contradictions = [], [], []
    for sid in ids:
        source = registry.get(sid) or {}
        declaration = source.get("publisher_dimensions")
        if not valid_publisher_dimensions(declaration):
            missing.append(sid)
            declaration = None
        if sid not in originals:
            unverified.append(sid)
        if declaration is None:
            continue
        declared = (declaration.get("currency") or "").upper() or None
        observed = (originals.get(sid, {}).get("source_currency") or "").upper() or None
        registered = (source.get("currency") or "").upper() or None
        for label, value in (("original_source_currency", observed), ("registry_currency", registered)):
            if value is not None and declared != value:
                contradictions.append({"series_id": sid, "field": "currency", "against": label,
                                       "declared": declared, "observed": value})
        for field in ("index_base", "price_basis"):
            if field in expected and declaration.get(field) != expected[field]:
                contradictions.append({"series_id": sid, "field": field, "against": "role_expected",
                                       "declared": declaration.get(field), "observed": expected[field]})
    # Tiered evidence (owner decision 2026-11-06): the curated catalogue
    # declaration, checked against the verified original, suffices; a cited
    # review adds evidence and contradiction checks but is not required.
    state = ("incomplete" if not ids else "failed" if contradictions
             else "incomplete" if unverified else "passed")
    code = ("publisher_dimensions_unbound" if not ids
            else "publisher_dimensions_contradicted" if contradictions
            else "original_values_required_for_dimension_review" if unverified
            else "publisher_dimensions_declared_and_uncontradicted" if missing
            else "publisher_dimensions_reviewed_and_uncontradicted")
    limitations = ([{"code": "dimensions_as_declared_in_catalogue", "series_ids": sorted(missing),
                     "detail": "Population, currency and price basis follow the curated catalogue declaration of the publisher series; no separate cited review."}]
                   if state == "passed" and missing else [])
    return _gate("publisher_dimensions", state, code, ids,
        required_evidence=["population", "currency_and_quote", "price_basis_and_index_base"],
        expected=expected, missing_reviews=sorted(missing), unverified_originals=sorted(unverified),
        limitations=limitations,
        contradictions=contradictions,
        reviews=[{"series_id": sid, **registry[sid]["publisher_dimensions"]}
                 for sid in ids if valid_publisher_dimensions((registry.get(sid) or {}).get("publisher_dimensions"))],
        original_metadata=[{"series_id": sid, "source_sha256": originals[sid]["source_sha256"],
            **{key: originals[sid][key] for key in PUBLISHER_METADATA_FIELDS if key in originals[sid]}}
            for sid in ids if sid in originals],
        scope="Cited per-series publisher review, checked against archived original metadata and the role's declared index base and price basis.")


def _uncovered_history(row: dict, stored: dict) -> bool:
    """True unless verified windows cover every stored period without a gap."""
    first, last = stored.get("oldest_source_date"), stored.get("latest_source_date")
    if not first or not last:
        return True
    reach = None
    for start, end in row.get("verified_window_ranges", []):
        start, end = date.fromisoformat(start), date.fromisoformat(end)
        if reach is None:
            if start > date.fromisoformat(first):
                return True
            reach = end
        elif start > reach + timedelta(days=1):
            return True
        reach = max(reach, end)
    return reach is None or reach < date.fromisoformat(last)


def _temporal_gate(role, ids, registry, originals, revisions, release_originals,
                   counts=None) -> dict:
    details = dict(required_mode=role["temporal_requirement"],
        verified_official_series_vintages=release_originals,
        original_publisher_series_vintage_count=len(release_originals),
        verified_original_revision_sources=revisions,
        alfred_windows_with_complete_realtime_intervals=sum(
            row["hash_verified_original_windows"] for row in revisions),
        observation_first_release_dates_verified=0)
    if not ids:
        return _gate("temporal_evidence", "incomplete", "temporal_evidence_unbound", ids, **details)
    unverified = sorted(sid for sid in ids if sid not in originals)
    if role["temporal_requirement"] == "latest_revised":
        return _gate("temporal_evidence", "incomplete" if unverified else "passed",
            "verified_original_required" if unverified else "latest_revised_values_verified",
            ids, unverified_originals=unverified, **details,
            limitations=[] if unverified else [{"code": "latest_revised_values_not_real_time",
                "series_ids": sorted(ids),
                "detail": "Descriptive analysis uses the publisher's latest revised values; it does not show what was known at past dates."}],
            scope="Descriptive evidence tier: latest revised values from a verified original.")
    if role["temporal_requirement"] == "source_asof":
        return _gate("temporal_evidence", "incomplete" if unverified else "passed",
            "verified_original_asof_required" if unverified else "verified_original_source_asof",
            ids, unverified_originals=unverified, limitations=[], **details,
            scope="Point-in-time source as-of evidence is the verified archived original itself.")
    by_series = {row["series_id"]: row for row in revisions}
    missing, pending, conflicting, limitations, archives = [], [], [], [], []
    for sid in ids:
        declaration = (registry.get(sid) or {}).get("release_dating")
        if not valid_release_dating(declaration):
            missing.append(sid)
        elif declaration["mode"] == "alfred_real_time":
            row = by_series.get(sid)
            if row and row["invalid_or_conflicting_original_windows"]:
                conflicting.append(sid)
            elif (not row or not row["hash_verified_original_windows"]
                  or _uncovered_history(row, (counts or {}).get(sid, {}))):
                pending.append(sid)
            else:
                limitations.append({"series_id": sid, "code": "alfred_records_not_agency_first_release",
                    "evidence_url": declaration["evidence_url"]})
        elif declaration["mode"] == "unrevised_market_observation":
            # Daily market prices/yields are published once (next business
            # day) and not revised; the observation date is its release date.
            limitations.append({"series_id": sid, "code": "market_observation_assumed_unrevised",
                "evidence_url": declaration["evidence_url"],
                "detail": "Treated as known one business day after the observation date; occasional publisher corrections are not modelled."})
        elif declaration["mode"] == "publisher_vintage_archive":
            # The publisher keeps historical releases; until they are
            # collected and verified the role cannot claim release timing.
            archives.append(sid)
        else:
            limitations.append({"series_id": sid, "code": "release_dates_not_published_by_publisher",
                "evidence_url": declaration["evidence_url"],
                "detail": "Only the latest revised values are available; analyses cannot be evaluated as of a historical release date."})
    state = ("failed" if conflicting else "incomplete" if missing or pending or archives or unverified
             else "passed")
    code = ("conflicting_alfred_revision_windows" if conflicting
            else "release_dating_review_missing" if missing
            else "alfred_revision_windows_incomplete_for_stored_history" if pending
            else "publisher_vintage_archive_not_collected" if archives
            else "verified_original_values_required" if unverified
            else "release_dating_evidenced")
    return _gate("temporal_evidence", state, code, ids, missing_reviews=sorted(missing),
        pending_alfred_series=sorted(pending), conflicting_series=sorted(conflicting),
        uncollected_vintage_archive_series=sorted(archives),
        unverified_originals=unverified, limitations=limitations, **details,
        scope="ALFRED windows record what ALFRED held, not necessarily the producing agency's first release; publishers without release vintages are accepted only with that limitation carried forward.")


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
                        native_role_evidence: dict | None = None,
                        alfred_revision_proof: dict | None = None,
                        unbound_source_evidence: dict | None = None,
                        holdings_sources: dict | None = None,
                        as_of: date | None = None) -> dict[str, Any]:
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
    source_candidates = {
        (row["analysis_id"], row["role"]): row
        for row in (unbound_source_evidence or {}).get("role_candidates", [])
    }
    if len(source_candidates) != len(
            (unbound_source_evidence or {}).get("role_candidates", [])):
        raise ValueError("duplicate_unbound_original_role_evidence")
    matrix_available = (matrix.get("original_source_hash_verified") is True
                        and type(matrix.get("year")) is int and 1995 <= matrix["year"] <= 2022
                        and type(matrix.get("accounting_passed")) is bool)
    # Declared fallbacks are evaluated first, through the identical gates,
    # so each original role can be resolved against its finished result.
    reviews = holdings_sources if holdings_sources is not None else load_holdings_sources()
    today = as_of or date.today()
    originals_roles = list(analysis["comparison_contract"]["original_requirements"])
    roles = []
    fallback_results: dict[str, dict] = {}
    for role in originals_roles:
        unavailability = role.get("verified_unavailability")
        if unavailability is not None and valid_unavailability(unavailability):
            fallback = unavailability["fallback"]
            roles.append({"role": role["role"], "description": role["description"],
                          "series_ids": list(fallback.get("series_ids", [])), "expected": fallback["expected"],
                          "temporal_requirement": role["temporal_requirement"],
                          "input_type": role["input_type"], "artifact_ids": [],
                          **({"holdings_contract": fallback["holdings_contract"]}
                             if "holdings_contract" in fallback else {}),
                          "_fallback_for": role["role"]})
    roles.extend(originals_roles)
    for role in roles:
        if role.get("supply") == "user":
            # Owner-supplied parameters (weights, policies, costs, holdings
            # exports) are inputs to the application, not publisher data.
            check = _gate("user_supplied", "passed", "owner_supplied_parameter", (),
                          scope="Provided by the owner at analysis time; never fetched or inferred.")
            requirements.append({**role, "state": "user_input", "accepted": False,
                "sources_checked": observations_checked, "mapped_source_count": 0,
                "sources_with_observations": 0, "first_publication_verified": False,
                "limitations": [], "source_asof_verified": False, "checks": [check],
                "blocking_checks": []})
            continue
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
            limitations=[dict(item, variant_id=p["variant_id"]) for p in complete[:1]
                         for item in p.get("coverage_limitations", []) if item["series_id"] in ids]
                + [{"code": "no_approved_analysis_window_common_native_history", "variant_id": p["variant_id"]}
                   for p in complete[:1] if p.get("derived_from_role")],
            scope="Exact native-period joins; no fill. Interior absences are accepted only against verified full publisher snapshots and are carried as limitations."))
        checks.append(_publisher_dimensions_gate(ids, expected, registry, originals))
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
        revision_sources = (alfred_revision_proof or {}).get("series", {})
        revisions = [{
            "series_id": sid,
            "alfred_source_key": registry[sid]["source_key"],
            "hash_verified_original_windows": revision_sources[
                registry[sid]["source_key"]]["verified_windows"],
            "original_revision_rows": revision_sources[
                registry[sid]["source_key"]][
                    "verified_observation_revision_rows"],
            "invalid_or_conflicting_original_windows": revision_sources[
                registry[sid]["source_key"]][
                    "invalid_or_conflicting_windows"],
            "verified_window_ranges": sorted(
                [window["start"], window["end"]] for window in revision_sources[
                    registry[sid]["source_key"]].get("windows", [])
                if window.get("status") == "verified_original_revision_window"
                and window.get("start") and window.get("end")),
        } for sid in ids if sid in registry
            and registry[sid].get("provider") == "FRED"
            and registry[sid]["source_key"] in revision_sources]
        checks.append(_temporal_gate(role, ids, registry, originals, revisions, release_originals, counts))
        artifact = None
        icio_resolved = False
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
            # Every year 1995-2022 from the publisher's own January 2026
            # archives: one edition and update, so the matrix roles resolve.
            if history.get("full_history_verified") is True and history.get("common_update_verified") is True:
                icio_resolved = True
                limitations = [{"code": "latest_revised_values_not_real_time", "artifact": "icio",
                                "detail": "The 2025 edition's latest revised matrices; no earlier release is reconstructed."}]
                if not matrix.get("accounting_passed"):
                    limitations.append({"code": "publisher_matrix_residuals_within_materiality", "artifact": "icio",
                        "bound_relative_to_node_gross_output": (matrix.get("materiality") or {}).get(
                            "bound_relative_to_node_gross_output"),
                        "detail": "Row and column identities hold within 0.1% of each node's gross output in every year; residuals above serialization rounding are retained, not rebalanced."})
                checks = [
                    _gate("source_binding", "passed", "original_artifact_full_history_verified",
                          scope="OECD 2025 regular ICIO, all 28 annual matrices, publisher archives."),
                    _gate("native_dimensions", "passed", "original_artifact_dimensions_verified",
                          scope="Pinned ReadMe country/industry/final-demand codes; current USD million."),
                    _gate("stored_history", "passed", "original_artifact_full_history_verified", available_years=years),
                    _gate("original_source_values", "passed", "original_artifact_hashes_verified",
                          scope="Archive and member bytes pinned; 2016-2022 also match independent replicas."),
                    _gate("matched_periods", "passed", "single_edition_annual_matrices_complete", available_years=years),
                    _gate("publisher_dimensions", "passed", "icio_readme_dimensions_verified",
                          scope="Edition, unit and dimensions read from the publisher's own ReadMe."),
                    _gate("temporal_evidence", "passed", "latest_revised_values_verified", limitations=limitations)]
        # Some explicitly named original methods have a genuine typed native
        # reader before any scalar catalog identity is scientifically bound.
        # WIID survey rows, for example, retain welfare concept/scale/quality
        # and cannot be collapsed to an assumed country-year Gini.
        named_artifact = DOCUMENTED_NATIVE_DISCOVERY.get(
            (analysis["id"], role["role"]))
        named_evidence = (artifact_evidence or {}).get(
            named_artifact, {}) if named_artifact else {}
        if (not ids and named_evidence.get(
                "original_source_hash_verified") is True):
            checks[0] = _gate(
                "source_binding", "incomplete",
                "documented_native_original_without_scalar_identity",
                scope="Retained original survey/structured source verified; no validated scalar variable, common units or period selection exists.")
            checks[2] = _gate(
                "stored_history", "incomplete",
                "native_original_requires_matched_role_history")
            checks[3] = _gate(
                "original_source_values", "incomplete",
                "source_original_available_without_exact_method_projection")
        partial = [] if icio_resolved else _partial_artifacts(role, artifact_evidence or {})
        if named_artifact and named_evidence.get(
                "original_source_hash_verified") is True:
            partial.append({
                "artifact_id": named_artifact,
                "availability": "available_partial",
                "original_source_hash_verified": True,
                "original_role_satisfied": False,
                "full_history_verified": False,
                "first_publication_verified": False,
                "scalar_binding_established": False,
                "scope": "Native original rows require source-specific welfare measure, survey population, unit and release alignment before scalar derivation.",
            })
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
        # Original numeric source scopes may be genuine without proving the
        # economic original variable. Keep the exact binding and temporal
        # gates incomplete while exposing which same-retrieval source rows
        # exist for the approved original-method research question.
        candidate = source_candidates.get((analysis["id"], role["role"]))
        original_scopes = [
            source for item in (candidate or {}).get(
                "publisher_candidates", [])
            for source in item.get(
                "original_numeric_scope_evidence", {}).get(
                    "reviewed_original_scopes", [])
        ]
        if not ids and original_scopes and not icio_resolved:
            checks[0] = _gate(
                "source_binding", "incomplete",
                "native_original_measure_observed_not_economic_role_bound",
                scope="Source bytes contain a native measure, but the exact scientific economic variable and perimeter have not been established.")
            checks[2] = _gate(
                "stored_history", "incomplete",
                "original_native_source_scopes_not_full_compatible_history",
                original_publisher_scopes=len(original_scopes))
            checks[3] = _gate(
                "original_source_values", "incomplete",
                "published_original_values_require_same_scope_method_mapping",
                source_sha256=[x["source_sha256"] for x in original_scopes])
            if checks[1]["state"] == "not_checked":
                checks[1] = _gate(
                    "native_dimensions", "incomplete",
                    "original_native_publisher_dimensions_not_yet_matched",
                    scope="Industry/year, currency/price, economic measure and publication vintage must all match the original method.")
        # Holdings-backed roles have no scalar series: their gates are judged
        # on each declared fund's latest original snapshot instead.
        holdings = None
        if role.get("holdings_contract") is not None and not ids:
            holdings = holdings_role_checks(role["holdings_contract"], artifact_evidence or {},
                                            reviews, as_of=today)
            checks = holdings["checks"]
        # The announcement-dates role is the dated NBER originals themselves.
        chronology = None
        if role.get("artifact_ids") == ["nber_chronology"] and not ids:
            chronology = nber_announcement_checks((artifact_evidence or {}).get("nber_chronology", {}))
            checks = chronology["checks"]
        state = _state(checks)
        result = {**role, "state": state, "accepted": state == "accepted",
            "sources_checked": observations_checked, "mapped_source_count": len(ids),
            "sources_with_observations": len(stored), "first_publication_verified": False,
            "limitations": [item for check in checks for item in check.get("limitations", [])],
            "source_asof_verified": False, "checks": checks,
            "blocking_checks": [item["id"] for item in checks if item["state"] != "passed"]}
        if holdings is not None:
            result["holdings_evaluation"] = {"funds": holdings["funds"],
                                             "conditional": holdings["conditional"]}
        if chronology is not None:
            result["artifact_evaluation"] = {"artifact": "nber_chronology", "resolved": chronology["resolved"],
                                             "conditional": chronology["conditional"]}
        if artifact is not None:
            result["original_artifact_evidence"] = {**artifact, "role_resolved": icio_resolved}
        if partial:
            result["partial_artifact_evidence"] = partial
        if candidate is not None:
            result["reviewed_original_candidate_evidence"] = {
                "original_native_scope_count": len(original_scopes),
                "documented_native_artifact":
                    candidate.get("documented_native_artifact"),
                "documented_artifact_original_hash_verified":
                    candidate.get(
                        "documented_artifact_original_hash_verified") is True,
                "economic_original_method_verified": False,
                "scalar_series_automatically_bound": False,
            }
        if attached and attached.get("original_source_hash_verified") is True:
            result["attached_native_original"] = {
                "status": attached["status"],
                "original_source_hash_verified": True,
                "native_facts": attached["native_facts"],
                "origin": attached["origin"],
                "first_publication_verified": False,
                "original_economic_scope_verified": False,
            }
        if role.get("_fallback_for"):
            fallback_results[role["_fallback_for"]] = result
            continue
        unavailability = role.get("verified_unavailability")
        if unavailability is not None:
            fallback = fallback_results.get(role["role"])
            result["verified_unavailability"] = {
                "declaration_valid": valid_unavailability(unavailability),
                "reason": unavailability.get("reason") if isinstance(unavailability, dict) else None,
                "fallback_state": fallback["state"] if fallback else "not_evaluated",
            }
            if fallback is not None:
                result["fallback_evaluation"] = fallback
            if not result["accepted"] and fallback is not None and fallback["accepted"]:
                result["state"] = "unavailable_with_fallback"
                result["limitations"] = result["limitations"] + fallback["limitations"] + [{
                    "code": "exact_source_unavailable_fallback_used",
                    "fallback_series_ids": fallback["series_ids"],
                    **({"fallback_funds": [item["fund"] for item in fallback["holdings_evaluation"]["funds"]]}
                       if "holdings_evaluation" in fallback else {}),
                    "population_difference": unavailability["fallback"]["population_difference"]}]
        requirements.append(result)
    scientific_failures = [{"variant_id": panel["variant_id"], "panel_sha256": panel.get("panel_sha256"),
                            "check": check}
        for panel in panels for check in panel.get("checks", []) if check.get("passed") is False]
    def immaterial(item):
        return (item.get("accounting_passed") is True
                or (item.get("materiality") or {}).get("material_accounting_passed") is True)
    if matrix_available and matrix.get("accounting_passed") is False and not immaterial(matrix):
        scientific_failures.append({"artifact": f"OECD_ICIO_2025_REGULAR_{matrix['year']}",
            "matrix_sha256": matrix.get("matrix_sha256"),
            "check": {"id": "original_matrix_accounting", "passed": False,
                **{key: matrix.get(key) for key in ("row_accounting_failures", "column_accounting_failures",
                    "maximum_row_residual", "maximum_column_residual", "identities")}}})
    # Historical replicas and published TiVA levels/shares retain their own
    # accounting results even when a scalar panel has not been assembled.
    if analysis["id"] == "G06":
        for item in matrix.get("historical_matrices", []):
            if (item.get("original_source_hash_verified") is True and item.get("accounting_passed") is False
                    and not immaterial(item)):
                scientific_failures.append({"artifact": f"OECD_ICIO_2025_REGULAR_{item['year']}_"
                                            + ("PUBLISHER" if item.get("publisher_direct_verified") else "REPLICA"),
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
    panel_ids = {sid for panel in originals for sid in panel["series_ids"]}
    def effective_ids(role):
        if role["state"] == "unavailable_with_fallback":
            return role["fallback_evaluation"]["series_ids"]
        return role["series_ids"]
    def holdings_resolved(role):
        source = role.get("fallback_evaluation") if role["state"] == "unavailable_with_fallback" else role
        return role["state"] in RESOLVED_ROLE_STATES and (
            "holdings_evaluation" in (source or {})
            or ((source or {}).get("artifact_evaluation") or {}).get("resolved") is True
            or ((source or {}).get("original_artifact_evidence") or {}).get("role_resolved") is True)
    # A holdings role is one dated snapshot per fund, not a period panel; its
    # own gates are the original comparison for that input.
    covered = {role["role"] for role in requirements if effective_ids(role)
        and set(effective_ids(role)).issubset(panel_ids)} | {
        role["role"] for role in requirements if holdings_resolved(role)}
    # Owner-supplied parameters are not publisher data and join no comparison bundle.
    uncovered = sorted(role["role"] for role in requirements
                       if role["role"] not in covered and role["state"] != "user_input")
    comparison = _gate("original_comparison", "passed" if not uncovered else "incomplete",
        "original_native_input_bundle_verified" if not uncovered else "complete_original_comparison_outstanding",
        variants=sorted(p["variant_id"] for p in originals),
        covered_roles=sorted(covered), uncovered_roles=uncovered,
        scope="Original native input bundle only; temporal transformations and methodological alignment belong to Phase 3.")
    checks = [{"state": "passed" if r["state"] in RESOLVED_ROLE_STATES else r["state"]}
              for r in requirements] + [comparison]
    if scientific_failures:
        checks.append({"state": "failed"})
    state = _state(checks)
    descoped = analysis.get("descoped_roles", [])
    if state == "accepted" and (descoped or any(
            r["state"] == "unavailable_with_fallback"
            or (r.get("holdings_evaluation") or {}).get("conditional")
            or (r.get("artifact_evaluation") or {}).get("conditional") for r in requirements)):
        state = "conditional"
    if analysis.get("phase2_scope") == "deferred_extension":
        state = "deferred"
    result = {"contract_version": 1, "specification": analysis["comparison_contract"]["specification"],
        "state": state, "accepted": state == "accepted", "required_input_roles": len(requirements),
        "accepted_input_roles": sum(r["accepted"] for r in requirements),
        "phase2_resolved": state in ("accepted", "conditional"),
        "evidence_tier": analysis.get("evidence_tier"),
        "decision_informed": analysis.get("decision_informed"),
        "limitations": [item for r in requirements for item in r["limitations"]] + [
            {"code": "role_descoped_by_phase1_revision", "role": item["role"], "detail": item["reason"]}
            for item in descoped] + ([{"code": "deferred_research_extension",
                                       "detail": analysis.get("deferral_reason")}]
                                     if state == "deferred" else []),
        "requirements": requirements, "comparison": comparison, "scientific_failures": scientific_failures,
        "blocking_roles": [r["role"] for r in requirements if not r["accepted"]],
        "interpretation": "Original analysis acceptance requires every role and original comparison gate. Bounded native alternatives remain separately labelled."}
    fallbacks = analysis.get("fallback_options", [])
    if analysis["id"] == "G06":
        result["source_investigations"] = {key: matrix[key] for key in ("publisher_acquisition", "release_comparison") if key in matrix}
    policy = FALLBACK_POLICY
    if fallbacks and all(option.get("reference") == policy for option in fallbacks):
        result["source_resolution"] = {
            "classification": "certified" if result["accepted"] else "conditional",
            "policy_reference": policy,
            "phase2_resolved": result["phase2_resolved"],
            "unmet_original_roles": result["blocking_roles"],
            "comparison_outstanding": comparison["state"] != "passed",
            "scientific_failure_count": len(scientific_failures),
            "verified_native_alternative_variants": sorted(p["variant_id"] for p in panels
                if p.get("kind") in {"approved_narrower", "approved_fallback"}
                and p.get("state") == "bounded_current_vintage_verified"),
            "partial_artifact_ids": sorted({artifact["artifact_id"] for role in requirements
                for artifact in role.get("partial_artifact_evidence", [])}),
            "conditions": "Exact source identity, historical coverage, publisher dimensions and temporal eligibility remain required. Named alternatives retain their own populations; only a cited verified_unavailability whose fallback passes every gate resolves a role.",
        }
    return result


def acceptance_summary(analyses: list[dict]) -> dict:
    return {"analysis_count": len(analyses),
        "required_input_roles": sum(row["acceptance"]["required_input_roles"] for row in analyses),
        "accepted_input_roles": sum(row["acceptance"]["accepted_input_roles"] for row in analyses),
        "fully_accepted_analyses": sum(row["acceptance"]["accepted"] for row in analyses),
        "phase2_resolved_analyses": sum(row["acceptance"]["state"] in ("accepted", "conditional") for row in analyses),
        "active_analyses": sum(row["acceptance"]["state"] != "deferred" for row in analyses),
        "phase2_complete": all(row["acceptance"]["state"] in ("accepted", "conditional", "deferred")
                               for row in analyses),
        "analysis_states": {state: sum(row["acceptance"]["state"] == state for row in analyses)
                            for state in ("accepted", "conditional", "deferred", "failed", "blocked", "incomplete", "not_checked")},
        "role_states": {state: sum(role["state"] == state for row in analyses for role in row["requirements"])
                        for state in ("accepted", "unavailable_with_fallback", "user_input", "failed", "blocked", "incomplete", "not_checked")}}
