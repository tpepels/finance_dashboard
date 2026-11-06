#!/usr/bin/env python3
"""Capture immutable official ALFRED earliest-series-vintage original responses.

A source's first available ALFRED *series* vintage is not each observation's
first public release instant. No historical price or macro value is backfilled
or certified by this command. Read-only by default; --acquire is explicit.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from finance_dashboard.phase2_publication_evidence import (
    capture_first_series_vintage, publisher_vintage_evidence,
)
from finance_dashboard.source_policy import managed_client
from finance_dashboard.source_policy_ledger import SourcePolicyGate
from finance_dashboard.source_policy_registry import PolicyRegistry
from finance_dashboard.service import safe_source_failure_code
from finance_dashboard.vintage import SOURCES, _key_format_ok


def publication_batch(root: Path, *, series: list[str], acquire: bool,
                      budget: int, api_key: str | None = None,
                      client=None) -> dict:
    if (not series or len(series) != len(set(series))
            or set(series) - set(SOURCES)
            or type(budget) is not int or not 1 <= budget <= 100):
        raise ValueError("invalid_publisher_vintage_batch")
    before = publisher_vintage_evidence(root, set(series))
    if before["invalid_original_series"]:
        raise ValueError("invalid_existing_publisher_vintage_original")
    results = []
    attempts = 0
    if acquire:
        if not _key_format_ok(api_key or ""):
            raise ValueError("registered_fred_api_key_required")
        policy = SourcePolicyGate(registry=PolicyRegistry()).availability("fred-v1")
        if policy["state"] != "ready":
            return {
                "operation": "phase2_official_publication_vintages",
                "status": "blocked_publisher_policy_" + policy["state"],
                "policy_reason": policy["reason"],
                "publisher_requests": 0,
                "retry_at": policy["retry_at"],
                "scientific_analysis_certified": False,
            }
        for sid in series:
            if attempts >= budget:
                results.append({"series_id": sid, "state": "deferred_request_budget"})
                continue
            if (before["series"].get(sid) or {}).get("status") == (
                    "verified_original_publisher_vintage"):
                results.append({"series_id": sid, "state": "verified_cached"})
                continue
            try:
                result = capture_first_series_vintage(
                    sid, root=root, api_key=api_key, client=client)
                attempts += result["publisher_requests"]
                results.append({
                    "series_id": sid, "state": result["status"],
                    "first_available_alfred_series_vintage": result[
                        "first_available_alfred_series_vintage"],
                    "publisher_requests": result["publisher_requests"],
                })
            except Exception as exc:
                results.append({
                    "series_id": sid, "state": "failed",
                    "failure_category": safe_source_failure_code(exc),
                })
                # A publisher denial or network failure must not be followed
                # by multiple speculative requests.
                break
    after = publisher_vintage_evidence(root, set(series))
    return {
        "operation": "phase2_official_publication_vintages",
        "status": "read_only" if not acquire else (
            "partial" if any(x["state"] == "failed" for x in results)
            else "bounded_acquisition_complete"),
        "requested_series": series,
        "before_verified": before["verified_series_vintage_sources"],
        "after_verified": after["verified_series_vintage_sources"],
        "invalid_original_series": after["invalid_original_series"],
        "publisher_requests": attempts,
        "budget": budget,
        "results": results,
        "first_available_by_series": {
            sid: row.get("first_available_alfred_series_vintage")
            for sid, row in after["series"].items()
        },
        "observations_first_publication_verified": False,
        "scientific_analysis_certified": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vintage-dir", type=Path,
                        default=Path(os.environ.get(
                            "FINANCE_VINTAGE_DIR", "/data/vintages")))
    parser.add_argument("--series", action="append", choices=sorted(SOURCES))
    parser.add_argument("--acquire", action="store_true")
    parser.add_argument("--max-requests", type=int, default=10)
    args = parser.parse_args(argv)
    if not 1 <= args.max_requests <= 100:
        parser.error("Publisher request limit must be between 1 and 100")
    ids = args.series or sorted(SOURCES)
    if len(ids) != len(set(ids)):
        parser.error("Duplicate publisher series")
    try:
        if args.acquire:
            with managed_client(timeout=25, follow_redirects=False,
                                request_budget=args.max_requests) as client:
                result = publication_batch(
                    args.vintage_dir, series=ids, acquire=True,
                    budget=args.max_requests,
                    api_key=os.environ.get("FRED_API_KEY", ""),
                    client=client)
        else:
            result = publication_batch(
                args.vintage_dir, series=ids, acquire=False,
                budget=args.max_requests)
        print(json.dumps(result, separators=(",", ":"), allow_nan=False))
        return 0 if result["status"] in {
            "read_only", "bounded_acquisition_complete"} else 1
    except Exception as exc:
        print(json.dumps({
            "operation": "phase2_official_publication_vintages",
            "status": "failed",
            "failure_category": safe_source_failure_code(exc),
            "publisher_requests_unknown_on_error": True,
            "scientific_analysis_certified": False,
        }, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
