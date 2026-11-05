"""Original OECD AMNE and OECD–UNSD MEIP evidence with distinct populations.

AMNE describes estimated production by ownership, never accounting net profit.
MEIP reports a selected FY2024 parent sample, never worldwide listed earnings.
Original bytes and append-only acquisition receipts use the canonical evidence
bundle convention. Readers rebuild facts from the selected immutable originals.
"""
from __future__ import annotations

from .source_policy import require_managed_client

from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

from python_calamine import CalamineWorkbook

from .bis import ProviderError
from .source_evidence import record_acquisition_receipt


AMNE_BASE = ("https://www.oecd.org/content/dam/oecd/en/data/datasets/"
             "global-value-chain-data-across-trade-multinationals-and-services/"
             "analytical-amne/2026/")
MEIP_BASE = "https://unstats.un.org/unsd/business-stat/mne-platform/"
SOURCE_FILES = {
    "amne": {name: AMNE_BASE + name for name in (
        "readme-aamne.xlsx", "aamne-xvem.csv", "aamne-bilateral-output.csv", "aamne-mne-xvem.csv")},
    "meip": {name: MEIP_BASE + name for name in (
        "OECD_UNSD_MEIP_MNE-Indicators_2024.xlsx", "OECD_UNSD_MEIP_Global-Register_2024.xlsx",
        "MEIP_Methodology.pdf", "MEIP_31Dec2023.zip")},
}
EDITIONS = {"amne": "2026", "meip": "2024"}
INDICATOR_COLUMNS = ("Parent MNE", "HQ Country", "TRBC Economic Sector Name", "Employees",
                     "Revenue (USD)", "R&D (USD)", "Net Profit (USD)")
REGISTER_COLUMNS = ("Parent MNE", "Hierarchy", "ISO3", "Subsidiary Name (Clean)", "Business ID",
                    "OpenCorporates", "LEI", "PermID", "DUNL", "CapIQ", "Alternative Names",
                    "Address", "Complexity of Discovery", "Subsidiary Name (with Heirarchy)",
                    "Parent of Subsidiary")


def _fail(message):
    raise ProviderError(message)


def _number(value, *, missing=False):
    if missing and value in ("", "NA", None):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ProviderError("Invalid original multinational numerical observation") from exc
    if not number.is_finite():
        _fail("Nonfinite original multinational numerical observation")
    return number


def _workbook(raw, required):
    if len(raw) > 20_000_000:
        _fail("Original multinational workbook exceeds bounded size")
    try:
        book = CalamineWorkbook.from_filelike(io.BytesIO(raw))
        if not set(required).issubset(book.sheet_names):
            _fail("Original multinational workbook sheet identity mismatch")
        return {name: book.get_sheet_by_name(name).to_python() for name in required}
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderError("Original multinational workbook unreadable") from exc


def _metadata_rows(rows, columns):
    if not rows or tuple(rows[0]) != columns:
        _fail("Original multinational table columns changed")
    for row in rows[1:]:
        if len(row) != len(columns):
            _fail("Original multinational table row width changed")


