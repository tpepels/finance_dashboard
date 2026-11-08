"""Rotta & Kumar (2024) productive/unproductive framework originals for L04.

One bundle holds four pinned originals:

* the authors' Zenodo deposit (doi:10.5281/zenodo.17342264): Table A1, which
  classifies the 56 WIOD industries as productive (PA), unproductive (UA, by
  group) or excluded, and their 43-country 2000-2014 panel of Marxian
  variables with its published labour and capital variants;
* Tsoulfidis & Paitaridis, MPRA paper 81542 (2017), whose Appendix Table A1
  is a published alternative classification;
* the WIOD 2016 Socio-Economic Accounts from DataverseNL
  (doi:10.34894/PJ2M1C). DataverseNL's robots.txt disallows automated
  clients, so this file is an operator-supplied original, verified against
  the publisher's own SHA-1.

The reader verifies every byte against the pins, then recomputes the
authors' published panel from the publisher's SEA rows under Table A1. That
replication is the original-value check: nothing is accepted on the panel's
word alone. The panel's input-origin ratio (WIOT.VA.PA / WIOT.TV.PA) comes
from the WIOD input-output tables, which are not yet imported; identities
that use it are checked, the ratio itself is carried as author-published.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from hashlib import md5, sha1, sha256
import io
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

import httpx
from python_calamine import CalamineWorkbook

from .bis import ProviderError
from .source_capture import canonical_bytes
from .source_evidence import record_acquisition_receipt
from .source_policy import managed_client, require_managed_client

IDENTITY = {"publisher": "Rotta & Kumar (2024); GGDC WIOD 2016; Tsoulfidis & Paitaridis (2017)",
            "evidence_type": "marxian_productive_sector_framework_originals"}
FOLDER = "marxian-sectors"
ZENODO = "https://zenodo.org/api/records/17342264/files/"
SOURCES = {
    "rk-tables.xlsx": {
        "url": ZENODO + "Tables%201%20A1%20A2%20A3.xlsx/content", "origin": "publisher_collector",
        "bytes": 43094, "md5": "b22f05e3c26d7f8e6326dc4defb23717",
        "sha256": "d207b081b16d9f00189c1fc1baf90d10fdfa7dc6be2a4670b27dc026e6783c4a"},
    "rk-panel.xlsx": {
        "url": ZENODO + "SCED%20-%20Panel%20dataset%20of%20Marxist%20variables%20-%20%5B24october2023%5D.xlsx/content",
        "origin": "publisher_collector", "bytes": 2064917, "md5": "9af5b9a04811956729f8d5223761948e",
        "sha256": "cb4aea9866ef9eb3e0c687d1914aac4b3899403fa0d2e08b096e5dd1fe424258"},
    "tp-2017.pdf": {
        "url": "https://mpra.ub.uni-muenchen.de/81542/1/MPRA_paper_81542.pdf", "origin": "publisher_collector",
        "bytes": 423263, "sha256": "0ca480386c38524c1497b3d4c606b47da3dc4ffb7f02f9f1d82bc7e11531e3e1"},
    "wiod-sea.xlsx": {
        "url": "https://dataverse.nl/api/access/datafile/199095", "origin": "operator_original",
        "bytes": 5536437, "sha1": "821bba29c42f3a42009eb1b14dbdaa2922d01236",
        "sha256": "8cf5ed3d1b7d7ddae93037cc5e1c1d0a2721b9a7679dcc076b85ac5220c576ce"},
}
YEARS = tuple(range(2000, 2015))
COUNTRY_COUNT = 43
# Table A1 as published: 56 WIOD industries, 43 productive, 2 excluded.
TABLE_A1_COUNTS = {"industries": 56, "PA": 43, "EX": 2}
LEVELS = ("GO", "II", "VA", "EMP", "EMPE", "H_EMPE", "COMP", "LAB", "CAP", "K")
# Panel group suffix -> Table A1 group(s) it sums.
GROUPS = {"PA": ("PA",), "UA": ("UA.finance", "UA.real estate", "UA.government", "UA.trade", "UA.additional"),
          "UA.finance": ("UA.finance",), "UA.realestate": ("UA.real estate",), "UA.gov": ("UA.government",)}
# Tsoulfidis & Paitaridis (2017), Appendix Table A1, BEA NAICS sectors. Each
# label must appear in the pinned PDF's table; the WIOD mapping is a
# reviewed concordance (NACE classifies by activity, so government
# enterprises fall in their activity's industry and O84 is general
# government). Against Rotta & Kumar's Table A1 it moves waste management
# (E37-E39) and the professional, scientific and technical services that
# Rotta & Kumar keep productive (M71, M72, M74_M75) to unproductive.
TP_PRODUCTIVE = ("Farms", "Forestry, fishing, and related activities", "Mining", "Utilities", "Construction",
                 "Manufacturing", "Transportation and warehousing", "Information",
                 "Computer systems design and related services", "Educational services",
                 "Health care and social assistance", "Arts, entertainment, and recreation",
                 "Accommodation and food services", "Other services, except government",
                 "Government enterprises (Federal)", "Government enterprises (State and Local)")
TP_UNPRODUCTIVE = ("Wholesale trade", "Retail trade", "Real estate",
                   "Rental and leasing services and lessors of intangible assets",
                   "Federal Reserve banks, credit intermediation, and related activities",
                   "Securities, commodity contracts, and investments", "Insurance carriers and related activities",
                   "Funds, trusts, and other financial vehicles", "Legal services",
                   "Miscellaneous professional, scientific, and technical services",
                   "Management of companies and enterprises", "Administrative and support services",
                   "Waste management and remediation services", "Federal general government (defense)",
                   "Federal general government (nondefense)", "State and local general government")
TP_TO_UNPRODUCTIVE = ("E37-E39", "M71", "M72", "M74_M75")
# Relative and absolute tolerances: floating-point serialization only.
_SCALE_LEVEL = (1e-9, 1e-6)
_SCALE_DERIVED = (1e-9, 1e-9)


def _hashes(raw: bytes) -> dict:
    return {"bytes": len(raw), "sha256": sha256(raw).hexdigest(), "md5": md5(raw).hexdigest(),
            "sha1": sha1(raw).hexdigest()}


def _check_pin(name: str, raw: bytes) -> None:
    pin, seen = SOURCES[name], _hashes(raw)
    if any(seen[key] != pin[key] for key in ("bytes", "sha256", "md5", "sha1") if key in pin):
        raise ProviderError(f"{name} differs from the pinned original")


def store_marxian_sectors(originals: dict[str, bytes], evidence_root: Path) -> Path:
    """Archive the four pinned originals as one immutable bundle with a receipt."""
    if set(originals) != set(SOURCES):
        raise ValueError("marxian_original_file_set_invalid")
    for name, raw in originals.items():
        _check_pin(name, raw)
    files = {name: {"url": SOURCES[name]["url"], "origin": SOURCES[name]["origin"], **_hashes(raw)}
             for name, raw in sorted(originals.items())}
    content = {"source_identity": IDENTITY,
               "files": {name: {k: v[k] for k in ("url", "sha256", "bytes")} for name, v in files.items()}}
    parent = Path(evidence_root) / FOLDER
    parent.mkdir(parents=True, exist_ok=True)
    bundle = parent / sha256(canonical_bytes(content)).hexdigest()
    if not bundle.exists():
        staging = Path(tempfile.mkdtemp(prefix=".marxian-", dir=parent))
        try:
            for name, raw in originals.items():
                with (staging / name).open("wb") as handle:
                    handle.write(raw); handle.flush(); os.fsync(handle.fileno())
            manifest = {"schema_version": 1, "source_identity": IDENTITY, "content_identity": content,
                        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(), "files": files,
                        "publication_note": ("Zenodo record published 2023-12-22; WIOD SEA November 2016 release, "
                                             "published February 2018; retrieval time is not a release date.")}
            (staging / "manifest.json").write_bytes(canonical_bytes(manifest))
            os.rename(staging, bundle)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
    record_acquisition_receipt(bundle, IDENTITY)
    return bundle


def acquire_marxian_sectors(evidence_root: Path, *, wiod_sea: Path, client: httpx.Client | None = None) -> Path:
    """Fetch the robots-permitted Zenodo and MPRA originals; read the operator's SEA copy."""
    sea = Path(wiod_sea)
    if sea.is_symlink() or not sea.is_file() or sea.stat().st_size != SOURCES["wiod-sea.xlsx"]["bytes"]:
        raise ProviderError("WIOD SEA original file is missing or not the pinned size")
    owned = client is None
    client = require_managed_client(client) if client is not None else managed_client(
        timeout=120, follow_redirects=False, headers={"User-Agent": "finance-dashboard-research/0.2 (private research)"})
    try:
        originals = {"wiod-sea.xlsx": sea.read_bytes()}
        for name, pin in SOURCES.items():
            if pin["origin"] != "publisher_collector":
                continue
            response = client.get(pin["url"])
            if response.status_code != 200 or len(response.content) != pin["bytes"]:
                raise ProviderError(f"{name} original request failed")
            originals[name] = response.content
        return store_marxian_sectors(originals, evidence_root)
    except (httpx.HTTPError, OSError) as exc:
        raise ProviderError("Marxian framework originals could not be acquired") from exc
    finally:
        if owned:
            client.close()


