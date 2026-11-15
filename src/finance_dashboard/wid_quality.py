"""Read-only original WID data-quality codes from checked acquisition receipts.

WID's native `data_quality` field is an opaque publisher code. It is not
converted into a numeric accuracy score, a research acceptance guarantee, or
an invented grade. The underlying original data/metadata pair was separately
checked during ingestion/reconciliation; this lightweight endpoint verifies
the manifest receipt, not the complete 250MB publisher bytes.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re

from .source_reconciliation import _selected_manifest, EvidenceError
from .wid import WID_ALL_SERIES

AREAS = ("US", "FR", "PT", "CN", "IN", "WO")


def original_wid_quality(root: Path) -> dict:
    by_area = {}
    for area in AREAS:
        try:
            time,manifest_hash,_,manifest,selection = _selected_manifest(
                Path(root)/"wid"/area, {"publisher":"WID.world","area":area})
            if (manifest.get("schema_version")!=1 or
                    manifest.get("publisher")!="WID.world" or
                    manifest.get("area")!=area):
                raise EvidenceError("source_identity_mismatch")
            files = manifest.get("sources") or {}
            if any(not isinstance(files.get(kind),dict) or
                   not re.fullmatch(r"[0-9a-f]{64}",
                                    str(files[kind].get("sha256","")))
                   for kind in ("data","metadata")):
                raise EvidenceError("source_identity_mismatch")
            original_quality=manifest.get("observation_quality")
            if not isinstance(original_quality,dict):
                original_quality={}
            selected={}
            for sid, (selected_area,variable,percentile) in sorted(WID_ALL_SERIES.items()):
                if selected_area!=area:
                    continue
                entries=original_quality.get(variable+"/"+percentile)
                if not isinstance(entries,dict):
                    selected[sid]={"state":"not_reported",
                                   "quality_code":None,"latest_original_period":None}
                    continue
                candidates=[]
                for period,value in entries.items():
                    if not re.fullmatch(r"\d{4}-01-01",str(period)):
                        continue
                    if value is not None and (not isinstance(value,str) or len(value)>24):
                        continue
                    candidates.append((period,value))
                if not candidates:
                    selected[sid]={"state":"not_reported",
                                   "quality_code":None,"latest_original_period":None}
                else:
                    period,code=max(candidates)
                    selected[sid]={"state":"reported" if code else "not_reported",
                                   "quality_code":code or None,
                                   "latest_original_period":period}
            by_area[area]={
                "state":"archived_metadata",
                "retrieved_at":time.isoformat(),
                "manifest_sha256":manifest_hash,
                "source_sha256":files["data"]["sha256"],
                "source_metadata_sha256":files["metadata"]["sha256"],
                "selection_method":selection,
                "series":selected,
            }
        except (EvidenceError, OSError, ValueError, KeyError, TypeError):
            by_area[area]={"state":"no_verified_quality_metadata","series":{}}
    return {
        "schema_version":1,
        "quality_interpretation":"Native WID source quality codes, shown unchanged without inferring their meaning.",
        "validation_scope":("Manifest integrity and acquisition receipt verified. "
                            "Original full data bytes are not rehashed by this status endpoint. "
                            "Research scientific acceptance is independent."),
        "areas":by_area,
    }
