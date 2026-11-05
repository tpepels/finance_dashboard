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
from finance_dashboard.stan_research import audit_stan_originals


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
    results = []
    for name, measures, activity, with_format in tests:
        url, params = stan_source_request(country, year, measures=measures,
                                          activity=activity, end_year=year)
        if with_format:
            params = {**params, "format": "csvfile"}
        item = {"check": name, "activity": activity or "all_industries",
                "measures_requested": list(measures),
                "year": year, "format_parameter": with_format,
                "state": "source_check_failed"}
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
            if item.get("http_status") == 429:
                item["failure_category"] = "publisher_rate_limited"
            elif item.get("http_status", 0) >= 500:
                item["failure_category"] = "publisher_http_5xx"
            elif item.get("http_status") in (204, 404):
                item["failure_category"] = "no_published_observations_for_selection"
            elif item.get("http_status") in (400, 406, 422):
                item["failure_category"] = "publisher_rejected_source_filter"
            else:
                item["failure_category"] = "transport_or_native_schema"
        results.append(item)
        if item.get("http_status") in (429, 503):
            break  # Respect publisher backpressure; do not retry blindly.
    return {
        "phase": "phase2",
        "operation": "oecd_stan_native_request_diagnostics",
        "country": country, "probe_year": year,
        "checks": results,
        "publisher_requests": len(results),
        "no_archive_writes": True, "no_macro_database_writes": True,
        "original_role_bindings_created": 0,
        "full_historical_acquisition_verified": False,
        "scientific_analysis_certified": False,
        "first_publication_verified": False,
    }



def probe_surplus(client, *, country: str, year: int) -> dict:
    """At most two exact-year, total-activity candidate requests; no archive writes.

    OECD historical methods use B2N_B3_N and B2G_B3G for combined mixed
    income. The live 2025 publisher dataflow must still validate each code.
    """
    from hashlib import sha256
    checks = []
    for candidate in STAN_SURPLUS_CANDIDATES:
        url, params = stan_source_request(
            country, year, measures=(candidate,),
            activity="_T", end_year=year)
        entry = {"candidate_measure": candidate, "probe_year": year,
                 "state": "source_check_failed"}
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
            code = entry.get("http_status")
            if code == 429:
                entry["failure_category"] = "publisher_rate_limited"
            elif code == 503:
                entry["failure_category"] = "publisher_unavailable"
            elif code == 404:
                entry["failure_category"] = "no_published_observations_for_selection"
            elif isinstance(code, int) and code >= 500:
                entry["failure_category"] = "publisher_http_5xx"
            else:
                entry["failure_category"] = "publisher_rejected_or_invalid_native_csv"
        checks.append(entry)
        if entry.get("http_status") in (429, 503):
            break
    return {
        "phase": "phase2", "operation": "native_stan_surplus_code_probe",
        "country": country, "checks": checks,
        "publisher_requests": len(checks),
        "stopped_on_publisher_backpressure": any(
            item.get("http_status") in (429, 503) for item in checks),
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
    publisher_requests = 0
    for number, country in enumerate(countries, start=1):
        entry = {"country": country, "status": "acquisition_failed",
                 "requested_native_measures": list(selection),
                 "unresolved_candidate_measures": sorted(set(STAN_MEASURES) - set(selection))}
        if backpressure:
            entry.update(status="deferred_publisher_backpressure",
                         failure_category=backpressure)
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
            if code == 429:
                backpressure = "publisher_rate_limited"
                entry["failure_category"] = backpressure
            elif code == 503:
                backpressure = "publisher_unavailable"
                entry["failure_category"] = backpressure
            elif code == 404:
                entry["failure_category"] = "no_published_observations_for_selection"
            elif isinstance(code, int) and code >= 500:
                entry["failure_category"] = "publisher_http_5xx"
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



def brief_report(data: dict) -> dict:
    """Presentation summary only; source verification and archives are unchanged."""
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
            "last_country_requested": data.get("last_country_requested"),
            "verified_countries": data["source_evidence"]["country_count"],
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
                scopes.append({
                    "scope": s["scope"], "industry_years": s["distinct_industry_years"],
                    "core_four_overlap": s["core_four_matched_industry_years"],
                    "identities": {
                        name: {"matched": v["eligible_matched_industry_years"],
                               "outside_precision": v["outside_printed_precision_bounds"],
                               "non_A": v["groups_with_non_A_source_flags"],
                               "largest": v["largest_residual_examples"][:1]}
                        for name, v in s["identity_checks"].items()
                    },
                })
            countries.append({
                "country": c["country"], "status": c["status"], "scopes": scopes,
                "additional_scopes": max(0, len(c["scope_audits"]) - 3),
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
    parser.add_argument("--max-requests", type=int,
                        help="Limit new publisher requests; --expand defaults to 4")
    parser.add_argument("--after-country", choices=sorted(OECD_MEMBER_ISO3),
                        help="Continue a sorted country batch after this ISO3 code")
    parser.add_argument("--resolve-surplus", action="store_true",
                        help="Probe bounded native net/gross combined-surplus candidates; "
                             "with --acquire, retain a separate five-measure source")
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
    if args.resolve_surplus and (args.expand or args.diagnose or args.audit or
                                 len(countries) != 1 or args.measures):
        parser.error("--resolve-surplus requires one country and no other mode/selection")
    if (args.diagnose or args.resolve_surplus) and not (
            1970 <= args.probe_year <= date.today().year):
        parser.error("--probe-year is outside the supported historical period")
    if args.audit and (args.acquire or args.expand or args.diagnose):
        parser.error("--audit is read-only")
    try:
        since = date.fromisoformat(args.since)
        if since.month != 1 or since.day != 1:
            raise ValueError
        stan_source_request(countries[0], since.year)
    except ValueError:
        parser.error("Invalid YYYY-01-01 source start")
    if args.diagnose:
        if args.acquire:
            parser.error("--diagnose cannot be combined with --acquire")
        import httpx
        with httpx.Client(timeout=45, follow_redirects=False) as client:
            results = [diagnose_publisher(client, country=country, year=args.probe_year)
                       for country in countries]
        emit_report({"diagnostics": results}, brief=args.brief)
        return 0 if all(
            any(check["state"] == "validated_native_csv" for check in report["checks"])
            for report in results
        ) else 1
    if args.resolve_surplus:
        import httpx
        with httpx.Client(timeout=60, follow_redirects=False) as client:
            probe = probe_surplus(client, country=countries[0], year=args.probe_year)
            result = {"surplus_probe": probe}
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
        with httpx.Client(timeout=60, follow_redirects=False) as client:
            report = acquire(client, args.evidence_dir, countries=countries,
                             start_year=since.year,
                             measures=tuple(args.measures) if args.measures else None,
                             max_requests=(args.max_requests if args.max_requests is not None
                                           else 4 if args.expand else None),
                             quiet=args.brief)
        emit_report(report, brief=args.brief)
        if args.expand:
            failed = any(
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