def _sheet(raw: bytes, name: str) -> list[list]:
    try:
        return CalamineWorkbook.from_filelike(io.BytesIO(raw)).get_sheet_by_name(name).to_python()
    except Exception:  # calamine raises its own errors for damaged workbooks or absent sheets
        raise ProviderError("framework workbook is unreadable or lacks a published sheet") from None


def parse_classification(raw: bytes) -> dict[str, str]:
    """Table A1: WIOD code -> PA, UA.<group> or EX, exactly as the authors list them."""
    rows = _sheet(raw, "Activities (complete)")
    out, group = {}, None
    for row in rows:
        code, number, label = (list(row) + ["", "", ""])[:3]
        code = str(code).strip()
        if code == "code" and str(label).strip() == "Productive Activities":
            group = "PA"
        elif not code and isinstance(label, str) and label.startswith("Unproductive Activities ("):
            group = "UA." + label[len("Unproductive Activities ("):].rstrip(") ").lower()
        elif not code and isinstance(label, str) and label.strip() == "Excluded Activities":
            group = "EX"
        elif code and isinstance(number, float):
            if group is None or code in out:
                raise ProviderError("Rotta-Kumar Table A1 layout differs from the published table")
            out[code] = group
    counts = defaultdict(int)
    for value in out.values():
        counts[value] += 1
    if (len(out) != TABLE_A1_COUNTS["industries"] or counts["PA"] != TABLE_A1_COUNTS["PA"]
            or counts["EX"] != TABLE_A1_COUNTS["EX"] or set(out.values()) - {"PA", "EX", *GROUPS["UA"]}):
        raise ProviderError("Rotta-Kumar Table A1 does not classify the 56 WIOD industries as published")
    return out