def parse_meip_indicators(original: bytes) -> dict:
    """Keep the native USD unit and FY label; infer no fiscal end or parent income."""
    sheets = _workbook(original, ("MNE Indicators", "Metadata"))
    rows = sheets["MNE Indicators"]
    _metadata_rows(rows, INDICATOR_COLUMNS)
    metadata = {r[0]: r[1] for r in sheets["Metadata"] if len(r) == 2 and r[0]}
    for label in INDICATOR_COLUMNS[3:]:
        if "FY2024" not in metadata.get(label, ""):
            _fail("MEIP fiscal reference label unverified")
    records, seen, excluded = [], set(), []
    for rowno, row in enumerate(rows[1:], 2):
        if not row[0]:
            if any(row):
                # The original contains an unnamed revenue-only subtotal. It is
                # evidence about the workbook, not a company or a new source sum.
                if any(row[i] != "" for i in (0, 1, 2, 3, 5, 6)):
                    _fail("Unrecognised unnamed MEIP financial row")
                excluded.append({"source_row": rowno, "reason": "unnamed_revenue_subtotal",
                                 "source_revenue_usd": str(_number(row[4]))})
            else:
                excluded.append({"source_row": rowno, "reason": "blank_row"})
            continue
        name, hq, sector = row[:3]
        if (not isinstance(name, str) or name in seen or not re.fullmatch(r"[A-Z]{3}", str(hq))
                or not isinstance(sector, str) or not sector):
            _fail("Original MEIP parent/HQ/sector identity invalid or repeated")
        seen.add(name)
        values = [_number(value, missing=True) for value in row[3:]]
        if values[0] is not None and (values[0] < 0 or values[0] != values[0].to_integral_value()):
            _fail("Original MEIP employee count invalid")
        records.append({"parent_mne": name, "hq_country": hq, "trbc_sector": sector,
                        "source_row": rowno, "source_fiscal_label": "FY2024",
                        "employees": str(values[0]) if values[0] is not None else None,
                        **{key: str(value) if value is not None else None for key, value in
                           zip(("revenue_usd", "rd_usd", "net_profit_usd"), values[1:], strict=True)},
                        "currency": "USD", "unit_multiplier": 0,
                        "fiscal_start": None, "fiscal_end": None,
                        "parent_attributable_income_verified": False,
                        "consolidation_scope_verified": False,
                        "native_reporting_currency_verified": False,
                        "fx_conversion_method_verified": False,
                        "first_publication_verified": False})
    if not records:
        _fail("Original MEIP indicators contain no named parents")
    return {"records": records, "excluded_non_entity_rows": excluded,
            "original_sha256": sha256(original).hexdigest(), "reference_year": 2024}


def _register_summary(rows, parent_names):
    _metadata_rows(rows, REGISTER_COLUMNS)
    hierarchy, jurisdictions = Counter(), set()
    heads, parents, identifiers = defaultdict(list), set(), Counter()
    missing_links = missing_jurisdictions = 0
    for row in rows[1:]:
        if not any(row):
            continue
        if (not row[0] or row[1] not in {"MNE Head", "Known", "Partial", "Unknown"}
                or (row[2] != "" and not re.fullmatch(r"[A-Z]{3}", str(row[2]))) or not row[3]):
            _fail("Original MEIP register hierarchy/entity identity invalid")
        hierarchy[row[1]] += 1
        parents.add(row[0])
        if row[2]:
            jurisdictions.add(row[2])
        else:
            missing_jurisdictions += 1
        missing_links += not bool(row[-1])
        for i in range(4, 10):
            identifiers[REGISTER_COLUMNS[i]] += bool(row[i])
        if row[1] == "MNE Head":
            heads[row[0]].append(row)
    head_coverage = {REGISTER_COLUMNS[i]: sum(any(r[i] for r in group) for group in heads.values())
                     for i in range(4, 10)}
    return {"entity_rows": sum(hierarchy.values()), "parent_labels": len(parents),
            "jurisdiction_count": len(jurisdictions), "hierarchy_counts": dict(sorted(hierarchy.items())),
            "entity_identifier_coverage": dict(identifiers),
            "parent_head_identifier_coverage": head_coverage,
            "identifier_count_semantics": "Nonempty source fields, not independently validated identifiers; entity rows are not deduplicated legal entities.",
            "parents_with_multiple_head_rows": sorted(k for k, v in heads.items() if len(v) > 1),
            "parents_without_head_rows": sorted(parent_names - set(heads)),
            "financial_parents_not_in_register": sorted(parent_names - parents),
            "register_parents_without_financial_rows": sorted(parents - parent_names),
            "missing_immediate_parent_labels": missing_links,
            "missing_jurisdiction_rows": missing_jurisdictions,
            "ownership_share_percentages_reported": False,
            "identifier_registry_validation_verified": False,
            "ultimate_parent_deduplication_verified": False,
            "ownership_semantics": "Source hierarchy is MNE Head/Known/Partial/Unknown; MNE Head is a candidate ultimate parent, not an independently validated ownership chain."}


