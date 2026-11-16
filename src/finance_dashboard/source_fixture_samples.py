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
        digest = sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != entry["sha256"]:
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
            row_counts: dict[tuple[str,str],int] = defaultdict(int)
            with data.open("r",encoding="utf-8-sig",newline="") as handle:
                reader = csv.DictReader(handle,delimiter=";")
                fields = reader.fieldnames
                if not fields or not {"country","variable","percentile","year","value","age","pop"} <= set(fields):
                    raise SampleUnavailable("source_csv_schema_invalid")
                for row in reader:
                    key=(row.get("variable",""),row.get("percentile",""))
                    if row.get("country") != area or key not in expected:
                        continue
                    row_counts[key] += 1
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
                original_fields=reader.fieldnames
                if not original_fields or not {"country","variable","age","pop","unit","source"} <= set(original_fields):
                    raise SampleUnavailable("source_csv_schema_invalid")
                # Preserve literal values of the identity, method and unit
                # cells used by ingestion. Unrelated multi-paragraph
                # descriptions would make diagnostic fixtures unnecessarily
                # large without changing parser expectations.
                required_meta=("country","variable","age","pop","shortname",
                               "shorttype","shortpop","shortage","unit","source","method")
                meta_fields=[field for field in required_meta if field in original_fields]
                selected_vars={key[0] for key in expected}
                for row in reader:
                    if row.get("country")==area and row.get("variable") in selected_vars:
                        meta_rows.append({field:row.get(field,"") for field in meta_fields})
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
                "selected_keys":[{"variable":v,"percentile":p,
                                  "rows":row_counts.get((v,p),0),
                                  "sampled_rows":len(rows.get((v,p),[]))}
                                 for v,p in sorted(expected)],
                "sample_policy":"first and last 3 original data rows plus exact metadata identity/method columns",
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
    for directory in ("responses","rejected-responses"):
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
            except (KeyError, TypeError, OSError, ValueError, RuntimeError, SampleUnavailable):
                continue
    raise SampleUnavailable("verified_pink_sheet_original_unavailable")


def _sample_bls_oews(root: Path, sid: str) -> dict:
    """Reproduce one national total from the exact archived BLS ZIP release.

    The archive may also contain an index HTML original; it is never treated
    as a wage response. Denied/HTML publisher responses are excluded.
    """
    from zipfile import ZipFile, BadZipFile
    from python_calamine import CalamineWorkbook
    from .bls_oews import INDEX_URL, parse_national_rows
    source_pattern=re.compile(
        r"https://www\.bls\.gov/oes/special-requests/oesm(\d{2})nat\.zip")
    for directory in ("responses","rejected-responses"):
        for folder,manifest in _latest_archives(root / directory / sid):
            if manifest.get("series_id")!=sid or manifest.get("provider")!="BLS_OEWS":
                continue
            samples=[]
            try:
                for record in manifest.get("sources",[]):
                    match=source_pattern.fullmatch(str(record.get("url","")))
                    if not match:
                        continue
                    year=2000+int(match.group(1))
                    filename=record.get("file")
                    if not re.fullmatch(r"response-\d+\.bin",str(filename)):
                        continue
                    path=_archive_file(folder,record,filename,8_000_000)
                    raw=path.read_bytes()
                    if not raw.startswith(b"PK\x03\x04"):
                        continue
                    with ZipFile(io.BytesIO(raw)) as archive:
                        members=[x for x in archive.infolist() if not x.is_dir()]
                        expected=f"national_M{year}_dl.xlsx"
                        if len(members)!=1 or members[0].filename not in {
                                expected,f"oesm{year % 100:02d}nat/{expected}"}:
                            continue
                        if members[0].file_size>12_000_000:
                            continue
                        book_raw=archive.read(members[0])
                    if not book_raw.startswith(b"PK\x03\x04"):
                        continue
                    book=CalamineWorkbook.from_filelike(io.BytesIO(book_raw))
                    for index in range(len(book.sheet_names)):
                        rows=book.get_sheet_by_index(index).to_python()
                        headers=[(i,[str(c).strip().upper().replace(" ","_")
                                     for c in row]) for i,row in enumerate(rows[:25])
                                 if {"OCC_CODE","OCC_TITLE","TOT_EMP","H_MEAN","H_MEDIAN"}
                                    <= {str(c).strip().upper().replace(" ","_") for c in row}]
                        if len(headers)!=1:
                            continue
                        offset,names=headers[0]
                        pos=names.index("OCC_CODE")
                        totals=[r for r in rows[offset+1:]
                                if len(r)>pos and str(r[pos]).strip()=="00-0000"]
                        if len(totals)!=1:
                            continue
                        verify=parse_national_rows([rows[offset],*totals],year)
                        samples.append({"reference_year":year,"workbook":expected,
                            "original_sha256":record["sha256"],"source_url":record["url"],
                            "header":rows[offset],"national_total_row":totals[0],
                            "expected_values":{key:str(value) for key,value in verify.items()}})
                        break
            except (BadZipFile,ValueError,TypeError,KeyError,OSError,RuntimeError,SampleUnavailable):
                continue
            if samples:
                return {"kind":"bls_oews_national","series_id":sid,
                        "samples":sorted(samples,key=lambda row:row["reference_year"])[-2:],
                        "sample_policy":"exact source national total and column header for last 2 available years"}
    raise SampleUnavailable("verified_bls_national_archive_unavailable")



