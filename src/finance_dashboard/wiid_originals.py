"""UNU-WIDER WIID (8 September 2026, corrected release) and WIID Companion originals.

The publisher's file host rejects scripted clients, so these workbooks are
registered from an ordinary browser download of the links on the publisher page;
bytes, hashes and the acquisition method are preserved. The Companion `gini_std`
is a standardized per-capita net-income Gini, adjusted from the originally
reported welfare concept; it is evaluated against, never substituted for, the
original country-survey Gini with its welfare concept, survey population,
source and missingness.
"""
from __future__ import annotations

from collections import Counter, OrderedDict
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile
from threading import RLock

from python_calamine import CalamineWorkbook

from .bis import ProviderError
from .source_capture import canonical_bytes
from .source_evidence import record_acquisition_receipt

PAGE_URL = "https://www.wider.unu.edu/database/world-income-inequality-database-wiid"
IDENTITY = {"publisher": "UNU-WIDER", "dataset": "WIID and WIID Companion", "release": "2026-09-08"}
FILES = {
    "WIID-08SEP2026.xlsx": ("https://www.wider.unu.edu/sites/default/files/WIID/WIID-08SEP2026.xlsx", "wiid"),
    "wiidcountry_7.xlsx": ("https://www.wider.unu.edu/sites/default/files/WIID/wiidcountry_7.xlsx", "companion"),
    "WIID-User-Guide-08SEP2026.pdf": ("https://www.wider.unu.edu/sites/default/files/WIID/PDF/WIID_User_Guide_08SEP2026.pdf", "document"),
    "WIID-Companion-User-Guide-08September2026.pdf": ("https://www.wider.unu.edu/sites/default/files/WIID/PDF/WIID-Companion-User-Guide-08September2026.pdf", "document"),
}
MAIN_COLUMNS = ("country", "c3", "year", "gini", "resource", "resource_detailed", "scale", "sharing_unit",
                "reference_unit", "areacovr", "popcovr", "quality", "source", "survey", "wiidcompanion")
COMPANION_COLUMNS = ("c3", "year", "giniseries", "shareseries", "gini_std", "gini")
FOCUS = {"USA": "United States", "FRA": "France", "PRT": "Portugal", "CHN": "China", "IND": "India"}
_CACHE: OrderedDict = OrderedDict()
_LOCK = RLock()


def _hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def register_wiid_originals(sources: dict[str, Path], evidence_root: Path) -> Path:
    """Archive browser-downloaded originals under a content-addressed bundle."""
    if set(sources) != set(FILES):
        raise ProviderError("WIID registration needs exactly the four published files")
    records = {}
    for name, path in sorted(sources.items()):
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 60_000_000:
            raise ProviderError("WIID original file is invalid")
        records[name] = {"url": FILES[name][0], "bytes": path.stat().st_size, "sha256": _hash(path), "kind": FILES[name][1]}
    for name, record in records.items():
        header = Path(sources[name]).read_bytes()[:5]
        if (record["kind"] == "document") != (header == b"%PDF-") or (record["kind"] != "document" and header[:2] != b"PK"):
            raise ProviderError("WIID original file type differs from its published identity")
    content = {"source_identity": IDENTITY, "files": {n: {k: r[k] for k in ("url", "sha256", "bytes")} for n, r in records.items()}}
    digest = sha256(canonical_bytes(content)).hexdigest()
    parent = Path(evidence_root) / "wiid"
    parent.mkdir(parents=True, exist_ok=True)
    bundle = parent / digest
    if not bundle.exists():
        staging = Path(tempfile.mkdtemp(prefix=".wiid-", dir=parent))
        try:
            for name, path in sources.items():
                shutil.copyfile(path, staging / name)
            manifest = {"schema_version": 1, "source_identity": IDENTITY, "content_identity": content, "files": records,
                "retrieved_at_utc": datetime.now(timezone.utc).isoformat(), "page_url": PAGE_URL,
                "acquisition_method": "ordinary_browser_download_from_publisher_page",
                "scripted_download_status": "HTTP 403 from the publisher's application gateway for non-browser clients; no header spoofing was used",
                "publisher_release_note": "8 September 2026 is a corrected version of the 22 July 2026 update (LIS processing and other metadata fixes); use the September version."}
            (staging / "manifest.json").write_bytes(canonical_bytes(manifest))
            os.rename(staging, bundle)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
    record_acquisition_receipt(bundle, IDENTITY)
    return bundle


def _rows(path: Path, columns: tuple[str, ...]) -> list[dict]:
    rows = CalamineWorkbook.from_path(str(path)).get_sheet_by_name("Sheet1").to_python()
    header = {name: index for index, name in enumerate(rows[0])}
    if not set(columns) <= set(header):
        raise ProviderError("WIID workbook columns changed")
    return [{name: row[header[name]] for name in columns} for row in rows[1:]]


def _mean(values: list[Decimal]) -> str | None:
    return str((sum(values) / len(values)).quantize(Decimal("0.001"))) if values else None