def audit_meip_sources(payloads: dict[str, bytes]) -> dict:
    indicators = parse_meip_indicators(payloads["OECD_UNSD_MEIP_MNE-Indicators_2024.xlsx"])
    records = indicators["records"]
    register = _workbook(payloads["OECD_UNSD_MEIP_Global-Register_2024.xlsx"], ("Group Register",))
    register = _register_summary(register["Group Register"], {r["parent_mne"] for r in records})
    try:
        with zipfile.ZipFile(io.BytesIO(payloads["MEIP_31Dec2023.zip"])) as archive:
            previous = sorted(archive.namelist())
            if (previous != ["MEIP_DigitalRegister_2023.xlsx", "MEIP_GlobalRegister_2023.xlsx"]
                    or any(item.file_size > 20_000_000 for item in archive.infolist())):
                _fail("Original previous MEIP release members changed")
    except zipfile.BadZipFile as exc:
        raise ProviderError("Original previous MEIP release unreadable") from exc
    if not payloads["MEIP_Methodology.pdf"].startswith(b"%PDF-"):
        _fail("Original MEIP methodology document identity invalid")
    return {"schema_version": 1, "status": "verified_original_selected_mne_sample",
            "publisher": "OECD–UNSD", "edition": "2024", "reference_years": [2024],
            "parent_records": len(records), "hq_country_count": len({r["hq_country"] for r in records}),
            "hq_country_counts": dict(sorted(Counter(r["hq_country"] for r in records).items())),
            "variable_coverage": {key: {"reported_parents": sum(r[key] is not None for r in records),
                "missing_parents": sum(r[key] is None for r in records),
                "negative_observations": sum(_number(r[key]) < 0 for r in records if r[key] is not None)}
                for key in ("employees", "revenue_usd", "rd_usd", "net_profit_usd")},
            "excluded_non_entity_rows": indicators["excluded_non_entity_rows"], "register": register,
            "previous_release_members": previous, "previous_release_financial_indicators_present": False,
            "native_currency_scale_verified": True, "currency": "USD", "unit_multiplier": 0,
            "source_fiscal_label": "FY2024", "calendar_year_alignment_verified": False,
            "consolidation_scope_verified": False, "parent_attributable_income_verified": False,
            "fx_conversion_method_verified": False, "worldwide_population_verified": False,
            "complete_listed_population_verified": False, "ultimate_parent_deduplication_verified": False,
            "first_publication_verified": False, "full_history_verified": False, "aggregate_produced": False,
            "scope": "Selected 500-large-MNE platform sample, not a worldwide or complete listed-company universe. HQ is distinct from production location. FY2024 lacks per-parent fiscal dates, consolidation and controlling/noncontrolling profit split; USD reporting does not document native-currency conversion. The linked 2024 methodology predates the financial indicators. No profit aggregate is produced."}


def _amne_metadata(original):
    sheets = _workbook(original, ("ReadMe_analyticalAMNE", "Country", "Industry", "Revision_log"))
    text = "\n".join(str(cell) for row in sheets["ReadMe_analyticalAMNE"] for cell in row)
    for phrase in ("2000 to 2023", "million USD and current prices", "published in January 2026",
                   "2023 are based on projections", "includes taxes minus subsidies on products"):
        if phrase not in text:
            _fail("Original AMNE release accounting metadata changed")
    countries = {str(row[i]) for row in sheets["Country"][3:] for i in (0, 2)
                 if len(row) > i and re.fullmatch(r"[A-Z]{3}", str(row[i]))}
    industries = {str(row[0]) for row in sheets["Industry"][3:] if row[0]}
    if len(countries) != 81 or "ROW" not in countries or len(industries) != 41:
        _fail("Original AMNE country/industry classification changed")
    revisions = [{"date": str(row[0]), "revision": row[1], "description": row[2], "affected_data": row[3]}
                 for row in sheets["Revision_log"][1:] if any(row)]
    return countries, industries, revisions


def _amne_rows(original, columns):
    if len(original) > 55_000_000:
        _fail("Original AMNE table exceeds bounded size")
    reader = csv.DictReader(io.StringIO(original.decode("utf-8-sig")))
    if tuple(reader.fieldnames or ()) != tuple(columns):
        _fail("Original AMNE table columns changed")
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            _fail("Original AMNE table row width invalid")
        yield row


