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


def build_inventory(document: dict, registry: list[dict]) -> dict:
    """Summarise authored bindings, never infer data acquisition from mappings."""
    errors = validate_research_corpus(document, registry)
    analyses = []
    for item in document["analyses"]:
        requirements = item["comparison_contract"]["original_requirements"]
        scalar = [role for role in requirements if role["input_type"] == "scalar_history"]
        unbound = [role["role"] for role in scalar if not role["series_ids"]]
        analyses.append({
            "id": item["id"],
            "scalar_required": len(scalar),
            "scalar_bound": len(scalar) - len(unbound),
            "unbound_scalar_roles": unbound,
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


def format_inventory(report: dict, *, details: bool = False) -> str:
    scalar = report["scalar_roles"]
    lines = [
        "PHASE 2 — OFFLINE SOURCE-CONTRACT INVENTORY",
        "Definitions: " + ("PASS" if not report["errors"] else "FAILED"),
        f"Analyses: {report['analysis_count']}  |  Method sources: {report['method_source_count']}",
        f"Scalar roles mapped: {report['scalar_bound_roles']}/{scalar}",
        f"Unbound scalar roles: {report['unbound_scalar_roles']}  |  Structured/policy roles: {report['structured_roles']}",
        "Empirical scientific readiness: NOT EVALUATED (no database or original evidence read)",
    ]
    if report["analyses_with_unbound_scalar_roles"]:
        lines.append("Unbound original scalar roles, by analysis:")
        for item in report["analyses_with_unbound_scalar_roles"]:
            lines.append(f"  {item['id']}: " + ", ".join(item["roles"]))
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
    args = parser.parse_args(argv)
    document = load_research_corpus(ROOT)
    catalog, _ = load_documents(ROOT)
    report = build_inventory(document, catalog["series"])
    if args.json:
        output = dict(report)
        if not args.details:
            output.pop("analyses")
        print(json.dumps(output, indent=2))
    else:
        print(format_inventory(report, details=args.details))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
