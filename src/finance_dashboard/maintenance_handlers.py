"""Canonical maintenance action handlers; one dispatch registry only."""
from __future__ import annotations

from datetime import date
from pathlib import Path
import os
import httpx
from .source_policy import managed_client
from .maintenance_jobs import ACTION_REGISTRY, MaintenanceBlocked
from .maintenance_sync import run_sync as execute_sync

def run_sync(self, job_id, action, options, cancelled):
    return execute_sync(self,job_id, history=action=="sync_history",
                      options=options, cancelled=cancelled)


def run_repair_source_health(self, job_id, action, options, cancelled):
    """Target only actionable macro gaps using the canonical publisher clients.

    This operation is intentionally distinct from a full historical sync.
    It retains research evidence, quotes no synthetic replacements, and
    never re-requests already-current histories simply because an earlier
    optional refresh was policy-deferred.
    """
    from .catalog import load_documents
    from .market import instruments
    from .provider_registry import get_provider
    from .source_coverage import build_coverage
    from .worker import refresh_all

    definitions = load_documents()[0]["series"]
    supported = {
        item["id"] for item in definitions if item["status"] == "mapped"
        and (spec := get_provider(item["provider"])) is not None
        and spec.acquisition != "unsupported"
    }
    def census():
        report = build_coverage(self.engine, definitions, instruments())
        actionable = sorted(item["id"] for item in report["items"]
                            if item["family"] == "macro" and item["state"] != "available")
        return report, actionable
    before, issues = census()
    targets = set(issues) & supported
    unconfigured = sorted(set(issues) - targets)
    if cancelled.is_set():
        raise MaintenanceBlocked("cancelled")
    if not targets:
        return {"status": "skipped" if not issues else "blocked",
                "selected_sources": 0, "issues_before": len(issues),
                "issues_after": len(issues), "unavailable_source_mappings": unconfigured,
                "note": "No actionable mapped collectors available; retained observations are unchanged."}
    self._change(job_id, completed=0, total=len(targets),
                 stage="Repair actionable source histories",
                 current_item="Select stale and failed histories")

    # MSCI regional valuation adapters intentionally read only verified local
    # originals; refreshing those six series without first acquiring newer
    # original PDFs cannot repair the age gap. Use the existing publisher-
    # governed Wayback collector, not another download or synthetic fallback.
    msci_index_by_id = {
        "eafe": "EAFE", "europe": "EUROPE", "japan": "JAPAN",
        "us": "USA", "world": "WORLD", "em": "EM", "acwi": "ACWI",
    }
    msci_indexes = {
        msci_index_by_id[sid.split(".")[1]]
        for sid in targets
        if sid.startswith("valuation.") and ".msci_" in sid
        and sid.split(".")[1] in msci_index_by_id
    }
    msci_result = None
    if msci_indexes and not cancelled.is_set():
        from .msci_regional_factsheets import collect as collect_msci, MsciFactsheetError
        from .source_policy_types import PolicyDeferred, PolicyViolation
        from .service import safe_source_failure_code
        from .developer_logs import record_event
        self._change(job_id, stage="Acquire original MSCI factsheets",
                     current_item=", ".join(sorted(msci_indexes)))
        try:
            msci_result = collect_msci(
                Path(os.environ.get("FINANCE_SOURCE_EVIDENCE_DIR",
                                    "/data/source-evidence")),
                indexes=msci_indexes, stopped=cancelled,
                log=lambda summary: record_event(
                    "macro", "stage_finished", action="repair_msci_factsheets",
                    status="running", completed=len(summary)))
            msci_result["status"] = (
                "partial" if msci_result.get("cdx_failed") or
                msci_result.get("capture_failed") or
                msci_result.get("cancelled") else "complete")
        except (PolicyDeferred, PolicyViolation, httpx.HTTPError,
                MsciFactsheetError, OSError, ValueError) as exc:
            msci_result = {"status": "deferred" if isinstance(exc, PolicyDeferred)
                           else "blocked" if isinstance(exc, PolicyViolation)
                           else "failed",
                           "reason": safe_source_failure_code(exc)}
    if cancelled.is_set():
        raise MaintenanceBlocked("cancelled")
    self._change(job_id, stage="Refresh verified source histories",
                 current_item="Reconcile newly available publisher observations")
    failed = refresh_all(
        self.engine, full=False, series_ids=targets,
        stopped=cancelled,
        progress=lambda done, total, sid: self._progress(job_id, done, total, sid))
    if cancelled.is_set():
        raise MaintenanceBlocked("cancelled")
    after, remaining = census()
    repaired = len(set(issues) - set(remaining))
    result = {
        "status": "complete" if not remaining and not failed else "partial",
        "selected_sources": len(targets),
        "issues_before": len(issues), "issues_after": len(remaining),
        "resolved_issues": repaired, "failed_sources": failed,
        "unavailable_source_mappings": unconfigured,
        "remaining_series_ids": remaining,
        "msci_original_acquisition": msci_result,
        "note": ("Failed/deferred publisher requests stay visible. "
                 "A series is resolved only when the stored source coverage "
                 "or publisher-verified release bound establishes it, not "
                 "merely because a request was submitted."),
    }
    return result


def run_refresh_sources(self, job_id, action, options, cancelled):
    from .worker import refresh_all
    ids = options["series_ids"]
    failed = refresh_all(self.engine, full=True, series_ids=set(ids),
        progress=lambda done, total, sid: self._progress(job_id, done, total, sid),
        stopped=cancelled)
    return {"status": "partial" if failed else "complete",
            "attempted_sources": len(ids), "failed_sources": failed}