def _amne_key(row, countries, industries, first=2000, last=2023):
    if (not re.fullmatch(r"20[0-9]{2}", row["year"]) or not first <= int(row["year"]) <= last
            or row["cou"] not in countries or row["isic"] not in industries):
        _fail("Original AMNE period/country/industry invalid")
    return int(row["year"]), row["cou"], row["isic"]


def _amne_xvem(original, countries, industries, *, domestic_mne=False):
    measures = ("GO", "GVA", "EXGR", "IMGR") if domestic_mne else ("GO", "GVA", "EXP", "IMP")
    columns = ("year", "cou", "own", "isic", measures[0], "flag_go", measures[1], "flag_gva",
               measures[2], "flag_exgr", measures[3], "flag_imgr")
    flags = {key: Counter() for key in columns if key.startswith("flag_")}
    counts, missing, go, seen = Counter(), Counter(), {}, set()
    ownership = {"F", "D_MNE", "D_OTH"} if domestic_mne else {"D", "F"}
    for row in _amne_rows(original, columns):
        key = _amne_key(row, countries, industries, first=2008 if domestic_mne else 2000)
        own = row["own"]
        if own not in ownership or (*key, own) in seen:
            _fail("Original AMNE ownership invalid or repeated observation")
        seen.add((*key, own)); counts[key[0]] += 1
        for measure in measures:
            value = _number(row[measure], missing=True)
            missing[measure] += value is None
            if measure == "GO":
                go[(*key, own)] = value
        for flag in flags:
            if row[flag] not in {"", "e", "a", "e,a"}:
                _fail("Original AMNE estimate/adjustment flag changed")
            flags[flag][row[flag]] += 1
    expected_per_year = len(countries) * len(industries) * len(ownership)
    return {"rows": len(seen), "rows_by_year": dict(sorted(counts.items())),
            "years": sorted(counts), "ownership_codes": sorted(ownership),
            "expected_rows_per_year": expected_per_year,
            "complete_reported_grid": bool(counts) and all(v == expected_per_year for v in counts.values()),
            "missing_values_by_variable": dict(missing),
            "flags_by_variable": {key: dict(sorted(value.items())) for key, value in flags.items()}}, go