def tp_classification(raw: bytes, baseline: dict[str, str]) -> dict[str, str]:
    """The T&P alternative, after checking every sector label against the pinned PDF's table."""
    from pypdf import PdfReader
    import logging
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    try:
        pages = [page.extract_text() or "" for page in PdfReader(io.BytesIO(raw)).pages]
    except Exception:  # pypdf raises its own errors for damaged documents
        raise ProviderError("Tsoulfidis-Paitaridis paper is unreadable") from None
    table = next((text for text in pages if "Table A1. Classification of Sectors" in text), None)
    if table is None:
        raise ProviderError("Tsoulfidis-Paitaridis Table A1 is absent")
    flat = re.sub(r"\s+", " ", table[table.index("Table A1. Classification of Sectors"):])
    if any(label not in flat for label in TP_PRODUCTIVE + TP_UNPRODUCTIVE) or not flat.startswith(
            "Table A1. Classification of Sectors Productive Activities Unproductive Activities"):
        raise ProviderError("Tsoulfidis-Paitaridis Table A1 differs from the reviewed transcription")
    out = dict(baseline)
    for code in TP_TO_UNPRODUCTIVE:
        if out.get(code) != "PA":
            raise ProviderError("T&P concordance no longer differs from Table A1 as reviewed")
        out[code] = "UA.additional"
    return out




