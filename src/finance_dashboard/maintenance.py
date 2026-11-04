"""Bounded, browser-triggered maintenance in the existing API process.

One active operation, single-process serialized with automatic refresh.
Durable redacted job summaries survive a restart; interrupted jobs are marked
as such and are deliberately resumable using existing append-only importers.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from threading import Event, Lock, Thread
from uuid import uuid4
import json
import os
import re
import tempfile

import httpx
from sqlalchemy.engine import Engine

from .standalone import maintenance_network_lock, manual_sync_pending
from .developer_logs import record_event
from .vintage import SOURCES as VINTAGE_SOURCES

PUBLIC_ACTIONS = frozenset((
    "sync_current", "sync_history",
    "refresh_sources", "refresh_markets", "check_alfred", "backfill_alfred",
    "check_sec", "collect_sec", "refresh_earnings", "backup",
))
VINTAGE_IDS = frozenset(VINTAGE_SOURCES)
FX_IDS = frozenset(("USD", "GBP", "CHF"))
JOB_STATES = frozenset(("queued", "waiting", "running", "cancelling"))
SAFE_ERRORS = frozenset((
    "invalid_source", "provider_blocked", "provider_failed",
    "missing_credential", "access_denied", "rate_limited", "no_progress",
    "source_invalid", "internal_error", "cancelled", "interrupted",
))


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save_atomic(path: Path, jobs: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix=".jobs-", suffix=".tmp",
            dir=path.parent, delete=False,
        ) as out:
            json.dump({"version": 1, "jobs": jobs[-30:]}, out, sort_keys=True, indent=2)
            out.write("\n")
            tmp = Path(out.name)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        tmp = None
    finally:
        if tmp:
            tmp.unlink(missing_ok=True)


class MaintenanceBlocked(Exception):
    def __init__(self, code: str):
        self.code = code if code in SAFE_ERRORS else "provider_blocked"
        super().__init__(self.code)


class BusyMaintenance(Exception):
    pass


class MaintenanceManager:
    def __init__(self, engine: Engine, *, state_path: Path | None = None):
        self.engine = engine
        self.path = state_path or Path(os.environ.get(
            "FINANCE_MAINTENANCE_STATE", "/data/maintenance/jobs.json"))
        self._mutex = Lock()
        self._cancel = Event()
        self._active: str | None = None
        self._jobs: list[dict] = []
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            if saved.get("version") == 1 and isinstance(saved.get("jobs"), list):
                for item in saved["jobs"][-30:]:
                    if not isinstance(item, dict):
                        continue
                    # Historic files may have been interrupted mid-import.
                    if item.get("status") in JOB_STATES:
                        item["status"] = "interrupted"
                        item["finished_at"] = now()
                        item["error_code"] = "interrupted"
                    self._jobs.append(item)
        except (OSError, ValueError, TypeError, KeyError):
            pass

    def list(self) -> dict:
        with self._mutex:
            return {"active_job_id": self._active,
                    "jobs": [dict(item) for item in reversed(self._jobs[-20:])],
                    "operations": sorted(PUBLIC_ACTIONS)}

    def _change(self, job_id: str, **changes) -> None:
        with self._mutex:
            for item in self._jobs:
                if item["id"] == job_id:
                    item.update(changes)
                    _save_atomic(self.path, self._jobs)
                    break

    def submit(self, action: str, options: dict, *,
               valid_sources: set[str], valid_markets: set[str]) -> dict:
        if action not in PUBLIC_ACTIONS:
            raise ValueError("Unknown maintenance operation")
        allowed = {
            "sync_current": set(),
            "sync_history": set(),
            "refresh_sources": {"series_ids"},
            "refresh_markets": {"instrument_ids", "currencies"},
            "check_alfred": set(),
            "backfill_alfred": {"series_ids", "start", "end",
                                "max_requests", "complete_range"},
            "check_sec": set(),
            "collect_sec": {"limit"},
            "refresh_earnings": set(),
            "backup": set(),
        }
        if not set(options) <= allowed[action]:
            raise ValueError("Unexpected maintenance parameters")
        # All options are validated against an explicit allowlist. Never
        # accept a URL, file path, shell command or raw provider credential.
        if action in ("sync_current", "sync_history"):
            if options:
                raise ValueError("Sync operations accept no manual source settings")
            options = {
                "series_ids": sorted(valid_sources),
                "instrument_ids": sorted(valid_markets),
                "currencies": sorted(FX_IDS),
            }
        elif action == "refresh_sources":
            ids = options["series_ids"] if "series_ids" in options else sorted(valid_sources)
            if (not isinstance(ids, list) or not 1 <= len(ids) <= len(valid_sources) or
                len(ids) != len(set(ids)) or not set(ids) <= valid_sources):
                raise ValueError("Invalid canonical series selection")
            options = {"series_ids": sorted(ids)}
        elif action == "refresh_markets":
            ids = options["instrument_ids"] if "instrument_ids" in options else sorted(valid_markets)
            fx = options["currencies"] if "currencies" in options else sorted(FX_IDS)
            if (not isinstance(ids, list) or len(ids) > 24 or
                len(ids) != len(set(ids)) or not set(ids) <= valid_markets or
                not isinstance(fx, list) or len(fx) > 3 or
                len(fx) != len(set(fx)) or not set(fx) <= FX_IDS or
                not (ids or fx)):
                raise ValueError("Invalid market or FX selection")
            options = {"instrument_ids": sorted(ids), "currencies": sorted(fx)}
        elif action == "backfill_alfred":
            sources = options.get("series_ids") or sorted(VINTAGE_IDS)
            start = options.get("start", "2000-01-01")
            end = options.get("end", (date.today().replace(day=1) -
                                       timedelta(days=1)).isoformat())
            limit = options.get("max_requests", 60)
            full = options.get("complete_range", True)
            try:
                lower, upper = date.fromisoformat(start), date.fromisoformat(end)
            except (TypeError, ValueError):
                raise ValueError("Invalid historical date range") from None
            if (lower < date(1950,1,1) or lower > upper or upper > date.today()
                or not isinstance(sources, list) or not sources or
                not set(sources) <= VINTAGE_IDS or len(sources) != len(set(sources))
                or type(limit) is not int or not 1 <= limit <= 180
                or type(full) is not bool):
                raise ValueError("Invalid ALFRED backfill parameters")
            options = {"start": lower.isoformat(), "end": upper.isoformat(),
                       "series_ids": sorted(sources), "max_requests": limit,
                       "complete_range": full}
        elif action == "collect_sec":
            limit = options.get("limit", 12)
            if type(limit) is not int or not 1 <= limit <= 50:
                raise ValueError("Invalid SEC matching filing limit")
            options = {"limit": limit}
        else:
            if options:
                raise ValueError("This maintenance operation takes no parameters")
            options = {}

        with self._mutex:
            if self._active is not None:
                raise BusyMaintenance("A maintenance operation is already active")
            job = {"id": uuid4().hex, "action": action, "options": options,
                   "status": "queued", "created_at": now(), "started_at": None,
                   "finished_at": None, "completed": 0, "total": None,
                   "current_item": None, "result": None, "error_code": None}
            self._jobs.append(job)
            self._jobs = self._jobs[-30:]
            self._active = job["id"]
            self._cancel = Event()
            _save_atomic(self.path, self._jobs)
            manual_sync_pending.set()
        record_event("sync", "queued", action=action, job_id=job["id"],
                     status="queued")
        Thread(target=self._execute, args=(job["id"], action, options, self._cancel),
               name="gcm-manual-maintenance", daemon=True).start()
        return dict(job)

    def cancel(self, job_id: str) -> dict:
        with self._mutex:
            if self._active != job_id:
                raise ValueError("This job is not active")
            self._cancel.set()
        self._change(job_id, status="cancelling")
        record_event("sync", "cancel_requested", job_id=job_id, status="running")
        return {"id": job_id, "status": "cancelling"}

    def _execute(self, job_id: str, action: str, options: dict,
                 cancelled: Event) -> None:
        status = "complete"
        failure = None
        result = None
        try:
            self._change(job_id, status="waiting", current_item="Waiting for source collector")
            while not maintenance_network_lock.acquire(timeout=.25):
                if cancelled.is_set():
                    raise MaintenanceBlocked("cancelled")
            try:
                manual_sync_pending.clear()
                if cancelled.is_set():
                    raise MaintenanceBlocked("cancelled")
                self._change(job_id, status="running", started_at=now(), current_item=None)
                record_event("sync", "started", action=action, job_id=job_id,
                             status="running")
                result = self._perform(job_id, action, options, cancelled)
                if cancelled.is_set():
                    raise MaintenanceBlocked("cancelled")
                if result.get("status") in ("blocked", "failed", "partial"):
                    status = result["status"]
                    failure = result.get("reason") or "provider_failed"
            finally:
                maintenance_network_lock.release()
        except MaintenanceBlocked as exc:
            status = "cancelled" if exc.code == "cancelled" else "blocked"
            failure = exc.code
        except Exception:
            status, failure = "failed", "internal_error"
        finally:
            # Complete the best-effort journal attempt before readers can see
            # a terminal job. Keep diagnostic I/O outside the job-state lock.
            try:
                record_event("sync", "finished",
                             level="info" if status == "complete" else "warning",
                             action=action, job_id=job_id, status=status,
                             reason=failure)
            except Exception:
                # A diagnostic failure must not strand the active job.
                pass
            # Publish terminal state and clear the active slot atomically so
            # polling clients never see a finished job that is still busy.
            with self._mutex:
                for item in self._jobs:
                    if item["id"] == job_id:
                        item.update(status=status, finished_at=now(),
                                    result=result, current_item=None,
                                    error_code=failure)
                        break
                if self._active == job_id:
                    self._active = None
                manual_sync_pending.clear()
                _save_atomic(self.path, self._jobs)

    def _progress(self, job_id: str, count: int, total: int | None,
                  item: str | None = None) -> None:
        self._change(job_id, completed=count, total=total, current_item=item)

    def _sync(self, job_id: str, *, history: bool, options: dict,
              cancelled: Event) -> dict:
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
                with httpx.Client(timeout=25, headers={
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
                                # Stay below FRED's 120 requests/minute limit:
                                # https://fred.stlouisfed.org/docs/api/fred/errors.html
                                pause_seconds=0.6,
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

    def _perform(self, job_id: str, action: str, options: dict,
                 cancelled: Event) -> dict:
        if action in ("sync_current","sync_history"):
            return self._sync(job_id, history=action=="sync_history",
                              options=options, cancelled=cancelled)
        if action == "refresh_sources":
            from .worker import refresh_all
            ids = options["series_ids"]
            failed = refresh_all(self.engine, full=True, series_ids=set(ids),
                progress=lambda done, total, sid: self._progress(job_id, done, total, sid),
                stopped=cancelled)
            return {"status": "partial" if failed else "complete",
                    "attempted_sources": len(ids), "failed_sources": failed}
        if action == "refresh_markets":
            from .worker import refresh_market_all
            ids, fx = options["instrument_ids"], options["currencies"]
            failed = refresh_market_all(self.engine,
                instrument_ids=set(ids), currencies=set(fx), stopped=cancelled,
                progress=lambda done,total,sid: self._progress(job_id,done,total,sid))
            return {"status": "partial" if failed else "complete",
                    "attempted_sources": len(ids)+len(fx), "failed_sources": failed}
        if action in ("check_alfred", "backfill_alfred"):
            from .vintage import probe_access, backfill_batch, first_available_vintages
            key = os.environ.get("FRED_API_KEY", "").strip()
            with httpx.Client(timeout=25,headers={"User-Agent":"GlobalCapitalMonitor/0.2"}) as client:
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
                        # Same bounded spacing as full history synchronization.
                        pause_seconds=0.6, first_available=available_since,
                        max_requests=options["max_requests"])
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
        if action == "check_sec":
            from .sec_holdings_sync import check_sec_sources
            result=check_sec_sources()
            return {"status": "complete" if result["status"] == "ready" else "blocked",
                    "reason": result.get("reason") if not result["funds"] else None,
                    "funds": [{"id": f["instrument_id"], "status": f["status"],
                               "reason": f.get("reason"), "http_status": f.get("http_status")}
                              for f in result["funds"]]}
        if action == "collect_sec":
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
        if action == "refresh_earnings":
            from .wisesheets_local import refresh_local_wisesheets
            outcome=refresh_local_wisesheets()
            return {"status": "complete" if outcome in ("current", "updated")
                    else "blocked" if outcome == "disabled" else "partial",
                    "source_state": outcome}
        if action == "backup":
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
        raise MaintenanceBlocked("invalid_source")
