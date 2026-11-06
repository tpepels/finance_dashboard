"""Canonical Phase 2 acquisition capabilities for all approved structured artifacts.

This is a capability registry over the native collectors and immutable readers,
not an alternative provider or scientific source registry. Every collection
uses the managed HTTP transport, the publisher-policy ledger and one optional
global HTTP request cap. No publisher's rights or data is inferred by metadata.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .research_readiness import ARTIFACT_IDS
from .phase2_unbound_sources import DOCUMENTED_NATIVE_DISCOVERY
from .research_artifacts import research_artifact_evidence
from .source_policy_registry import PolicyRegistry
from .source_policy_types import PolicyViolation


@dataclass(frozen=True)
class StructuredCapability:
    kind: str
    collection: str    # publisher_collector | operator_original | access_probe_only
    verification: str  # native_reader | pinned_source | original_access_only
    reason: str
    required: tuple[str, ...] = ()


CAPABILITIES = {
    "nber_chronology": StructuredCapability(
        "nber_chronology", "publisher_collector", "native_reader",
        "Official recession chronology plus announcement pages"),
    "cvm": StructuredCapability(
        "cvm", "publisher_collector", "native_reader",
        "Year-scoped original regulator filing archive", ("cvm_year",)),
    "amne": StructuredCapability(
        "amne", "publisher_collector", "native_reader",
        "Original OECD Analytical AMNE workbook and tables"),
    "meip": StructuredCapability(
        "meip", "publisher_collector", "native_reader",
        "Original OECD/UN multinational enterprise indicator tables"),
    "tiva": StructuredCapability(
        "tiva", "publisher_collector", "native_reader",
        "Two official source-selected TiVA flows"),
    "stan": StructuredCapability(
        "stan", "publisher_collector", "native_reader",
        "Native STAN 2025 structure, surplus probes and industry-year archives"),
    "sec_holdings": StructuredCapability(
        "sec_holdings", "publisher_collector", "native_reader",
        "Original SEC accession and N-PORT XML with verified CIK/series ID",
        ("holdings_dir", "sec_user_agent")),
    "icio": StructuredCapability(
        "icio", "operator_original", "pinned_source",
        "Official package access is not a verified matrix; use pinned original package importer"),
    "ucits_holdings": StructuredCapability(
        "ucits_holdings", "publisher_collector", "native_reader",
        "Fixed publisher-pinned issuer PDFs and dated holdings originals",
        ("holdings_dir",)),
    "taiwan_profits": StructuredCapability(
        "taiwan_profits", "operator_original", "native_reader",
        "Official TWSE/TPEx native boards and matching fiscal filing definition required"),
    "msci_concentration": StructuredCapability(
        "msci_concentration", "operator_original", "native_reader",
        "Native automated factsheet collector not implemented; local originals supported"),
    "corporate_accounts": StructuredCapability(
        "corporate_accounts", "operator_original", "native_reader",
        "Sector-account source filings require exact publication and perimeter proof"),
    "wiid": StructuredCapability(
        "wiid", "operator_original", "native_reader",
        "Original WIID main and companion tables must be registered explicitly"),
}
if set(CAPABILITIES) != ARTIFACT_IDS:
    raise RuntimeError("structured_artifact_capability_registry_incomplete")


def original_artifact_matrix(document: dict, evidence: dict,
                             *, included: set[str] | None = None) -> dict:
    """Map all 44 structured roles to original artifacts or missing methods."""
    capabilities = CAPABILITIES
    wanted = ARTIFACT_IDS if included is None else included
    if wanted - ARTIFACT_IDS:
        raise ValueError("unregistered_structured_artifact")
    by_kind = {kind: {"artifact_id": kind,
                      "collection": capabilities[kind].collection,
                      "verification": capabilities[kind].verification,
                      "reason": capabilities[kind].reason,
                      "required_operator_inputs": list(capabilities[kind].required),
                      "roles": [], "affected_analyses": set(),
                      "unbound_scalar_native_references": [],
                      "original_proof_state": "missing_or_invalid",
                      "scientific_methods_certified": False}
               for kind in sorted(wanted)}
    unassigned = []
    total = 0
    for analysis in document["analyses"]:
        for kind in analysis.get("context_artifact_ids", []):
            if kind in by_kind:
                by_kind[kind]["affected_analyses"].add(analysis["id"])
        for role in analysis["comparison_contract"]["original_requirements"]:
            if role["input_type"] == "scalar_history":
                native = DOCUMENTED_NATIVE_DISCOVERY.get(
                    (analysis["id"], role["role"]))
                if native in by_kind and not role["series_ids"]:
                    by_kind[native]["affected_analyses"].add(analysis["id"])
                    by_kind[native]["unbound_scalar_native_references"].append({
                        "analysis_id": analysis["id"],
                        "role": role["role"],
                        "native_original_is_not_scalar_history": True,
                    })
                continue
            total += 1
            items = [k for k in role["artifact_ids"] if k in wanted]
            for kind in items:
                group = by_kind[kind]
                group["roles"].append({
                    "analysis_id": analysis["id"], "role": role["role"],
                    "input_type": role["input_type"],
                    "temporal_requirement": role["temporal_requirement"],
                    "expected": role["expected"],
                })
                group["affected_analyses"].add(analysis["id"])
            if not role["artifact_ids"]:
                unassigned.append({
                    "analysis_id": analysis["id"], "role": role["role"],
                    "input_type": role["input_type"], "expected": role["expected"],
                    "reason": "Original input has no verified publisher artifact binding",
                    "requires_operator_or_publisher_original": True,
                })
    rows = []
    for kind, group in sorted(by_kind.items()):
        original = evidence.get(kind, {})
        group["original_proof_state"] = (
            "hash_verified_partial" if original.get(
                "original_source_hash_verified") is True else
            "invalid_or_unavailable")
        group["verification_status"] = original.get("status", "not_checked")
        group["publisher_original_available"] = (
            original.get("original_source_hash_verified") is True)
        group["full_history_verified"] = (
            original.get("full_history_verified") is True)
        group["first_publication_verified"] = (
            original.get("first_publication_verified") is True)
        group["affected_analyses"] = sorted(group["affected_analyses"])
        group["role_count"] = len(group["roles"])
        group["unbound_scalar_native_reference_count"] = len(
            group["unbound_scalar_native_references"])
        rows.append(group)
    return {
        "phase": "phase2", "operation": "original_structured_workplan",
        "structured_roles": total,
        "roles_with_registered_artifacts": total - len(unassigned),
        "roles_without_registered_artifacts": len(unassigned),
        "unassigned_original_roles": unassigned,
        "artifact_workstreams": rows,
        "native_collectors_available": sorted(k for k, value in CAPABILITIES.items()
                                              if value.collection == "publisher_collector"),
        "direct_originals_requiring_explicit_registration": sorted(
            k for k, value in CAPABILITIES.items()
            if value.collection == "operator_original"),
        "historical_originals_rewritten": False,
        "research_certified": False,
    }


def ucits_original_routes() -> dict[str, tuple[str, ...]]:
    """Two independently paced publisher sources with one UCITS original reader.

    Source access classification is technical and does not infer a licence;
    the managed HTTP boundary supplies each publisher's durable request budget.
    """
    from .ucits_holdings import CSV_URL, ANNUALS, annual_url
    from .vanguard_ucits_holdings import REPORTS
    return {
        "ishares": tuple([annual_url(y) for y in sorted(ANNUALS)] +
                         [CSV_URL]),
        "vanguard": tuple(
            item["source_url"] for item in REPORTS.values()),
    }


def _classify_publisher_routes(
        endpoints: tuple[str, ...], policies: PolicyRegistry) -> tuple[list[str], str | None]:
    ids = set()
    for endpoint in endpoints:
        try:
            policy = policies.for_url(endpoint)
        except PolicyViolation:
            return sorted(ids), "publisher_api_host_unclassified"
        ids.add(policy.id)
    return sorted(ids), None


def task_policy_hosts(kind: str, *, cvm_year: int | None = None) -> tuple[str, ...]:
    """Exact registered collector URLs, never guessed from a document page."""
    if kind == "nber_chronology":
        from .nber_chronology import SITE, DATES_PATH, INDEX_PATH
        return SITE + DATES_PATH, SITE + INDEX_PATH
    if kind == "cvm":
        from .cvm_profits import BASE
        if cvm_year is None or not 2010 <= cvm_year <= date.today().year:
            return ()
        return (BASE + f"dfp_cia_aberta_{cvm_year}.zip",)
    if kind in {"amne", "meip"}:
        from .multinational_sources import SOURCE_FILES
        return tuple(SOURCE_FILES[kind].values())
    if kind == "tiva":
        from .oecd_tiva import TIVA_URLS
        return tuple(TIVA_URLS.values())
    if kind == "stan":
        from .stan_metadata import STRUCTURE_URL
        return (STRUCTURE_URL,)
    if kind == "sec_holdings":
        from .sec_holdings_sync import SUBMISSIONS_URL, EDGAR_URL
        return SUBMISSIONS_URL, EDGAR_URL
    if kind == "ucits_holdings":
        return tuple(url for group in ucits_original_routes().values()
                     for url in group)
    return ()


def collection_plan(matrix: dict, *, registry: PolicyRegistry | None = None,
                    cvm_year: int | None = None,
                    holdings_dir: Path | None = None,
                    sec_user_agent: str | None = None) -> dict:
    """Preclassify actual API hosts and required operator inputs before traffic."""
    policies = registry or PolicyRegistry()
    result = []
    for group in matrix["artifact_workstreams"]:
        kind = group["artifact_id"]
        if not group["affected_analyses"]:
            continue
        capability = CAPABILITIES[kind]
        endpoints = task_policy_hosts(kind, cvm_year=cvm_year)
        ids = set()
        blocker = None
        subsources = []
        if capability.collection != "publisher_collector":
            blocker = "operator_original_required"
        elif not endpoints:
            blocker = "required_publisher_scope_missing"
        elif kind in {"sec_holdings", "ucits_holdings"} and not holdings_dir:
            blocker = "original_holdings_archive_path_required"
        elif kind == "sec_holdings" and (
                not sec_user_agent or "@" not in sec_user_agent):
            blocker = "original_sec_contact_user_agent_missing"
        elif kind == "ucits_holdings":
            for name, urls in ucits_original_routes().items():
                route_ids, denied = _classify_publisher_routes(
                    urls, policies)
                ids.update(route_ids)
                subsources.append({
                    "subsource": name,
                    "policy_ids": route_ids,
                    "collection_state": denied or "original_collection_candidate",
                    "original_source_urls_checked": len(urls),
                })
            permitted = sum(x["collection_state"] ==
                            "original_collection_candidate"
                            for x in subsources)
            if not permitted:
                blocker = "publisher_api_host_unclassified"
            elif permitted != len(subsources):
                blocker = "partially_classified_original_collection"
        else:
            route_ids, blocker = _classify_publisher_routes(
                endpoints, policies)
            ids.update(route_ids)
        result.append({
            "kind": kind,
            "collection_state": (
                blocker if blocker else "original_collection_candidate"),
            "policy_ids": sorted(ids), "source_urls_classified": len(endpoints),
            "subsource_collectors": subsources,
            "authorized_subsources": [x["subsource"] for x in subsources
                                     if x["collection_state"] ==
                                     "original_collection_candidate"],
            "role_count": group["role_count"],
            "affected_analyses": group["affected_analyses"],
            "original_proof_state": group["original_proof_state"],
            "source_is_not_first_publication": True,
            "requires_original_method_validation": True,
        })
    return {
        "operation": "original_structured_acquisition_plan",
        "artifacts": result,
        "eligible_collections": sum(
            len(x["authorized_subsources"])
            if x["subsource_collectors"] else
            x["collection_state"] == "original_collection_candidate"
            for x in result),
        "publisher_requests_made": 0,
        "data_written": False,
        "scientific_certification": False,
    }


def collect_structured_original(kind: str, *, root: Path, client,
                                cvm_year: int | None = None,
                                holdings_dir: Path | None = None,
                                sec_user_agent: str | None = None,
                                stan_max_requests: int = 4,
                                subsource: str | None = None) -> dict:
    """Invoke only existing registered native acquisition and receipt logic."""
    from .source_policy import require_managed_client
    require_managed_client(client)
    if kind not in CAPABILITIES or (
            CAPABILITIES[kind].collection != "publisher_collector"):
        raise ValueError("original_structured_collector_not_registered")
    if kind == "nber_chronology":
        from .nber_chronology import acquire_nber_chronology
        bundle = acquire_nber_chronology(root, client=client)
        return {"kind": kind, "archive": bundle.name, "state": "retained_original"}
    if kind == "cvm":
        from .cvm_profits import collect_cvm_annual_source
        if cvm_year is None:
            raise ValueError("cvm_original_year_required")
        report = collect_cvm_annual_source(root=root, year=cvm_year, client=client)
        return {"kind": kind, "archive": report["bundle_digest"],
                "state": "retained_original"}
    if kind in {"amne", "meip"}:
        from .multinational_sources import collect_multinational_source
        report = collect_multinational_source(kind, root=root, client=client)
        return {"kind": kind, "archive": report["bundle_digest"],
                "state": "retained_original"}
    if kind == "tiva":
        from .oecd_tiva import TIVA_SERIES, TivaClient
        if not TIVA_SERIES:
            raise ValueError("original_tiva_series_not_registered")
        reader = TivaClient(client, archive_dir=root)
        reader.fetch(sorted(TIVA_SERIES)[0])
        return {"kind": kind, "state": "retained_original"}
    if kind == "stan":
        from finance_dashboard.stan_pipeline import stan_pipeline
        from .oecd_corporate import OECD_MEMBER_ISO3
        report = stan_pipeline(client, root,
                               countries=tuple(sorted(OECD_MEMBER_ISO3)),
                               max_requests=stan_max_requests)
        if report["state"] in {
            "publisher_structure_unavailable_or_denied",
            "blocked_invalid_original_probe",
            "blocked_invalid_publisher_metadata",
            "stopped_publisher_policy_or_backpressure",
        }:
            raise ValueError("stan_original_collection_did_not_complete")
        return {"kind": kind, "state": report["state"],
                "requests_reported": report["publisher_requests"]}
    if kind == "ucits_holdings":
        if subsource == "ishares":
            from .ucits_holdings import collect_ucits_sources
            report = collect_ucits_sources(root=holdings_dir, client=client)
        elif subsource == "vanguard":
            from .vanguard_ucits_holdings import collect_vanguard_ucits_sources
            report = collect_vanguard_ucits_sources(
                root=holdings_dir, client=client)
        else:
            raise ValueError("ucits_original_subsource_must_be_explicit")
        if report["status"] != "complete":
            raise ValueError("ucits_" + subsource +
                             "_original_collection_partial_or_blocked")
        return {"kind": kind, "subsource": subsource,
                "state": "retained_original"}
    if kind == "sec_holdings":
        from .sec_holdings_sync import collect_configured
        result = collect_configured(root=holdings_dir,
                                    user_agent=sec_user_agent,
                                    client=client, max_filings_per_fund=2)
        if result["status"] != "complete":
            raise ValueError("sec_original_collection_partial_or_blocked")
        return {"kind": kind, "state": "retained_original"}
    raise ValueError("no_structured_original_collector")