def audit_amne_sources(payloads: dict[str, bytes]) -> dict:
    countries, industries, revisions = _amne_metadata(payloads["readme-aamne.xlsx"])
    xvem, go = _amne_xvem(payloads["aamne-xvem.csv"], countries, industries)
    mne, _ = _amne_xvem(payloads["aamne-mne-xvem.csv"], countries, industries, domestic_mne=True)
    counts, excluded, seen = Counter(), defaultdict(Counter), set()
    comparisons, max_residual, nonzero = Counter(), defaultdict(lambda: Decimal(0)), Counter()
    owner_columns = sorted(countries)
    columns = ("year", "cou", "isic", *owner_columns)
    for row in _amne_rows(payloads["aamne-bilateral-output.csv"], columns):
        key = _amne_key(row, countries, industries, last=2024)
        if key in seen:
            _fail("Repeated original AMNE bilateral matrix row")
        seen.add(key)
        values = {owner: _number(row[owner], missing=True) for owner in owner_columns}
        if key[0] > 2023:
            excluded[key[0]]["rows"] += 1
            excluded[key[0]]["nonzero_cells"] += sum(v != 0 for v in values.values() if v is not None)
            excluded[key[0]]["missing_cells"] += sum(v is None for v in values.values())
            continue
        counts[key[0]] += 1
        if any(value is None for value in values.values()):
            continue
        domestic = values[key[1]]
        foreign = sum((value for owner, value in values.items() if owner != key[1]), Decimal(0))
        for own, value in (("D", domestic), ("F", foreign)):
            if go.get((*key, own)) is None:
                continue
            residual = value - go[(*key, own)]
            comparisons[own] += 1; nonzero[own] += residual != 0
            max_residual[own] = max(max_residual[own], abs(residual))
    return {"schema_version": 1, "status": "verified_original_ownership_production_evidence",
            "publisher": "OECD", "edition": "2026", "years": sorted(counts),
            "location_count": len(countries), "individual_economy_count": len(countries) - 1,
            "countries": sorted(countries), "includes_rest_of_world": True, "industry_count": len(industries),
            "currency": "USD", "unit_multiplier": 6, "price_basis": "current prices; ICIO basic prices",
            "gva_definition": "Gross value added includes taxes minus subsidies on products, per publisher readme.",
            "native_currency_scale_verified": True, "underlying_icio_release": "January 2026",
            "year_2023_projection_disclosed": True, "source_revision_log": revisions,
            "xvem": xvem, "domestic_mne_xvem": mne,
            "bilateral_output": {"rows": sum(counts.values()), "rows_by_year": dict(sorted(counts.items())),
                "owner_economy_columns": len(owner_columns),
                "complete_reported_grid": bool(counts) and all(v == len(countries) * len(industries) for v in counts.values()),
                "excluded_undeclared_years": {year: dict(value) for year, value in sorted(excluded.items())},
                "exclusion_reason": "Publisher declares 2000–2023; extra 2024 rows are retained in originals and excluded from usable coverage.",
                "go_vs_bilateral_diagnostic": {own: {"comparisons": comparisons[own],
                    "nonzero_exact_residuals": nonzero[own], "max_absolute_residual_usd_millions": str(max_residual[own])}
                    for own in ("D", "F")}},
            "firm_identifiers_reported": False, "ultimate_owner_economy_distinguished": True,
            "net_profit_reported": False, "worldwide_listed_profit_population_verified": False,
            "first_publication_verified": False, "full_history_verified": False, "aggregate_produced": False,
            "scope": "Analytical production and gross value added by host economy, industry and firm ownership; adjusted/estimated flags retained. Bilateral ultimate controlling economy is not a firm-level parent identifier, net profit, or a geographical allocation of consolidated income. January 2026 ICIO consistency does not establish equality with another release."}


def _source_identity(kind):
    if kind not in EDITIONS:
        _fail("Unknown original multinational source kind")
    return {"publisher": "OECD" if kind == "amne" else "OECD–UNSD", "dataset": kind,
            "edition": EDITIONS[kind], "source_urls": SOURCE_FILES[kind]}


def _audit(kind, payloads):
    if set(payloads) != set(SOURCE_FILES[kind]):
        _fail("Original multinational source bundle files mismatch")
    return audit_amne_sources(payloads) if kind == "amne" else audit_meip_sources(payloads)


def _verified_bundle(folder, kind):
    try:
        if folder.is_symlink() or (folder / "manifest.json").is_symlink():
            raise ValueError("symlink")
        manifest = json.loads((folder / "manifest.json").read_text())
        if (manifest["schema_version"] != 1 or manifest["source_identity"] != _source_identity(kind)
                or manifest["original_first_publication_at"] is not None
                or set(manifest["files"]) != {*SOURCE_FILES[kind], "facts.json"}
                or sha256(json.dumps(manifest["files"], sort_keys=True).encode()).hexdigest() != folder.name):
            raise ValueError("identity")
        payloads = {}
        for name, digest in manifest["files"].items():
            path = folder / name
            if path.is_symlink() or path.stat().st_size > 55_000_000:
                raise ValueError("file size/symlink")
            payloads[name] = path.read_bytes()
            if sha256(payloads[name]).hexdigest() != digest:
                raise ValueError("digest")
        facts = payloads.pop("facts.json")
        report = _audit(kind, payloads)
        # JSON converts integer year keys to strings; canonicalize on both sides.
        if json.loads(json.dumps(report)) != json.loads(facts):
            raise ValueError("facts changed")
        return manifest, report
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ProviderError("Immutable original multinational evidence inconsistent") from exc


