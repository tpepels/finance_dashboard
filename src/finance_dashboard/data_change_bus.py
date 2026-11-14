"""Coalesced, in-process post-commit evidence notifications.

Publisher ingestion, imported originals and automatic refresh all publish into
one small fan-out. No network requests or DB scans occur in publisher commits,
and concurrent apps/test engines never receive each other's notifications.
"""
from __future__ import annotations

from datetime import datetime, timezone
from threading import Event, Lock, Thread
from time import monotonic
from weakref import WeakKeyDictionary, WeakSet

_listeners = WeakKeyDictionary()
_listeners_lock = Lock()


def subscribe(engine, listener) -> None:
    with _listeners_lock:
        listeners = _listeners.get(engine)
        if listeners is None:
            listeners = WeakSet()
            _listeners[engine] = listeners
        listeners.add(listener)


def publish_change(engine, reason: str = "source_ingested") -> None:
    """Publish after commit (never inside the DB transaction)."""
    with _listeners_lock:
        listeners = list(_listeners.get(engine, ()))
    for listener in listeners:
        try:
            listener.changed(reason)
        except Exception:
            # The source transaction has already committed. A broken optional
            # subscriber must never turn a successful import into a false
            # failed IngestionRun or roll back accepted observations.
            from .developer_logs import record_event
            record_event("system", "collector_failed", level="warning",
                         stage="post_ingestion", reason="post_ingestion_event_failed")


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class DataChangeCoordinator:
    """One debounced post-ingestion task for all changes in one application.

    Invalidates scientific acceptance and starts a fresh coverage scan after
    a burst of commits. A later commit in the same burst postpones the work,
    but never cancels it. The acceptance cache handles changes during a running
    evaluation separately.
    """

    def __init__(self, acceptance, health, *, quiet_seconds: float = 1.0):
        self.acceptance, self.health = acceptance, health
        self.quiet_seconds = quiet_seconds
        self.lock = Lock()
        self.event = Event()
        self.thread: Thread | None = None
        self.revision = 0
        self.completed_revision = 0
        self.last_change_monotonic = 0.0
        self.last_change_at: str | None = None
        self.last_reconciled_at: str | None = None
        self.last_reason: str | None = None
        self.last_error: str | None = None
        self.runs = 0

    def changed(self, reason: str = "original_imported") -> None:
        with self.lock:
            self.revision += 1
            self.last_change_at = _utc()
            self.last_change_monotonic = monotonic()
            self.last_reason = reason
            self.event.set()
            if self.thread is None or not self.thread.is_alive():
                self.thread = Thread(target=self._drain,
                                     name="gcm-post-ingestion", daemon=True)
                self.thread.start()

    def _drain(self) -> None:
        while True:
            with self.lock:
                revision = self.revision
                if revision == self.completed_revision:
                    self.event.clear()
                    self.thread = None
                    return
                quiet_until = self.last_change_monotonic + self.quiet_seconds
                self.event.clear()
            wait = max(0, quiet_until - monotonic())
            if wait and self.event.wait(wait):
                continue
            with self.lock:
                if revision != self.revision:
                    continue
            # A scheduled source refresh or manual maintenance can hold one
            # canonical network/ingestion lock for its entire batch. Avoid a
            # competing full scientific census against that moving corpus.
            from .standalone import maintenance_network_lock
            if maintenance_network_lock.locked():
                self.event.wait(1)
                continue
            try:
                self.acceptance.invalidate()
                self.health.mark_dirty()
                error = None
            except Exception:
                error = "post_ingestion_reconciliation_failed"
            with self.lock:
                self.completed_revision = revision
                self.last_error = error
                self.last_reconciled_at = _utc()
                self.runs += 1

    def status(self) -> dict:
        with self.lock:
            return {
                "state": "pending" if self.completed_revision < self.revision
                         else "failed" if self.last_error else
                         "complete" if self.runs else "idle",
                "last_change_at": self.last_change_at,
                "last_reconciled_at": self.last_reconciled_at,
                "last_reason": self.last_reason,
                "events_seen": self.revision, "events_reconciled": self.completed_revision,
                "batches": self.runs, "error": self.last_error,
            }
