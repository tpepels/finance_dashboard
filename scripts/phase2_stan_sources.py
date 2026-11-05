#!/usr/bin/env python3
"""Acquire or inspect immutable OECD STAN 2025 native country-industry originals.

No scalar macro table is written. Structured country/industry/year values are
archived via the existing hashed original-source and receipt boundary.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from finance_dashboard.oecd_corporate import OECD_MEMBER_ISO3
from finance_dashboard.stan_originals import (
    MAX_STAN_SOURCE_BYTES, STAN_MEASURES, STAN_ALLOWED_MEASURES,
    STAN_SURPLUS_CANDIDATES, STAN_VERIFIED_PORTUGAL_MEASURES,
    parse_stan_original_csv, read_stan_evidence, stan_source_request,
    store_stan_original,
)
from finance_dashboard.stan_research import audit_stan_originals, summarize_stan_readiness
from finance_dashboard.source_policy import (managed_client, require_managed_client,
                                            publisher_interruption)
from finance_dashboard.stan_metadata import (
    STRUCTURE_URL, STRUCTURE_PARAMS, STRUCTURE_ACCEPT,
    MAX_STRUCTURE_BYTES, parse_stan_measure_structure,
    read_stan_structure, store_stan_structure,
)


def diagnose_publisher(client, *, country: str, year: int) -> dict:
    """Bounded native SDMX request matrix; report statuses without storing bodies.

    The first publisher-documented key (total activity, B1G, current national
    currency) isolates endpoint and CSV handling. Further requests distinguish
    a bad candidate measure from an oversized unbounded query.
    """
    from hashlib import sha256
    from finance_dashboard.stan_originals import STAN_MEASURES, parse_stan_original_csv

    tests = [
        ("published_value_added_control", ("B1G",), "_T", True),
        ("published_value_added_no_format", ("B1G",), "_T", False),
        ("all_industries_value_added_one_year", ("B1G",), None, True),
        *[(f"native_measure_{measure}", (measure,), "_T", True)
          for measure in STAN_MEASURES if measure != "B1G"],
        ("five_measure_total_activity_one_year", STAN_MEASURES, "_T", True),
    ]
    require_managed_client(client)
    results = []
    sent_requests = 0
    for name, measures, activity, with_format in tests:
        url, params = stan_source_request(country, year, measures=measures,
                                          activity=activity, end_year=year)
        if with_format:
            params = {**params, "format": "csvfile"}
        item = {"check": name, "activity": activity or "all_industries",
                "measures_requested": list(measures),
                "year": year, "format_parameter": with_format,
                "state": "source_check_failed"}
        interruption = None
        try:
            with client.stream("GET", url, params=params,
                               headers={"Accept": "text/csv"}) as response:
                item["http_status"] = response.status_code
                response.raise_for_status()
                payload = bytearray()
                for chunk in response.iter_bytes():
                    if len(payload) + len(chunk) > MAX_STAN_SOURCE_BYTES:
                        raise ValueError("Original source exceeds diagnostic limits")
                    payload.extend(chunk)
            # A 204 response is an empty published selection, not valid data.
            if not payload:
                item["state"] = "empty_response"
            else:
                raw = bytes(payload)
                item["source_sha256"] = sha256(raw).hexdigest()
                parsed = parse_stan_original_csv(
                    raw, country=country, start_year=year,
                    expected_measures=measures, expected_activity=activity,
                    end_year=year,
                )
                item.update(
                    state="validated_native_csv",
                    original_numeric_observations=parsed["numeric_observations"],
                    observed_measure_counts=parsed["native_measure_observation_counts"],
                    observed_industries=parsed["reported_industries"],
                    source_dataflow_field_verified=parsed["source_dataflow_field_verified"],
                )
        except Exception as exc:
            # Raw error payloads and URLs are never displayed or accepted.
            item["reason_type"] = type(exc).__name__
            interruption = publisher_interruption(exc, item.get("http_status"))
            if interruption:
                item["failure_category"] = interruption["category"]
                if interruption["policy_stop"]:
                    item["retry_after_seconds"] = interruption.get("retry_after_seconds")
            elif item.get("http_status") in (204, 404):
                item["failure_category"] = "no_published_observations_for_selection"
            elif item.get("http_status") in (400, 406, 422):
                item["failure_category"] = "publisher_rejected_source_filter"
            else:
                item["failure_category"] = "transport_or_native_schema"
        if interruption is None or interruption["request_emitted"]:
            sent_requests += 1
        results.append(item)
        if interruption is not None:
            break  # Shared policy owns cooldowns; stop this diagnostic batch.
    return {
        "phase": "phase2",
        "operation": "oecd_stan_native_request_diagnostics",
        "country": country, "probe_year": year,
        "checks": results,
        "publisher_requests": sent_requests,
        "checks_performed": len(results),
        "no_archive_writes": True, "no_macro_database_writes": True,
        "original_role_bindings_created": 0,
        "full_historical_acquisition_verified": False,
        "scientific_analysis_certified": False,
        "first_publication_verified": False,
    }



def discover_measure_codes(client, *, archive_root: Path | None = None) -> dict:
    """One governed SDMX structure request; optional immutable original capture."""
    require_managed_client(client)
    report = {
        "phase": "phase2", "operation": "stan_publisher_measure_metadata",
        "state": "source_check_failed", "publisher_requests": 1,
        "no_archive_writes": True, "no_macro_database_writes": True,
        "scientific_analysis_certified": False,
    }
    try:
        with client.stream(
                "GET", STRUCTURE_URL, params=STRUCTURE_PARAMS,
                headers={"Accept": STRUCTURE_ACCEPT}) as response:
            report["http_status"] = response.status_code
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_bytes():
                if len(body) + len(chunk) > MAX_STRUCTURE_BYTES:
                    raise ValueError("STAN publisher structure exceeds safe size")
                body.extend(chunk)
        report.update(parse_stan_measure_structure(bytes(body)))
        if archive_root is not None:
            report["original_evidence"] = store_stan_structure(
                bytes(body), root=archive_root)
            report["no_archive_writes"] = False
        report["state"] = "validated_publisher_measure_codelist"
    except Exception as exc:
        report["reason_type"] = type(exc).__name__
        interruption = publisher_interruption(exc, report.get("http_status"))
        if interruption:
            report["failure_category"] = interruption["category"]
            if not interruption["request_emitted"]:
                report["publisher_requests"] = 0
            if interruption["policy_stop"]:
                report["retry_after_seconds"] = interruption.get("retry_after_seconds")
            return report
        code = report.get("http_status")
        if code == 429:
            report["failure_category"] = "publisher_rate_limited"
        elif code == 503:
            report["failure_category"] = "publisher_unavailable"
        elif code == 404:
            report["failure_category"] = "publisher_structure_not_found"
        elif isinstance(code, int) and code >= 500:
            report["failure_category"] = "publisher_http_5xx"
        else:
            report["failure_category"] = "publisher_structure_invalid_or_unavailable"
    return report


def plan_surplus_probe(root: Path) -> dict:
    """Fail closed unless a verified 2025 structure advertises exact candidates.

    This is offline metadata classification, never an inference of country data.
    Legacy method-paper codes cannot independently authorize live requests.
    """
    metadata = read_stan_structure(root)
    verified = metadata["status"] == "verified_publisher_structure"
    published_surplus = {
        row["id"] for row in metadata.get("surplus_measures", [])
    } if verified else set()
    candidates = [
        code for code in STAN_SURPLUS_CANDIDATES
        if code in published_surplus
    ]
    return {
        "phase": "phase2", "operation": "stan_surplus_metadata_gate",
        "state": ("ready_for_bounded_publisher_probe" if candidates
                  else "publisher_structure_has_no_supported_surplus_code"
                  if verified else "verified_publisher_structure_required"),
        "metadata_status": metadata["status"],
        "source_sha256": metadata.get("source_sha256"),
        "candidate_measures": candidates,
        "other_published_surplus_ids": sorted(published_surplus - set(candidates)),
        "publisher_requests": 0,
        "country_coverage_verified": False,
        "scientific_analysis_certified": False,
    }


def probe_surplus(client, *, country: str, year: int,
                  candidates: tuple[str, ...] | None = None) -> dict:
    """At most two exact-year, total-activity candidate requests; no archive writes.

    OECD historical methods use B2N_B3_N and B2G_B3G for combined mixed
    income. The live 2025 publisher dataflow must still validate each code.
    """
    from hashlib import sha256
    require_managed_client(client)
    requested = STAN_SURPLUS_CANDIDATES if candidates is None else tuple(candidates)
    if (not requested or len(requested) > len(STAN_SURPLUS_CANDIDATES)
            or len(set(requested)) != len(requested)
            or not set(requested) <= set(STAN_SURPLUS_CANDIDATES)):
        raise ValueError("invalid_verified_stan_surplus_candidates")
    checks = []
    sent_requests = 0
    stopped = False
    for candidate in requested:
        url, params = stan_source_request(
            country, year, measures=(candidate,),
            activity="_T", end_year=year)
        entry = {"candidate_measure": candidate, "probe_year": year,
                 "state": "source_check_failed"}
        interruption = None
        try:
            with client.stream("GET", url, params={**params, "format": "csvfile"},
                               headers={"Accept": "text/csv"}) as response:
                entry["http_status"] = response.status_code
                response.raise_for_status()
                payload = bytearray()
                for chunk in response.iter_bytes():
                    if len(payload) + len(chunk) > 2_000_000:
                        raise ValueError("Publisher surplus probe exceeds 2 MB")
                    payload.extend(chunk)
            raw = bytes(payload)
            parsed = parse_stan_original_csv(
                raw, country=country, start_year=year,
                expected_measures=(candidate,), expected_activity="_T",
                end_year=year)
            if not parsed["source_dataflow_field_verified"]:
                raise ValueError("Publisher native dataflow identity missing")
            entry.update(state="validated_native_csv",
                         original_numeric_observations=parsed["numeric_observations"],
                         observed_measure_counts=parsed["native_measure_observation_counts"],
                         source_sha256=sha256(raw).hexdigest())
        except Exception as exc:
            entry["reason_type"] = type(exc).__name__
            interruption = publisher_interruption(exc, entry.get("http_status"))
            if interruption:
                entry["failure_category"] = interruption["category"]
                entry["retry_after_seconds"] = interruption.get("retry_after_seconds")
            elif entry.get("http_status") == 404:
                entry["failure_category"] = "no_published_observations_for_selection"
            else:
                entry["failure_category"] = "publisher_rejected_or_invalid_native_csv"
        if interruption is None or interruption["request_emitted"]:
            sent_requests += 1
        checks.append(entry)
        if interruption is not None:
            stopped = True
            break
    return {
        "phase": "phase2", "operation": "native_stan_surplus_code_probe",
        "country": country, "checks": checks,
        "publisher_requests": sent_requests,
        "stopped_on_publisher_backpressure": stopped,
        "no_archive_writes": True, "no_macro_database_writes": True,
        "code_availability_requires_live_csv": True,
        "scientific_analysis_certified": False,
    }


def acquire(client, root: Path, *, countries: tuple[str, ...], start_year: int,
            measures: tuple[str, ...] | None = None,
            max_requests: int | None = None,
            quiet: bool = False) -> dict:
    """Acquire only an exact declared native selection; no automatic retries.

    OECD publishes at most 60 data responses per hour; an HTTP 429/503 ends
    this run immediately. The country cache uses independently rehashed bytes.
    Requests never silently fill the unverified B2N role.
    """
    require_managed_client(client)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("existing_non_symlink_evidence_directory_required")
    if max_requests is not None and max_requests < 1:
        raise ValueError("positive_request_budget_required")
    selection = (STAN_VERIFIED_PORTUGAL_MEASURES if measures is None
                 else tuple(measures))
    if not countries:
        raise ValueError("countries_required")
    stan_source_request(countries[0], start_year, measures=selection)
    report = []
    backpressure = None
    policy_stop = None
    retry_after_seconds = None
    publisher_requests = 0
    for number, country in enumerate(countries, start=1):
        entry = {"country": country, "status": "acquisition_failed",
                 "requested_native_measures": list(selection),
                 "unresolved_candidate_measures": sorted(set(STAN_MEASURES) - set(selection))}
        if backpressure or policy_stop:
            entry.update(
                status=("deferred_publisher_backpressure" if backpressure
                        else "skipped_source_policy_block"),
                failure_category=backpressure or policy_stop)
            report.append(entry)
            continue
        if not quiet:
            print(f"STAN {number}/{len(countries)}: {country}",
                  file=sys.stderr, flush=True)
        country_evidence = read_stan_evidence(root, countries=(country,))["country_results"][0]
        if country_evidence["status"] == "invalid_original_stan":
            entry.update(status="invalid_existing_original_archive",
                         failure_category="original_archive_integrity")
            report.append(entry)
            continue
        matching_scope = "measure-" + "+".join(selection)
        if any(item["scope"] == matching_scope
               for item in country_evidence.get("source_scopes", [])
               if item["requested_since"] == start_year):
            entry.update(status="already_verified", cache_hit=True)
            report.append(entry)
            continue
        if max_requests is not None and publisher_requests >= max_requests:
            entry.update(status="deferred_request_budget",
                         failure_category="request_budget_exhausted")
            report.append(entry)
            continue
        try:
            url, params = stan_source_request(country, start_year, measures=selection)
            publisher_requests += 1
            with client.stream("GET", url, params={**params, "format": "csvfile"},
                               headers={"Accept": "text/csv"}) as response:
                entry["http_status"] = response.status_code
                response.raise_for_status()
                payload = bytearray()
                for chunk in response.iter_bytes():
                    if len(payload) + len(chunk) > MAX_STAN_SOURCE_BYTES:
                        raise ValueError("STAN source exceeds archive bounds")
                    payload.extend(chunk)
            preserved = store_stan_original(
                bytes(payload), country=country, start_year=start_year,
                root=root, measures=selection,
            )
            entry.update(status="retained",
                         original_response_sha256=preserved["original_response_sha256"],
                         bundle_digest=preserved["bundle_digest"],
                         original_receipt_sha256=preserved["receipt_sha256"],
                         numeric_observations=preserved["facts"]["numeric_observations"],
                         observed_native_measure_counts=preserved[
                             "facts"]["native_measure_observation_counts"])
            if not quiet:
                print(f"STAN {number}/{len(countries)}: retained",
                      file=sys.stderr, flush=True)
        except Exception as exc:
            entry["reason_type"] = type(exc).__name__
            code = entry.get("http_status")
            interruption = publisher_interruption(exc, code)
            if interruption:
                entry["failure_category"] = interruption["category"]
                if interruption["policy_stop"]:
                    policy_stop = interruption["category"]
                    retry_after_seconds = interruption.get("retry_after_seconds")
                    publisher_requests -= 1  # Never transmitted beyond the gate.
                    entry["status"] = "blocked_source_policy"
                else:
                    backpressure = interruption["category"]
            elif code == 404:
                entry["failure_category"] = "no_published_observations_for_selection"
            else:
                entry["failure_category"] = "transport_or_native_schema"
            if not quiet:
                print(f"STAN {number}/{len(countries)}: failed ({type(exc).__name__})",
                      file=sys.stderr, flush=True)
        report.append(entry)
    evidence = read_stan_evidence(root, countries=countries)
    completed = {"retained", "already_verified"}
    return {
        "phase": "phase2", "operation": "original_stan_industry_acquisition",
        "requested_start_year": start_year, "countries_requested": len(countries),
        "requested_native_measures": list(selection),
        "unresolved_candidate_measures": sorted(set(STAN_MEASURES) - set(selection)),
        "original_responses_archived": sum(item["status"] == "retained" for item in report),
        "already_verified_archives": sum(item["status"] == "already_verified" for item in report),
        "acquisition_failures": sum(item["status"] not in completed for item in report),
        "stopped_on_publisher_backpressure": backpressure is not None,
        "stopped_on_source_policy": policy_stop is not None,
        "stop_reason": backpressure or policy_stop,
        "retry_after_seconds": retry_after_seconds,
        "publisher_requests": publisher_requests,
        "request_budget": max_requests,
        "deferred_request_budget": sum(
            item["status"] == "deferred_request_budget" for item in report),
        "last_country_requested": next(
            (item["country"] for item in reversed(report)
             if "http_status" in item), None),
        "acquisitions": report,
        "source_evidence": evidence,
        "no_macro_database_writes": True,
        "scientific_analysis_certified": False,
        "first_publication_verified": False,
    }



def plan_expansion(root: Path, *, countries: tuple[str, ...],
                   start_year: int, measures: tuple[str, ...],
                   max_requests: int = 4) -> dict:
    """Read-only country acquisition plan using the canonical verified reader.

    A missing selection is listed as pending, never treated as an implicit
    source observation. Invalid archives are blocked rather than overwritten.
    """
    if not 1 <= max_requests <= 60:
        raise ValueError("invalid_stan_request_budget")
    if not countries:
        raise ValueError("countries_required")
    stan_source_request(countries[0], start_year, measures=measures)
    evidence = read_stan_evidence(root, countries=countries)
    selected_scope = "measure-" + "+".join(measures)
    verified = []
    pending = []
    invalid = []
    scope_measure_gaps = []
    for row in evidence["country_results"]:
        country = row["country"]
        if row["status"] == "invalid_original_stan":
            invalid.append(country)
        else:
            matched = next((
                scope for scope in row.get("source_scopes", [])
                if scope["scope"] == selected_scope
                and scope["requested_since"] == start_year
            ), None)
            if matched is None:
                pending.append(country)
            else:
                verified.append(country)
                absent = sorted(set(measures) - set(matched["native_measure_counts"]))
                if absent:
                    scope_measure_gaps.append({
                        "country": country,
                        "measures_without_numeric_observations": absent,
                        "numeric_observations_in_source": matched["numeric_observations"],
                    })
    batches = [
        pending[i:i + max_requests]
        for i in range(0, len(pending), max_requests)
    ]
    return {
        "phase": "phase2", "operation": "stan_expansion_plan",
        "requested_start_year": start_year,
        "native_measures": list(measures),
        "scope": selected_scope,
        "verified_countries": verified,
        "verified_scopes_with_missing_measures": scope_measure_gaps,
        "publisher_measure_metadata": read_stan_structure(root)["status"],
        "pending_countries": pending,
        "blocked_invalid_original_countries": invalid,
        "request_budget_per_batch": max_requests,
        "suggested_country_batches": batches,
        "planned_publisher_requests": len(pending),
        "publisher_requests_made": 0,
        "no_archive_writes": True, "no_macro_database_writes": True,
        "scientific_analysis_certified": False,
    }


def brief_report(data: dict) -> dict:
    """Presentation summary only; source verification and archives are unchanged."""
    if data.get("operation") == "stan_readiness":
        return {
            "operation": "stan_readiness",
            "status_counts": data["status_counts"],
            "verified_scope_countries": data["verified_scope_countries"],
            "same_scope_identity_countries": data["same_scope_identity_countries"],
            "publisher_measure_metadata": data["publisher_measure_metadata"],
            "incomplete_verified": [{
                "country": row["country"],
                "status": row["status"],
                "per_measure_max_numeric": row.get("per_measure_max_numeric", {}),
                "missing_in_all_scopes": row.get("core_measures_absent_in_all_scopes", []),
                "core_four_overlap": row.get("core_four_max_industry_years_in_single_scope", 0),
            } for row in data["country_readiness"]
               if row["status"] == "insufficient_same_scope_measure_coverage"][:8],
            "additional_incomplete": max(0,
                sum(row["status"] == "insufficient_same_scope_measure_coverage"
                    for row in data["country_readiness"]) - 8),
            "scientific_analysis_certified": False,
        }
    if data.get("operation") == "stan_expansion_plan":
        return {
            "operation": "plan_expansion",
            "publisher_measure_metadata": data["publisher_measure_metadata"],
            "incomplete_verified_scopes": data["verified_scopes_with_missing_measures"][:8],
            "measures": data["native_measures"],
            "verified": data["verified_countries"],
            "pending_count": len(data["pending_countries"]),
            "blocked_invalid": data["blocked_invalid_original_countries"],
            "next_batch": data["suggested_country_batches"][0]
                          if data["suggested_country_batches"] else [],
            "batch_count": len(data["suggested_country_batches"]),
            "publisher_requests_made": 0,
        }
    if data.get("operation") == "stan_inspected_publisher_measure_metadata":
        return {
            "operation": "inspect_metadata", "state": data["state"],
            "status": data["metadata"]["status"],
            "source_sha256": data["metadata"].get("source_sha256"),
            "surplus_measures": data["metadata"].get("surplus_measures"),
            "historical_candidates_present": data["metadata"].get("historical_candidates_present"),
            "originals_verified": data["metadata"].get("originals_verified"),
        }
    if data.get("operation") == "stan_publisher_measure_metadata":
        return {
            "operation": "discover_measures", "state": data["state"],
            "http": data.get("http_status"),
            "failure": data.get("failure_category"),
            "measure_code_count": data.get("measure_code_count"),
            "surplus_measures": data.get("surplus_measures"),
            "historical_candidates_present": data.get("historical_candidates_present"),
            "source_sha256": data.get("source_sha256"),
            "country_coverage_verified": False,
            "archived": bool(data.get("original_evidence")),
            "receipt_sha256": data.get("original_evidence", {}).get("receipt_sha256"),
        }
    if data.get("operation") == "stan_surplus_metadata_gate":
        return {
            "operation": "surplus_metadata_gate",
            "state": data["state"],
            "metadata_status": data["metadata_status"],
            "candidate_measures": data["candidate_measures"],
            "other_published_surplus_ids": data["other_published_surplus_ids"],
            "source_sha256": data["source_sha256"],
            "publisher_requests": 0,
        }
    if "surplus_probe" in data:
        probe = data["surplus_probe"]
        out = {
            "operation": "resolve_surplus", "country": probe["country"],
            "selected": data.get("selected_observed_surplus_measure"),
            "checks": [{
                "measure": row["candidate_measure"], "state": row["state"],
                "http": row.get("http_status"), "failure": row.get("failure_category"),
            } for row in probe["checks"]],
            "publisher_backpressure": probe["stopped_on_publisher_backpressure"],
            "metadata_source_sha256": data.get("metadata_source_sha256"),
        }
        if "acquisition" in data:
            out["acquisition"] = brief_report(data["acquisition"])
        if "accounting_audit" in data:
            out["accounting_audit"] = brief_report(data["accounting_audit"])
        return out
    if "diagnostics" in data:
        return {"operation": "diagnose", "countries": [{
            "country": country["country"], "checks": [{
                "check": row["check"], "http": row.get("http_status"),
                "state": row["state"], "failure": row.get("failure_category"),
            } for row in country["checks"]]
        } for country in data["diagnostics"]]}
    op = data.get("operation")
    if op == "original_stan_industry_acquisition":
        from collections import Counter
        rows = data["acquisitions"]
        exceptional = [r for r in rows if r["status"] not in (
            "already_verified", "deferred_request_budget")]
        return {
            "operation": "acquire", "measures": data["requested_native_measures"],
            "statuses": dict(sorted(Counter(r["status"] for r in rows).items())),
            "requests": data.get("publisher_requests"),
            "backpressure": data["stopped_on_publisher_backpressure"],
            "policy_stop": data.get("stopped_on_source_policy", False),
            "stop_reason": data.get("stop_reason"),
            "last_country_requested": data.get("last_country_requested"),
            "countries_with_selected_scope": sum(
                r["status"] in ("retained", "already_verified") for r in rows),
            "countries_with_any_verified_scope": data["source_evidence"]["country_count"],
            "events": [{
                "country": r["country"], "status": r["status"],
                "http": r.get("http_status"), "observations": r.get("numeric_observations"),
                "failure": r.get("failure_category"),
            } for r in exceptional[:5]],
            "additional_events": max(0, len(exceptional) - 5),
            "scientific_analysis_certified": False,
        }
    if op == "stan_original_industry_accounting_audit":
        countries = []
        for c in data["country_audits"][:5]:
            scopes = []
            for s in c["scope_audits"][:3]:
                coverage = s["coverage"]
                scopes.append({
                    "scope": s["scope"], "industry_years": s["distinct_industry_years"],
                    "core_four_overlap": s["core_four_matched_industry_years"],
                    "years_observed": coverage["observed_year_count"],
                    "flags": coverage["source_status_flag_counts"],
                    "measure_spans": {
                        key: [value["first_observed_year"], value["last_observed_year"],
                              value["numeric_observations"]]
                        for key, value in coverage["per_measure"].items()
                    },
                    "identities": {
                        name: {"matched": v["eligible_matched_industry_years"],
                               "outside_precision": v["outside_printed_precision_bounds"],
                               "non_A": v["groups_with_non_A_source_flags"],
                               "largest": v["largest_residual_examples"][:1]}
                        for name, v in s["identity_checks"].items()
                    },
                })
            compare = c.get("cross_scope_reconciliation", {})
            comparisons = compare.get("comparisons", [])
            countries.append({
                "country": c["country"], "status": c["status"], "scopes": scopes,
                "additional_scopes": max(0, len(c["scope_audits"]) - 3),
                "cross_scope": {
                    "pairs": compare.get("compared_scope_pairs", 0),
                    "overlap": sum(x["same_measure_industry_year_overlap"]
                                   for x in comparisons),
                    "value_disagreements": sum(
                        x["numeric_value_disagreements_same_unit"]
                        for x in comparisons),
                    "unit_conflicts": sum(
                        x["incompatible_or_unreported_units"]
                        for x in comparisons),
                    "flag_changes": sum(x["source_flag_changes"]
                                        for x in comparisons),
                },
            })
        return {"operation": "audit", "countries": countries,
                "additional_countries": max(0, len(data["country_audits"]) - 5),
                "cross_scope_join_performed": False, "scientific_analysis_certified": False}
    if op == "original_stan_evidence_inspection":
        e = data["source_evidence"]
        return {
            "operation": "inspect", "status": e["status"],
            "verified_countries": e["country_count"],
            "countries": [{
                "country": c["country"], "status": c["status"],
                "observations": c.get("observations"),
                "measures": c.get("covered_native_measures"),
                "scopes": len(c.get("source_scopes", [])),
            } for c in e["country_results"][:5]],
            "additional_countries": max(0, len(e["country_results"]) - 5),
            "full_history_verified": e["full_history_verified"],
        }
    return data


def emit_report(data: dict, *, brief: bool) -> None:
    if brief:
        print(json.dumps(brief_report(data), separators=(",", ":")))
    else:
        print(json.dumps(data, indent=2))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True,
                        help="Existing original source-evidence archive root")
    parser.add_argument("--brief", action="store_true",
                        help="One-line summary instead of full JSON")
    parser.add_argument("--countries", nargs="+",
                        default=sorted(OECD_MEMBER_ISO3),
                        help="OECD ISO3 member codes (default: all 38 countries)")
    parser.add_argument("--since", default="1970-01-01",
                        help="First requested source year, YYYY-01-01")
    parser.add_argument("--acquire", action="store_true",
                        help="Download, validate and retain original responses (otherwise read-only)")
    parser.add_argument("--expand", action="store_true",
                        help="Bounded, resumable acquisition of OECD member originals")
    parser.add_argument("--plan-expansion", action="store_true",
                        help="Read-only cached/missing/invalid country scope plan")
    parser.add_argument("--max-requests", type=int,
                        help="Limit new publisher requests; --expand defaults to 4")
    parser.add_argument("--after-country", choices=sorted(OECD_MEMBER_ISO3),
                        help="Continue a sorted country batch after this ISO3 code")
    parser.add_argument("--discover-measures", action="store_true",
                        help="One read-only publisher structure request; list actual surplus codes")
    parser.add_argument("--acquire-metadata", action="store_true",
                        help="One governed publisher structure request, retain original XML and receipt")
    parser.add_argument("--inspect-metadata", action="store_true",
                        help="Read-only verification of retained OECD STAN structure XML")
    parser.add_argument("--resolve-surplus", action="store_true",
                        help="Probe bounded native net/gross combined-surplus candidates; "
                             "with --acquire, retain a separate five-measure source")
    parser.add_argument("--readiness", action="store_true",
                        help="Read-only per-country STAN source and identity readiness; no publisher calls")
    parser.add_argument("--audit", action="store_true",
                        help="Read-only, per-scope original industry-year overlap and identity audit")
    parser.add_argument("--measures", nargs="+", choices=sorted(STAN_ALLOWED_MEASURES),
                        help="Exact native measure selection for --acquire; default: "
                             "four confirmed Portugal measure codes, excluding unresolved B2N")
    parser.add_argument("--diagnose", action="store_true",
                        help="Bounded one-year publisher key/schema diagnostics, no archive writes")
    parser.add_argument("--probe-year", type=int, default=2020,
                        help="Exact calendar year for --diagnose (default 2020)")
    args = parser.parse_args(argv)
    countries = tuple(dict.fromkeys(args.countries))
    if len(countries) != len(args.countries) or any(
            country not in OECD_MEMBER_ISO3 for country in countries):
        parser.error("Invalid or duplicated OECD country")
    if args.after_country:
        if not args.expand or args.after_country not in countries:
            parser.error("--after-country requires --expand and an included OECD member")
        countries = countries[countries.index(args.after_country) + 1:]
        if not countries:
            parser.error("No countries remain after --after-country")
    if args.max_requests is not None and args.max_requests < 1:
        parser.error("--max-requests must be positive")
    if args.expand and args.acquire:
        parser.error("Use either --expand or --acquire")
    if args.plan_expansion and (
            args.acquire or args.expand or args.audit or args.diagnose
            or args.resolve_surplus or args.discover_measures or args.after_country
            or args.readiness or args.acquire_metadata or args.inspect_metadata):
        parser.error("--plan-expansion is a standalone read-only operation")
    if args.discover_measures and (
            args.expand or args.acquire or args.resolve_surplus or args.diagnose
            or args.audit or args.measures or args.after_country or args.readiness
            or args.acquire_metadata or args.inspect_metadata):
        parser.error("--discover-measures is a standalone read-only operation")
    if args.resolve_surplus and (args.expand or args.diagnose or args.audit or
                                 len(countries) != 1 or args.measures):
        parser.error("--resolve-surplus requires one country and no other mode/selection")
    if (args.diagnose or args.resolve_surplus) and not (
            1970 <= args.probe_year <= date.today().year):
        parser.error("--probe-year is outside the supported historical period")
    if args.readiness and (args.acquire or args.expand or args.diagnose or
                           args.resolve_surplus or args.audit or args.measures
                           or args.discover_measures or args.plan_expansion
                           or args.acquire_metadata or args.inspect_metadata):
        parser.error("--readiness is a standalone read-only operation")
    if args.audit and (args.acquire or args.expand or args.diagnose):
        parser.error("--audit is read-only")
    if args.acquire_metadata or args.inspect_metadata:
        if (args.acquire_metadata and args.inspect_metadata
                or args.acquire or args.expand or args.diagnose or args.audit
                or args.resolve_surplus or args.measures or args.after_country
                or args.discover_measures or args.plan_expansion or args.readiness):
            parser.error("--acquire-metadata/--inspect-metadata require standalone use")
    try:
        since = date.fromisoformat(args.since)
        if since.month != 1 or since.day != 1:
            raise ValueError
        stan_source_request(countries[0], since.year)
    except ValueError:
        parser.error("Invalid YYYY-01-01 source start")
    if args.inspect_metadata:
        result = read_stan_structure(args.evidence_dir)
        emit_report({"operation": "stan_inspected_publisher_measure_metadata",
                     "state": result["status"], "metadata": result},
                    brief=args.brief)
        return 0 if result["status"] == "verified_publisher_structure" else 1
    if args.readiness:
        report = summarize_stan_readiness(args.evidence_dir, countries=countries)
        emit_report(report, brief=args.brief)
        return 1 if report["invalid_original_countries"] else 0
    if args.plan_expansion:
        selection = (tuple(args.measures) if args.measures
                     else STAN_VERIFIED_PORTUGAL_MEASURES)
        result = plan_expansion(
            args.evidence_dir, countries=countries, start_year=since.year,
            measures=selection, max_requests=args.max_requests or 4)
        emit_report(result, brief=args.brief)
        return 1 if result["blocked_invalid_original_countries"] else 0
    if args.discover_measures or args.acquire_metadata:
        with managed_client(timeout=45, follow_redirects=False) as client:
            result = discover_measure_codes(
                client, archive_root=args.evidence_dir if args.acquire_metadata else None)
        emit_report(result, brief=args.brief)
        return 0 if result["state"] == "validated_publisher_measure_codelist" else 1
    if args.diagnose:
        if args.acquire:
            parser.error("--diagnose cannot be combined with --acquire")
        import httpx
        with managed_client(timeout=45, follow_redirects=False) as client:
            results = [diagnose_publisher(client, country=country, year=args.probe_year)
                       for country in countries]
        emit_report({"diagnostics": results}, brief=args.brief)
        return 0 if all(
            any(check["state"] == "validated_native_csv" for check in report["checks"])
            for report in results
        ) else 1
    if args.resolve_surplus:
        gate = plan_surplus_probe(args.evidence_dir)
        if not gate["candidate_measures"]:
            emit_report(gate, brief=args.brief)
            return 1
        with managed_client(timeout=60, follow_redirects=False) as client:
            probe = probe_surplus(
                client, country=countries[0], year=args.probe_year,
                candidates=tuple(gate["candidate_measures"]))
            result = {"surplus_probe": probe,
                      "metadata_source_sha256": gate["source_sha256"]}
            net, gross = STAN_SURPLUS_CANDIDATES
            validated = [item["candidate_measure"] for item in probe["checks"]
                         if item["state"] == "validated_native_csv"]
            selected = net if net in validated else gross if gross in validated else None
            result["selected_observed_surplus_measure"] = selected
            if args.acquire and selected and not probe["stopped_on_publisher_backpressure"]:
                selection = ("B1G", "D1", selected, "P51C", "D29X39")
                result["acquisition"] = acquire(
                    client, args.evidence_dir, countries=countries,
                    start_year=since.year, measures=selection,
                    max_requests=args.max_requests, quiet=args.brief)
        if args.acquire and "acquisition" in result:
            result["accounting_audit"] = audit_stan_originals(
                args.evidence_dir, countries=countries)
        emit_report(result, brief=args.brief)
        return 0 if (selected and (not args.acquire or
                 result.get("acquisition", {}).get("acquisition_failures") == 0)) else 1
    if args.audit:
        emit_report(audit_stan_originals(
            args.evidence_dir, countries=countries), brief=args.brief)
        return 0
    if args.acquire or args.expand:
        import httpx
        with managed_client(timeout=60, follow_redirects=False) as client:
            report = acquire(client, args.evidence_dir, countries=countries,
                             start_year=since.year,
                             measures=tuple(args.measures) if args.measures else None,
                             max_requests=(args.max_requests if args.max_requests is not None
                                           else 4 if args.expand else None),
                             quiet=args.brief)
        emit_report(report, brief=args.brief)
        if args.expand:
            failed = report["stopped_on_source_policy"] or any(
                item["status"] not in (
                    "retained", "already_verified", "deferred_request_budget")
                for item in report["acquisitions"])
            return 1 if failed or report["stopped_on_publisher_backpressure"] else 0
        return 1 if report["acquisition_failures"] or (
            report["source_evidence"]["country_count"] != len(countries)) else 0
    evidence = read_stan_evidence(args.evidence_dir, countries=countries)
    emit_report({
        "phase": "phase2", "operation": "original_stan_evidence_inspection",
        "no_macro_database_writes": True,
        "source_evidence": evidence,
        "scientific_analysis_certified": False,
    }, brief=args.brief)
    return 0 if evidence["country_count"] == len(countries) else 1


if __name__ == "__main__":
    raise SystemExit(main())
