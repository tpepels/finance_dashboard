"""Bounded, factual publisher-row excerpts for ingestion regression work.

Only previously archived original source files are read. Each selected row
retains its exact original value, column labels and cryptographic source
identity; samples are neither validated source histories nor ingestion inputs.
Failures are reported without leaking HTTP bodies or arbitrary filesystem data.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re

from .wid import WID_ROOT, WID_ALL_SERIES, WID_SERIES

MAX_WID_FILE = 250_000_000
MAX_RESPONSE = 15_000_000
MAX_OUTPUT_BYTES = 2_000_000


class SampleUnavailable(ValueError):
    """A fixed reason; no untrusted source text is emitted."""


def _archive_file(folder: Path, entry: dict, filename: str, limit: int) -> Path:
    if (folder.is_symlink() or not folder.is_dir()
            or entry.get("file") != filename
            or not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("sha256", "")))):
        raise SampleUnavailable("source_identity_unverified")
    path = folder / filename
    try:
        if (path.is_symlink() or not path.is_file()
                or path.stat().st_size != entry.get("bytes")
                or path.stat().st_size > limit):
            raise SampleUnavailable("source_file_unavailable")
        with path.open("rb") as handle:
            if sha256(handle.read()).hexdigest() != entry["sha256"]:
                raise SampleUnavailable("source_hash_mismatch")
    except OSError:
        raise SampleUnavailable("source_file_unavailable") from None
    return path


def _manifest(folder: Path) -> dict:
    path = folder / "manifest.json"
    try:
        if path.is_symlink() or path.stat().st_size > 2_000_000:
            raise SampleUnavailable("source_manifest_unavailable")
        obj = json.loads(path.read_bytes())
        if not isinstance(obj, dict):
            raise SampleUnavailable("source_manifest_unavailable")
        return obj
    except (OSError, ValueError, TypeError):
        raise SampleUnavailable("source_manifest_unavailable") from None


def _latest_archives(parent: Path) -> list[tuple[Path, dict]]:
    if not parent.is_dir() or parent.is_symlink():
        return []
    candidates = []
    for path in parent.iterdir():
        if not path.is_dir() or path.is_symlink() or not re.fullmatch(r"[a-f0-9]{64}", path.name):
            continue
        try:
            record = _manifest(path)
            time = datetime.fromisoformat(record["retrieved_at_utc"].replace("Z","+00:00"))
            if time.tzinfo is None:
                continue
            candidates.append((time,path,record))
        except (KeyError, ValueError, TypeError, SampleUnavailable):
            continue
    return [(folder,manifest) for _,folder,manifest in
            sorted(candidates,key=lambda entry:entry[0],reverse=True)]


def _sample_wid(root: Path, area: str, requested: list[str]) -> dict:
    """Compact raw WID rows, including original base-share validation rows."""
    expected = {WID_ALL_SERIES[sid][1:] for sid in requested}
    expected.update((variable,percentile) for registered_area,variable,percentile
                    in WID_SERIES.values() if registered_area == area)
    parent = root / "wid" / area
    for folder,manifest in _latest_archives(parent):
        if manifest.get("publisher") != "WID.world" or manifest.get("area") != area:
            continue
        try:
            sources = manifest["sources"]
            data_name, metadata_name = f"WID_data_{area}.csv", f"WID_metadata_{area}.csv"
            if (sources["data"].get("url") != f"{WID_ROOT}/{data_name}"
                    or sources["metadata"].get("url") != f"{WID_ROOT}/{metadata_name}"):
                raise SampleUnavailable("source_identity_unverified")
            data = _archive_file(folder,sources["data"],data_name,MAX_WID_FILE)
            metadata = _archive_file(folder,sources["metadata"],metadata_name,20_000_000)
            rows: dict[tuple[str,str],list[dict]] = defaultdict(list)
            with data.open("r",encoding="utf-8-sig",newline="") as handle:
                reader = csv.DictReader(handle,delimiter=";")
                fields = reader.fieldnames
                if not fields or not {"country","variable","percentile","year","value","age","pop"} <= set(fields):
                    raise SampleUnavailable("source_csv_schema_invalid")
                for row in reader:
                    key=(row.get("variable",""),row.get("percentile",""))
                    if row.get("country") != area or key not in expected:
                        continue
                    bucket=rows[key]
                    # Preserve earliest and newest rows, not inferred or
                    # normalized values. WID data is not guaranteed sorted.
                    bucket.append(row)
                    bucket.sort(key=lambda entry:entry.get("year",""))
                    if len(bucket)>4:
                        bucket[:]=[bucket[0],*bucket[-3:]]
            meta_fields,meta_rows=[],[]
            with metadata.open("r",encoding="utf-8-sig",newline="") as handle:
                reader=csv.DictReader(handle,delimiter=";")
                meta_fields=reader.fieldnames
                if not meta_fields or not {"country","variable","age","pop","unit","source"} <= set(meta_fields):
                    raise SampleUnavailable("source_csv_schema_invalid")
                selected_vars={key[0] for key in expected}
                for row in reader:
                    if row.get("country")==area and row.get("variable") in selected_vars:
                        meta_rows.append(row)
            data_rows=[row for key in sorted(rows) for row in rows[key]]
            if not data_rows:
                raise SampleUnavailable("source_has_no_requested_rows")
            result={
                "kind":"wid_original_pair","area":area,
                "requested_series":sorted(requested),
                "source_sha256":{"data":sources["data"]["sha256"],
                                 "metadata":sources["metadata"]["sha256"]},
                "source_urls":{"data":sources["data"]["url"],
                               "metadata":sources["metadata"]["url"]},
                "data_header":fields,"metadata_header":meta_fields,
                "data_rows":data_rows,"metadata_rows":meta_rows,
                "selected_keys":[{"variable":v,"percentile":p,"rows":len(rows.get((v,p),[]))}
                                 for v,p in sorted(expected)],
                "sample_policy":"first and last 3 original rows of each registered variable/percentile",
            }
            if len(json.dumps(result,ensure_ascii=False).encode("utf-8"))>MAX_OUTPUT_BYTES:
                raise SampleUnavailable("sample_size_limit")
            return result
        except (KeyError, TypeError, UnicodeError, csv.Error, OSError, SampleUnavailable):
            continue
    raise SampleUnavailable("verified_wid_original_pair_unavailable")


def _sample_pink_sheet(root: Path, sid: str) -> dict:
    """Sample rejected or accepted publisher XLSX for the *exact* copper series."""
    from python_calamine import CalamineWorkbook
    for directory in ("rejected-responses","responses"):
        for folder,manifest in _latest_archives(root / directory / sid):
            try:
                if (manifest.get("provider")!="WORLD_BANK_PINK_SHEET"
                        or manifest.get("series_id")!=sid
                        or len(manifest.get("sources",[]))!=1):
                    continue
                source=manifest["sources"][0]
                from .provider_parsers import PINK_SHEET_URL
                if source.get("url")!=PINK_SHEET_URL:
                    continue
                path=_archive_file(folder,source,"response-0.bin",MAX_RESPONSE)
                with path.open("rb") as handle:
                    raw=handle.read()
                if not raw.startswith(b"PK\x03\x04"):
                    continue
                book=CalamineWorkbook.from_filelike(io.BytesIO(raw))
                if "Monthly Prices" not in book.sheet_names:
                    continue
                rows=book.get_sheet_by_name("Monthly Prices").to_python()
                headers=[(i,j) for i,row in enumerate(rows[:15])
                         for j,x in enumerate(row) if str(x).strip()=="Copper"]
                if len(headers)!=1:
                    continue
                i,j=headers[0]
                if j>=len(rows[i+1]) or str(rows[i+1][j]).strip()!="($/mt)":
                    continue
                prices=[row for row in rows[i+2:]
                        if row and re.fullmatch(r"\d{4}M(0[1-9]|1[0-2])",str(row[0]).strip())
                        and len(row)>j]
                excerpt=[rows[i],rows[i+1],*prices[-3:]]
                return {"kind":"world_bank_pink_sheet","series_id":sid,
                        "source_sha256":source["sha256"],"source_url":source["url"],
                        "sheet":"Monthly Prices","rows":excerpt,
                        "original_periods":[str(x[0]) for x in prices[-3:]],
                        "sample_policy":"native header, unit row, and last 3 published months"}
            except (KeyError, TypeError, OSError, ValueError, SampleUnavailable):
                continue
    raise SampleUnavailable("verified_pink_sheet_original_unavailable")


def collect_failure_samples(evidence_root: Path, coverage_items: list[dict]) -> dict:
    """Bounded, safe excerpts from actual archived failed/pending source families.

    Missing bytes generate explicit unavailable entries. No fallback values,
    synthetic fixtures, credentials, or HTTP rejection bodies are published.
    """
    root=Path(evidence_root)
    wanted={row["id"] for row in coverage_items
            if row.get("id") in WID_ALL_SERIES
            and row.get("state") not in ("available","source_checked_no_newer_data")}
    groups=defaultdict(list)
    for sid in sorted(wanted):
        groups[WID_ALL_SERIES[sid][0]].append(sid)
    samples, unavailable=[],[]
    for area,series in sorted(groups.items()):
        try:
            samples.append(_sample_wid(root,area,series))
        except SampleUnavailable as exc:
            unavailable.append({"area":area,"source":"WID.world",
                                "affected_series":len(series),"reason":str(exc)})
    copper="prices.commodity.copper_usd"
    if any(row.get("id")==copper and row.get("state")!="available"
           for row in coverage_items):
        try:
            samples.append(_sample_pink_sheet(root,copper))
        except SampleUnavailable as exc:
            unavailable.append({"series_id":copper,
                                "source":"World Bank Pink Sheet","reason":str(exc)})
    result={"schema_version":1,"samples":samples,"unavailable":unavailable,
            "provenance":"Read-only excerpts from archived publisher source bytes, each SHA-256 checked",
            "warning":"Samples preserve literal rows but are not complete or independently accepted originals."}
    if len(json.dumps(result,default=str,ensure_ascii=False).encode("utf-8"))>8_000_000:
        return {"schema_version":1,"samples":[],"unavailable":[
            {"source":"source sampling","reason":"diagnostic_sample_total_size_limit"}],
            "warning":"Samples exceeded the bounded diagnostic export size."}
    return result
