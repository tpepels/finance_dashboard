"""One-process home-server mode: API, built UI, persistent DB and periodic refresh.

No scheduler daemon, supervisor, Redis or separate worker container is needed.
The existing refresh adapters run in a background thread of the same process,
with the same transactional source and ingestion semantics as the normal worker.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
import json
import logging
import math
import os
from os import environ
from pathlib import Path
import tempfile
import time
from datetime import datetime, timezone
from threading import Event, Lock, Thread
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy.engine import Engine

from .developer_logs import record_event
from .failure_journal import record_failure

log = logging.getLogger(__name__)

# Manual browser actions and scheduled refreshes never overlap network writes.
maintenance_network_lock = Lock()
# Manual browser sync preempts scheduled refresh between provider requests.
# The shared lock still prevents concurrent writes.
manual_sync_pending = Event()

_schedule_lock = Lock()
_schedule_progress = {
    "refresh_running": False, "refresh_state": "not_started",
    "next_refresh_at": None, "last_refresh_finished_at": None,
    "refresh_stage": None, "refresh_completed": 0, "refresh_total": None,
    "refresh_current_source": None, "refresh_started_at": None,
    "last_refresh_outcome": None, "last_error_code": None,
    "last_error_stage": None, "last_error_at": None,
    "last_failure_id": None, "last_failure_persisted": None,
}


def _record_schedule(**updates) -> None:
    with _schedule_lock:
        _schedule_progress.update(updates)


def scheduled_refresh_status() -> dict:
    """Observed in-process scheduler transitions; no SQL or network access."""
    with _schedule_lock:
        return dict(_schedule_progress)


def _utc_time(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


class _ScheduledStop:
    def __init__(self, stopped):
        self.stopped = stopped
        self.preempted = False

    def is_set(self) -> bool:
        pending = manual_sync_pending.is_set()
        if pending:
            self.preempted = True
        return self.stopped.is_set() or pending


def enabled(name: str, default: str = "0") -> bool:
    return environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def refresh_interval() -> int:
    raw = environ.get("REFRESH_INTERVAL_SECONDS", "86400")
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError("REFRESH_INTERVAL_SECONDS must be an integer") from exc
    if value < 3600:
        raise ValueError("REFRESH_INTERVAL_SECONDS must be at least 3600")
    return value


def _schedule_path() -> Path:
    return Path(environ.get("FINANCE_REFRESH_SCHEDULE_PATH",
                            "/data/maintenance/refresh-schedule.json"))


def _schedule_due(interval_seconds: int) -> float:
    """Persist the first scheduled due time, so restart does not reset it.

    A missing record begins a single interval on the first boot. The document
    contains only a schema version and a UTC deadline, not any source data.
    Missing/unreadable storage falls back to the legacy deferred interval.
    """
    now = time.time()
    path = _schedule_path()
    try:
        if path.is_symlink():
            raise ValueError("schedule_symlink_refused")
        if path.is_file():
            if path.stat().st_size > 1024:
                raise ValueError("schedule_unbounded_state")
            record = json.loads(path.read_text(encoding="utf-8"))
            due = record.get("next_due_unix")
            if record.get("schema_version") != 1 or type(due) not in (float, int):
                raise ValueError("schedule_invalid_schema")
            if not float("-inf") < float(due) < float("inf"):
                raise ValueError("schedule_invalid_time")
            # Long-dormant installations are overdue, not reset to another
            # 24-hour delay. Reject only impossible epoch dates or absurdly
            # distant future deadlines.
            if 1609459200 <= due and due - now <= interval_seconds * 14:
                return float(due)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        log.warning("Refresh schedule state unreadable; using safe initial interval")
    due = now + interval_seconds
    _save_schedule_due(due)
    return due


def _save_schedule_due(due: float) -> None:
    """Atomic small scheduler metadata update on the existing /data mount."""
    path = _schedule_path()
    temporary = None
    try:
        if path.is_symlink():
            raise ValueError("schedule_symlink_refused")
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
                mode="w", dir=path.parent, prefix=".refresh-schedule-",
                encoding="utf-8", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump({"schema_version": 1, "next_due_unix": due}, handle,
                      separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except (OSError, ValueError):
        log.warning("Could not persist refresh deadline; keeping scheduler operational")
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                log.warning("Could not remove temporary schedule metadata")


def refresh_loop(engine: Engine, stopped: Event, *, interval_seconds: int,
                 include_markets: bool, refresh_wisesheets: bool = True,
                 original_sources=None) -> None:
    # Import the already tested source adapters only when refresh is enabled.
    from .worker import refresh_all, refresh_market_all

    scheduled_stop = _ScheduledStop(stopped)
    # Restored/verified releases can warm acceptance without immediately
    # reacquiring the entire corpus. Normal daily updates remain enabled.
    _record_schedule(refresh_running=False, refresh_state="starting",
                     next_refresh_at=None)
    if not enabled('FINANCE_REFRESH_ON_START', '1'):
        # Restarting Docker must not reset the clock indefinitely. A due
        # deadline is persisted before the initial wait and updated after
        # each cycle. An overdue refresh begins immediately.
        due = _schedule_due(interval_seconds)
        initial_wait = max(0, math.ceil(due - time.time()))
        _record_schedule(refresh_running=False, refresh_state="waiting",
                         next_refresh_at=_utc_time(due))
        if engine is not None and enabled("FINANCE_SOURCE_PREFLIGHT_ON_START", "1"):
            # Source refresh is deliberately delayed after deployment. A
            # read-only planner check nevertheless exercises the real stored
            # histories and publisher registration now, without network
            # requests or modifying observations. This exposes a
            # production-only planner defect immediately rather than
            # postponing the first diagnosable failure for 24 hours.
            try:
                findings = refresh_all(engine, stopped=scheduled_stop,
                                       skip_complete_pinned=True,
                                       preflight_only=True)
                if findings:
                    # Per-source planner failures were recorded independently;
                    # a partial preflight does not imply the whole catalogue
                    # cannot be collected at the next scheduled refresh.
                    _record_schedule(refresh_state="preflight_partial",
                                     last_error_code="planner_partial",
                                     last_error_stage="startup_refresh_preflight",
                                     last_error_at=_utc_time(time.time()))
                    record_event("macro", "stage_finished", level="warning",
                                 action="source_refresh_preflight",
                                 status="partial", failed=findings)
            except Exception as exc:
                failure = record_failure("scheduler", "startup_refresh_preflight", exc)
                _record_schedule(refresh_running=False,
                                 refresh_state="preflight_failed",
                                 last_error_code="internal_error",
                                 last_error_stage="startup_refresh_preflight",
                                 last_error_at=_utc_time(time.time()),
                                 last_failure_id=failure["id"],
                                 last_failure_persisted=failure["persisted"])
                record_event("system", "collector_failed", level="error",
                             action="source_refresh_preflight",
                             reason="internal_error",
                             stage="startup_refresh_preflight")
        if initial_wait > 0 and stopped.wait(initial_wait):
            _record_schedule(refresh_running=False, refresh_state="stopped",
                             next_refresh_at=None)
            return
    consecutive_core_errors = 0
    while not stopped.is_set():
        if manual_sync_pending.is_set():
            _record_schedule(refresh_running=False,
                             refresh_state="waiting_for_manual_collection",
                             next_refresh_at=None)
            # The manual job clears its event independently. Recheck it
            # promptly instead of parking the interrupted schedule for a day.
            if stopped.wait(min(interval_seconds, 30)):
                break
            continue
        with maintenance_network_lock:
            scheduled_stop.preempted = False
            _record_schedule(refresh_running=True, refresh_state="collecting",
                             refresh_stage="macro", refresh_completed=0,
                             refresh_total=None, refresh_current_source=None,
                             refresh_started_at=_utc_time(time.time()),
                             last_error_code=None, last_error_stage=None,
                             last_error_at=None, last_failure_id=None,
                             last_failure_persisted=None, last_refresh_outcome=None,
                             next_refresh_at=None)
            cycle_failed = False
            core_crashed = False
            def macro_progress(completed, total, source_id):
                # Completed tasks include policy deferrals. This is task
                # progress, never a fabricated count of successful imports.
                _record_schedule(refresh_stage="macro", refresh_completed=completed,
                                 refresh_total=total, refresh_current_source=source_id)
            record_event("system", "started", action="scheduled_refresh",
                         status="running")
            if refresh_wisesheets:
                try:
                    from .wisesheets_local import refresh_local_wisesheets
                    refresh_local_wisesheets()
                except Exception as exc:
                    cycle_failed = True
                    record_failure("earnings", "wisesheets", exc)
                    record_event("earnings", "collector_failed", level="warning",
                                 action="scheduled_refresh", reason="provider_failed")
                    log.warning("Local Wisesheets refresh cycle failed; retaining previous aggregate")
            def record_core_exception(phase: str, exc: Exception):
                nonlocal cycle_failed, core_crashed
                cycle_failed = True
                core_crashed = True
                failure = record_failure("scheduler", phase, exc)
                _record_schedule(refresh_state="source_collection_failed",
                                 refresh_stage=phase,
                                 last_error_code="internal_error",
                                 last_error_stage=phase,
                                 last_error_at=_utc_time(time.time()),
                                 last_failure_id=failure["id"],
                                 last_failure_persisted=failure["persisted"])
                record_event("system", "collector_failed", level="error",
                             action="scheduled_refresh", reason="internal_error",
                             stage=phase)
                log.error("%s refresh stage aborted (details redacted); "
                          "continuing independent source stages", phase)

            try:
                macro_failures = refresh_all(
                    engine, stopped=scheduled_stop, skip_complete_pinned=True,
                    progress=macro_progress)
                if macro_failures:
                    cycle_failed = True
                    record_event("macro", "stage_finished", level="warning",
                                 action="scheduled_refresh", status="partial",
                                 failed=macro_failures)
                    log.warning("%d macro sources failed; retained successful observations",
                                macro_failures)
            except Exception as exc:
                # Never prevent the independent market/FX collection stage.
                record_core_exception("macro", exc)

            if include_markets and not scheduled_stop.is_set():
                _record_schedule(refresh_stage="markets")
                try:
                    market_failures = refresh_market_all(engine, stopped=scheduled_stop)
                    if market_failures:
                        cycle_failed = True
                        record_event("markets", "stage_finished", level="warning",
                                     action="scheduled_refresh", status="partial",
                                     failed=market_failures)
                        log.warning("%d market/FX sources failed; retained successful observations",
                                    market_failures)
                except Exception as exc:
                    record_core_exception("markets", exc)
            if enabled("FINANCE_VINTAGE_REFRESH", "1") and not scheduled_stop.is_set():
                _record_schedule(refresh_stage="vintage")
                try:
                    from .vintage import capture_previous_month
                    outcome = capture_previous_month()
                    if outcome["errors"]:
                        cycle_failed = True
                        record_event("alfred", "stage_finished", level="warning",
                                     action="scheduled_refresh", status="partial",
                                     reason="provider_failed")
                        log.warning("Historical ALFRED monthly collection partially failed; "
                                    "existing verified vintages retained")
                    elif outcome["status"] == "complete":
                        log.info("Completed ALFRED month-end capture for %s",
                                 outcome["asof"])
                except Exception as exc:
                    cycle_failed = True
                    record_failure("alfred", "vintage", exc)
                    record_event("alfred", "collector_failed", level="warning",
                                 action="scheduled_refresh", reason="provider_failed")
                    log.warning("ALFRED month-end capture failed; source API credentials redacted")
            if enabled("FINANCE_SEC_HOLDINGS_REFRESH", "0") and not scheduled_stop.is_set():
                _record_schedule(refresh_stage="sec")
                try:
                    from .sec_holdings_sync import collect_if_due
                    result=collect_if_due()
                    if result["status"] == "partial":
                        cycle_failed = True
                        record_event("sec", "stage_finished", level="warning",
                                     action="scheduled_refresh", status="partial")
                        log.warning("Official SEC N-PORT refresh partially failed; retaining stored filings")
                    elif result["status"] == "complete":
                        log.info("Official SEC N-PORT monthly report collection completed")
                except Exception as exc:
                    cycle_failed = True
                    record_failure("sec", "holdings", exc)
                    record_event("sec", "collector_failed", level="warning",
                                 action="scheduled_refresh", reason="provider_failed")
                    log.warning("SEC N-PORT collection failed; preserving verified historical filings")
            if enabled("FINANCE_AUTO_BACKUP", "1") and not scheduled_stop.is_set():
                _record_schedule(refresh_stage="backup")
                try:
                    from .backup import backup_local, source_database_path
                    backup_local(
                        Path(environ.get("FINANCE_BACKUP_DIR", "/data/backups")),
                        source_db=source_database_path(),
                        earnings_snapshot=Path(environ.get(
                            "WISESHEETS_SNAPSHOT_PATH",
                            "/data/wisesheets/sec_filer_profit.json")),
                        keep=int(environ.get("FINANCE_BACKUP_KEEP", "14")),
                    )
                    log.info("Verified SQLite online backup created")
                except Exception as exc:
                    cycle_failed = True
                    record_failure("backup", "sqlite_backup", exc)
                    record_event("backup", "collector_failed", level="error",
                                 action="scheduled_refresh", reason="backup_failed")
                    log.warning("SQLite online backup failed; latest verified backups retained")
            interrupted = scheduled_stop.preempted or manual_sync_pending.is_set()
            record_event("system", "finished",
                         level="warning" if cycle_failed or interrupted else "info",
                         action="scheduled_refresh",
                         status=("interrupted" if interrupted else
                                 "partial" if cycle_failed else "complete"))
            if interrupted:
                # Another collection preempted this batch; the untouched
                # suffix still needs its regular attempt. Retry soon after
                # the manual job, respecting the existing per-publisher quotas.
                consecutive_core_errors = 0
                retry_seconds = min(interval_seconds, 60)
            elif core_crashed:
                # A planner/collector exception leaves source histories
                # unattempted. Retry sooner than the normal daily cadence,
                # with bounded exponential backoff; publisher HTTP retries
                # still obey the existing durable rate/cooldown policy.
                consecutive_core_errors += 1
                retry_seconds = min(interval_seconds,
                                    900 * (2 ** min(consecutive_core_errors - 1, 5)))
            else:
                consecutive_core_errors = 0
                retry_seconds = interval_seconds
            next_due = time.time() + retry_seconds
            _save_schedule_due(next_due)
            _record_schedule(refresh_running=False, refresh_state="waiting",
                             refresh_stage=None, refresh_current_source=None,
                             next_refresh_at=_utc_time(next_due),
                             last_refresh_outcome=("interrupted" if interrupted else
                                                    "partial" if cycle_failed else "complete"),
                             last_refresh_finished_at=_utc_time(time.time()))
        # A complete scheduled cycle can also update vintage, SEC or other
        # original evidence outside IngestionService.refresh. Notify one
        # downstream reconciliation for those native archive changes.
        from .data_change_bus import publish_change
        try:
            publish_change(engine, "scheduled_cycle_finished")
        except Exception as exc:
            record_failure("scheduler", "publish_change", exc)
            record_event("system", "collector_failed", level="error",
                         action="scheduled_refresh",
                         reason="downstream_notification_failed",
                         stage="publish_change")
        # The already-existing immutable-original queue has publisher budgets,
        # pending retries, expiry intervals and an ingestion callback. Kick its
        # due work once per scheduled cycle, outside the network lock. The
        # queue handles actual downloads; this loop never opens a second
        # source-acquisition path or duplicates existing imports.
        if original_sources is not None and not stopped.is_set():
            try:
                queued = original_sources.fetch()
                record_event("system", "stage_finished",
                             action="scheduled_original_sources",
                             status="complete",
                             completed=len(queued.get("jobs") or []))
            except Exception as exc:
                cycle_failed = True
                record_failure("scheduler", "scheduled_original_sources", exc)
                record_event("system", "collector_failed", level="warning",
                             action="scheduled_original_sources",
                             reason="original_source_schedule_failed")
        if stopped.wait(retry_seconds):
            break
    _record_schedule(refresh_running=False, refresh_state="stopped",
                     refresh_stage=None, refresh_current_source=None,
                     next_refresh_at=None)


@asynccontextmanager
async def standalone_lifespan(app: FastAPI, *, engine: Engine) -> AsyncIterator[None]:
    if not enabled("FINANCE_AUTO_REFRESH"):
        _record_schedule(refresh_running=False, refresh_state="disabled",
                         next_refresh_at=None)
        yield
        return
    interval_seconds = refresh_interval()
    include_markets = enabled("FINANCE_INCLUDE_MARKETS")
    refresh_wisesheets = enabled("FINANCE_WISESHEETS_REFRESH", "1")
    stopped = Event()
    def guarded_refresh():
        try:
            refresh_loop(engine, stopped, interval_seconds=interval_seconds,
                         include_markets=include_markets,
                         refresh_wisesheets=refresh_wisesheets,
                         original_sources=getattr(app.state, "manual_sources", None))
        except Exception as exc:
            # Absolute last-resort guard for errors outside the normal
            # macro/source/backup catches. Never leave a dead thread claiming
            # that source collection is still running.
            failure = record_failure("scheduler", "thread_uncaught", exc)
            _record_schedule(refresh_running=False, refresh_state="crashed",
                             last_error_code="internal_error",
                             last_error_stage="thread_uncaught",
                             last_error_at=_utc_time(time.time()),
                             last_failure_id=failure["id"],
                             last_failure_persisted=failure["persisted"],
                             next_refresh_at=None)
            record_event("system", "collector_failed", level="error",
                         action="scheduled_refresh", reason="internal_error",
                         stage="thread_uncaught")
    thread = Thread(target=guarded_refresh, name="finance-macro-refresh",
                    daemon=True)
    thread.start()
    log.info("Single-container refresh started: interval=%ss markets=%s",
             interval_seconds, include_markets)
    try:
        yield
    finally:
        stopped.set()
        thread.join(timeout=2)


def mount_built_dashboard(app: FastAPI) -> bool:
    """Serve built Vite files at / after all /api/* routes, same origin."""
    path = environ.get("FINANCE_DASHBOARD_UI_DIR")
    if not path:
        return False
    root = Path(path).resolve()
    if not root.is_dir() or not (root / "index.html").is_file():
        raise RuntimeError("FINANCE_DASHBOARD_UI_DIR must contain a built index.html")
    # StaticFiles is last route: existing /api and /docs always take priority.
    app.mount("/", StaticFiles(directory=str(root), html=True), name="dashboard")
    return True
