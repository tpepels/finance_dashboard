"""Read-only decomposition of two exact original 2022 ICIO releases.

An earlier balanced source cannot certify or replace a later failed source.
Changes localize the discrepancy; they do not establish why OECD revised it.
"""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
from decimal import Decimal
import json
from pathlib import Path

from .icio import (EARLY_MEMBER_ROOT, EARLY_PACKAGE_SHA256, EARLY_PACKAGE_URL,
                   HISTORY_MATRICES, HISTORY_ROOT, OCTOBER_2025_MATRICES, README_SHA256, README_URL,
                   _hash, _store_original_bundle, _verified_manifest, audit_matrix, canonical_bytes, readme_dimensions)


COMPARISON_METHOD = "icio-original-release-difference-v1"
# Exact original-pair, ReadMe and method-version output; reproduced by the
# optional full-original regression before being trusted by canonical readers.
PINNED_COMPARISON_SHA256 = "5fe6b3aed95b6f0672ccfa91d3fec2bcc6d0c1fa95557018303e25cf50ba68e8"


def _summary(audit):
    return {key: audit[key] for key in ("accounting_passed", "maximum_row_residual",
        "maximum_column_residual", "row_accounting_failures", "column_accounting_failures",
        "output_vector_mismatches", "identities")}


def compare_matrix_files(older: Path, newer: Path, industry_codes: list[str],
                         final_demand_codes: list[str]) -> dict:
    """Validate both sources, then exactly decompose changes in failed margins.

    This generic calculation makes no publisher-identity claim. The public
    release-specific entry point below additionally enforces original hashes.
    Archived audits and every original byte remain untouched.
    """
    audits = []
    for path in (older, newer):
        with Path(path).open(encoding="utf-8-sig", newline="") as stream:
            audits.append(audit_matrix(stream, industry_codes, final_demand_codes))
    old_audit, new_audit = audits
    n = len(industry_codes)
    failed_rows = set(old_audit["row_accounting_failures"]) | set(new_audit["row_accounting_failures"])
    failed_columns = set(old_audit["column_accounting_failures"]) | set(new_audit["column_accounting_failures"])
    changed = dict.fromkeys(("intermediate_use", "final_demand", "industry_output", "taxes", "value_added", "output_margin"), 0)
    row_changes, column_changes = [], []
    old_columns, new_columns = [Decimal(0)] * n, [Decimal(0)] * n
    specials = []
    with Path(older).open(encoding="utf-8-sig", newline="") as left, Path(newer).open(encoding="utf-8-sig", newline="") as right:
        readers = csv.reader(left), csv.reader(right)
        next(readers[0]); next(readers[1])
        for index, (old_row, new_row) in enumerate(zip(*readers, strict=True)):
            old_values = [Decimal(value) for value in old_row[1:]]
            new_values = [Decimal(value) for value in new_row[1:]]
            delta = [current - previous for previous, current in zip(old_values, new_values, strict=True)]
            if index < n:
                changed["intermediate_use"] += sum(value != 0 for value in delta[:n])
                changed["final_demand"] += sum(value != 0 for value in delta[n:-1])
                changed["industry_output"] += delta[-1] != 0
                for col, code in enumerate(industry_codes):
                    if code in failed_columns:
                        old_columns[col] += old_values[col]
                        new_columns[col] += new_values[col]
                if old_row[0] in failed_rows:
                    changes = {"intermediate_use": sum(delta[:n], Decimal(0)),
                               "final_demand": sum(delta[n:-1], Decimal(0)), "published_output": delta[-1]}
                    old_residual = sum(old_values[:-1], Decimal(0)) - old_values[-1]
                    new_residual = sum(new_values[:-1], Decimal(0)) - new_values[-1]
                    row_changes.append({"code": old_row[0], "older_residual": str(old_residual),
                        "newer_residual": str(new_residual), "residual_change": str(new_residual - old_residual),
                        "changes": {key: str(value) for key, value in changes.items()}})
            else:
                kind = {"TLS": "taxes", "VA": "value_added", "OUT": "output_margin"}[old_row[0]]
                changed[kind] += sum(value != 0 for value in delta)
                specials.append((old_values, new_values))
    for col, code in enumerate(industry_codes):
        if code not in failed_columns:
            continue
        old_tls, new_tls = (values[col] for values in specials[0])
        old_va, new_va = (values[col] for values in specials[1])
        old_output, new_output = (values[col] for values in specials[2])
        old_residual = old_columns[col] + old_tls + old_va - old_output
        new_residual = new_columns[col] + new_tls + new_va - new_output
        changes = {"intermediate_input": new_columns[col] - old_columns[col], "taxes": new_tls - old_tls,
                   "value_added": new_va - old_va, "published_output": new_output - old_output}
        column_changes.append({"code": code, "older_residual": str(old_residual), "newer_residual": str(new_residual),
            "residual_change": str(new_residual - old_residual), "changes": {key: str(value) for key, value in changes.items()}})
    order = lambda item: (-abs(Decimal(item["newer_residual"])), item["code"])
    return {"schema_version": 1, "comparison": "newer_minus_older_original_values",
        "older_accounting": _summary(old_audit), "newer_accounting": _summary(new_audit),
        "numerically_changed_cells": changed,
        "failed_row_changes": sorted(row_changes, key=order), "failed_column_changes": sorted(column_changes, key=order),
        "cause_verified": False, "common_release_verified": False,
        "limitation": "Release differences locate original discrepancies but do not explain the publisher's revision; neither source is rebalanced or substituted."}


