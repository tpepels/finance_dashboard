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
    MAX_STAN_SOURCE_BYTES, read_stan_evidence, stan_source_request,
    store_stan_original,
)


def acquire(client, root: Path, *, countries: tuple[str, ...], start_year: int) -> dict:
    if not root.is_dir() or root.is_symlink():
        raise ValueError("existing_non_symlink_evidence_directory_required")
    report = []
    for number, country in enumerate(countries, start=1):
        print(f"STAN {number}/{len(countries)}: {country}", file=sys.stderr, flush=True)
        entry = {"country": country, "status": "acquisition_failed"}
        try:
            url, params = stan_source_request(country, start_year)
            with client.stream("GET", url, params={**params, "format": "csvfile"},
                               headers={"Accept": "csvfile"}) as response:
                entry["http_status"] = response.status_code
                response.raise_for_status()
                payload = bytearray()
                for chunk in response.iter_bytes():
                    if len(payload) + len(chunk) > MAX_STAN_SOURCE_BYTES:
                        raise ValueError("STAN source exceeds archive bounds")
                    payload.extend(chunk)
            preserved = store_stan_original(bytes(payload), country=country,
                                            start_year=start_year, root=root)
            entry.update(status="retained", original_response_sha256=preserved[
                "original_response_sha256"], bundle_digest=preserved["bundle_digest"],
                original_receipt_sha256=preserved["receipt_sha256"],
                numeric_observations=preserved["facts"]["numeric_observations"])
            print(f"STAN {number}/{len(countries)}: retained", file=sys.stderr, flush=True)
        except Exception as exc:
            # No original HTTP response, exception message or private paths in logs.
            entry["reason_type"] = type(exc).__name__
            print(f"STAN {number}/{len(countries)}: failed ({type(exc).__name__})",
                  file=sys.stderr, flush=True)
        report.append(entry)
    evidence = read_stan_evidence(root, countries=countries)
    return {
        "phase": "phase2", "operation": "original_stan_industry_acquisition",
        "requested_start_year": start_year, "countries_requested": len(countries),
        "original_responses_archived": sum(item["status"] == "retained" for item in report),
        "acquisition_failures": sum(item["status"] != "retained" for item in report),
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
    if args.acquire:
        import httpx
        with httpx.Client(timeout=60, follow_redirects=False) as client:
            report = acquire(client, args.evidence_dir,
                             countries=countries, start_year=since.year)
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
