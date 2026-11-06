#!/usr/bin/env python3
"""One governed OECD STAN evidence pipeline: structure -> native surplus -> countries.

Every actual HTTP request uses the canonical managed OECD policy client.
The pipeline never assumes that legacy method-paper surplus codes are in the
current publisher codelist. All retained originals and retrieval receipts are
managed by existing immutable STAN evidence functions. Missing publisher
coverage and scientific acceptance remain explicitly unresolved.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from finance_dashboard.oecd_corporate import OECD_MEMBER_ISO3
from finance_dashboard.source_policy import managed_client
from finance_dashboard.source_policy_ledger import SourcePolicyGate
from finance_dashboard.source_policy_registry import PolicyRegistry
from finance_dashboard.stan_metadata import read_stan_structure
from scripts.phase2_stan_sources import (
    discover_measure_codes, plan_surplus_probe, probe_surplus,
    resolve_stan_country_selection, ordered_stan_acquisition_countries,
    acquire, plan_expansion,
)


def stan_pipeline(client, root: Path, *, countries: tuple[str, ...],
                  anchor: str = "PRT", probe_year: int = 2020,
                  start_year: int = 1970, max_requests: int = 4) -> dict:
    """Bound new publisher requests across ALL STAN stages, including metadata.

    A missing/invalid official measure codelist blocks surplus-code promotion.
    A single bounded total-activity probe cannot prove a historical country
    archive. Country acquisition proceeds only once the selected combined
    surplus measure has both native publisher metadata and an original
    source-verified observation in the chosen anchor country.
    """
    root = Path(root)
    if (not root.is_dir() or root.is_symlink() or not countries
            or len(set(countries)) != len(countries)
            or set(countries) - OECD_MEMBER_ISO3
            or anchor not in OECD_MEMBER_ISO3
            or not 1970 <= start_year <= date.today().year
            or not 1970 <= probe_year <= date.today().year
            or type(max_requests) is not int or max_requests < 1):
        raise ValueError("invalid_stan_pipeline_request")
    steps = []
    used = 0
    status = "complete_or_partial"
    metadata = read_stan_structure(root)
    if metadata["status"] == "invalid_metadata_original_or_receipt":
        return {
            "operation": "stan_original_pipeline",
            "state": "blocked_invalid_publisher_metadata",
            "publisher_requests": 0, "max_requests": max_requests,
            "remaining_budget": max_requests,
            "stages": [], "scientific_analysis_certified": False,
        }
    if metadata["status"] != "verified_publisher_structure":
        structure = discover_measure_codes(client, archive_root=root)
        used += structure["publisher_requests"]
        steps.append({
            "stage": "official_structure",
            "status": structure["state"],
            "failure": structure.get("failure_category"),
            "new_publisher_requests": structure["publisher_requests"],
            "archived": bool(structure.get("original_evidence")),
        })
        if structure["state"] != "validated_publisher_measure_codelist":
            status = "publisher_structure_unavailable_or_denied"
        else:
            metadata = read_stan_structure(root)
            if metadata["status"] != "verified_publisher_structure":
                status = "publisher_structure_not_independently_verified"
    else:
        steps.append({
            "stage": "official_structure", "status": "verified_cached",
            "new_publisher_requests": 0,
            "metadata_source_sha256": metadata.get("source_sha256"),
        })

    gate = plan_surplus_probe(root) if status == "complete_or_partial" else None
    if gate is not None:
        candidates = tuple(gate["candidate_measures"])
        if not candidates:
            status = "no_supported_native_surplus_in_verified_structure"
            steps.append({
                "stage": "native_surplus",
                "status": status,
                "published_unmatched_codes": gate["other_published_surplus_ids"],
                "new_publisher_requests": 0,
            })
        else:
            probe = probe_surplus(
                client, country=anchor, year=probe_year, candidates=candidates,
                archive_root=root, max_requests=max_requests - used)
            used += probe["publisher_requests"]
            steps.append({
                "stage": "native_surplus",
                "status": (
                    "invalid_original_probe" if probe.get(
                        "blocked_invalid_archived_probes")
                    else "source_policy_or_backpressure_stop"
                    if probe.get("stopped_on_publisher_backpressure")
                    else "publisher_originals_probed"),
                "new_publisher_requests": probe["publisher_requests"],
                "original_probes_archived": probe.get("original_probes_archived", 0),
                "cache_hits": probe.get("verified_cached_probes", 0),
                "validated_codes": [
                    item["candidate_measure"] for item in probe["checks"]
                    if item["state"] == "validated_native_csv"],
                "failures": [{
                    "measure": item["candidate_measure"],
                    "reason": item.get("failure_category", item["state"]),
                } for item in probe["checks"]
                    if item["state"] not in {"validated_native_csv"}],
            })
            if probe.get("blocked_invalid_archived_probes"):
                status = "blocked_invalid_original_probe"
            elif probe.get("stopped_on_publisher_backpressure"):
                status = "stopped_publisher_policy_or_backpressure"

    native = resolve_stan_country_selection(
        root, anchor_country=anchor, probe_year=probe_year,
        explicit_measures=None)
    selection = list(native["native_measures"])
    archived = already_verified = 0
    if status == "complete_or_partial":
        if native["state"] != "verified_surplus_native_code":
            status = ("deferred_request_budget" if used >= max_requests else
                      "native_surplus_original_not_verified")
            steps.append({
                "stage": "full_historical_country_scope",
                "status": "not_authorized_without_source_proven_surplus",
                "new_publisher_requests": 0,
            })
        elif used >= max_requests:
            status = "deferred_request_budget"
            steps.append({
                "stage": "full_historical_country_scope",
                "status": "deferred_request_budget",
                "new_publisher_requests": 0,
            })
        else:
            ordered = ordered_stan_acquisition_countries(
                countries, selection=native, anchor_country=anchor)
            acquired = acquire(
                client, root, countries=ordered, start_year=start_year,
                measures=tuple(selection),
                max_requests=max_requests - used, quiet=True)
            used += acquired["publisher_requests"]
            archived = acquired["original_responses_archived"]
            already_verified = acquired["already_verified_archives"]
            steps.append({
                "stage": "full_historical_country_scope",
                "status": "stopped_on_policy" if acquired[
                    "stopped_on_source_policy"] else "stopped_on_backpressure"
                    if acquired["stopped_on_publisher_backpressure"]
                    else "partial_request_budget" if acquired[
                        "deferred_request_budget"] else
                    "country_original_acquisition_finished",
                "new_publisher_requests": acquired["publisher_requests"],
                "originals_archived": archived,
                "already_verified": already_verified,
                "deferred_request_budget": acquired["deferred_request_budget"],
                "failures": [{
                    "country": item["country"],
                    "status": item["status"],
                    "reason": item.get("failure_category"),
                } for item in acquired["acquisitions"]
                    if item["status"] not in {
                        "retained", "already_verified",
                        "refreshed_revised", "refreshed_unchanged",
                        "deferred_request_budget"}][:8],
            })
            if acquired["stopped_on_source_policy"] or acquired[
                    "stopped_on_publisher_backpressure"]:
                status = "stopped_publisher_policy_or_backpressure"
            elif acquired["deferred_request_budget"]:
                status = "deferred_request_budget"
            elif acquired["acquisition_failures"]:
                status = "partial_source_acquisition_failure"
            else:
                status = "all_requested_country_scopes_checked"
    if used > max_requests:
        raise RuntimeError("stan_pipeline_request_budget_exceeded")
    plan = plan_expansion(
        root, countries=countries, start_year=start_year,
        measures=tuple(selection), max_requests=min(4, max_requests))
    return {
        "operation": "stan_original_pipeline",
        "state": status,
        "publisher_requests": used,
        "max_requests": max_requests,
        "remaining_budget": max_requests - used,
        "anchor_country": anchor,
        "probe_year": probe_year,
        "source_measure_selection": selection,
        "selection_evidence": native["selection_evidence"],
        "metadata_status": plan["publisher_measure_metadata"],
        "original_country_scopes_archived_this_run": archived,
        "original_country_scopes_previously_verified": already_verified,
        "verified_country_scopes": len(plan["verified_countries"]),
        "verified_country_scopes_with_numeric_measure_presence": len(plan[
            "verified_country_scopes_with_each_requested_measure_observed"]),
        "pending_country_scopes": len(plan["pending_countries"]),
        "next_country_batch": plan["suggested_country_batches"][0]
                              if plan["suggested_country_batches"] else [],
        "stages": steps,
        "source_originals_immutable": True,
        "same_scope_accounting_certified": False,
        "first_publication_verified": False,
        "scientific_analysis_certified": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--acquire", action="store_true",
                        help="Explicitly run governed source acquisition; otherwise read-only")
    parser.add_argument("--max-requests", type=int, default=4,
                        help="Total new publisher requests across all steps (default 4)")
    parser.add_argument("--countries", nargs="+", choices=sorted(OECD_MEMBER_ISO3),
                        default=sorted(OECD_MEMBER_ISO3))
    parser.add_argument("--source-anchor", choices=sorted(OECD_MEMBER_ISO3),
                        default="PRT")
    parser.add_argument("--probe-year", type=int, default=2020)
    parser.add_argument("--start-year", type=int, default=1970)
    args = parser.parse_args(argv)
    countries = tuple(args.countries)
    if len(set(countries)) != len(countries) or args.max_requests < 1:
        parser.error("invalid countries or non-positive publisher request budget")
    if not (1970 <= args.start_year <= date.today().year
            and 1970 <= args.probe_year <= date.today().year):
        parser.error("invalid publisher history year")
    try:
        if args.acquire:
            # Advisory, read-only publisher preflight: a known policy denial
            # or cooldown requires no request and must never be overridden.
            # The managed client remains the sole atomic HTTP permit checker.
            available = SourcePolicyGate(
                registry=PolicyRegistry()).availability("oecd-sdmx")
            if available["state"] != "ready":
                result = {
                    "operation": "stan_original_pipeline",
                    "state": "publisher_policy_" + available["state"],
                    "policy_id": available["policy_id"],
                    "policy_reason": available["reason"],
                    "next_request_eligible_at": available["retry_at"],
                    "publisher_requests": 0,
                    "max_requests": args.max_requests,
                    "scientific_analysis_certified": False,
                }
            else:
                with managed_client(timeout=60, follow_redirects=False) as client:
                    result = stan_pipeline(
                        client, args.evidence_dir, countries=countries,
                        anchor=args.source_anchor, probe_year=args.probe_year,
                        start_year=args.start_year, max_requests=args.max_requests)
        else:
            native = resolve_stan_country_selection(
                args.evidence_dir, anchor_country=args.source_anchor,
                probe_year=args.probe_year, explicit_measures=None)
            measure = tuple(native["native_measures"])
            plan = plan_expansion(
                args.evidence_dir, countries=countries,
                start_year=args.start_year, measures=measure,
                max_requests=args.max_requests)
            result = {
                "operation": "stan_original_pipeline_plan",
                "state": "read_only",
                "metadata_status": plan["publisher_measure_metadata"],
                "next_evidence_action": plan["next_evidence_action"],
                "native_measures": list(measure),
                "selection_evidence": native["selection_evidence"],
                "verified_country_scopes": len(plan["verified_countries"]),
                "pending_country_scopes": len(plan["pending_countries"]),
                "next_country_batch": plan["suggested_country_batches"][0]
                                      if plan["suggested_country_batches"] else [],
                "publisher_requests": 0,
                "scientific_analysis_certified": False,
            }
    except Exception as error:
        from finance_dashboard.service import safe_source_failure_code
        result = {
            "operation": "stan_original_pipeline",
            "state": "pipeline_failed",
            "failure_code": safe_source_failure_code(error),
            "scientific_analysis_certified": False,
        }
    print(json.dumps(result, separators=(",", ":"), allow_nan=False))
    return 0 if result["state"] in {
        "read_only", "all_requested_country_scopes_checked",
        "deferred_request_budget", "complete_or_partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
