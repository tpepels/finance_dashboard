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
    MAX_STAN_SOURCE_BYTES, STAN_MEASURES,
    STAN_VERIFIED_PORTUGAL_MEASURES, read_stan_evidence, stan_source_request,
    store_stan_original,
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


def acquire(client, root: Path, *, countries: tuple[str, ...], start_year: int,
            measures: tuple[str, ...] | None = None) -> dict:
    """Acquire only an exact declared native selection; no automatic retries.

    OECD publishes at most 60 data responses per hour; an HTTP 429/503 ends
    this run immediately. The country cache uses independently rehashed bytes.
    Requests never silently fill the unverified B2N role.
    """
    if not root.is_dir() or root.is_symlink():
        raise ValueError("existing_non_symlink_evidence_directory_required")
    selection = (STAN_VERIFIED_PORTUGAL_MEASURES if measures is None
                 else tuple(measures))
    if not countries:
        raise ValueError("countries_required")
    stan_source_request(countries[0], start_year, measures=selection)
    report = []
    backpressure = None
    for number, country in enumerate(countries, start=1):
        entry = {"country": country, "status": "acquisition_failed",
                 "requested_native_measures": list(selection),
                 "unresolved_candidate_measures": sorted(set(STAN_MEASURES) - set(selection))}
        if backpressure:
            entry.update(status="deferred_publisher_backpressure",
                         "failure_category": backpressure)
            report.append(entry)
            continue
        print(f"STAN {number}/{len(countries)}: {country}", file=sys.stderr, flush=True)
        country_evidence = read_stan_evidence(root, countries=(country,))["country_results"][0]
        if country_evidence["status"] == "invalid_original_stan":
            entry.update(status="invalid_existing_original_archive",
                         "failure_category": "original_archive_integrity")
            report.append(entry)
            continue
        matching_scope = "measure-" + "+".join(selection)
        if any(item["scope"] == matching_scope
               for item in country_evidence.get("source_scopes", [])
               if item["requested_since"] == start_year):
            entry.update(status="already_verified", cache_hit=True)
            report.append(entry)
            continue
        try:
            url, params = stan_source_request(country, start_year, measures=selection)
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
            print(f"STAN {number}/{len(countries)}: retained", file=sys.stderr, flush=True)
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
        "acquisitions": report,
        "source_evidence": evidence,
        "no_macro_database_writes": True,
        "scientific_analysis_certified": False,
        "first_publication_verified": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True,
                        help="Existing original source-evidence archive root")
    parser.add_argument("--countries", nargs="+",
                        default=sorted(OECD_MEMBER_ISO3),
                        help="OECD ISO3 member codes (default: all 38 countries)")
    parser.add_argument("--since", default="1970-01-01",
                        help="First requested source year, YYYY-01-01")
    parser.add_argument("--acquire", action="store_true",
                        help="Download, validate and retain original responses (otherwise read-only)")
    parser.add_argument("--measures", nargs="+", choices=STAN_MEASURES,
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
        if not 1970 <= args.probe_year <= date.today().year:
            parser.error("Invalid --probe-year")
        import httpx
        with httpx.Client(timeout=45, follow_redirects=False) as client:
            results = [diagnose_publisher(client, country=country, year=args.probe_year)
                       for country in countries]
        print(json.dumps({"diagnostics": results}, indent=2))
        return 0 if all(
            any(check["state"] == "validated_native_csv" for check in report["checks"])
            for report in results
        ) else 1
    if args.acquire:
        import httpx
        with httpx.Client(timeout=60, follow_redirects=False) as client:
            report = acquire(client, args.evidence_dir, countries=countries,
                             start_year=since.year,
                             measures=tuple(args.measures) if args.measures else None)
        print(json.dumps(report, indent=2))
        return 1 if report["acquisition_failures"] or (
            report["source_evidence"]["country_count"] != len(countries)) else 0
    evidence = read_stan_evidence(args.evidence_dir, countries=countries)
    print(json.dumps({
        "phase": "phase2", "operation": "original_stan_evidence_inspection",
        "no_macro_database_writes": True,
        "source_evidence": evidence,
        "scientific_analysis_certified": False,
    }, indent=2))
    return 0 if evidence["country_count"] == len(countries) else 1


if __name__ == "__main__":
    raise SystemExit(main())
