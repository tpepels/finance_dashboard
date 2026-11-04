"""Original OECD 2025 regular ICIO, 2022 cross-section from an identified replica.

Validate the complete Z, six final-demand categories, output, value added and
taxes. This is data accounting, not a Leontief model or historical acceptance.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

from python_calamine import CalamineWorkbook

from .source_capture import canonical_bytes
from .source_evidence import record_acquisition_receipt

PACKAGE_URL = "https://reproducibility.worldbank.org/catalog/511/download/1471/RR_WLD_2026_593.zip"
README_URL = "https://webfs-sti.oecd.org/files/STI-PIE/ICIO/2025/ReadMe_ICIO_small.xlsx"
CATALOGUE_URL = "https://reproducibility.worldbank.org/catalog/511"
MEMBER = "RR_WLD_2026_593/reproducibility_package/data_raw/2022_SML.csv"
PACKAGE_SHA256 = "de4011bc3205761b8622b7d1d67d1df80f09f892626d64d8a0e6b985e5a28bac"
README_SHA256 = "dec015b4d89190607fac90710352c9076d0c58ddfcdf6abf1fb6703d6cfca1ba"
MATRIX_SHA256 = "fbab8fd2727bda9fd8c6cfee8227816db82d33bef6aa4b90194ca5dcbc5ad14b"
IDENTITY = {"publisher": "OECD", "edition": "2025", "update": "January 2026",
            "table": "regular", "year": 2022, "replica": "RR_WLD_2026_593"}


def _hash(path):
    digest = sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def readme_dimensions(raw: bytes) -> dict:
    if sha256(raw).hexdigest() != README_SHA256:
        raise ValueError("icio_readme_identity_mismatch")
    workbook = CalamineWorkbook.from_filelike(io.BytesIO(raw))
    text = " ".join(str(cell) for row in workbook.get_sheet_by_name("ReadMe").to_python() for cell in row)
    if "2025 edition" not in text or "Data are expressed in current USD, million" not in text:
        raise ValueError("icio_unit_or_edition_mismatch")
    def codes(sheet):
        # Published numeric item labels have some numbering errors. Source
        # codes and their actual ordering, not those labels, define dimensions.
        return [str(row[1]) for row in workbook.get_sheet_by_name(sheet).to_python()
                if isinstance(row[0], (int, float))]
    rows, columns = codes("RowItems"), codes("ColItems")
    industries = rows[:-3]
    final = columns[len(industries):-1]
    countries = list(dict.fromkeys(code.split("_", 1)[0] for code in industries))
    sectors = list(dict.fromkeys(code.split("_", 1)[1] for code in industries))
    if (rows[-3:] != ["TLS", "VA", "OUT"] or columns[-1] != "OUT"
            or columns[:len(industries)] != industries or len(rows) != 4053 or len(columns) != 4537
            or len(set(rows)) != len(rows) or len(set(columns)) != len(columns)
            or len(countries) != 81 or len(sectors) != 50
            or industries != [f"{area}_{sector}" for area in countries for sector in sectors]
            or final != [f"{area}_{category}" for area in countries
                         for category in ("HFCE", "NPISH", "GGFC", "GFCF", "INVNT", "DPABR")]):
        raise ValueError("icio_readme_dimensions_invalid")
    return {"industry_codes": industries, "final_demand_codes": final, "unit": "current_USD_million",
            "country_count": len(countries), "industry_count": len(sectors)}


def audit_matrix(stream, industry_codes: list[str], final_demand_codes: list[str]) -> dict:
    n, f = len(industry_codes), len(final_demand_codes)
    expected = industry_codes + ["TLS", "VA", "OUT"]
    if not n or len(set(expected)) != len(expected):
        raise ValueError("icio_dimensions_invalid")
    reader = csv.reader(stream)
    if next(reader, None) != ["V1", *industry_codes, *final_demand_codes, "OUT"]:
        raise ValueError("icio_header_mismatch")
    column_sums = [Decimal(0)] * n
    outputs, zero_output, negatives, source_scale = [], [], 0, 0
    row_failures, row_residuals, specials = [], [], {}
    totals = {"intermediate_use": Decimal(0), "final_demand": Decimal(0), "gross_output": Decimal(0)}
    countries = {}
    for index, row in enumerate(reader):
        if index >= len(expected) or len(row) != n + f + 2 or row[0] != expected[index]:
            raise ValueError("icio_row_identity_or_width_invalid")
        try:
            values = [Decimal(cell) for cell in row[1:]]
            if any(not value.is_finite() for value in values):
                raise InvalidOperation
        except (InvalidOperation, ValueError):
            raise ValueError("icio_numeric_value_invalid") from None
        negatives += sum(value < 0 for value in values)
        source_scale = max(source_scale, max(-value.as_tuple().exponent for value in values))
        if source_scale > 4:
            raise ValueError("icio_unexpected_source_precision")
        if index < n:
            intermediate = sum(values[:n], Decimal(0))
            final = sum(values[n:n + f], Decimal(0))
            output = values[-1]
            if output < 0:
                raise ValueError("icio_negative_gross_output")
            if output == 0:
                zero_output.append(row[0])
            outputs.append(output)
            for col, value in enumerate(values[:n]):
                column_sums[col] += value
            residual = intermediate + final - output
            row_residuals.append(abs(residual))
            # Rounding bound for n+f independently serialized 4dp cells and
            # output. This is finite-precision accounting, not uncertainty.
            if abs(residual) > Decimal("0.00005") * (n + f + 1):
                row_failures.append(row[0])
            totals["intermediate_use"] += intermediate
            totals["final_demand"] += final
            totals["gross_output"] += output
            area = row[0].split("_", 1)[0]
            country = countries.setdefault(area, {key: Decimal(0) for key in totals})
            for key, value in (("intermediate_use", intermediate), ("final_demand", final), ("gross_output", output)):
                country[key] += value
        else:
            specials[row[0]] = values
    if set(specials) != {"TLS", "VA", "OUT"} or len(outputs) != n:
        raise ValueError("icio_incomplete_matrix")
    column_failures, output_failures, residuals = [], [], []
    for index, code in enumerate(industry_codes):
        residual = column_sums[index] + specials["TLS"][index] + specials["VA"][index] - specials["OUT"][index]
        residuals.append(abs(residual))
        if abs(residual) > Decimal("0.00005") * (n + 3):
            column_failures.append(code)
        if outputs[index] != specials["OUT"][index]:
            output_failures.append(code)
        country = countries[code.split("_", 1)[0]]
        for name, source in (("value_added", "VA"), ("taxes_less_subsidies", "TLS")):
            country[name] = country.get(name, Decimal(0)) + specials[source][index]
    def strings(value):
        if isinstance(value, Decimal): return str(value)
        if isinstance(value, dict): return {key: strings(item) for key, item in value.items()}
        return value
    return {"audit_method_version": 1, "industry_cells": n * n, "final_demand_cells": n * f,
        "industry_nodes": n, "final_demand_columns": f, "negative_cells": negatives,
        "source_decimal_places": source_scale, "zero_output_nodes": zero_output,
        "identities": {"outputs": "row_sum(Z)+row_sum(F)=OUT",
                       "inputs_plus_taxes_plus_value_added": "column_sum(Z)+TLS+VA=OUT",
                       "rounding_quantum_current_USD_million": "0.0001",
                       "row_rounding_bound": str(Decimal("0.00005") * (n + f + 1)),
                       "column_rounding_bound": str(Decimal("0.00005") * (n + 3))},
        "maximum_row_residual": str(max(row_residuals)), "maximum_column_residual": str(max(residuals)),
        "row_accounting_failures": row_failures, "column_accounting_failures": column_failures,
        "output_vector_mismatches": output_failures,
        "accounting_passed": not (row_failures or column_failures or output_failures),
        "global_totals": strings(totals), "countries": strings(countries)}


@lru_cache(maxsize=2)
def _pinned_audit(package_path: str, readme_path: str) -> dict:
    # Callers rehash original files before using this immutable-content cache.
    dimensions = readme_dimensions(Path(readme_path).read_bytes())
    with zipfile.ZipFile(package_path) as archive:
        if archive.namelist().count(MEMBER) != 1 or archive.getinfo(MEMBER).file_size > 100_000_000:
            raise ValueError("icio_archive_member_invalid")
        raw = archive.read(MEMBER)
        ledger = archive.read("RR_WLD_2026_593/data_hash_report.csv").decode("utf-8")
        if sha256(raw).hexdigest() != MATRIX_SHA256 or f"2022_SML.csv,2022_SML.csv,{MATRIX_SHA256}," not in ledger:
            raise ValueError("icio_original_matrix_hash_mismatch")
    with io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8-sig") as stream:
        audit = audit_matrix(stream, dimensions["industry_codes"], dimensions["final_demand_codes"])
    return {**audit, **IDENTITY, "country_count": dimensions["country_count"],
        "industry_count": dimensions["industry_count"], "unit": dimensions["unit"],
        "matrix_sha256": MATRIX_SHA256, "readme_sha256": README_SHA256,
        "package_sha256": PACKAGE_SHA256, "matrix_archive_member": MEMBER,
        "full_history_verified": False, "first_publication_verified": False,
        "rights": "OECD matrix CC BY 4.0 as documented by the World Bank catalogue; other package inputs have separate rights",
        "citation": "OECD (2025), OECD Inter-Country Input-Output Tables, January 2026 regular update; World Bank replication RR_WLD_2026_593",
        "source_url": CATALOGUE_URL,
        "limitations": ["2022 cross-section only; 1995–2021 matrices remain absent.",
            "Original matrix supplied by an identified replica, not publisher-direct ZIP bytes.",
            "Source accounting residuals above serialization rounding are retained and block a balanced-matrix claim; no cells are adjusted.",
            "Zero-output nodes require explicit treatment before forming technical coefficients.",
            "No Leontief inverse, causal shock or whole G06 scientific acceptance is claimed."]}


def _verify_pins(package, readme):
    if (Path(package).is_symlink() or Path(readme).is_symlink()
            or _hash(package) != PACKAGE_SHA256 or _hash(readme) != README_SHA256):
        raise ValueError("icio_pinned_original_identity_mismatch")


def store_icio_package(package: Path, readme: Path, evidence_root: Path) -> Path:
    _verify_pins(package, readme)
    audit = _pinned_audit(str(package.resolve()), str(readme.resolve()))
    # Preserve the exact publisher-replica bytes even when their accounting
    # fails. Acquisition is evidence, never permission to silently rebalance.
    payload = canonical_bytes(audit)
    files = {"package.zip": PACKAGE_SHA256, "readme.xlsx": README_SHA256, "audit.json": sha256(payload).hexdigest()}
    digest = sha256(canonical_bytes(files)).hexdigest()
    parent = Path(evidence_root) / "icio" / "regular-2025-2022"
    parent.mkdir(parents=True, exist_ok=True)
    bundle, temporary = parent / digest, None
    try:
        if not bundle.exists():
            temporary = Path(tempfile.mkdtemp(prefix=".icio-", dir=parent))
            shutil.copyfile(package, temporary / "package.zip")
            shutil.copyfile(readme, temporary / "readme.xlsx")
            (temporary / "audit.json").write_bytes(payload)
            (temporary / "manifest.json").write_bytes(canonical_bytes({"schema_version": 1,
                "source_identity": IDENTITY, "files": files, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "sources": {"package": PACKAGE_URL, "readme": README_URL}, "matrix_sha256": MATRIX_SHA256}))
            os.rename(temporary, bundle)
            temporary = None
        _verify_icio_bundle(bundle)
        record_acquisition_receipt(bundle, IDENTITY)
        return bundle
    finally:
        if temporary is not None: shutil.rmtree(temporary)


def _verify_icio_bundle(bundle):
    if bundle.is_symlink() or (bundle / "manifest.json").is_symlink():
        raise ValueError("icio_archive_identity_invalid")
    manifest = json.loads((bundle / "manifest.json").read_bytes())
    files = manifest["files"]
    if (manifest.get("schema_version") != 1 or manifest.get("source_identity") != IDENTITY
            or set(files) != {"package.zip", "readme.xlsx", "audit.json"}
            or sha256(canonical_bytes(files)).hexdigest() != bundle.name):
        raise ValueError("icio_archive_identity_invalid")
    for name, digest in files.items():
        if (bundle / name).is_symlink() or _hash(bundle / name) != digest:
            raise ValueError("icio_archive_hash_mismatch")
    _verify_pins(bundle / "package.zip", bundle / "readme.xlsx")
    audit = json.loads((bundle / "audit.json").read_bytes())
    if audit != _pinned_audit(str((bundle / "package.zip").resolve()), str((bundle / "readme.xlsx").resolve())):
        raise ValueError("icio_archive_audit_mismatch")
    return audit


def read_icio_evidence(evidence_root: Path) -> dict:
    from .source_reconciliation import _selected_manifest
    parent = Path(evidence_root) / "icio" / "regular-2025-2022"
    if not parent.exists():
        return {"status": "missing_original_matrix", "full_history_verified": False,
                "first_publication_verified": False}
    observed, manifest_hash, path, _manifest, selection = _selected_manifest(parent, IDENTITY)
    audit = _verify_icio_bundle(path.parent)
    return {**audit, "status": "verified_2022_original_matrix" if audit["accounting_passed"] else "original_matrix_accounting_failed",
            "original_source_hash_verified": True, "bundle_digest": path.parent.name,
            "source_manifest_sha256": manifest_hash, "acquisition_observed_at_utc": observed.isoformat(),
            "selection_method": selection}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--readme", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path(os.environ.get("FINANCE_SOURCE_EVIDENCE_DIR", "/data/source-evidence")))
    args = parser.parse_args()
    store_icio_package(args.package, args.readme, args.root)
    print(json.dumps(read_icio_evidence(args.root), indent=2))


if __name__ == "__main__": main()
