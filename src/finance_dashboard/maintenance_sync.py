"""Canonical current and historical synchronization stages.

One manager controls progress, cancellation and event reporting. Publisher
access is always handled by centrally managed transport clients.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import os
import httpx
from .developer_logs import record_event
from .source_policy import managed_client
from .maintenance_jobs import MaintenanceBlocked, VINTAGE_IDS


def run_sync(self, job_id: str, *, history: bool, options: dict, cancelled) -> dict:
    """Single-click sync using the same validated source collectors.

    Both modes are additive/revision-aware. Individual provider failure
    leaves other collection stages running, unless the user cancels.
    """
    from .worker import refresh_all, refresh_market_all

    stages = 5 if history else 4
    stage_results = {}
    issue_count = 0

    def stage(index: int, label: str) -> None:
        self._change(job_id, completed=index, total=stages,
                     current_item=label, stage=label,
                     stage_completed=0, stage_total=None)

    def progress(index: int, label: str):
        def update(done: int, total: int, sid: str) -> None:
            self._change(job_id, completed=index, total=stages,
                         current_item=sid, stage=label,
                         stage_completed=done, stage_total=total)
        return update

    def record(key: str, value: dict) -> None:
        nonlocal issue_count
        stage_results[key] = value
        if value.get("status") in ("partial", "blocked", "failed"):
            issue_count += 1
        self._change(job_id, result={"parts":dict(stage_results)})
        severity = ("info" if value.get("status") in ("complete", "skipped")
                    else "warning")
        record_event("sync", "stage_finished", level=severity,
                     action="sync_history" if history else "sync_current",
                     job_id=job_id, stage=key, status=value.get("status"),
                     reason=value.get("reason"), failed=value.get("failed"),
                     http_status=value.get("http_status"))
        for fund in value.get("funds", []):
            if fund.get("status") != "complete":
                record_event("sec", "stage_finished", level="warning",
                             action="sync_history", job_id=job_id,
                             source_id=fund.get("id"), status=fund.get("status"),
                             reason=fund.get("reason"),
                             http_status=fund.get("http_status"),
                             failed=fund.get("errors"))

    if cancelled.is_set():
        raise MaintenanceBlocked("cancelled")
    macro_ids = set(options["series_ids"])
    stage(0, "Economic indicators")
    try:
        failed = refresh_all(
            self.engine, full=history, series_ids=macro_ids,
            progress=progress(0, "Economic indicators"), stopped=cancelled)
        record("macro", {"status":"partial" if failed else "complete",
                         "sources":len(macro_ids),"failed":failed})
    except Exception:
        record("macro", {"status":"failed","reason":"provider_failed"})
    if cancelled.is_set():
        raise MaintenanceBlocked("cancelled")

    market_ids = set(options["instrument_ids"])
    fx_ids = set(options["currencies"])
    stage(1, "Markets and exchange rates")
    try:
        failed = refresh_market_all(
            self.engine, instrument_ids=market_ids, currencies=fx_ids,
            full=history, progress=progress(1, "Markets and exchange rates"),
            stopped=cancelled)
        record("markets", {"status":"partial" if failed else "complete",
                           "sources":len(market_ids)+len(fx_ids),"failed":failed})
    except Exception:
        record("markets", {"status":"failed","reason":"provider_failed"})
    if cancelled.is_set():
        raise MaintenanceBlocked("cancelled")

    if not history:
        stage(2, "Corporate earnings")
        try:
            from .wisesheets_local import refresh_local_wisesheets
            outcome = refresh_local_wisesheets()
            kind = ("complete" if outcome in ("current","updated") else
                    "skipped" if outcome in ("disabled","deferred") else
                    "failed")
            record("earnings", {"status":kind,"source_state":outcome})
        except Exception:
            record("earnings", {"status":"failed","reason":"provider_failed"})
    else:
        stage(2, "ALFRED historical publication vintages")
        try:
            from .vintage import probe_access, backfill_batch, first_available_vintages
            key = os.environ.get("FRED_API_KEY", "").strip()
            with managed_client(timeout=25, headers={
                "User-Agent":"GlobalCapitalMonitor/0.2"}) as client:
                check = probe_access(api_key=key, client=client)
                if check["status"] != "ready":
                    record("alfred", {"status":"blocked",
                        "reason":check.get("reason","provider_blocked"),
                        "http_status":check.get("http_status"),
                        "requests":check.get("requests",0)})
                else:
                    end = date.today().replace(day=1)-timedelta(days=1)
                    start = date(2000,1,1)
                    available_since = first_available_vintages(
                        sorted(VINTAGE_IDS), api_key=key, client=client)
                    downloaded = 0
                    result = None
                    first_failure = None
                    failures_in_run = 0
                    attempted_failed: set[tuple[str, date]] = set()
                    for cycle in range(60):
                        if cancelled.is_set():
                            raise MaintenanceBlocked("cancelled")
                        result = backfill_batch(
                            start,end,sorted(VINTAGE_IDS),api_key=key,
                            client=client,max_requests=180,
                            first_available=available_since,
                            skip_failed=attempted_failed)
                        downloaded += result["downloaded_now"]
                        failed_now = result.get("failed_now") or []
                        if first_failure is None and failed_now:
                            first_failure = failed_now[0]
                        failures_in_run += len(failed_now)
                        for failed in failed_now:
                            attempted_failed.add((
                                failed["series_id"],
                                date.fromisoformat(failed["asof"])))
                        self._change(job_id, completed=2,total=stages,
                            current_item="Historical releases",
                            stage="ALFRED historical publication vintages",
                            stage_completed=(result["source_vintages_requested"]
                                             -result["missing_after_run"]),
                            stage_total=result["source_vintages_requested"])
                        if (result["status"] in ("complete","blocked") or
                            (result["downloaded_now"] == 0 and
                             not failed_now)):
                            break
                    assert result is not None
                    if not isinstance(first_failure, dict):
                        first_failure = {}
                    record("alfred", {
                        "first_failed_series": first_failure.get("series_id")
                            if first_failure.get("series_id") in VINTAGE_IDS else None,
                        "first_failed_asof": first_failure.get("asof")
                            if isinstance(first_failure.get("asof"), str) else None,
                        "http_status": first_failure.get("http_status"),
                        "first_failed_reason": first_failure.get("reason"),
                        "failures_in_run": failures_in_run,
                        "status": ("complete" if result["missing_after_run"] == 0
                                   else "blocked" if result["status"] == "blocked"
                                   else "partial"),
                        "downloaded": downloaded,
                        "missing": result["missing_after_run"],
                        "prepublication_excluded": result["prepublication_excluded"],
                        "requested": result["source_vintages_requested"],
                        "reason": (result.get("halted_reason")
                                   if result["status"] == "blocked"
                                   else "unresolved_source_failures"
                                   if failures_in_run else "no_progress"
                                   if result["missing_after_run"] else None),
                    })
        except MaintenanceBlocked:
            raise
        except httpx.HTTPStatusError as exc:
            from .vintage import _safe_http_diagnostic
            record("alfred", {"status":"blocked",
                **_safe_http_diagnostic(exc.response)})
        except httpx.RequestError:
            record("alfred", {"status":"blocked","reason":"fred_network_error"})
        except Exception:
            record("alfred", {"status":"failed","reason":"provider_failed"})
        if cancelled.is_set():
            raise MaintenanceBlocked("cancelled")

        stage(3, "SEC original fund holdings")
        try:
            from .sec_holdings_sync import collect_configured
            report = collect_configured(
                max_filings_per_fund=50, stopped=cancelled,
                progress=progress(3, "SEC original fund holdings"))
            state = report["status"]
            if state in ("disabled_missing_SEC_USER_AGENT","unconfigured"):
                record("sec", {"status":"blocked","reason":
                    "missing_credential" if state.startswith("disabled")
                    else "invalid_source"})
            else:
                funds = report.get("funds",[])
                incomplete_scan = any(
                    row.get("unexamined_candidate_filings", 0) > 0 for row in funds)
                record("sec", {
                    "status": ("complete" if state == "complete" and not
                               incomplete_scan else "partial"),
                    "funds": [{
                        "id":row["instrument_id"],"status":row["status"],
                        "stored":row.get("stored_or_already_present",0),
                        "errors":row.get("errors",0),
                        "reason":row.get("halted_reason"),
                        "first_error_reason":row.get("first_error_reason"),
                        "http_status":row.get("http_status"),
                        "examined":row.get("index_candidates_examined",0),
                        "candidates":row.get("source_candidates_found",0),
                        "unexamined":row.get("unexamined_candidate_filings",0),
                        "missing_verified_xml":row.get("no_verified_xml_in_index",0),
                        "other_series_skipped":row.get("other_series_skipped",0),
                        "historical_coverage_limited": (
                            row.get("unexamined_candidate_filings",0)>0),
                    } for row in funds],
                    "note": ("SEC importer checks up to 50 matching filings per "
                             "fund, not a guarantee of its full lifetime history."),
                })
        except Exception:
            record("sec", {"status":"failed","reason":"provider_failed"})
    if cancelled.is_set():
        raise MaintenanceBlocked("cancelled")
    stage(stages-1, "Verified data backup")
    try:
        from .backup import backup_local, source_database_path, verify_manifest
        folder = Path(os.environ.get("FINANCE_BACKUP_DIR","/data/backups"))
        archive = backup_local(
            folder, source_db=source_database_path(),
            earnings_snapshot=Path(os.environ.get(
                "WISESHEETS_SNAPSHOT_PATH",
                "/data/wisesheets/sec_filer_profit.json")),
            keep=int(os.environ.get("FINANCE_BACKUP_KEEP","14")))
        manifest = folder / archive["database"]["file"].replace(".sqlite3",".json")
        checked = verify_manifest(manifest)
        if checked.get("verified") is not True:
            raise ValueError("Backup failed verification")
        record("backup", {"status":"complete","verified":True,
                          "manifest":manifest.name})
    except Exception:
        record("backup", {"status":"failed","reason":"backup_failed"})
    self._change(job_id, completed=stages,total=stages,
                 stage_completed=None, stage_total=None)
    return {"status":"partial" if issue_count else "complete",
            "mode":"historical" if history else "current",
            "parts":stage_results,
            "limitations":("Source coverage, publication dates, and "
                           "unavailable source rights must be checked "
                           "separately. Missing data are never invented.")}