def evaluate_wiid(main: list[dict], companion: list[dict]) -> dict:
    flagged_by_key: dict = {}
    for row in main:
        if row["wiidcompanion"] == "Yes":
            flagged_by_key.setdefault((row["c3"], int(row["year"])), []).append(row)
    countries = {}
    for code, name in FOCUS.items():
        rows = [row for row in main if row["c3"] == code]
        flagged = [row for row in rows if row["wiidcompanion"] == "Yes"]
        concepts = Counter((r["resource"], r["scale"], r["sharing_unit"], r["reference_unit"], r["areacovr"], r["popcovr"]) for r in flagged)
        differences, ambiguous = [], 0
        for row in (r for r in companion if r["c3"] == code):
            matches = flagged_by_key.get((code, int(row["year"])), [])
            if len(matches) != 1:
                ambiguous += 1
            elif matches[0]["gini"] not in ("", None) and row["gini_std"] not in ("", None):
                differences.append(abs(Decimal(str(matches[0]["gini"])) - Decimal(str(row["gini_std"]))))
        countries[code] = {"country": name, "survey_records": len(rows), "companion_selected_records": len(flagged),
            "companion_selected_unique_years": len({int(r["year"]) for r in flagged}),
            "first_year": min(int(r["year"]) for r in rows), "last_year": max(int(r["year"]) for r in rows),
            "missing_gini": sum(r["gini"] in ("", None) for r in rows),
            "quality": dict(sorted(Counter(r["quality"] for r in flagged).items())),
            "welfare_concepts_in_selected_series": [dict(zip(("resource", "scale", "sharing_unit", "reference_unit", "area", "population"), key), records=count)
                for key, count in concepts.most_common()],
            "welfare_concept_changes_within_selected_series": len(concepts) > 1,
            "companion_rows": sum(1 for r in companion if r["c3"] == code),
            "companion_rows_without_unique_selected_survey": ambiguous,
            "selected_survey_gini_vs_companion_gini_std": {"matched_country_years": len(differences),
                "mean_absolute_difference": _mean(differences),
                "maximum_absolute_difference": str(max(differences)) if differences else None}}
    return {"survey_records": len(main), "companion_rows": len(companion),
        "survey_records_missing_gini": sum(r["gini"] in ("", None) for r in main),
        "welfare_resource_counts": dict(sorted(Counter(r["resource"] for r in main).items())),
        "quality_counts": dict(sorted(Counter(r["quality"] for r in main).items())),
        "companion_flag_counts": dict(sorted(Counter(r["wiidcompanion"] for r in main).items())),
        "companion_giniseries_counts": {str(k): v for k, v in sorted(Counter(r["giniseries"] for r in companion).items())},
        "focus_countries": countries}


def read_wiid_originals(evidence_root: Path) -> dict:
    from .source_reconciliation import _selected_manifest
    parent = Path(evidence_root) / "wiid"
    if not parent.exists():
        return {"status": "missing_original_wiid_files", "original_source_hash_verified": False,
                "full_history_verified": False, "first_publication_verified": False}
    observed, manifest_hash, path, manifest, selection = _selected_manifest(parent, IDENTITY)
    folder = path.parent
    content = manifest["content_identity"]
    if (manifest.get("schema_version") != 1 or folder.name != sha256(canonical_bytes(content)).hexdigest()
            or set(manifest["files"]) != set(FILES)):
        raise ValueError("wiid_source_identity_mismatch")
    for name, record in manifest["files"].items():
        target = folder / name
        if target.is_symlink() or not target.is_file() or target.stat().st_size != record["bytes"] or _hash(target) != record["sha256"]:
            raise ValueError("wiid_source_hash_mismatch")
    key = (manifest["files"]["WIID-08SEP2026.xlsx"]["sha256"], manifest["files"]["wiidcountry_7.xlsx"]["sha256"])
    with _LOCK:
        summary = _CACHE.get(key)
    if summary is None:
        summary = evaluate_wiid(_rows(folder / "WIID-08SEP2026.xlsx", MAIN_COLUMNS), _rows(folder / "wiidcountry_7.xlsx", COMPANION_COLUMNS))
        with _LOCK:
            _CACHE[key] = summary
            while len(_CACHE) > 2:
                _CACHE.popitem(last=False)
    return {"status": "verified_original_wiid_release_partial", "original_source_hash_verified": True,
        "bundle_digest": folder.name, "source_manifest_sha256": manifest_hash,
        "acquisition_observed_at_utc": observed.isoformat(), "selection_method": selection,
        "release": "WIID 8 September 2026 (corrected version of the 22 July 2026 update)",
        "acquisition_method": manifest["acquisition_method"], "source_hashes": {n: r["sha256"] for n, r in manifest["files"].items()},
        **summary,
        "exact_gini_contract_satisfied_by_companion": False,
        "companion_evaluation": "gini_std is the Companion's standardized per-capita net-income Gini, adjusted from the reported concept; it differs materially where the original concept is consumption or gross income (India, Japan, China), so it cannot stand in for the original welfare-measure Gini. The original survey Gini is retained with welfare concept, scale, sharing and reference unit, coverage, source, survey and quality; Companion-selected series change concept within a country, so a single scalar country series needs an explicit scientific choice.",
        "scalar_binding": "none; a country-year scalar would hide per-observation welfare concepts and multiple selected observations",
        "bounded_data_verified": True, "full_history_verified": False, "first_publication_verified": False}