def _number(value):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def sea_aggregates(raw: bytes, classification: dict[str, str]) -> tuple[dict, dict]:
    """(country, year, variable, group) sums of the publisher's SEA rows, plus its units."""
    notes = _sheet(raw, "Notes")
    if not any("November 2016 release" in str(cell) for row in notes[:5] for cell in row):
        raise ProviderError("WIOD SEA is not the November 2016 release")
    units = {str(row[3]).strip(): str(row[4]).strip() for row in notes if len(row) > 4 and str(row[3]).strip() in LEVELS}
    if set(units) != set(LEVELS):
        raise ProviderError("WIOD SEA notes do not define every variable")
    rows = _sheet(raw, "DATA")
    header = rows[0]
    if [str(cell) for cell in header[:4]] != ["country", "variable", "description", "code"]:
        raise ProviderError("WIOD SEA layout differs from the published release")
    years = {int(cell): index for index, cell in enumerate(header) if isinstance(cell, float)}
    if tuple(sorted(years)) != YEARS:
        raise ProviderError("WIOD SEA years differ from 2000-2014")
    sums, codes = {}, set()
    for row in rows[1:]:
        country, variable, code = str(row[0]), str(row[1]), str(row[3])
        codes.add(code)
        group = classification.get(code)
        if group is None:
            raise ProviderError("WIOD SEA industry is not in the classification")
        if group == "EX" or variable not in LEVELS:
            continue
        for year, index in years.items():
            value = _number(row[index])
            if value is None:
                continue
            for target, members in GROUPS.items():
                if group in members:
                    key = (country, year, variable, target)
                    sums[key] = sums.get(key, 0.0) + value
    if codes != set(classification):
        raise ProviderError("WIOD SEA industries differ from Table A1")
    return sums, units


def _close(mine, published, tolerance) -> bool:
    relative, absolute = tolerance
    return abs(mine - published) <= max(relative * abs(published), absolute)


