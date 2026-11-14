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
from threading import Event, Lock, Thread
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy.engine import Engine

from .developer_logs import record_event

log = logging.getLogger(__name__)

# Manual browser actions and scheduled refreshes never overlap network writes.
maintenance_network_lock = Lock()
# Manual browser sync preempts scheduled refresh between provider requests.
# The shared lock still prevents concurrent writes.
manual_sync_pending = Event()

class _ScheduledStop:
    def __init__(self, stopped):
        self.stopped = stopped

    def is_set(self) -> bool:
        return self.stopped.is_set() or manual_sync_pending.is_set()


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
                 include_markets: bool, refresh_wisesheets: bool = True) -> None:
    # Import the already tested source adapters only when refresh is enabled.
    from .worker import refresh_all, refresh_market_all

    scheduled_stop = _ScheduledStop(stopped)
    # Restored/verified releases can warm acceptance without immediately
    # reacquiring the entire corpus. Normal daily updates remain enabled.
    if not enabled('FINANCE_REFRESH_ON_START', '1'):
        # Restarting Docker must not reset the clock indefinitely. A due
        # deadline is persisted before the initial wait and updated after
        # each cycle. An overdue refresh begins immediately.
        initial_wait = max(0, math.ceil(_schedule_due(interval_seconds) - time.time()))
        if initial_wait > 0 and stopped.wait(initial_wait):
            return
    while not stopped.is_set():
        if manual_sync_pending.is_set():
            if stopped.wait(interval_seconds):
                break
            continue
        with maintenance_network_lock:
            cycle_failed = False
            record_event("system", "started", action="scheduled_refresh",
                         status="running")
            if refresh_wisesheets:
                try:
                    from .wisesheets_local import refresh_local_wisesheets
                    refresh_local_wisesheets()
                except Exception:
                    cycle_failed = True
                    record_event("earnings", "collector_failed", level="warning",
                                 action="scheduled_refresh", reason="provider_failed")
                    log.warning("Local Wisesheets refresh cycle failed; retaining previous aggregate")
            try:
                macro_failures = refresh_all(
                    engine, stopped=scheduled_stop, skip_complete_pinned=True)
                if macro_failures:
                    cycle_failed = True
                    record_event("macro", "stage_finished", level="warning",
                                 action="scheduled_refresh", status="partial",
                                 failed=macro_failures)
                    log.warning("%d macro sources failed; retained last successful observations",
                                macro_failures)
                if include_markets and not scheduled_stop.is_set():
                    market_failures = refresh_market_all(engine, stopped=scheduled_stop)
                    if market_failures:
                        cycle_failed = True
                        record_event("markets", "stage_finished", level="warning",
                                     action="scheduled_refresh", status="partial",
                                     failed=market_failures)
                        log.warning("%d market/FX sources failed; retained last successful observations",
                                    market_failures)
            except Exception:
                cycle_failed = True
                record_event("system", "collector_failed", level="error",
                             action="scheduled_refresh", reason="internal_error")
                # A malformed provider response must not terminate the API or
                # silently kill refresh. Do not log URLs containing API keys.
                log.error("Background refresh cycle aborted (error redacted); preserving previous data")
            if enabled("FINANCE_VINTAGE_REFRESH", "1") and not scheduled_stop.is_set():
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
                except Exception:
                    cycle_failed = True
                    record_event("alfred", "collector_failed", level="warning",
                                 action="scheduled_refresh", reason="provider_failed")
                    log.warning("ALFRED month-end capture failed; source API credentials redacted")
            if enabled("FINANCE_SEC_HOLDINGS_REFRESH", "0") and not scheduled_stop.is_set():
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
                except Exception:
                    cycle_failed = True
                    record_event("sec", "collector_failed", level="warning",
                                 action="scheduled_refresh", reason="provider_failed")
                    log.warning("SEC N-PORT collection failed; preserving verified historical filings")
            if enabled("FINANCE_AUTO_BACKUP", "1") and not scheduled_stop.is_set():
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
                except Exception:
                    cycle_failed = True
                    record_event("backup", "collector_failed", level="error",
                                 action="scheduled_refresh", reason="backup_failed")
                    log.warning("SQLite online backup failed; latest verified backups retained")
            interrupted = manual_sync_pending.is_set()
            record_event("system", "finished",
                         level="warning" if cycle_failed or interrupted else "info",
                         action="scheduled_refresh",
                         status=("interrupted" if interrupted else
                                 "partial" if cycle_failed else "complete"))
            _save_schedule_due(time.time() + interval_seconds)
        # A complete scheduled cycle can also update vintage, SEC or other
        # original evidence outside IngestionService.refresh. Notify one
        # downstream reconciliation for those native archive changes.
        from .data_change_bus import publish_change
        publish_change(engine, "scheduled_cycle_finished")
        if stopped.wait(interval_seconds):
            break


@asynccontextmanager
async def standalone_lifespan(app: FastAPI, *, engine: Engine) -> AsyncIterator[None]:
    if not enabled("FINANCE_AUTO_REFRESH"):
        yield
        return
    interval_seconds = refresh_interval()
    include_markets = enabled("FINANCE_INCLUDE_MARKETS")
    refresh_wisesheets = enabled("FINANCE_WISESHEETS_REFRESH", "1")
    stopped = Event()
    thread = Thread(target=refresh_loop, name="finance-macro-refresh",
                    args=(engine, stopped),
                    kwargs={"interval_seconds": interval_seconds,
                            "include_markets": include_markets,
                            "refresh_wisesheets": refresh_wisesheets}, daemon=True)
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
