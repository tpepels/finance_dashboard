"""OECD ICIO 2025 (1995-2022) input-origin ratio for L04's full method after 2014.

The same published rule as `wiod_io`: total value of the productive activities
is output plus the taxes-less-subsidies row of their columns, and their
Marxian value added is that less the inputs bought from productive industries
of every country. ICIO's 50 industries are coarser than WIOD's 56; each WIOD
industry maps to one ICIO industry (U, extraterritorial organisations, is not
in ICIO). An ICIO industry spanning both sides of the productive line (M under
Rotta & Kumar, E under Tsoulfidis & Paitaridis) is counted once as productive
and once as unproductive, on rows and columns alike; nothing is split.
"""
from __future__ import annotations

import csv
from hashlib import sha256
import json
from pathlib import Path

from .source_capture import canonical_bytes

ICIO_CONCORDANCE = {
    "A01": ("A01",), "A02": ("A02",), "A03": ("A03",), "B05": ("B",), "B06": (), "B07": (), "B08": (), "B09": (),
    "C10T12": ("C10-C12",), "C13T15": ("C13-C15",), "C16": ("C16",), "C17_18": ("C17", "C18"), "C19": ("C19",),
    "C20": ("C20",), "C21": ("C21",), "C22": ("C22",), "C23": ("C23",), "C24A": ("C24",), "C24B": (),
    "C25": ("C25",), "C26": ("C26",), "C27": ("C27",), "C28": ("C28",), "C29": ("C29",), "C301": ("C30",),
    "C302T309": (), "C31T33": ("C31_C32", "C33"), "D": ("D35",), "E": ("E36", "E37-E39"), "F": ("F",),
    "G": ("G45", "G46", "G47"), "H49": ("H49",), "H50": ("H50",), "H51": ("H51",), "H52": ("H52",), "H53": ("H53",),
    "I": ("I",), "J58T60": ("J58", "J59_J60"), "J61": ("J61",), "J62_63": ("J62_J63",), "K": ("K64", "K65", "K66"),
    "L": ("L68",), "M": ("M69_M70", "M71", "M72", "M73", "M74_M75"), "N": ("N",), "O": ("O84",), "P": ("P85",),
    "Q": ("Q",), "R": ("R_S",), "S": (), "T": ("T",),
}
# ICIO splits that WIOD keeps together: they take the WIOD industry of their sibling.
_SIBLING = {"B06": "B05", "B07": "B05", "B08": "B05", "B09": "B05", "C24B": "C24A", "C302T309": "C301", "S": "R"}
L04_COUNTRIES = ("USA", "DEU", "FRA", "GBR", "ITA", "ESP", "PRT", "JPN", "CHN")


def _group(industry: str, classification: dict[str, str], mixed_as: str) -> str | None:
    codes = ICIO_CONCORDANCE.get(_SIBLING.get(industry, industry), ())
    groups = {classification.get(code, "") for code in codes} - {"EX", ""}
    if not groups:
        return None
    sides = {"PA" if g == "PA" else "UA" for g in groups}
    return mixed_as if len(sides) > 1 else sides.pop()


def icio_aggregates(header: list[str], rows, classification: dict[str, str], *, countries: set[str],
                    mixed_as: str) -> dict[str, dict[str, float]]:
    """{country: {TV.PA, VA.PA}} from one year's ICIO table (header row, then data rows)."""
    columns: dict[str, list[int]] = {}
    for j, name in enumerate(header):
        country, _, industry = str(name).partition("_")
        if country in countries and industry in ICIO_CONCORDANCE and _group(industry, classification, mixed_as) == "PA":
            columns.setdefault(country, []).append(j)
    tv = {c: 0.0 for c in columns}
    inputs = {c: 0.0 for c in columns}
    for row in rows:
        label = str(row[0])
        if label in ("TLS", "OUT"):
            for c, js in columns.items():
                tv[c] += sum(float(row[j] or 0) for j in js)
            continue
        _, _, industry = label.partition("_")
        if _group(industry, classification, mixed_as) != "PA":
            continue
        for c, js in columns.items():
            inputs[c] += sum(float(row[j] or 0) for j in js)
    return {c: {"TV.PA": tv[c], "VA.PA": tv[c] - inputs[c]} for c in columns}


def icio_ratios(evidence_root: Path, classification: dict[str, str], mixed_as: str) -> dict[tuple[str, int], float] | None:
    """{(country, year): VA.PA / TV.PA} from the verified archived ICIO 2025 tables; None when not archived.

    Each matrix is verified by the existing ICIO reader's publisher pins; results are cached beside the archive."""
    from .icio import PUBLISHER_MATRICES, _verify_publisher_bundle
    base = Path(evidence_root) / "icio"
    if not base.is_dir():
        return None
    key = sha256(canonical_bytes({"classification": classification, "mixed_as": mixed_as,
                                  "pins": {str(y): d["sha256"] for y, d in PUBLISHER_MATRICES.items()}})).hexdigest()
    cache = base / f"marxian-ratios-{key}.json"
    if cache.is_file():
        # The derived cache is not independent scientific evidence. Its
        # pinned source bytes and material accounting must still pass.
        from .icio import read_icio_evidence
        proof = read_icio_evidence(evidence_root)
        if not proof.get("historical_coverage", {}).get("full_history_verified"):
            raise ValueError("icio_marxian_source_history_unverified")
        if any(not row["materiality"]["material_accounting_passed"]
               for row in proof.get("historical_matrices", [])):
            raise ValueError("icio_marxian_source_accounting_failed")
        data = json.loads(cache.read_text())
        return {(k.split("|")[0], int(k.split("|")[1])): v for k, v in data.items()}
    out = {}
    for year in sorted(PUBLISHER_MATRICES):
        parent = base / f"regular-2025-{year}-publisher"
        bundles = [p for p in parent.iterdir() if p.is_dir() and len(p.name) == 64] if parent.is_dir() else []
        if len(bundles) != 1:
            return None
        from .icio import material_accounting
        audit = _verify_publisher_bundle(bundles[0], year)
        if not material_accounting(audit)["material_accounting_passed"]:
            raise ValueError("icio_marxian_source_accounting_failed")
        with (bundles[0] / "matrix.csv").open(newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader)
            for country, values in icio_aggregates(header, reader, classification, countries=set(L04_COUNTRIES),
                                                   mixed_as=mixed_as).items():
                if values["TV.PA"]:
                    out[(country, year)] = values["VA.PA"] / values["TV.PA"]
    cache.write_text(json.dumps({f"{c}|{y}": v for (c, y), v in out.items()}))
    return out