def _derived(a, ratio) -> dict:
    """Table A3 formulas that use only SEA aggregates and the panel's input-origin ratio."""
    def get(variable, group="PA"):
        return a.get((variable, group))
    out = {}
    def put(name, function):
        try:
            value = function()
        except (TypeError, ZeroDivisionError):
            return
        out[name] = value
    va, comp, lab, k = get("VA"), get("COMP"), get("LAB"), get("K")
    put("COMP_PE.PA", lambda: get("EMP") / get("EMPE") * comp)
    cpe = out.get("COMP_PE.PA")
    total = None if k is None or get("K", "UA") is None else k + get("K", "UA")
    put("K", lambda: k + get("K", "UA"))
    put("OCC.K", lambda: total / comp)
    put("SEA.Rate.of.Surplus.Value.PA", lambda: (va - comp) / comp)
    put("SEA.Rate.of.Surplus.Value.PA.LAB", lambda: (va - lab) / lab)
    put("SEA.Rate.of.Surplus.Value.PA.COMP_PE", lambda: (va - cpe) / cpe)
    put("SEA.Net.Profit.Rate.PA.COMP", lambda: (va - comp) / k)
    put("SEA.Net.Profit.Rate.PA.LAB", lambda: (va - lab) / k)
    put("SEA.Net.Profit.Rate.UA.COMP", lambda: (get("VA", "UA") - get("COMP", "UA")) / get("K", "UA"))
    put("SEA.Net.Profit.Rate.UA.LAB", lambda: (get("VA", "UA") - get("LAB", "UA")) / get("K", "UA"))
    if ratio is not None:
        put("WIOT.SEA.VA.PA", lambda: ratio * get("GO"))
        marx = out.get("WIOT.SEA.VA.PA")
        no_gov = None if total is None or get("K", "UA.gov") is None else total - get("K", "UA.gov")
        for suffix, wage in (("", comp), (".LAB", lab), (".COMP_PE", cpe)):
            put("WIOT.SEA.Surplus.Value.PA" + suffix, lambda wage=wage: marx - wage)
            put("WIOT.SEA.Rate.of.Surplus.Value.PA" + suffix, lambda wage=wage: (marx - wage) / wage)
            put("WIOT.SEA.Rate.of.Profit.over.Kpa" + suffix, lambda wage=wage: (marx - wage) / k)
            put("WIOT.SEA.Rate.of.Profit.over.K" + suffix, lambda wage=wage: (marx - wage) / total)
            put("WIOT.SEA.Rate.of.Profit.over.K.noGov" + suffix, lambda wage=wage: (marx - wage) / no_gov)
    return out


def replicate_panel(panel_raw: bytes, sums: dict, countries: set[str]) -> dict:
    """Recompute every published level and SEA/identity ratio, country-year by country-year."""
    rows = _sheet(panel_raw, "Panel Data")
    header = [str(cell) for cell in rows[0]]
    if header[:2] != ["Country", "Year"]:
        raise ProviderError("Rotta-Kumar panel layout differs from the deposit")
    column = {name: index for index, name in enumerate(header)}
    seen, levels, derived, both_missing, mismatches = set(), [0, 0], [0, 0], 0, []
    for row in rows[1:]:
        country, year = str(row[0]), int(float(row[1]))
        seen.add((country, year))
        mine = {}
        for variable in LEVELS:
            for group in GROUPS:
                name = f"{variable}.{group}"
                published, value = _number(row[column[name]]), sums.get((country, year, variable, group))
                mine[(variable, group)] = value
                if published is None and value is None:
                    both_missing += 1
                    continue
                levels[0] += 1
                if published is not None and value is not None and _close(value, published, _SCALE_LEVEL):
                    levels[1] += 1
                elif len(mismatches) < 20:
                    mismatches.append({"country": country, "year": year, "variable": name,
                                       "published": published, "recomputed": value})
        tv, va = _number(row[column["WIOT.TV.PA"]]), _number(row[column["WIOT.VA.PA"]])
        for name, value in _derived(mine, va / tv if tv and va is not None else None).items():
            if name not in column or (published := _number(row[column[name]])) is None:
                continue
            derived[0] += 1
            if _close(value, published, _SCALE_DERIVED):
                derived[1] += 1
            elif len(mismatches) < 20:
                mismatches.append({"country": country, "year": year, "variable": name,
                                   "published": published, "recomputed": value})
    expected = {(country, year) for country in countries for year in YEARS}
    return {"country_years": len(seen), "complete_country_years": seen == expected,
            "level_checks": levels[0], "level_matches": levels[1],
            "derived_checks": derived[0], "derived_matches": derived[1],
            "missing_in_publisher_and_panel": both_missing, "mismatches": mismatches,
            "passed": seen == expected and levels[0] == levels[1] and derived[0] == derived[1] and levels[0] > 0}


