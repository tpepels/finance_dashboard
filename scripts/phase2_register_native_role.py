#!/usr/bin/env python3
"""Register an approved Phase 2 structured role's exact original CSV/JSON.

Explicit local import only: immutable native bytes and receipts, exact
research-contract validation, keys/dates/numeric schema audit. It never
converts, interpolates, aggregates or certifies publisher economic dimensions.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from finance_dashboard.phase2_native_role_originals import (
    register_native_role_original, read_native_role_original,
    native_role_original_evidence,
)
from finance_dashboard.research_corpus import load_research_corpus
from finance_dashboard.service import safe_source_failure_code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--original", type=Path)
    parser.add_argument("--fields", nargs="+")
    parser.add_argument("--keys", nargs="+")
    parser.add_argument("--numeric", nargs="*", default=[])
    parser.add_argument("--date-field")
    parser.add_argument("--origin", choices=["user_supplied", "publisher_original"],
                        default="user_supplied")
    parser.add_argument("--publisher-url")
    args = parser.parse_args(argv)
    if args.original is not None and (not args.fields or not args.keys):
        parser.error("--original requires --fields and --keys")
    if args.original is None and (
            args.fields or args.keys or args.numeric or args.date_field
            or args.publisher_url):
        parser.error("Source schema and publisher URL require --original")
    try:
        document = load_research_corpus(ROOT)
        if args.original is None:
            result = read_native_role_original(
                document, root=args.evidence_dir,
                analysis_id=args.analysis, role=args.role)
        else:
            result = register_native_role_original(
                document, root=args.evidence_dir, analysis_id=args.analysis,
                role=args.role, original=args.original, fields=args.fields,
                key_fields=args.keys, numeric_fields=args.numeric,
                date_field=args.date_field,
                origin=args.origin, publisher_url=args.publisher_url)
        print(json.dumps({
            "phase": "phase2", "operation": "original_native_role_registration",
            "analysis_id": args.analysis, "role": args.role,
            **result, "scientific_analysis_certified": False,
        }, separators=(",", ":"), allow_nan=False))
        return 0 if result["status"] != "invalid_original_role_archive" else 1
    except Exception as exc:
        print(json.dumps({
            "operation": "original_native_role_registration",
            "status": "failed",
            "reason": safe_source_failure_code(exc),
            "scientific_analysis_certified": False,
        }, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
