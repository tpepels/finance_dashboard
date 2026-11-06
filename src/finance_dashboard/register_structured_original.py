"""Explicitly register already reviewed original structured publisher files.

This command only delegates to existing source-specific, original-byte
parsers and immutable archive writers. It performs no publisher download and
cannot elevate an artifact from partial evidence to original-method acceptance.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]

from finance_dashboard.service import safe_source_failure_code


def register_structured(kind: str, *, root: Path, files: dict[str, Path],
                        year: int | None = None,
                        source_url: str | None = None) -> dict:
    """Use exactly one registered reviewed original importer."""
    if kind == "icio":
        from finance_dashboard.icio import (
            store_icio_package, store_icio_matrix,
            HISTORY_MATRICES, read_icio_evidence,
        )
        if year is None and set(files) == {"package", "readme"}:
            archive = store_icio_package(
                files["package"], files["readme"], root)
        elif year in HISTORY_MATRICES and set(files) == {"matrix", "readme"}:
            archive = store_icio_matrix(
                files["matrix"], files["readme"], year, root)
        else:
            raise ValueError("icio_original_source_configuration_invalid")
        proof = read_icio_evidence(root)
        return {
            "kind": kind, "archive": archive.name,
            "status": proof["status"],
            "original_source_hash_verified":
                proof["original_source_hash_verified"],
            "accounting_passed": proof.get("accounting_passed"),
        }
    if kind == "wiid":
        from finance_dashboard.wiid_originals import (
            FILES, register_wiid_originals, read_wiid_originals,
        )
        if set(files) != set(FILES) or year is not None or source_url is not None:
            raise ValueError("wiid_source_file_selection_invalid")
        archive = register_wiid_originals(files, root)
        proof = read_wiid_originals(root)
        return {
            "kind": kind, "archive": archive.name,
            "status": proof["status"],
            "original_source_hash_verified":
                proof["original_source_hash_verified"],
        }
    if kind == "msci_concentration":
        from finance_dashboard.msci_concentration_originals import (
            store_msci_concentration_original,
            read_msci_concentration_originals,
        )
        if (set(files) != {"factsheet"} or not source_url
                or year is not None):
            raise ValueError("msci_publisher_original_source_required")
        original = files["factsheet"]
        if original.is_symlink() or not original.is_file() or (
                original.stat().st_size > 5_000_000):
            raise ValueError("msci_original_file_invalid")
        archive = store_msci_concentration_original(
            original.read_bytes(), source_url=source_url, root=root)
        _, proof = read_msci_concentration_originals(root)
        return {
            "kind": kind, "archive": archive.name,
            "status": "verified_sparse_original_index_snapshots",
            "original_source_hash_verified": True,
            "complete_historical_index_verified": False,
        }
    raise ValueError("structured_original_importer_not_registered")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--artifact", choices=[
        "icio", "wiid", "msci_concentration"], required=True)
    parser.add_argument("--file", action="append", required=True,
                        help="Repeat exact reviewed name=absolute-local-original-file")
    parser.add_argument("--year", type=int)
    parser.add_argument("--source-url", help="Exact original publisher factsheet URL")
    args = parser.parse_args(argv)
    files = {}
    for item in args.file:
        if "=" not in item:
            parser.error("--file must use exact name=path")
        name, value = item.split("=", 1)
        if not name or not value or name in files:
            parser.error("--file names must be unique and nonempty")
        files[name] = Path(value)
    try:
        result = register_structured(
            args.artifact, root=args.evidence_dir,
            files=files, year=args.year, source_url=args.source_url)
        print(json.dumps({
            "phase": "phase2",
            "operation": "registered_reviewed_original_files",
            **result,
            "first_publication_verified": False,
            "scientific_analysis_certified": False,
        }, separators=(",", ":"), allow_nan=False))
        return 0
    except Exception as exc:
        print(json.dumps({
            "phase": "phase2",
            "operation": "registered_reviewed_original_files",
            "status": "failed",
            "failure_code": safe_source_failure_code(exc),
            "scientific_analysis_certified": False,
        }, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
