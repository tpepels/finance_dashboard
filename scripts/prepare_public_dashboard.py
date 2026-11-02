"""Publish only explicitly redistributable macro source observations to Pages.

Input is a fully validated *private* static export. The transformation never
copies market, FX, SEC/Wisesheets, proprietary Siblis or unreviewed MSCI/BIS
data into the public Vite site. Missing series remain visible as chart metadata,
with clear rights-blocked states in the frontend.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import tempfile

PUBLIC_RIGHTS = frozenset({"cc_by_4_0"})
SERIES_METADATA = {
    "id", "name", "theme", "provider", "geography", "frequency",
    "unit", "source_url", "measurement", "rights", "first", "last", "count",
    "file", "revision_policy", "notes",
}
SERIES_DOCUMENT = {
    "schema_version", "id", "name", "theme", "provider", "geography",
    "frequency", "unit", "source_url", "source_key", "measurement",
    "rights", "revision_policy", "notes", "observations",
}


def prepare_public(input_dir: Path, output_dir: Path) -> dict:
    """Reject ambiguity, missing source identity, and non-allowlisted content."""
    source = input_dir.resolve()
    destination = output_dir.resolve()
    if destination == source or source in destination.parents:
        raise ValueError("Public destination must not be inside the private source directory")
    manifest = json.loads((source / "index.json").read_text(encoding="utf-8"))
    charts = json.loads((source / "charts.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or charts.get("schema_version") != 1:
        raise ValueError("Unknown private export schema")
    items = manifest.get("series")
    if not isinstance(items, list) or len(items) != manifest.get("series_count"):
        raise ValueError("Incomplete private source manifest")
    if not isinstance(charts.get("charts"), list) or not charts["charts"]:
        raise ValueError("No chart definitions")
    allowed: dict[str, dict] = {}
    files: dict[str, dict] = {}
    for entry in items:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise ValueError("Invalid source identity")
        if entry["id"] in allowed or entry["id"] in files:
            raise ValueError("Duplicate private source identity")
        sid = entry["id"]
        if not sid.replace("_", "").replace(".", "").replace("-", "").isalnum():
            raise ValueError("Invalid source path component")
        if entry.get("rights") not in PUBLIC_RIGHTS:
            continue
        expected = f"series/{sid}.json"
        if entry.get("file") != expected:
            raise ValueError("Unexpected source export path")
        doc = json.loads((source / expected).read_text(encoding="utf-8"))
        if (doc.get("id") != sid or doc.get("rights") != entry["rights"]
            or doc.get("schema_version") != 1
            or not isinstance(doc.get("observations"), list)
            or len(doc["observations"]) != entry["count"]
            or not set(doc).issubset(SERIES_DOCUMENT)):
            raise ValueError(f"Unverified published source: {sid}")
        if not all(isinstance(row, dict) and set(row) == {"date", "value"}
                   and isinstance(row["date"], str) and isinstance(row["value"], str)
                   for row in doc["observations"]):
            raise ValueError("Public point fields are not approved")
        allowed[sid] = {key: entry[key] for key in SERIES_METADATA if key in entry}
        files[sid] = doc
    if not allowed:
        raise ValueError("No positively licensed public series; refusing empty publication")

    # Chart *definitions* are metadata only. Existing chart requests without
    # public observations show a blocked-rights message in the app.
    known = {entry["id"] for entry in items}
    for chart in charts["charts"]:
        if any(id not in known for id in chart.get("series_ids", [])):
            raise ValueError("Unknown chart source identity")
    public_manifest = {
        "schema_version": 1,
        "public_dataset": True,
        "generated_at_utc": manifest["generated_at_utc"],
        "series_count": len(allowed),
        "series": [allowed[sid] for sid in sorted(allowed)],
        "rights_note": "Only cc_by_4_0 sources. All other observation series withheld.",
        "temporal_note": "Latest ingested observations; not publication vintages.",
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".public-macro-", dir=destination.parent) as tmp:
        out = Path(tmp)
        (out / "series").mkdir()
        (out / "index.json").write_text(json.dumps(public_manifest, indent=2) + "\n", encoding="utf-8")
        (out / "charts.json").write_text(json.dumps(charts, indent=2) + "\n", encoding="utf-8")
        for sid, doc in files.items():
            (out / "series" / f"{sid}.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(out, destination)
    if any((destination / path).exists() for path in ("markets", "fx", "supplementary")):
        raise AssertionError("Restricted non-macro data leaked into public bundle")
    return public_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="build/static-data")
    parser.add_argument("--output", default="frontend/public/data")
    args = parser.parse_args()
    manifest = prepare_public(Path(args.input), Path(args.output))
    print(f"PUBLIC_MACRO_ALLOWLIST=PASS licensed={manifest['series_count']} no_markets_no_fx_no_supplementary")


if __name__ == "__main__":
    main()
