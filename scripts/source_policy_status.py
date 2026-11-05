#!/usr/bin/env python3
"""Read-only canonical publisher restrictions, cooldowns and rule inventory."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from finance_dashboard.source_policy import PolicyRegistry, PolicyViolation, policy_summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brief", action="store_true")
    parser.add_argument("--check-url", help="Classify an HTTPS source URL, no request")
    args = parser.parse_args(argv)
    if args.check_url:
        try:
            policy = PolicyRegistry().for_url(args.check_url)
        except PolicyViolation as exc:
            result = {"classification": "denied", "reason": exc.reason}
            print(json.dumps(result, separators=(",", ":")))
            return 1
        result = {
            "classification": policy.classification, "publisher_id": policy.id,
            "limit": policy.rate["limit"],
            "window_seconds": policy.rate["window_seconds"],
            "source_rule_evidence": policy.evidence_url,
            "automation_allowed": policy.restrictions["allow_automated_download"],
            "redistribution": policy.rights["redistribution"],
            "no_network_request": True,
        }
        print(json.dumps(result, separators=(",", ":")))
        return 0
    report = policy_summary()
    if args.brief:
        report = {
            "operation": "source_policy_status",
            "registry_sha256": report["registry_sha256"],
            "registered_publishers": report["publisher_count"],
            "classified_hosts": report["host_count"],
            "unknown_hosts_denied": report["unclassified_hosts_denied"],
            "publisher_cooldowns": [
                {"publisher": row["publisher"],
                 "seconds_remaining": row["cooldown_seconds_remaining"],
                 "http_status": row["last_http_status"]}
                for row in report["state"]
                if row["cooldown_seconds_remaining"] > 0
            ],
            "restricted_publishers": [
                row["id"] for row in report["publishers"]
                if not row["automated_download_allowed"]
            ],
            "publisher_requests_recorded": report["requests_recorded"],
            "catalog_references_classified": report[
                "catalog_source_reference_coverage"]["source_references_classified"],
            "catalog_reference_issues": report[
                "catalog_source_reference_coverage"][
                    "unclassified_or_invalid_source_references"],
        }
    print(json.dumps(report, separators=(",", ":") if args.brief else None,
                     indent=None if args.brief else 2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
