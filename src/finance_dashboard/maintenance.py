"""Bounded, browser-triggered maintenance in the existing API process.

One active operation, single-process serialized with automatic refresh.
Durable redacted job summaries survive a restart; interrupted jobs are marked
as such and are deliberately resumable using existing append-only importers.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Lock, Thread
from uuid import uuid4
import json
import os
import tempfile

from sqlalchemy.engine import Engine

from .standalone import maintenance_network_lock, manual_sync_pending
from .developer_logs import record_event
from .maintenance_jobs import PUBLIC_ACTIONS, MaintenanceBlocked, normalize_options
from .maintenance_handlers import execute_action

JOB_STATES = frozenset(("queued", "waiting", "running", "cancelling"))
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
        options = normalize_options(action, options, valid_sources=valid_sources,
                                    valid_markets=valid_markets)

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
                result = execute_action(self, job_id, action, options, cancelled)
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
