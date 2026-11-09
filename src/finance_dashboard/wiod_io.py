"""WIOD 2016 world input-output tables (DataverseNL doi:10.34894/PJ2M1C) for L04.

Rotta & Kumar's Table A3 defines, per country and year, from the world
input-output table in millions of US dollars:

* WIOT.TV.PA, total value of the productive activities (PA);
* WIOT.VA.PA, their Marxian value added: total value less inputs bought from
  productive industries of every country (inputs from unproductive
  industries are part of PA value added);
* WIOT.GI.UA and WIOT.NI.UA, the same for unproductive activities.

Replication against all 645 published country-years shows that the authors'
total value is output at basic prices plus the "taxes less subsidies on
products" row of the same columns (basic-price output already contains that
row). The published values are reproduced to about 1e-7 with that rule, and
it is kept here so the input-origin ratio WIOT.VA.PA / WIOT.TV.PA is the
authors' own; the double count is recorded as a method limitation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha1, sha256
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

from python_calamine import CalamineWorkbook

from .bis import ProviderError
from .source_capture import canonical_bytes
from .source_evidence import record_acquisition_receipt

IDENTITY = {"publisher": "GGDC WIOD 2016 release (DataverseNL doi:10.34894/PJ2M1C)",
            "evidence_type": "wiod_2016_world_input_output_tables"}
FOLDER = "wiod-wiot"
NAME = "WIOTS_in_EXCEL.zip"
PIN = {"url": "https://dataverse.nl/api/access/datafile/199104", "bytes": 919328606,
       "sha1": "72748c32ed94a2b19a7e96c22b2f9d68930cffaa"}
YEARS = tuple(range(2000, 2015))


def _file_hashes(path: Path) -> dict:
    h256, h1, size = sha256(), sha1(), 0
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h256.update(chunk); h1.update(chunk); size += len(chunk)
    return {"bytes": size, "sha256": h256.hexdigest(), "sha1": h1.hexdigest()}


def store_wiod_tables(original: Path, evidence_root: Path) -> Path:
    """Verify the publisher's SHA-1 and size, then archive the zip as an immutable bundle with a receipt."""
    seen = _file_hashes(original)
    if seen["bytes"] != PIN["bytes"] or seen["sha1"] != PIN["sha1"]:
        raise ProviderError("WIOD input-output tables differ from the publisher's pinned SHA-1")
    content = {"source_identity": IDENTITY, "files": {NAME: {"url": PIN["url"], "sha256": seen["sha256"], "bytes": seen["bytes"]}}}
    parent = Path(evidence_root) / FOLDER
    parent.mkdir(parents=True, exist_ok=True)
    bundle = parent / sha256(canonical_bytes(content)).hexdigest()
    if not bundle.exists():
        staging = Path(tempfile.mkdtemp(prefix=".wiod-", dir=parent))
        try:
            shutil.copyfile(original, staging / NAME)
            manifest = {"schema_version": 1, "source_identity": IDENTITY, "content_identity": content,
                        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
                        "files": {NAME: {"url": PIN["url"], "origin": "publisher_collector", **seen}},
                        "publication_note": "WIOD 2016 release (November 2016 tables); retrieval time is not a release date."}
            (staging / "manifest.json").write_bytes(canonical_bytes(manifest))
            os.rename(staging, bundle)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
    record_acquisition_receipt(bundle, IDENTITY)
    return bundle


def table_aggregates(rows: list[list], classification: dict[str, str]) -> dict[str, dict[str, float]]:
    """{country: {TV.PA, VA.PA, GI.UA, NI.UA}} from one year's world table, under the published rule."""
    codes, countries = [str(c) for c in rows[2]], [str(c) for c in rows[4]]
    named = {str(r[0]): r for r in rows if len(r) > 2 and str(r[2]) == "TOT"}
    body = [r for r in rows[6:] if len(r) > 2 and str(r[2]) not in ("TOT", "") and str(r[0]) in classification]
    group = lambda code: classification.get(code, "")
    columns: dict[str, dict[str, list[int]]] = {}
    for j in range(4, len(codes)):
        kind = group(codes[j])
        if countries[j] in ("", "TOT") or not kind or kind == "EX":
            continue
        side = "PA" if kind == "PA" else "UA"
        columns.setdefault(countries[j], {"PA": [], "UA": []})[side].append(j)
    pa_rows = [r for r in body if group(str(r[0])) == "PA"]
    ua_rows = [r for r in body if group(str(r[0])).startswith("UA")]
    total = lambda js: sum(float(named["GO"][j]) + float(named["TXSP"][j]) for j in js)
    out = {}
    for country, side in columns.items():
        tv, gi = total(side["PA"]), total(side["UA"])
        out[country] = {"TV.PA": tv, "VA.PA": tv - sum(float(r[j]) for r in pa_rows for j in side["PA"]),
                        "GI.UA": gi, "NI.UA": gi - sum(float(r[j]) for r in ua_rows for j in side["UA"])}
    return out