def diagnose_2022_release_change(older: Path, newer: Path, readme: Path) -> dict:
    """Require the retained October-2025 and January-2026 originals exactly."""
    for path, descriptor in ((older, OCTOBER_2025_MATRICES[2022]), (newer, HISTORY_MATRICES[2022])):
        path = Path(path)
        if path.is_symlink() or path.stat().st_size != descriptor["bytes"] or _hash(path) != descriptor["sha256"]:
            raise ValueError("icio_release_comparison_original_identity_mismatch")
    dimensions = readme_dimensions(Path(readme).read_bytes())
    result = compare_matrix_files(older, newer, dimensions["industry_codes"], dimensions["final_demand_codes"])
    # Do not certify a source changed between identity verification and the
    # separate accounting/decomposition reads.
    for path, descriptor in ((older, OCTOBER_2025_MATRICES[2022]), (newer, HISTORY_MATRICES[2022])):
        if Path(path).is_symlink() or _hash(path) != descriptor["sha256"]:
            raise ValueError("icio_release_comparison_original_identity_mismatch")
    return {**result, "comparison_method": COMPARISON_METHOD,
        "publisher": "OECD", "edition": "2025", "table": "regular", "year": 2022,
        "unit": dimensions["unit"], "matrix_sha256": OCTOBER_2025_MATRICES[2022]["sha256"],
        "readme_sha256": README_SHA256, "original_source_hashes_verified": True,
        "older_source": {**OCTOBER_2025_MATRICES[2022], "replica_declared_update": "October 2025",
            "replica": "RR_THA_2026_689", "source_url": EARLY_PACKAGE_URL,
            "package_sha256": EARLY_PACKAGE_SHA256, "archive_member": f"{EARLY_MEMBER_ROOT}/2022_SML.csv"},
        "newer_source": {**HISTORY_MATRICES[2022], "replica_declared_update": "January 2026",
            "independent_World_Bank_replica_match_verified": True}}


def _comparison_identity():
    return {"publisher": "OECD", "edition": "2025", "table": "regular", "year": 2022,
        "evidence_type": "original_release_comparison", "method": COMPARISON_METHOD,
        "older_matrix_sha256": OCTOBER_2025_MATRICES[2022]["sha256"],
        "newer_matrix_sha256": HISTORY_MATRICES[2022]["sha256"]}


def _comparison_sources():
    return {"older_matrix": EARLY_PACKAGE_URL, "newer_matrix": f"{HISTORY_ROOT}/2022_SML.csv", "readme": README_URL}


