"""Bounded, browser-triggered maintenance in the existing API process.

One active operation, single-process serialized with automatic refresh.
Durable redacted job summaries survive a restart; interrupted jobs are marked
as such and are deliberately resumable using existing append-only importers.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from threading import Event, Lock, Thread
from uuid import uuid4
import json
import os
import re
import tempfile

import httpx
from sqlalchemy.engine import Engine

from .standalone import maintenance_network_lock

PUBLIC_ACTIONS = frozenset((
    "refresh_sources", "refresh_markets", "check_alfred", "backfill_alfred",
    "check_sec", "collect_sec", "refresh_earnings", "backup",
))
VINTAGE_IDS = frozenset(("T10Y3M", "SAHMREALTIME", "USREC"))
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
        # All options are validated against an explicit allowlist. Never
        # accept a URL, file path, shell command or raw provider credential.
        if action == "refresh_sources":
            ids = options.get("series_ids") or sorted(valid_sources)
            if (not isinstance(ids, list) or not 1 <= len(ids) <= 53 or
                len(ids) != len(set(ids)) or not set(ids) <= valid_sources):
                raise ValueError("Invalid canonical series selection")
            options = {"series_ids": sorted(ids)}
        elif action == "refresh_markets":
            ids = options.get("instrument_ids") or sorted(valid_markets)
            fx = options.get("currencies") or sorted(FX_IDS)
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
            end = options.get("end", date.today().replace(day=1).isoformat())
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
        Thread(target=self._execute, args=(job["id"], action, options, self._cancel),
               name="gcm-manual-maintenance", daemon=True).start()
        return dict(job)

    def cancel(self, job_id: str) -> dict:
        with self._mutex:
            if self._active != job_id:
                raise ValueError("This job is not active")
            self._cancel.set()
        self._change(job_id, status="cancelling")
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
                if cancelled.is_set():
                    raise MaintenanceBlocked("cancelled")
                self._change(job_id, status="running", started_at=now(), current_item=None)
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
            self._change(job_id, status=status, finished_at=now(),
                         result=result, current_item=None, error_code=failure)
            with self._mutex:
                if self._active == job_id:
                    self._active = None

    def _progress(self, job_id: str, count: int, total: int | None,
                  item: str | None = None) -> None:
        self._change(job_id, completed=count, total=total, current_item=item)

    def _perform(self, job_id: str, action: str, options: dict,
                 cancelled: Event) -> dict:
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
            from .vintage import probe_access, backfill_batch
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
                total_captured=0
                cycles=0
                result=None
                while not cancelled.is_set():
                    result=backfill_batch(start,end,options["series_ids"],
                        api_key=key, client=client,
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
                        "downloaded_now": total_captured,
                        "cycles": cycles,
                        "reason": result.get("halted_reason") or
                            ("no_progress" if result["failed_now"] or not result["downloaded_now"]
                             else None)}
        if action == "check_sec":
            from .sec_holdings_sync import check_sec_sources
            result=check_sec_sources()
            return {"status": "complete" if result["status"] == "ready" else "blocked",
                    "funds": [{"id": f["instrument_id"], "status": f["status"],
                               "reason": f.get("reason"), "http_status": f.get("http_status")}
                              for f in result["funds"]]}
        if action == "collect_sec":
            from .sec_holdings_sync import collect_configured
            result=collect_configured(max_filings_per_fund=options["limit"])
            return {"status": result["status"],
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
            from .backup import backup_local, source_database_path
            output=backup_local(
                Path(os.environ.get("FINANCE_BACKUP_DIR","/data/backups")),
                source_db=source_database_path(),
                earnings_snapshot=Path(os.environ.get("WISESHEETS_SNAPSHOT_PATH",
                                                    "/data/wisesheets/sec_filer_profit.json")),
                keep=int(os.environ.get("FINANCE_BACKUP_KEEP","14")))
            return {"status": "complete",
                    "verified_manifest": output.get("manifest", {}).get("filename")
                    if isinstance(output.get("manifest"), dict) else None}
        raise MaintenanceBlocked("invalid_source")