def read_marxian_evidence(evidence_root: Path) -> dict:
    """Verify the pinned originals and the replication; return no raw rows."""
    from .source_reconciliation import _selected_manifest
    parent = Path(evidence_root) / FOLDER
    if not parent.exists():
        return {"status": "missing_original_framework_files", "original_source_hash_verified": False,
                "full_history_verified": False, "first_publication_verified": False}
    observed, manifest_hash, path, manifest, selection = _selected_manifest(parent, IDENTITY)
    folder = path.parent
    content = manifest["content_identity"]
    if (manifest.get("schema_version") != 1 or folder.name != sha256(canonical_bytes(content)).hexdigest()
            or content["source_identity"] != IDENTITY or set(manifest["files"]) != set(SOURCES)):
        raise ValueError("marxian_source_identity_mismatch")
    raw = {}
    for name, record in manifest["files"].items():
        target = folder / name
        if target.is_symlink() or not target.is_file():
            raise ValueError("marxian_source_file_invalid")
        raw[name] = target.read_bytes()
        if _hashes(raw[name])["sha256"] != record["sha256"]:
            raise ValueError("marxian_source_hash_mismatch")
        _check_pin(name, raw[name])
    baseline = parse_classification(raw["rk-tables.xlsx"])
    alternative = tp_classification(raw["tp-2017.pdf"], baseline)
    # Table 1 lists the countries in two code/name column pairs.
    countries = {str(cell).strip() for row in _sheet(raw["rk-tables.xlsx"], "List of Countries")
                 for cell in row[0::2] if re.fullmatch(r"[A-Z]{3}", str(cell).strip()) and str(cell).strip() != "ROW"}
    sums, units = sea_aggregates(raw["wiod-sea.xlsx"], baseline)
    if len(countries) != COUNTRY_COUNT or {key[0] for key in sums} != countries:
        raise ValueError("marxian_country_set_mismatch")
    replication = replicate_panel(raw["rk-panel.xlsx"], sums, countries)
    def counts(classification):
        result = defaultdict(int)
        for group in classification.values():
            result[group] += 1
        return dict(sorted(result.items()))
    return {"status": "verified_framework_originals_replicated" if replication["passed"]
            else "framework_replication_failed",
            "original_source_hash_verified": True, "bundle_digest": folder.name,
            "source_manifest_sha256": manifest_hash, "acquisition_observed_at_utc": observed.isoformat(),
            "selection_method": selection,
            "file_sha256": {name: record["sha256"] for name, record in sorted(manifest["files"].items())},
            "countries": sorted(countries), "years": list(YEARS), "industries": len(baseline),
            "sea_units": units, "replication": replication,
            "classifications": {
                "rotta_kumar_2024_table_a1": {"groups": counts(baseline), "source": "rk-tables.xlsx"},
                "tsoulfidis_paitaridis_2017_table_a1": {
                    "groups": counts(alternative), "source": "tp-2017.pdf",
                    "moved_to_unproductive": list(TP_TO_UNPRODUCTIVE),
                    "concordance": "reviewed NAICS sector -> WIOD industry transcription"},
                "all_industries": {"groups": {"all_except_excluded": sum(g != "EX" for g in baseline.values())},
                                   "source": "specification method alternative; no productive split"}},
            "input_output_correction_recomputed": False,
            "scope": "Rotta & Kumar (2024) framework, 43 WIOD countries, 56 industries, 2000-2014, latest revised values.",
            "bounded_data_verified": replication["passed"], "full_history_verified": replication["passed"],
            "first_publication_verified": False}


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--wiod-sea", type=Path, required=True,
                        help="Socio_Economic_Accounts.xlsx downloaded by the owner from DataverseNL")
    args = parser.parse_args(argv)
    acquire_marxian_sectors(args.evidence_dir, wiod_sea=args.wiod_sea)
    evidence = read_marxian_evidence(args.evidence_dir)
    print(json.dumps({key: evidence[key] for key in ("status", "bundle_digest", "industries", "replication",
                                                     "classifications")}, indent=2))
    return 0 if evidence["status"] == "verified_framework_originals_replicated" else 1


if __name__ == "__main__":
    raise SystemExit(main())