def _bundle(evidence_root: Path) -> Path | None:
    parent = Path(evidence_root) / FOLDER
    if not parent.exists():
        return None
    from .source_reconciliation import _selected_manifest
    _, _, path, manifest, _ = _selected_manifest(parent, IDENTITY)
    folder = path.parent
    record = manifest["files"][NAME]
    zipped = folder / NAME
    if zipped.is_symlink() or not zipped.is_file() or zipped.stat().st_size != record["bytes"]:
        raise ValueError("wiod_tables_file_invalid")
    return folder


_CACHE: dict = {}


def wiot_aggregates(evidence_root: Path, classification: dict[str, str]) -> dict | None:
    """{(country, year): aggregates} from the verified bundle, or None when it is not archived.

    The zip is hash-checked once per bundle; results are cached in memory and in a
    derived file beside (never inside) the immutable bundle folder.
    """
    folder = _bundle(evidence_root)
    if folder is None:
        return None
    key = sha256(canonical_bytes({"bundle": folder.name, "classification": classification})).hexdigest()
    if key in _CACHE:
        return _CACHE[key]
    derived = folder.parent / f"{folder.name}.derived" / f"{key}.json"
    if derived.is_file():
        data = json.loads(derived.read_text())
    else:
        manifest = json.loads((folder / "manifest.json").read_text())
        if _file_hashes(folder / NAME)["sha256"] != manifest["files"][NAME]["sha256"]:
            raise ValueError("wiod_tables_hash_mismatch")
        data = {}
        with zipfile.ZipFile(folder / NAME) as archive:
            for year in YEARS:
                raw = archive.read(f"WIOT{year}_Nov16_ROW.xlsb")
                rows = CalamineWorkbook.from_filelike(io.BytesIO(raw)).get_sheet_by_name(str(year)).to_python()
                for country, values in table_aggregates(rows, classification).items():
                    data[f"{country}|{year}"] = values
        derived.parent.mkdir(parents=True, exist_ok=True)
        derived.write_text(json.dumps(data))
    result = {(k.split("|")[0], int(k.split("|")[1])): v for k, v in data.items()}
    _CACHE[key] = result
    return result


def acquire_wiod_tables(evidence_root: Path, *, local_zip: Path | None = None) -> Path:
    """Archive a local copy, or stream the publisher's file once through the managed client, then verify and store."""
    if local_zip is not None:
        return store_wiod_tables(Path(local_zip), evidence_root)
    from .source_policy import managed_client
    staging = Path(tempfile.mkdtemp(prefix=".wiod-download-"))
    try:
        with managed_client(timeout=600, follow_redirects=True,
                            headers={"User-Agent": "finance-dashboard-research/0.2 (private research)"}) as client:
            with client.stream("GET", PIN["url"]) as response, (staging / NAME).open("wb") as handle:
                if response.status_code != 200:
                    raise ProviderError("WIOD input-output tables request failed")
                for chunk in response.iter_bytes(1 << 20):
                    handle.write(chunk)
        return store_wiod_tables(staging / NAME, evidence_root)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Archive the WIOD 2016 world input-output tables for L04.")
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--zip", type=Path, help="an already downloaded WIOTS_in_EXCEL.zip (verified against the pin)")
    args = parser.parse_args(argv)
    bundle = acquire_wiod_tables(args.evidence_dir, local_zip=args.zip)
    print(json.dumps({"bundle": str(bundle)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
