"""Resource-bounded numeric inspection of OECD ICIO RData auxiliary archives.

OECD publishes A, B, VB, Z and other economic-account R workspaces alongside
the annual CSV originals. These are supplementary matrices, not alternative
ICIO country-years and not substitutes for the raw Z/Y Leontief calculation.

Parsing is performed in an isolated subprocess so a corrupt, unexpectedly
large or unsupported R workspace cannot terminate the running API process.
The original ZIP bytes stay in the existing canonical ICIO archive.
"""
from __future__ import annotations

from collections.abc import Mapping
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import numpy as np

MAX_MEMBER_BYTES = 4 * 1024**3
MAX_MEMBER_REPORTS = 12
MAX_NUMERIC_OBJECTS = 256
MAX_RECURSION_DEPTH = 6
MAX_SUBPROCESS_SECONDS = 300
MAX_AS_BYTES = 8 * 1024**3


def summarize_numeric_object(data, *, max_objects: int = MAX_NUMERIC_OBJECTS) -> dict:
    """Summarize actual numeric arrays while preserving their source identity.

    This is a real numeric extraction: shape, counts, ranges and sums are
    measured from values returned by the native RData parser. Matrix contents
    are not echoed into public diagnostics or assumed to have a TiVA meaning.
    """
    results = []
    visited = 0
    unsupported = 0
    def visit(name, item, depth):
        nonlocal visited, unsupported
        if visited >= max_objects or depth > MAX_RECURSION_DEPTH:
            unsupported += 1
            return
        if isinstance(item, Mapping):
            for key, child in list(item.items())[:MAX_NUMERIC_OBJECTS]:
                visit(str(name) + "/" + str(key)[:70], child, depth + 1)
            return
        if isinstance(item, (list, tuple)) and not isinstance(item, np.ndarray):
            if len(item) <= 50 and all(
                    isinstance(v, (Mapping, list, tuple, np.ndarray))
                    for v in item):
                for i, child in enumerate(item):
                    visit(name + "/" + str(i), child, depth + 1)
                return
        visited += 1
        try:
            obj = item.to_numpy(copy=False) if hasattr(item, "to_numpy") else item
            numeric = np.asarray(obj)
        except (ValueError, TypeError):
            unsupported += 1
            return
        if numeric.dtype.kind not in "iuf" or numeric.ndim not in (1, 2, 3):
            unsupported += 1
            return
        if numeric.size > 100_000_000:
            unsupported += 1
            return
        if not np.isfinite(numeric).all():
            results.append({"name": name[:150], "shape": list(numeric.shape),
                            "status": "nonfinite_numeric_values"})
            return
        # Reductions operate on the numeric array, not the object's repr.
        results.append({
            "name": name[:150], "shape": list(numeric.shape),
            "numeric_cells": int(numeric.size),
            "nonzero_cells": int(np.count_nonzero(numeric)),
            "negative_cells": int(np.count_nonzero(numeric < 0)),
            "minimum": float(np.min(numeric)) if numeric.size else None,
            "maximum": float(np.max(numeric)) if numeric.size else None,
            "sum": float(np.sum(numeric, dtype=np.float64)),
            "status": "numeric_values_extracted",
        })
    visit("rdata", data, 0)
    return {
        "numeric_objects": results,
        "objects_examined": visited,
        "non_numeric_or_unsupported_objects": unsupported,
        "data_values_validated": bool(results) and all(
            row["status"] == "numeric_values_extracted" for row in results),
        "used_in_published_tiva": False,
    }


def _read_rdata_file(path: Path) -> dict:
    import rdata
    suffix = path.suffix.lower()
    try:
        objects = rdata.read_rds(path) if suffix == ".rds" else rdata.read_rda(path)
    except Exception as exc:
        # Exact parser exceptions are not user-supplied output; avoid raw paths.
        raise ValueError("icio_rdata_decode_failed") from exc
    return summarize_numeric_object(objects)


def _worker():
    # Limit the R parser's address space, not the long-running app. This
    # prevents memory pressure from terminating the SQLite/API process.
    if os.name == "posix":
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (MAX_AS_BYTES, MAX_AS_BYTES))
    try:
        report = _read_rdata_file(Path(sys.argv[1]))
        print(json.dumps(report, separators=(",", ":"), allow_nan=False))
    except (ValueError, MemoryError, OSError):
        print(json.dumps({"status": "rdata_decode_or_resource_failure",
                          "data_values_validated": False}))


def inspect_auxiliary_zip(z: ZipFile, *, staging_parent: Path) -> dict:
    """Verify and read supported numeric R workspaces without executing R.

    ZIP member path names are never used as output paths; all temporary files
    are placed inside a private temporary directory on the input data volume.
    """
    members = [info for info in z.infolist() if not info.is_dir() and
               re.search(r"\.(?:rdata|rda|rds)$", info.filename, re.IGNORECASE)]
    if not members:
        return {"status": "no_rdata_members", "numeric_reports": [],
                "value_added_comparability_certified": False}
    if len(members) > MAX_MEMBER_REPORTS:
        return {"status": "too_many_auxiliary_members",
                "numeric_reports": [], "value_added_comparability_certified": False}
    reports = []
    with TemporaryDirectory(prefix=".icio-numeric-", dir=staging_parent) as folder:
        root = Path(folder)
        for pos, member in enumerate(members):
            if member.file_size > MAX_MEMBER_BYTES:
                reports.append({"member": member.filename, "status": "auxiliary_member_resource_limit",
                                "data_values_validated": False})
                continue
            suffix = Path(member.filename).suffix.lower()
            path = root / (f"source-{pos}{suffix}")
            with z.open(member) as original, path.open("wb") as destination:
                shutil.copyfileobj(original, destination, length=1024 * 1024)
            try:
                child = subprocess.run(
                    [sys.executable, "-m", "finance_dashboard.icio_auxiliary", str(path)],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    text=True, check=False, timeout=MAX_SUBPROCESS_SECONDS,
                    env={**os.environ, "OPENBLAS_NUM_THREADS": "1",
                         "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"},
                )
                if child.returncode != 0 or len(child.stdout) > 2_000_000:
                    raise ValueError("icio_rdata_worker_failed")
                parsed = json.loads(child.stdout)
                if not isinstance(parsed, dict):
                    raise ValueError("icio_rdata_report_invalid")
                reports.append({"member": member.filename,
                                "status": ("auxiliary_values_extracted"
                                           if parsed.get("data_values_validated")
                                           else "auxiliary_values_unresolved"),
                                **parsed})
            except (ValueError, OSError, subprocess.TimeoutExpired):
                reports.append({"member": member.filename,
                                "status": "auxiliary_numeric_parser_failed",
                                "data_values_validated": False})
            finally:
                path.unlink(missing_ok=True)
    good = sum(bool(r.get("data_values_validated")) for r in reports)
    return {"status": ("auxiliary_numeric_extracted" if good == len(reports)
                       else "auxiliary_numeric_partial" if good else
                       "auxiliary_numeric_unresolved"),
            "numeric_reports": reports, "parsed_members": good,
            "total_rdata_members": len(reports),
            "value_added_comparability_certified": False}


if __name__ == "__main__":
    _worker()