def collect_sec_archive_inspection(evidence_root: Path, coverage_items: list[dict]) -> dict:
    """Inspect a bounded sample of retained SEC monthly originals, never their bodies.

    The archive catalogue is SHA-deduplicated across the four measures. Parser
    replay uses an authenticated-by-hash publisher ZIP and its *publisher index*
    month label, never the filename's filing window. Failed captures remain
    explicitly noncertifying, even if offline parsing happens to succeed.
    """
    from zipfile import BadZipFile, ZipFile
    from .extra_publisher_sources import (
        SEC_NMFP_INDEX, SEC_NMFP_ROOT, nmfp_archives, parse_nmfp_month,
    )
    from .service import safe_source_failure_code
    from .source_documents import MAX_DOCUMENT_BYTES

    affected = sorted(
        (row for row in coverage_items
         if row.get("provider") == "SEC_NMFP"
         and row.get("state") not in ("available", "source_checked_no_newer_data")),
        key=lambda row: row["id"],
    )
    result = {
        "schema_version": 1,
        "source_ids": [{
            "id": row["id"], "state": row.get("state"),
            "last_failure_code": row.get("last_failure_code"),
        } for row in affected],
        "archives_found": 0, "archives_inspected": [], "uninspected_archives": 0,
        "unavailable": [], "source": "SEC N-MFP3",
        "constraints": {
            "max_archive_catalogue": 48, "max_archives_inspected": 10,
            "max_replayed_archives": 5,
            "original_bytes_included": False,
            "publisher_index_required_for_month": True,
        },
    }
    if not affected:
        return result

    root = Path(evidence_root)
    archives: dict[str, dict] = {}
    absent = set()
    for row in affected:
        sid = row["id"]
        snapshots = []
        for kind in ("rejected-responses", "responses"):
            snapshots.extend(
                (folder, manifest, kind)
                for folder, manifest in _latest_archives(root / kind / sid)[:2])
        snapshots.sort(key=lambda item: item[1].get("retrieved_at_utc", ""), reverse=True)
        found = False
        for folder, manifest, kind in snapshots[:3]:
            if (manifest.get("series_id") != sid
                    or manifest.get("provider") != "SEC_NMFP"
                    or not isinstance(manifest.get("sources"), list)):
                continue
            sources = manifest["sources"]
            periods = {}
            if sources and sources[0].get("url") == SEC_NMFP_INDEX:
                try:
                    index = _archive_file(
                        folder, sources[0], "response-0.bin", 2_000_000)
                    periods = {
                        url: month.isoformat()
                        for month, url in nmfp_archives(index.read_text("utf-8-sig"))
                    }
                except (SampleUnavailable, ValueError, UnicodeError, OSError):
                    pass
            for item in sources[1:]:
                url = item.get("url")
                name = item.get("file")
                if (not isinstance(url, str)
                        or not re.fullmatch(
                            re.escape(SEC_NMFP_ROOT) + r"\d{8}-\d{8}_nmfp\.zip",
                            url, re.I)
                        or not re.fullmatch(r"response-\d+\.bin", str(name))
                        or item.get("http_status", 200) != 200
                        or not re.fullmatch(
                            r"[0-9a-f]{64}", str(item.get("sha256", "")))):
                    continue
                found = True
                digest = item["sha256"]
                if digest not in archives and len(archives) >= 48:
                    result["uninspected_archives"] += 1
                    continue
                if digest not in archives:
                    archives[digest] = {
                        "source_sha256": digest,
                        "bytes": item.get("bytes"), "publisher_month": periods.get(url),
                        "publisher_index_month_verified": url in periods,
                        "archive_filename": url.rsplit("/", 1)[-1],
                        "capture_state": kind,
                        "referenced_by": [sid],
                        "_folder": folder, "_record": item, "_filename": name,
                    }
                else:
                    archive = archives[digest]
                    if sid not in archive["referenced_by"]:
                        archive["referenced_by"].append(sid)
                    if archive["publisher_month"] is None and url in periods:
                        archive["publisher_month"] = periods[url]
                        archive["publisher_index_month_verified"] = True
        if not found:
            absent.add(sid)
    result["unavailable"] = [
        {"series_id": sid, "reason": "no_hash_identified_archived_sec_zip"}
        for sid in sorted(absent)]
    result["archives_found"] = len(archives)

    required = {
        "SUBMISSION": ("ACCESSION_NUMBER", "SUBMISSIONTYPE", "REPORTDATE",
                       "FILING_DATE", "SERIESID"),
        "SERIESLEVELINFO": ("ACCESSION_NUMBER", "FEEDERFUNDFLAG",
                            "NETASSETOFSERIES", "AVERAGEPORTFOLIOMATURITY",
                            "AVERAGELIFEMATURITY"),
        "LIQUIDASSETSDETAILS": ("ACCESSION_NUMBER",
                                "TOTLIQUIDASSETSNEARPCTDATE",
                                "PCTWEEKLYLIQUIDASSETS"),
    }
    # Inspect first, middle and latest files across the publisher's labelled
    # months; the full catalogue remains hashed and visible as metadata.
    ordered = sorted(archives.values(), key=lambda a: (
        a["publisher_month"] or "", a["source_sha256"]))
    sample_indices = set(range(min(3, len(ordered))))
    sample_indices.update(range(max(0, len(ordered)-3), len(ordered)))
    if ordered:
        sample_indices.add(len(ordered)//2)
    sample_indices.update(
        round(i*(len(ordered)-1)/9) for i in range(10) if ordered)
    # Retain latest and earliest even when the set has more than ten points.
    prioritized = sorted(sample_indices, key=lambda i: (
        0 if i in (0, len(ordered)-1) else
        1 if i in (1, len(ordered)-2, len(ordered)//2) else 2,
        i))
    chosen = set(prioritized[:10])
    result["archive_catalogue"] = [{
        k: a[k] for k in ("source_sha256", "bytes", "publisher_month",
                         "publisher_index_month_verified", "archive_filename",
                         "capture_state", "referenced_by")
    } for a in ordered]
    replayed = 0
    for index, item in enumerate(ordered):
        if index not in chosen:
            result["uninspected_archives"] += 1
            continue
        entry = {
            k: item[k] for k in ("source_sha256", "bytes", "publisher_month",
                               "publisher_index_month_verified", "archive_filename",
                               "capture_state", "referenced_by")
        }
        entry["tables"] = {}
        try:
            path = _archive_file(item["_folder"], item["_record"],
                                 item["_filename"], MAX_DOCUMENT_BYTES)
            from .extra_publisher_sources import _tsv
            with ZipFile(path) as zf:
                members = zf.infolist()
                entry["zip_member_count"] = len(members)
                entry["zip_members"] = [
                    (name if re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", name)
                     else "unsafe_or_nested_member")
                    for name in (member.filename.rsplit("/", 1)[-1]
                                 for member in members[:64])]
                entry["zip_members_omitted"] = max(0, len(members)-64)
                for table, columns in required.items():
                    names = {f"NMFP_{table}.TSV", f"{table}.TSV"}
                    matches = [m for m in members if not m.is_dir()
                               and m.filename.rsplit("/", 1)[-1].upper() in names]
                    info = {"matches": len(matches), "required_columns": list(columns)}
                    if len(matches) == 1:
                        member = matches[0]
                        info.update(uncompressed_bytes=member.file_size,
                                    compressed_bytes=member.compress_size)
                        if (0 < member.file_size <= 35_000_000 and
                                member.compress_size > 0 and
                                member.file_size <= member.compress_size*500):
                            with zf.open(member) as fh:
                                header = fh.readline(8193)
                            if len(header) <= 8192:
                                try:
                                    fields = header.decode("utf-8-sig").rstrip("\r\n").split("\t")
                                    safe_fields = [f if re.fullmatch(
                                        r"[A-Za-z0-9_]{1,100}", f)
                                        else "invalid_column_name" for f in fields[:80]]
                                    info["column_headers"] = safe_fields
                                    info["missing_columns"] = sorted(set(columns)-set(fields))
                                    info["extra_columns_count"] = max(0, len(fields)-len(columns))
                                    info["headers_truncated"] = len(fields)>80
                                except UnicodeError:
                                    info["header_error"] = "non_utf8_header"
                            else:
                                info["header_error"] = "header_size_limit"
                        else:
                            info["header_error"] = "member_size_or_ratio_limit"
                    entry["tables"][table] = info
            if item["publisher_month"] and replayed < 5 and path.stat().st_size <= 20_000_000:
                from datetime import date
                replayed += 1
                try:
                    metrics = parse_nmfp_month(
                        path.read_bytes(), date.fromisoformat(item["publisher_month"]))
                    entry["parser_outcome"] = "accepted_shape_not_certified"
                    entry["parsed_metric_keys"] = sorted(metrics)
                except Exception as exc:
                    entry["parser_outcome"] = "rejected"
                    entry["parser_failure_code"] = safe_source_failure_code(exc)
            else:
                entry["parser_outcome"] = (
                    "publisher_month_unverified" if not item["publisher_month"]
                    else "replay_limit")
        except (SampleUnavailable, BadZipFile, OSError, RuntimeError,
                ValueError, KeyError, TypeError):
            entry["archive_inspection_error"] = "hash_or_zip_unavailable"
        result["archives_inspected"].append(entry)
    return result

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
        except Exception:
            unavailable.append({"area":area,"source":"WID.world",
                                "affected_series":len(series),"reason":"source_sampling_failed"})
    bls_ids=sorted(row["id"] for row in coverage_items
                   if row.get("provider")=="BLS_OEWS"
                   and row.get("state") not in ("available","source_checked_no_newer_data")
                   and row.get("id","").startswith("labour.us.oews_all_"))
    if bls_ids:
        # Both measures share the same publisher release but may have
        # independently captured evidence records.
        for sid in bls_ids:
            try:
                samples.append(_sample_bls_oews(root,sid))
            except SampleUnavailable as exc:
                unavailable.append({"series_id":sid,"source":"BLS OEWS","reason":str(exc)})
            except Exception:
                unavailable.append({"series_id":sid,"source":"BLS OEWS","reason":"source_sampling_failed"})
    copper="prices.commodity.copper_usd"
    # Research gates can reject a perfectly stored series. Sample this one
    # named source even when source-health says available; no extra download.
    if any(row.get("id")==copper for row in coverage_items):
        try:
            samples.append(_sample_pink_sheet(root,copper))
        except SampleUnavailable as exc:
            unavailable.append({"series_id":copper,
                                "source":"World Bank Pink Sheet","reason":str(exc)})
        except Exception:
            unavailable.append({"series_id":copper,
                                "source":"World Bank Pink Sheet","reason":"source_sampling_failed"})
    result={"schema_version":1,"samples":samples,"unavailable":unavailable,
            "provenance":"Read-only excerpts from archived publisher source bytes, each SHA-256 checked",
            "warning":"Samples preserve literal rows but are not complete or independently accepted originals."}
    if len(json.dumps(result,default=str,ensure_ascii=False).encode("utf-8"))>8_000_000:
        return {"schema_version":1,"samples":[],"unavailable":[
            {"source":"source sampling","reason":"diagnostic_sample_total_size_limit"}],
            "warning":"Samples exceeded the bounded diagnostic export size."}
    return result
