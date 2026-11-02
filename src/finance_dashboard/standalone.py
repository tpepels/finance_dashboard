"""One-process home-server mode: API, built UI, persistent DB and periodic refresh.

No scheduler daemon, supervisor, Redis or separate worker container is needed.
The existing refresh adapters run in a background thread of the same process,
with the same transactional source and ingestion semantics as the normal worker.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from os import environ
from pathlib import Path
from threading import Event, Thread
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)


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


def refresh_loop(engine: Engine, stopped: Event, *, interval_seconds: int,
                 include_markets: bool, refresh_wisesheets: bool = True) -> None:
    # Import the already tested source adapters only when refresh is enabled.
    from .worker import refresh_all, refresh_market_all

    while not stopped.is_set():
        if refresh_wisesheets:
            try:
                from .wisesheets_local import refresh_local_wisesheets
                refresh_local_wisesheets()
            except Exception:
                log.warning("Local Wisesheets refresh cycle failed; retaining previous aggregate")
        try:
            macro_failures = refresh_all(engine)
            if macro_failures:
                log.warning("%d macro sources failed; retained last successful observations",
                            macro_failures)
            if include_markets and not stopped.is_set():
                market_failures = refresh_market_all(engine)
                if market_failures:
                    log.warning("%d market/FX sources failed; retained last successful observations",
                                market_failures)
        except Exception:
            # A malformed provider response must not terminate the API or
            # silently kill refresh. Do not log URLs containing API keys.
            log.error("Background refresh cycle aborted (error redacted); preserving previous data")
        if enabled("FINANCE_AUTO_BACKUP", "1") and not stopped.is_set():
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
                log.warning("SQLite online backup failed; latest verified backups retained")
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
