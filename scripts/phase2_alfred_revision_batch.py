#!/usr/bin/env python3
"""Bounded, resumable original ALFRED observation/revision acquisition.

Read-only plan by default. With --acquire, the canonical managed publisher
transport enforces all registered per-source restrictions and a global HTTP
request budget. A complete original window is atomically archived; partially
downloaded pages never become a scientific original. Repeat the same command
for the next unacquired window. Historical source versions remain immutable.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, timedelta
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from finance_dashboard.phase2_alfred_revisions import (
    capture_revision_window, read_revision_window, revision_inventory,
)
from finance_dashboard.source_policy import (
    managed_client, publisher_interruption,
)
from finance_dashboard.source_policy_registry import PolicyRegistry
from finance_dashboard.source_policy_ledger import SourcePolicyGate
from finance_dashboard.service import safe_source_failure_code
from finance_dashboard.vintage import SOURCES, _key_format_ok


def _next_month(day: date) -> date:
    return date(day.year + (day.month == 12),
                day.month % 12 + 1, 1)


def planned_revision_windows(series_ids: list[str], start: date,
                             end: date, asof: date) -> list[dict]:
    """Explicit non-overlapping calendar windows; no synthetic dates."""
    if (not series_ids or len(series_ids) != len(set(series_ids))
            or set(series_ids) - set(SOURCES)
            or start > end or end > asof or asof > date.today()
            or start.year < 1900):
        raise ValueError("invalid_original_revision_backfill_plan")
    work = []
    for sid in series_ids:
        daily = SOURCES[sid]["frequency"] == "D"
        cursor = start
        while cursor <= end:
            next_boundary = (_next_month(cursor) if daily
                             else date(cursor.year + 1, 1, 1))
            last = min(end, next_boundary - timedelta(days=1))
            work.append({
                "series_id": sid, "start": cursor,
                "end": last, "asof": asof,
            })
            cursor = next_boundary
    return work


def revision_batch(root: Path, *, series_ids: list[str], start: date,
                   end: date, asof: date, acquire: bool,
                   api_key: str | None, client=None,
                   max_requests: int = 30, max_windows: int = 20,
                   max_pages: int = 5, refresh: bool = False) -> dict:
    if not 1 <= max_requests <= 300 or not 1 <= max_windows <= 100:
        raise ValueError("invalid_revision_acquisition_limits")
    if not 1 <= max_pages <= 20:
        raise ValueError("invalid_revision_page_limit")
    if acquire and (client is None or not _key_format_ok(api_key or "")):
        raise ValueError("original_alfred_acquisition_requires_managed_client_and_key")
    work = planned_revision_windows(series_ids, start, end, asof)
    pending, cached = [], 0
    for item in work:
        current = read_revision_window(
            root, item["series_id"], item["start"],
            item["end"], item["asof"])
        if current["status"] == "verified_original_revision_window" and not refresh:
            cached += 1
        elif current["status"] in {
                "missing_original_revision_window", "verified_original_revision_window"}:
            pending.append(item)
        else:
            raise ValueError("existing_original_revision_window_invalid")
    state = "read_only"
    results = []
    stopped = None
    if acquire:
        policy = SourcePolicyGate(registry=PolicyRegistry()).availability("fred-v1")
        if policy["state"] != "ready":
            return {
                "operation": "original_alfred_revisions_batch",
                "state": "publisher_policy_" + policy["state"],
                "publisher_requests": 0,
                "publisher_policy_reason": policy["reason"],
                "publisher_retry_at": policy["retry_at"],
                "original_windows_written": 0,
                "scientific_analysis_certified": False,
            }
        state = "bounded"
        for item in pending[:max_windows]:
            try:
                result = capture_revision_window(
                    item["series_id"], start=item["start"], end=item["end"],
                    asof=item["asof"], root=root,
                    api_key=api_key or "", client=client,
                    max_pages=max_pages, refresh=refresh)
                results.append({
                    "series_id": item["series_id"],
                    "start": item["start"].isoformat(),
                    "end": item["end"].isoformat(),
                    "state": result["status"],
                    "revision_rows": result["rows_in_all_verified_pages"],
                    "source_sha256": result["source_sha256"],
                })
            except Exception as exc:
                interruption = publisher_interruption(
                    exc, exc.response.status_code
                    if hasattr(exc, "response") and exc.response is not None
                    else None)
                stopped = (interruption["category"]
                           if interruption else safe_source_failure_code(exc))
                results.append({
                    "series_id": item["series_id"],
                    "start": item["start"].isoformat(),
                    "end": item["end"].isoformat(),
                    "state": "failed",
                    "reason": stopped,
                })
                state = "stopped"
                break
    consumed = getattr(getattr(client, "_transport", None),
                       "requests_reserved", 0) if acquire else 0
    successful = sum(x["state"] == "verified_original_revision_window"
                     for x in results)
    return {
        "phase": "phase2",
        "operation": "original_alfred_revisions_batch",
        "state": state,
        "source_series": series_ids,
        "planned_windows": len(work),
        "already_verified_before_batch": cached,
        "pending_before_batch": len(pending),
        "newly_verified_windows": successful,
        "pending_after_batch": max(0, len(pending) - successful),
        "next_unacquired_window": (
            {key: value.isoformat() if isinstance(value, date) else value
             for key, value in pending[successful].items()}
            if successful < len(pending) else None),
        "publisher_requests": consumed,
        "global_request_budget": max_requests,
        "publisher_policy_stop": stopped,
        "results": results,
        "original_source_archive_rewritten": False,
        "observation_first_publication_independently_certified": False,
        "no_cross_release_values_merged": True,
        "scientific_analysis_certified": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vintage-dir", type=Path,
                        default=Path(os.environ.get(
                            "FINANCE_VINTAGE_DIR", "/data/vintages")))
    parser.add_argument("--series", action="append", choices=sorted(SOURCES))
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--asof", type=date.fromisoformat, default=date.today())
    parser.add_argument("--acquire", action="store_true")
    parser.add_argument("--refresh-existing", action="store_true")
    parser.add_argument("--max-requests", type=int, default=30)
    parser.add_argument("--max-windows", type=int, default=20)
    parser.add_argument("--max-pages", type=int, default=5)
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args(argv)
    ids = args.series or sorted(SOURCES)
    if args.refresh_existing and not args.acquire:
        parser.error("--refresh-existing requires --acquire")
    if (not 1 <= args.max_requests <= 300
            or not 1 <= args.max_windows <= 100
            or not 1 <= args.max_pages <= 20):
        parser.error("Acquisition budget must be bounded")
    try:
        if args.acquire:
            with managed_client(
                    timeout=50, follow_redirects=False,
                    request_budget=args.max_requests) as client:
                report = revision_batch(
                    args.vintage_dir, series_ids=ids,
                    start=args.start, end=args.end, asof=args.asof,
                    acquire=True, client=client,
                    api_key=os.environ.get("FRED_API_KEY", ""),
                    max_requests=args.max_requests,
                    max_windows=args.max_windows,
                    max_pages=args.max_pages,
                    refresh=args.refresh_existing)
        else:
            report = revision_batch(
                args.vintage_dir, series_ids=ids,
                start=args.start, end=args.end, asof=args.asof,
                acquire=False, api_key=None)
        if args.details:
            report["verified_revision_inventory"] = revision_inventory(
                args.vintage_dir, set(ids))
        if not args.details:
            report["results"] = report.get("results", [])[:12]
        print(json.dumps(report, separators=(",", ":"), allow_nan=False))
        return 0 if report["state"] in {"read_only", "bounded"} else 1
    except Exception as exc:
        print(json.dumps({
            "phase": "phase2",
            "operation": "original_alfred_revisions_batch",
            "state": "failed_before_completion",
            "reason": safe_source_failure_code(exc),
            "scientific_analysis_certified": False,
        }, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