def _verify_comparison_bundle(bundle):
    manifest = _verified_manifest(bundle, _comparison_identity(), {"older.csv", "readme.xlsx", "audit.json"},
        _comparison_sources(), OCTOBER_2025_MATRICES[2022]["sha256"])
    if (manifest["files"]["older.csv"] != OCTOBER_2025_MATRICES[2022]["sha256"]
            or manifest["files"]["readme.xlsx"] != README_SHA256):
        raise ValueError("icio_release_comparison_original_identity_mismatch")
    audit = json.loads((bundle / "audit.json").read_bytes())
    if sha256(canonical_bytes(audit)).hexdigest() != PINNED_COMPARISON_SHA256:
        raise ValueError("icio_release_comparison_audit_mismatch")
    return audit


def store_2022_release_comparison(older: Path, newer: Path, readme: Path, evidence_root: Path) -> Path:
    """Acquire through the existing immutable original/audit/receipt boundary."""
    audit = diagnose_2022_release_change(older, newer, readme)
    return _store_original_bundle(Path(evidence_root) / "icio" / "2022-release-comparison",
        {"older.csv": older, "readme.xlsx": readme}, audit, _comparison_identity(),
        _comparison_sources(), _verify_comparison_bundle)


def read_2022_release_comparison(evidence_root: Path, *, verified_newer_sha256: str | None) -> dict:
    """Verify older original and pinned method; reuse the caller's verified newer original.

    The canonical ICIO reader already verifies its current original package or
    matrix. This shares that identity boundary, with no duplicate current
    matrix copy and no repeated accounting calculation on API reads.
    """
    from .source_reconciliation import _selected_manifest
    parent = Path(evidence_root) / "icio" / "2022-release-comparison"
    if not parent.exists():
        return {"status": "missing_original_release_comparison", "original_source_hashes_verified": False}
    observed, manifest_hash, path, _manifest, selection = _selected_manifest(parent, _comparison_identity())
    audit = _verify_comparison_bundle(path.parent)
    if verified_newer_sha256 != HISTORY_MATRICES[2022]["sha256"]:
        return {"status": "missing_verified_current_original_for_comparison", "original_source_hashes_verified": False}
    def compact(accounting):
        return {"accounting_passed": accounting["accounting_passed"],
            "row_accounting_failures": len(accounting["row_accounting_failures"]),
            "column_accounting_failures": len(accounting["column_accounting_failures"]),
            "maximum_row_residual": accounting["maximum_row_residual"],
            "maximum_column_residual": accounting["maximum_column_residual"]}
    return {"status": "verified_original_release_difference", "original_source_hashes_verified": True,
        "comparison_method": audit["comparison_method"], "unit": audit["unit"],
        "older_source": audit["older_source"], "newer_source": audit["newer_source"],
        "older_accounting": compact(audit["older_accounting"]), "newer_accounting": compact(audit["newer_accounting"]),
        "numerically_changed_cells": audit["numerically_changed_cells"],
        "largest_failed_row_change": next(iter(audit["failed_row_changes"]), None),
        "largest_failed_column_change": next(iter(audit["failed_column_changes"]), None),
        "cause_verified": False, "common_release_verified": False, "first_publication_verified": False,
        "bundle_digest": path.parent.name, "source_manifest_sha256": manifest_hash,
        "acquisition_observed_at_utc": observed.isoformat(), "selection_method": selection,
        "limitation": audit["limitation"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--older", type=Path, required=True, help="Exact October-2025 2022 regular matrix")
    parser.add_argument("--newer", type=Path, required=True, help="Exact January-2026 2022 regular matrix")
    parser.add_argument("--readme", type=Path, required=True)
    parser.add_argument("--root", type=Path, help="Acquire via the canonical immutable source store; omit for read-only diagnostics")
    args = parser.parse_args()
    if args.root:
        store_2022_release_comparison(args.older, args.newer, args.readme, args.root)
        print(json.dumps(read_2022_release_comparison(args.root, verified_newer_sha256=HISTORY_MATRICES[2022]["sha256"]), indent=2))
    else:
        print(json.dumps(diagnose_2022_release_change(args.older, args.newer, args.readme), indent=2))


if __name__ == "__main__":
    main()