def run_refresh_markets(self, job_id, action, options, cancelled):
    from .worker import refresh_market_all
    ids, fx = options["instrument_ids"], options["currencies"]
    failed = refresh_market_all(self.engine,
        instrument_ids=set(ids), currencies=set(fx), stopped=cancelled,
        progress=lambda done,total,sid: self._progress(job_id,done,total,sid))
    return {"status": "partial" if failed else "complete",
            "attempted_sources": len(ids)+len(fx), "failed_sources": failed}


def run_alfred(self, job_id, action, options, cancelled):
    from .vintage import probe_access, backfill_batch, first_available_vintages
    key = os.environ.get("FRED_API_KEY", "").strip()
    with managed_client(timeout=25,headers={"User-Agent":"GlobalCapitalMonitor/0.2"}) as client:
        check = probe_access(api_key=key, client=client)
        if check["status"] != "ready":
            return {"status": "blocked", "reason": check.get("reason", "provider_failed"),
                    "http_status": check.get("http_status")}
        if action == "check_alfred":
            return {"status": "complete", "asof_probe": "2020-01-31",
                    "requests": check["requests"]}
        start,end = date.fromisoformat(options["start"]),date.fromisoformat(options["end"])
        try:
            available_since = first_available_vintages(
                options["series_ids"], api_key=key, client=client)
        except httpx.HTTPStatusError as exc:
            from .vintage import _safe_http_diagnostic
            return {"status": "blocked", **_safe_http_diagnostic(exc.response)}
        except httpx.RequestError:
            return {"status": "blocked", "reason": "fred_network_error"}
        except (ValueError, KeyError, TypeError):
            return {"status": "blocked", "reason": "fred_publication_metadata_invalid"}
        total_captured=0
        cycles=0
        result=None
        while not cancelled.is_set():
            result=backfill_batch(start,end,options["series_ids"],
                api_key=key, client=client,
                max_requests=options["max_requests"],
                first_available=available_since)
            total_captured += result["downloaded_now"]
            cycles+=1
            requested=result["source_vintages_requested"]
            self._progress(job_id, requested-result["missing_after_run"],
                requested, result["next_missing"]["series_id"] if result["next_missing"] else None)
            if result["status"] in ("complete","blocked"):
                break
            if result["failed_now"] or not result["downloaded_now"]:
                break
            if not options["complete_range"] or cycles>=60:
                break
        assert result is not None or cancelled.is_set()
        if cancelled.is_set():
            raise MaintenanceBlocked("cancelled")
        return {"status": result["status"], "vintages_total": result["source_vintages_requested"],
                "vintages_missing": result["missing_after_run"],
                "prepublication_excluded": result["prepublication_excluded"],
                # Source-level availability bounds do not establish
                # each observation's first-publication history.
                "first_publication_vintage_verified": False,
                "downloaded_now": total_captured,
                "cycles": cycles,
                "reason": result.get("halted_reason") or
                    ("no_progress" if result["status"] != "complete" and
                     (result["failed_now"] or not result["downloaded_now"])
                     else None)}


def run_check_sec(self, job_id, action, options, cancelled):
    from .sec_holdings_sync import check_sec_sources
    result=check_sec_sources()
    return {"status": "complete" if result["status"] == "ready" else "blocked",
            "reason": result.get("reason") if not result["funds"] else None,
            "funds": [{"id": f["instrument_id"], "status": f["status"],
                       "reason": f.get("reason"), "http_status": f.get("http_status")}
                      for f in result["funds"]]}


def run_collect_sec(self, job_id, action, options, cancelled):
    from .sec_holdings_sync import collect_configured
    result=collect_configured(max_filings_per_fund=options["limit"],
        progress=lambda done,total,sid:self._progress(job_id,done,total,sid),
        stopped=cancelled)
    state = result["status"]
    if state == "disabled_missing_SEC_USER_AGENT":
        return {"status":"blocked", "reason":"missing_credential","funds":[]}
    if state == "unconfigured":
        return {"status":"blocked","reason":"invalid_source","funds":[]}
    return {"status": state,
            "funds": [{"id": f["instrument_id"], "status": f["status"],
                       "stored": f.get("stored_or_already_present", 0),
                       "attempted": f.get("attempted", 0),
                       "errors": f.get("errors", 0),
                       "http_status": f.get("http_status")}
                      for f in result["funds"]]}


def run_refresh_earnings(self, job_id, action, options, cancelled):
    from .wisesheets_local import refresh_local_wisesheets
    outcome=refresh_local_wisesheets()
    return {"status": "complete" if outcome in ("current", "updated")
            else "blocked" if outcome == "disabled" else "partial",
            "source_state": outcome}


def run_backup(self, job_id, action, options, cancelled):
    from .backup import backup_local, source_database_path, verify_manifest
    folder=Path(os.environ.get("FINANCE_BACKUP_DIR","/data/backups"))
    output=backup_local(
        folder, source_db=source_database_path(),
        earnings_snapshot=Path(os.environ.get("WISESHEETS_SNAPSHOT_PATH",
                                            "/data/wisesheets/sec_filer_profit.json")),
        keep=int(os.environ.get("FINANCE_BACKUP_KEEP","14")))
    manifest=folder / output["database"]["file"].replace(".sqlite3",".json")
    confirmed=verify_manifest(manifest)
    return {"status": "complete", "verified": confirmed["verified"],
            "manifest": manifest.name,
            "components": confirmed["components"]}


def execute_action(manager, job_id: str, action: str, options: dict, cancelled):
    spec = ACTION_REGISTRY.get(action)
    if spec is None:
        raise MaintenanceBlocked("invalid_source")
    handler = globals().get(spec.handler)
    if not callable(handler):
        raise RuntimeError("Registered maintenance handler unavailable")
    return handler(manager, job_id, action, options, cancelled)
