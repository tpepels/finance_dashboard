"""EU KLEMS & INTANProd Release 2025 industry data for extending L04 to 1995-2021.

EU KLEMS publishes NACE Rev. 2 industries that are equal to or coarser than
WIOD's 56. Each WIOD industry belongs to exactly one EU KLEMS leaf
(CONCORDANCE). Per country and year the finest published cover is used: a leaf
when published, else the published aggregate (the United States publishes
C20-C21, D-E, G, H and J; Japan publishes M-N). A leaf or aggregate whose WIOD
industries fall on both sides of the productive line (M under Rotta & Kumar,
E under Tsoulfidis & Paitaridis, M-N in Japan) is never split by imputation:
it is counted once as productive and once as unproductive, two bounds.

Sums come out in the shape `rates_from_sums` reads, so the same Table A3
formulas apply: VA, GO, COMP, EMP, EMPE from the national accounts, LAB from
the growth accounts, K = K_GFCF (current-price capital stock) from the capital
accounts; millions of national currency.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import tempfile

from .bis import ProviderError
from .source_capture import canonical_bytes
from .source_evidence import record_acquisition_receipt

CONCORDANCE = {
    "A": ("A01", "A02", "A03"), "B": ("B",), "C10-C12": ("C10-C12",), "C13-C15": ("C13-C15",),
    "C16-C18": ("C16", "C17", "C18"), "C19": ("C19",), "C20": ("C20",), "C21": ("C21",), "C22-C23": ("C22", "C23"),
    "C24-C25": ("C24", "C25"), "C26": ("C26",), "C27": ("C27",), "C28": ("C28",), "C29-C30": ("C29", "C30"),
    "C31-C33": ("C31_C32", "C33"), "D": ("D35",), "E": ("E36", "E37-E39"), "F": ("F",), "G45": ("G45",),
    "G46": ("G46",), "G47": ("G47",), "H49": ("H49",), "H50": ("H50",), "H51": ("H51",), "H52": ("H52",),
    "H53": ("H53",), "I": ("I",), "J58-J60": ("J58", "J59_J60"), "J61": ("J61",), "J62-J63": ("J62_J63",),
    "K": ("K64", "K65", "K66"), "L": ("L68",), "M": ("M69_M70", "M71", "M72", "M73", "M74_M75"), "N": ("N",),
    "O": ("O84",), "P": ("P85",), "Q": ("Q",), "R-S": ("R_S",), "T": ("T",), "U": ("U",),
}
AGGREGATES = {"C20-C21": ("C20", "C21"), "C26-C27": ("C26", "C27"), "D-E": ("D", "E"),
              "G": ("G45", "G46", "G47"), "H": ("H49", "H50", "H51", "H52", "H53"),
              "J": ("J58-J60", "J61", "J62-J63"), "M-N": ("M", "N")}
COUNTRIES = {"US": "USA", "DE": "DEU", "FR": "FRA", "UK": "GBR", "IT": "ITA", "ES": "ESP", "PT": "PRT", "JP": "JPN"}
NATIONAL = {"VA_CP": "VA", "GO_CP": "GO", "COMP": "COMP", "EMP": "EMP", "EMPE": "EMPE"}
YEARS = tuple(range(1995, 2022))


def _wiod_codes(code: str) -> tuple[str, ...]:
    if code in CONCORDANCE:
        return CONCORDANCE[code]
    return tuple(w for child in AGGREGATES[code] for w in _wiod_codes(child))


def group_of(code: str, classification: dict[str, str]) -> str:
    """PA, a UA group, EX, or 'mixed' when the industry spans both sides of the productive line."""
    groups = {classification.get(w, "") for w in _wiod_codes(code)} - {"EX"}
    if not groups:
        return "EX"
    productive = {g == "PA" for g in groups}
    if len(productive) > 1:
        return "mixed"
    return groups.pop() if len(groups) == 1 else "UA"


def industry_cover(available: set[str]) -> list[str]:
    """The finest non-overlapping set of published codes covering the economy."""
    cover = set(CONCORDANCE)
    for parent, children in AGGREGATES.items():
        leaves = {leaf for child in children for leaf in ((child,) if child in CONCORDANCE else AGGREGATES[child])}
        if not leaves <= available and parent in available:
            cover = (cover - leaves) | {parent}
    return sorted(code for code in cover if code in available)


def klems_sums(rows: list[dict], classification: dict[str, str], *, mixed_as: str) -> dict:
    """{(ISO3, year, variable, 'PA'|'UA'): sum} over the finest published cover; mixed industries go to `mixed_as`."""
    by_cy: dict = {}
    for row in rows:
        by_cy.setdefault((row["geo"], int(row["year"])), {})[row["code"]] = row
    out: dict = {}
    for (geo, year), industries in by_cy.items():
        country = COUNTRIES.get(geo)
        if country is None:
            continue
        for code in industry_cover(set(industries)):
            group = group_of(code, classification)
            if group == "EX":
                continue
            side = mixed_as if group == "mixed" else ("PA" if group == "PA" else "UA")
            for variable, value in industries[code].items():
                if variable in ("geo", "year", "code") or value is None:
                    continue
                key = (country, year, variable, side)
                out[key] = out.get(key, 0.0) + value
    return out


def _number(raw: str) -> float | None:
    if raw in ("", "NA", None):
        return None
    try:
        return float(raw)
    except ValueError as exc:
        raise ProviderError("EU KLEMS cell is not numeric") from exc


def read_rows(national: Path, growth: Path, capital: Path) -> list[dict]:
    """One row per (country, year, industry) for the L04 countries, from the three all-country CSV files."""
    rows: dict = {}

    def row(geo, year, code):
        return rows.setdefault((geo, int(year), code), {"geo": geo, "year": int(year), "code": code})
    with Path(national).open(newline="") as handle:
        for r in csv.DictReader(handle):
            if r["geo_code"] in COUNTRIES:
                target = row(r["geo_code"], r["year"], r["nace_r2_code"])
                for source, name in NATIONAL.items():
                    target[name] = _number(r.get(source))
    with Path(growth).open(newline="") as handle:
        for r in csv.DictReader(handle):
            if r["var"] == "LAB" and r["geo_code"] in COUNTRIES:
                row(r["geo_code"], r["year"], r["nace_r2_code"])["LAB"] = _number(r["value"])
    with Path(capital).open(newline="") as handle:
        for r in csv.DictReader(handle):
            if r["geo_code"] in COUNTRIES:
                row(r["geo_code"], r["year"], r["nace_r2_code"])["K"] = _number(r.get("K_GFCF"))
    return list(rows.values())


FOLDER = "euklems-industry"
IDENTITY = {"publisher": "EU KLEMS & INTANProd Release 2025 (Luiss Lab of European Economics)",
            "evidence_type": "euklems_2025_all_country_csv"}
FILES = {
    "national accounts.csv": "https://dl.dropboxusercontent.com/s/nkz7mdp0onken1j/national%20accounts.csv",
    "growth accounts.csv": "https://dl.dropboxusercontent.com/s/w0mdttie9kjlh82/growth%20accounts.csv",
    "capital accounts.csv": "https://dl.dropboxusercontent.com/s/sp2p4m86et66nfg/capital%20accounts.csv",
}


def _hash(path: Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def store(root: Path, originals: dict[str, Path]) -> Path:
    if set(originals) != set(FILES):
        raise ValueError("euklems_file_set_invalid")
    content = {"source_identity": IDENTITY,
               "files": {name: {"url": FILES[name], "sha256": _hash(path), "bytes": Path(path).stat().st_size}
                         for name, path in sorted(originals.items())}}
    parent = Path(root) / FOLDER
    parent.mkdir(parents=True, exist_ok=True)
    bundle = parent / sha256(canonical_bytes(content)).hexdigest()
    if not bundle.exists():
        staging = Path(tempfile.mkdtemp(prefix=".euklems-", dir=parent))
        try:
            for name, path in originals.items():
                shutil.copyfile(path, staging / name)
            manifest = {"schema_version": 1, "source_identity": IDENTITY, "content_identity": content,
                        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                        "publication_note": "EU KLEMS & INTANProd Release 2025; retrieval time is not a release date."}
            (staging / "manifest.json").write_bytes(canonical_bytes(manifest))
            os.rename(staging, bundle)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
    record_acquisition_receipt(bundle, IDENTITY)
    return bundle


_CACHE: dict = {}


def archived_rows(root: Path) -> list[dict] | None:
    """Rows from the verified archived files (hash-checked once, cached beside the bundle); None when absent."""
    parent = Path(root) / FOLDER
    if not parent.exists():
        return None
    from .source_reconciliation import _selected_manifest
    _, _, path, manifest, _ = _selected_manifest(parent, IDENTITY)
    folder = path.parent
    if folder.name in _CACHE:
        return _CACHE[folder.name]
    derived = folder.parent / f"{folder.name}.rows.json"
    if derived.is_file():
        rows = json.loads(derived.read_text())
    else:
        for name, record in manifest["content_identity"]["files"].items():
            if _hash(folder / name) != record["sha256"]:
                raise ProviderError("EU KLEMS archived file differs from its manifest")
        rows = read_rows(folder / "national accounts.csv", folder / "growth accounts.csv", folder / "capital accounts.csv")
        derived.write_text(json.dumps(rows))
    _CACHE[folder.name] = rows
    return rows


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Archive EU KLEMS 2025 all-country CSV files for L04.")
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--national", type=Path, required=True)
    parser.add_argument("--growth", type=Path, required=True)
    parser.add_argument("--capital", type=Path, required=True)
    args = parser.parse_args(argv)
    bundle = store(args.evidence_dir, {"national accounts.csv": args.national, "growth accounts.csv": args.growth,
                                       "capital accounts.csv": args.capital})
    print(json.dumps({"bundle": str(bundle)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
