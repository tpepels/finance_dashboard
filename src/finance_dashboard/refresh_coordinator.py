"""Single cross-process source-ingestion lock for macro, FX and market refresh.

PostgreSQL uses its existing advisory lock identity. SQLite uses an OS file
lock adjacent to the actual database. This complements the API's in-process
maintenance lock, which coordinates backups and non-ingestion operations.
"""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import tempfile
from typing import Iterator

from sqlalchemy import text

POSTGRES_REFRESH_LOCK_ID = 75390812


def refresh_lock_path(engine) -> Path:
    """Derive a stable lock identity; never store a lock inside source evidence."""
    database = engine.url.database
    if database and database != ":memory:":
        location = Path(database).expanduser().resolve()
        return location.with_name(location.name + ".refresh.lock")
    # In-memory databases exist only for isolated tests and ephemeral CLI work.
    return Path(tempfile.gettempdir()) / "global-capital-monitor-memory-refresh.lock"


@contextmanager
def reserve_refresh(engine) -> Iterator[bool]:
    """Yield whether the caller owns the single global ingestion lock.

    Never wait indefinitely or steal a lock from another refresh process.
    The file descriptor/PG connection lifetime holds ownership reliably even
    if collection raises. No historical/source evidence file is modified.
    """
    if engine.dialect.name == "postgresql":
        with engine.connect() as connection:
            acquired = bool(connection.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {"lock_id": POSTGRES_REFRESH_LOCK_ID}).scalar())
            try:
                yield acquired
            finally:
                if acquired:
                    connection.execute(
                        text("SELECT pg_advisory_unlock(:lock_id)"),
                        {"lock_id": POSTGRES_REFRESH_LOCK_ID})
        return

    if engine.dialect.name != "sqlite":
        raise RuntimeError("Global ingestion lock requires SQLite or PostgreSQL")

    path = refresh_lock_path(engine)
    path.parent.mkdir(parents=True, exist_ok=True)
    # O_NOFOLLOW blocks a symlink substitution at the lock-file boundary.
    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
                 0o600)
    acquired = False
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except BlockingIOError:
            pass
        yield acquired
    finally:
        if acquired:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