def store_multinational_source(kind: str, payloads: dict[str, bytes], *, root: Path,
                               http_metadata: dict | None = None) -> Path:
    """Archive reviewed native originals atomically, without database writes."""
    identity = _source_identity(kind)
    report = _audit(kind, payloads)
    bodies = {**payloads, "facts.json": json.dumps(report, sort_keys=True).encode()}
    hashes = {name: sha256(body).hexdigest() for name, body in bodies.items()}
    digest = sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    parent = Path(root) / "multinationals" / kind / EDITIONS[kind]
    folder, temporary = parent / digest, None
    try:
        parent.mkdir(parents=True, exist_ok=True)
        if not folder.exists():
            temporary = Path(tempfile.mkdtemp(prefix=".multinational-", dir=parent))
            for name, body in bodies.items():
                with (temporary / name).open("wb") as handle:
                    handle.write(body); handle.flush(); os.fsync(handle.fileno())
            manifest = {"schema_version": 1, "source_identity": identity, "files": hashes,
                        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                        "original_first_publication_at": None, "http_metadata": http_metadata,
                        "acquisition_method": "publisher_http" if http_metadata is not None else "imported_original_bytes",
                        "publication_note": "Observation/FY labels, HTTP modification, edition and local acquisition are distinct from first public release."}
            with (temporary / "manifest.json").open("w") as handle:
                json.dump(manifest, handle, indent=2); handle.flush(); os.fsync(handle.fileno())
            try:
                os.rename(temporary, folder)
            except OSError:
                if not folder.exists():
                    raise
        _verified_bundle(folder, kind)
        record_acquisition_receipt(folder, identity)
        return folder
    finally:
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)


def read_multinational_evidence(root: Path, kind: str) -> dict:
    """Select a canonical receipt, verify originals and return bounded summaries."""
    from .source_reconciliation import _selected_manifest
    identity = _source_identity(kind)
    parent = Path(root) / "multinationals" / kind / EDITIONS[kind]
    if not parent.exists():
        return {"status": f"missing_original_{kind}_evidence", "source_count": 0,
                "original_source_hash_verified": False, "aggregate_produced": False,
                "full_history_verified": False, "first_publication_verified": False}
    retrieved, manifest_hash, path, _record, selection = _selected_manifest(parent, identity)
    manifest, report = _verified_bundle(path.parent, kind)
    if selection != "acquisition_receipt" or sha256(path.read_bytes()).hexdigest() != manifest_hash:
        _fail("Original multinational acquisition receipt missing")
    return {**report, "source_count": len(SOURCE_FILES[kind]), "original_source_hash_verified": True,
            "bundle_digest": path.parent.name, "source_manifest_sha256": manifest_hash,
            "evidence_retrieved_at_utc": retrieved.isoformat(), "selection_method": selection,
            "acquisition_method": manifest["acquisition_method"],
            "sources": [{"file": name, "url": url, "sha256": manifest["files"][name],
                         "http_metadata": (manifest.get("http_metadata") or {}).get(name)}
                        for name, url in SOURCE_FILES[kind].items()]}


def read_amne_evidence(root: Path) -> dict:
    return read_multinational_evidence(root, "amne")


def read_meip_evidence(root: Path) -> dict:
    return read_multinational_evidence(root, "meip")


def collect_multinational_source(kind: str, *, root: Path, client) -> dict:
    """Fetch only the reviewed publisher routes and preserve their native bytes."""
    require_managed_client(client)
    _source_identity(kind)
    payloads, metadata = {}, {}
    for name, url in SOURCE_FILES[kind].items():
        response = client.get(url, follow_redirects=False)
        response.raise_for_status()
        if response.status_code != 200 or len(response.content) > 55_000_000:
            _fail("Original multinational HTTP response status or size invalid")
        payloads[name] = response.content
        metadata[name] = {"url": url, "status": response.status_code,
                          "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                          "last_modified": response.headers.get("last-modified"),
                          "etag": response.headers.get("etag"),
                          "content_type": response.headers.get("content-type")}
    folder = store_multinational_source(kind, payloads, root=root, http_metadata=metadata)
    return {"kind": kind, "edition": EDITIONS[kind], "bundle_digest": folder.name,
            "source_count": len(payloads), "database_writes": 0}
