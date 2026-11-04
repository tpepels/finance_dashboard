"""Original OECD 2025 regular ICIO from identified, hash-pinned replicas.

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
HISTORY_REPLICA = "aditya1240/liberation-day-data"
HISTORY_REVISION = "9376a67717c1ab5f1ba24379ce5ea8669b72eacb"
HISTORY_ROOT = f"https://huggingface.co/datasets/{HISTORY_REPLICA}/resolve/{HISTORY_REVISION}/data/OECD_ICIO_SML_2016_2022"
# Public LFS content hashes, checked against every retained original. The 2022
# member is also independently identical to the World Bank package above.
# A mirror's MIT repository card does not change the OECD matrix's rights.
HISTORY_MATRICES = {
    2016: {"sha256": "de91a560b3f4b1c75ab18846da13418d663844b465724691598a4e39bf5a09c2", "bytes": 86745061},
    2017: {"sha256": "07a07dc53f1302a35c984f2801a98899ea3e73c9704e8350cbb36587200a4b19", "bytes": 87440646},
    2018: {"sha256": "3d14b8d34c5cc036fd2eb91fc44edce97c904ea8657cc273a162de84153ae23b", "bytes": 87878366},
    2019: {"sha256": "85bd13fd8c2385c41d239d2ddc973ced1caa87c59c2b90b7bed3ff97048043d8", "bytes": 88008102},
    2020: {"sha256": "92955212d9c8942112b7cc9b9251e55dd841e5a607376580a20d37fc54eb20a9", "bytes": 87356600},
    2021: {"sha256": "9a5c161ff1625e841c5901218adcdba0a81b3ee5872c2180ba2cbbabfcba4694", "bytes": 88793390},
    2022: {"sha256": MATRIX_SHA256, "bytes": 90120552},
}
# Independently reproduced audit outputs for these exact original/ReadMe pairs.
# A reader verifies original bytes, immutable receipts and this code-pinned
# result; acquisition/explicit diagnostics still run the complete accounting.
# This avoids redoing 130 million Decimal cell operations on a cold API read.
PINNED_AUDITS = {
    (MATRIX_SHA256, README_SHA256, 2022, "regular-package-accounting-v1"):
        "38aa8ccf7a12a0d512b6e2022c543da425336762918adf0538905eab4c48bdcb",
    **{(HISTORY_MATRICES[year]["sha256"], README_SHA256, year, "regular-history-accounting-v1"): digest
       for year, digest in {
           2016: "8492820482ad5aafdda3bfadc8ef57f98d2144c4fac2f252bbdcee486b11d4dc",
           2017: "61d03fffd73cc632b59916a1aa928495f5acccad473dfed93c6c05226ca4cd16",
           2018: "f21fa962139464e41a596f93da42bc5aa492f93aa11fca6f561a20ad7cff1ee6",
           2019: "e49cdb2daad88efb59c3404ae75868c9f394a133edc4701d3181470f06ef3582",
           2020: "ccacf1c0e9541cb930d62a4f2ca7e49e65cc4a6dd1784e8dcb265bc85c036e96",
           2021: "702fcaf719a95aafe5fa8ca1480c936d15b87d485d671f9b283eb2702f5ccf51",
           2022: "144a796c4938b77f408497b6e5f99e67b2df8e59ed75cc35c4d4cce640857bb9",
       }.items()},
}


def _history_identity(year):
    if year not in HISTORY_MATRICES:
        raise ValueError("icio_unregistered_original_year")
    return {"publisher": "OECD", "edition": "2025", "table": "regular", "year": year,
            "replica": HISTORY_REPLICA, "replica_revision": HISTORY_REVISION}


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


def audit_matrix(stream, industry_codes: list[str], final_demand_codes: list[str], *,
                 include_residuals: bool = False) -> dict:
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
    row_details, column_details = [], []
    signed_row_total = signed_column_total = Decimal(0)
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
            signed_row_total += residual
            row_residuals.append(abs(residual))
            # Rounding bound for n+f independently serialized 4dp cells and
            # output. This is finite-precision accounting, not uncertainty.
            if abs(residual) > Decimal("0.00005") * (n + f + 1):
                row_failures.append(row[0])
                row_details.append({"code": row[0], "residual": str(residual), "gross_output": str(output)})
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
        signed_column_total += residual
        residuals.append(abs(residual))
        if abs(residual) > Decimal("0.00005") * (n + 3):
            column_failures.append(code)
            column_details.append({"code": code, "residual": str(residual),
                                   "gross_output": str(specials["OUT"][index])})
        if outputs[index] != specials["OUT"][index]:
            output_failures.append(code)
        country = countries[code.split("_", 1)[0]]
        for name, source in (("value_added", "VA"), ("taxes_less_subsidies", "TLS")):
            country[name] = country.get(name, Decimal(0)) + specials[source][index]
    def strings(value):
        if isinstance(value, Decimal): return str(value)
        if isinstance(value, dict): return {key: strings(item) for key, item in value.items()}
        return value
    report = {"audit_method_version": 1, "industry_cells": n * n, "final_demand_cells": n * f,
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
    if include_residuals:
        def counts(entries, dimension):
            result = {}
            for entry in entries:
                key = entry["code"].split("_", 1)[dimension]
                result[key] = result.get(key, 0) + 1
            return dict(sorted(result.items()))
        # Opt-in investigation details leave the archived version-1 audit
        # byte-reproducible. Localization does not establish a source cause.
        report["residual_diagnostics"] = {
            "schema_version": 1, "cause_status": "unexplained_original_source_residuals",
            "sign_convention": "sum_of_inputs_or_uses_minus_published_output",
            "signed_row_residual_total": str(signed_row_total),
            "signed_column_residual_total": str(signed_column_total),
            "rows": sorted(row_details, key=lambda item: (-abs(Decimal(item["residual"])), item["code"])),
            "columns": sorted(column_details, key=lambda item: (-abs(Decimal(item["residual"])), item["code"])),
            "row_failure_counts_by_country": counts(row_details, 0),
            "row_failure_counts_by_industry": counts(row_details, 1),
            "column_failure_counts_by_country": counts(column_details, 0),
            "column_failure_counts_by_industry": counts(column_details, 1),
        }
    return report


@lru_cache(maxsize=4)
def _pinned_audit(package_path: str, readme_path: str, include_residuals: bool = False) -> dict:
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
        audit = audit_matrix(stream, dimensions["industry_codes"], dimensions["final_demand_codes"],
                             include_residuals=include_residuals)
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


def diagnose_icio_package(package: Path, readme: Path) -> dict:
    """Read-only signed residual investigation, separate from archived audits."""
    _verify_pins(package, readme)
    return _pinned_audit(str(package.resolve()), str(readme.resolve()), True)


def store_icio_package(package: Path, readme: Path, evidence_root: Path) -> Path:
    _verify_pins(package, readme)
    audit = _pinned_audit(str(package.resolve()), str(readme.resolve()))
    return _store_original_bundle(Path(evidence_root) / "icio" / "regular-2025-2022",
        {"package.zip": Path(package), "readme.xlsx": Path(readme)}, audit, IDENTITY,
        {"package": PACKAGE_URL, "readme": README_URL}, _verify_icio_bundle)


def _store_original_bundle(parent, originals, audit, identity, sources, verify):
    """One atomic original/audit/receipt boundary for both ICIO replica formats."""
    # Preserve the exact publisher-replica bytes even when their accounting
    # fails. Acquisition is evidence, never permission to silently rebalance.
    payload = canonical_bytes(audit)
    files = {name: _hash(path) for name, path in originals.items()}
    files["audit.json"] = sha256(payload).hexdigest()
    digest = sha256(canonical_bytes(files)).hexdigest()
    parent.mkdir(parents=True, exist_ok=True)
    bundle, temporary = parent / digest, None
    try:
        if not bundle.exists():
            temporary = Path(tempfile.mkdtemp(prefix=".icio-", dir=parent))
            for name, path in originals.items():
                shutil.copyfile(path, temporary / name)
            (temporary / "audit.json").write_bytes(payload)
            (temporary / "manifest.json").write_bytes(canonical_bytes({"schema_version": 1,
                "source_identity": identity, "files": files, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                "sources": sources, "matrix_sha256": audit["matrix_sha256"]}))
            os.rename(temporary, bundle)
            temporary = None
        verify(bundle)
        record_acquisition_receipt(bundle, identity)
        return bundle
    finally:
        if temporary is not None: shutil.rmtree(temporary)


def _verified_manifest(bundle, identity, names, sources, matrix_hash):
    if bundle.is_symlink() or (bundle / "manifest.json").is_symlink():
        raise ValueError("icio_archive_identity_invalid")
    manifest = json.loads((bundle / "manifest.json").read_bytes())
    files = manifest["files"]
    if (manifest.get("schema_version") != 1 or manifest.get("source_identity") != identity
            or set(files) != names or manifest.get("sources") != sources
            or manifest.get("matrix_sha256") != matrix_hash
            or sha256(canonical_bytes(files)).hexdigest() != bundle.name):
        raise ValueError("icio_archive_identity_invalid")
    for name, digest in files.items():
        if (bundle / name).is_symlink() or _hash(bundle / name) != digest:
            raise ValueError("icio_archive_hash_mismatch")
    return manifest


def _verify_icio_bundle(bundle):
    manifest = _verified_manifest(bundle, IDENTITY, {"package.zip", "readme.xlsx", "audit.json"},
                       {"package": PACKAGE_URL, "readme": README_URL}, MATRIX_SHA256)
    if manifest["files"]["package.zip"] != PACKAGE_SHA256 or manifest["files"]["readme.xlsx"] != README_SHA256:
        raise ValueError("icio_pinned_original_identity_mismatch")
    audit = json.loads((bundle / "audit.json").read_bytes())
    _verify_audit_pin(audit, MATRIX_SHA256, 2022, "regular-package-accounting-v1")
    return audit


def _verify_audit_pin(audit, matrix_hash, year, method):
    expected = PINNED_AUDITS.get((matrix_hash, README_SHA256, year, method))
    if expected is None or sha256(canonical_bytes(audit)).hexdigest() != expected:
        raise ValueError("icio_archive_audit_mismatch")


def _verify_matrix_pins(matrix, readme, year):
    expected = HISTORY_MATRICES.get(year)
    if (expected is None or Path(matrix).is_symlink() or Path(readme).is_symlink()
            or Path(matrix).stat().st_size != expected["bytes"] or _hash(matrix) != expected["sha256"]
            or _hash(readme) != README_SHA256):
        raise ValueError("icio_pinned_original_identity_mismatch")


def _historical_audit(matrix_path: str, readme_path: str, year: int, original_hash: str) -> dict:
    """Run complete accounting during acquisition or explicit diagnostics."""
    dimensions = readme_dimensions(Path(readme_path).read_bytes())
    with Path(matrix_path).open(encoding="utf-8-sig", newline="") as stream:
        audit = audit_matrix(stream, dimensions["industry_codes"], dimensions["final_demand_codes"],
                             include_residuals=True)
    return {**audit, **_history_identity(year), "unit": dimensions["unit"],
            "country_count": dimensions["country_count"], "industry_count": dimensions["industry_count"],
            "matrix_sha256": original_hash, "readme_sha256": README_SHA256,
            "source_url": f"{HISTORY_ROOT}/{year}_SML.csv",
            "replica_content_hash_verified": True,
            "independent_replica_match_verified": year == 2022 and original_hash == MATRIX_SHA256,
            "publisher_direct_verified": False, "common_update_verified": False,
            "full_history_verified": False, "first_publication_verified": False,
            "rights": "OECD matrix CC BY 4.0; replica repository licence does not supersede OECD data rights",
            "limitations": ["Original regular-table bytes from a public replica; publisher-direct historical package remains unavailable.",
                "Matching ReadMe dimensions and replica content hashes do not independently establish the historical publisher update.",
                "The 2022 replica bytes independently match the World Bank ledger; earlier years lack that second source.",
                "Accounting failures, negative cells and zero-output nodes are retained without rebalancing.",
                "The regular table cannot reproduce extended-table TiVA exactly; no Leontief or shock result is certified."]}


def store_icio_matrix(matrix: Path, readme: Path, year: int, evidence_root: Path) -> Path:
    """Retain one pinned historical replica via the canonical ICIO evidence store."""
    _verify_matrix_pins(matrix, readme, year)
    audit = _historical_audit(str(matrix.resolve()), str(readme.resolve()), year, HISTORY_MATRICES[year]["sha256"])
    identity = _history_identity(year)
    return _store_original_bundle(Path(evidence_root) / "icio" / f"regular-2025-{year}-replica",
        {"matrix.csv": Path(matrix), "readme.xlsx": Path(readme)}, audit, identity,
        {"matrix": f"{HISTORY_ROOT}/{year}_SML.csv", "readme": README_URL},
        lambda bundle: _verify_historical_bundle(bundle, year))


def _verify_historical_bundle(bundle, year):
    matrix_hash = HISTORY_MATRICES[year]["sha256"]
    manifest = _verified_manifest(bundle, _history_identity(year), {"matrix.csv", "readme.xlsx", "audit.json"},
        {"matrix": f"{HISTORY_ROOT}/{year}_SML.csv", "readme": README_URL}, HISTORY_MATRICES[year]["sha256"])
    if manifest["files"]["matrix.csv"] != matrix_hash or manifest["files"]["readme.xlsx"] != README_SHA256:
        raise ValueError("icio_pinned_original_identity_mismatch")
    audit = json.loads((bundle / "audit.json").read_bytes())
    _verify_audit_pin(audit, matrix_hash, year, "regular-history-accounting-v1")
    return audit


def read_icio_evidence(evidence_root: Path, *, include_residuals: bool = False) -> dict:
    from .source_reconciliation import _selected_manifest
    historical = []
    for year in sorted(HISTORY_MATRICES):
        history_parent = Path(evidence_root) / "icio" / f"regular-2025-{year}-replica"
        if history_parent.exists():
            observed, manifest_hash, path, _manifest, selection = _selected_manifest(history_parent, _history_identity(year))
            historical.append({**_verify_historical_bundle(path.parent, year),
                "original_source_hash_verified": True, "bundle_digest": path.parent.name,
                "source_manifest_sha256": manifest_hash, "acquisition_observed_at_utc": observed.isoformat(),
                "selection_method": selection})
    parent = Path(evidence_root) / "icio" / "regular-2025-2022"
    if parent.exists():
        observed, manifest_hash, path, _manifest, selection = _selected_manifest(parent, IDENTITY)
        audit = _verify_icio_bundle(path.parent)
        if include_residuals:
            audit = diagnose_icio_package(path.parent / "package.zip", path.parent / "readme.xlsx")
        primary = {**audit, "original_source_hash_verified": True, "bundle_digest": path.parent.name,
            "source_manifest_sha256": manifest_hash, "acquisition_observed_at_utc": observed.isoformat(),
            "selection_method": selection}
    elif historical:
        primary = dict(historical[-1])
    else:
        primary = {"full_history_verified": False, "first_publication_verified": False,
                   "original_source_hash_verified": False}
    verified_years = sorted({item["year"] for item in historical} | ({2022} if parent.exists() else set()))
    coverage = {"required_years": [1995, 2022], "verified_years": verified_years,
                "missing_years": sorted(set(range(1995, 2023)) - set(verified_years)),
                "replica_only_years": sorted(item["year"] for item in historical if not item["independent_replica_match_verified"]),
                "full_history_verified": verified_years == list(range(1995, 2023)),
                "first_publication_verified": False, "common_update_verified": False}
    status = (f"verified_{primary['year']}_original_matrix" if primary.get("accounting_passed")
              else "original_matrix_accounting_failed") if verified_years else "missing_original_matrix"
    return {**primary, "status": status, "historical_matrices": historical, "historical_coverage": coverage}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    original = parser.add_mutually_exclusive_group(required=True)
    original.add_argument("--package", type=Path)
    original.add_argument("--matrix", type=Path, help="A pinned 2016–2022 original replica CSV")
    parser.add_argument("--year", type=int, choices=sorted(HISTORY_MATRICES))
    parser.add_argument("--readme", type=Path, required=True)
    parser.add_argument("--diagnose", action="store_true", help="Read-only signed residual investigation; do not store or rewrite source evidence")
    parser.add_argument("--root", type=Path, default=Path(os.environ.get("FINANCE_SOURCE_EVIDENCE_DIR", "/data/source-evidence")))
    args = parser.parse_args()
    if args.matrix:
        if args.year is None:
            parser.error("--matrix requires --year")
        if args.diagnose:
            _verify_matrix_pins(args.matrix, args.readme, args.year)
            print(json.dumps(_historical_audit(str(args.matrix.resolve()), str(args.readme.resolve()),
                args.year, HISTORY_MATRICES[args.year]["sha256"]), indent=2))
        else:
            bundle = store_icio_matrix(args.matrix, args.readme, args.year, args.root)
            print(json.dumps(_verify_historical_bundle(bundle, args.year), indent=2))
        return
    if args.year is not None:
        parser.error("--year applies to --matrix")
    if args.diagnose:
        print(json.dumps(diagnose_icio_package(args.package, args.readme), indent=2))
        return
    store_icio_package(args.package, args.readme, args.root)
    print(json.dumps(read_icio_evidence(args.root), indent=2))


if __name__ == "__main__": main()
