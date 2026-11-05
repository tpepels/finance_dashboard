#!/usr/bin/env python3
"""Offline scientific source-contract inventory, without data-readiness claims.

This examines only versioned definitions. For empirical readiness, use the
canonical database/source-evidence evaluation, not this offline inventory.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from finance_dashboard.catalog import load_documents
from finance_dashboard.research_corpus import load_research_corpus, validate_research_corpus
from finance_dashboard.phase2_report_summary import load_saved_run, load_saved_text, format_saved_run


def build_inventory(document: dict, registry: list[dict]) -> dict:
    """Summarise authored bindings, never infer data acquisition from mappings."""
    errors = validate_research_corpus(document, registry)
    analyses = []
    for item in document["analyses"]:
        requirements = item["comparison_contract"]["original_requirements"]
        scalar = [role for role in requirements if role["input_type"] == "scalar_history"]
        unbound = [role["role"] for role in scalar if not role["series_ids"]]
        candidates = [
            {"role": role["role"], "candidate_sources": [
                {key: source[key] for key in (
                    "publisher", "dataset", "source_url", "potential_original_measure",
                    "status", "required_original_checks")}
                for source in role.get("source_candidates", [])
                if source.get("status") == "unverified_candidate"
            ]}
            for role in scalar if not role["series_ids"] and any(
                source.get("status") == "unverified_candidate"
                for source in role.get("source_candidates", []))
        ]
        analyses.append({
            "id": item["id"],
            "scalar_required": len(scalar),
            "scalar_bound": len(scalar) - len(unbound),
            "unbound_scalar_roles": unbound,
            "unverified_candidate_roles": candidates,
            "structured_required": len(requirements) - len(scalar),
        })
    analyses.sort(key=lambda item: item["id"])
    return {
        "phase": "phase2",
        "report_kind": "source_contract_inventory",
        "empirical_readiness_evaluated": False,
        "analysis_count": len(analyses),
        "method_source_count": len(document["original_sources"]),
        "scalar_roles": sum(item["scalar_required"] for item in analyses),
        "scalar_bound_roles": sum(item["scalar_bound"] for item in analyses),
        "unbound_scalar_roles": sum(len(item["unbound_scalar_roles"]) for item in analyses),
        "structured_roles": sum(item["structured_required"] for item in analyses),
        "unverified_source_candidate_roles": sum(len(item["unverified_candidate_roles"]) for item in analyses),
        "analyses_with_unverified_candidates": [
            {"id": item["id"], "roles": item["unverified_candidate_roles"]}
            for item in analyses if item["unverified_candidate_roles"]
        ],
        "analyses_with_unbound_scalar_roles": [
            {"id": item["id"], "roles": item["unbound_scalar_roles"]}
            for item in analyses if item["unbound_scalar_roles"]
        ],
        "analyses": analyses,
        "errors": errors,
        "note": (
            "Source definitions only: no observations, archived responses, "
            "published vintages, panels or scientific acceptance were checked. "
            "Blocked/complete analysis decisions require runtime evidence."
        ),
    }


def format_inventory(report: dict, *, details: bool = False, candidates: bool = False) -> str:
    scalar = report["scalar_roles"]
    lines = [
        "PHASE 2 — OFFLINE SOURCE-CONTRACT INVENTORY",
        "Definitions: " + ("PASS" if not report["errors"] else "FAILED"),
        f"Analyses: {report['analysis_count']}  |  Method sources: {report['method_source_count']}",
        f"Scalar roles mapped: {report['scalar_bound_roles']}/{scalar}",
        f"Unbound scalar roles: {report['unbound_scalar_roles']}  |  Structured/policy roles: {report['structured_roles']}",
        f"Unverified publisher-source candidates: {report['unverified_source_candidate_roles']} unbound roles",
        "Empirical scientific readiness: NOT EVALUATED (no database or original evidence read)",
    ]
    if report["analyses_with_unbound_scalar_roles"]:
        lines.append("Unbound original scalar roles, by analysis:")
        for item in report["analyses_with_unbound_scalar_roles"]:
            lines.append(f"  {item['id']}: " + ", ".join(item["roles"]))
    if candidates:
        lines.append("Original publisher candidates (not mapped, fetched or scientifically verified):")
        for item in report["analyses_with_unverified_candidates"]:
            for role in item["roles"]:
                names = ", ".join(candidate["publisher"] + " " + candidate["dataset"]
                                  for candidate in role["candidate_sources"])
                lines.append(f"  {item['id']}/{role['role']}: {names}")
    if details:
        lines.append("Per-analysis source-binding counts (not data-availability decisions):")
        for item in report["analyses"]:
            lines.append(f"  {item['id']}: scalar {item['scalar_bound']}/{item['scalar_required']}; "
                         f"structured {item['structured_required']}")
    if report["errors"]:
        lines.append("Definition validation errors:")
        lines.extend(f"  {error}" for error in report["errors"])
    lines.append("For verified readiness, evaluate the stored data and original-source archive.")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true",
                        help="Print the same declaration-only inventory as JSON")
    parser.add_argument("--details", action="store_true",
                        help="Include all 35 per-analysis binding counts")
    parser.add_argument("--candidates", action="store_true",
                        help="Display unverified publisher dataset candidates for unmapped original roles")
    parser.add_argument("--run-report", type=Path,
                        help="Summarize a completed acquisition JSON file without reopening the database")
    args = parser.parse_args(argv)
    if args.run_report is not None:
        try:
            if str(args.run_report) == "-":
                # Bounded stdin lets a host-held report be summarized by the container
                # without copying or archiving another private copy.
                raw = sys.stdin.buffer.read(12_000_001)
                saved = load_saved_text(raw.decode("utf-8"))
            else:
                saved = load_saved_run(args.run_report)
        except ValueError:
            # No upstream, JSON or decoder exceptions can leak private text.
            print("Phase 2 saved report invalid or incomplete", file=sys.stderr)
            return 1
        if args.json:
            output = dict(saved)
            if not args.details:
                output.pop("analysis_gaps")
            print(json.dumps(output, indent=2))
        else:
            print(format_saved_run(saved, details=args.details))
        return 0 if saved["run_marked_passed"] else 1
    document = load_research_corpus(ROOT)
    catalog, _ = load_documents(ROOT)
    report = build_inventory(document, catalog["series"])
    if args.json:
        output = dict(report)
        if not args.details:
            output.pop("analyses")
        if not args.candidates:
            output.pop("analyses_with_unverified_candidates")
        print(json.dumps(output, indent=2))
    else:
        print(format_inventory(report, details=args.details, candidates=args.candidates))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
