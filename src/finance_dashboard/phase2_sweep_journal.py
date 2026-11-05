"""Crash-safe, append-only attempt journal for an explicit Phase 2 acquisition sweep.

This journal is only operational scheduling history. A recorded success does NOT
certify original publisher values, observation vintages or research readiness.
Source evidence and release histories remain the authority. Every source is
marked started before its first network request, so a crash cannot silently
repeat an unknown in-flight publisher request after resumption.
"""
from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime, timezone
from hashlib import sha256
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile

from .source_capture import canonical_bytes


_ID = re.compile(r"[A-Za-z0-9_.:-]{1,160}\Z")
_HASH = re.compile(r"[a-f0-9]{64}\Z")
_SAFE_REASON = re.compile(r"[a-z0-9_]{1,100}\Z")
MAX_EVENT_BYTES = 8_192
MAX_CONTEXT_BYTES = 128_000


def _check_ancestors(path: Path) -> None:
    target = Path(path).absolute()
    if any(part.is_symlink() for part in (target, *target.parents)):
        raise ValueError("sweep_journal_symlink_forbidden")


def _write_once(target: Path, record: dict) -> None:
    """Fully flush a file before linking its immutable final name."""
    raw = canonical_bytes(record)
    limit = MAX_CONTEXT_BYTES if target.name == "context.json" else MAX_EVENT_BYTES
    if len(raw) > limit:
        raise ValueError("sweep_event_oversized")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="wb", dir=target.parent, prefix=".event-",
                delete=False) as writer:
            temporary = Path(writer.name)
            writer.write(raw)
            writer.flush()
            os.fsync(writer.fileno())
        os.link(temporary, target)
        directory = os.open(str(target.parent), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _read_json(path: Path) -> dict:
    limit = MAX_CONTEXT_BYTES if path.name == "context.json" else MAX_EVENT_BYTES
    if (path.is_symlink() or not path.is_file()
            or path.stat().st_size > limit):
        raise ValueError("sweep_event_invalid")
    raw = path.read_bytes()
    try:
        data = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("sweep_event_invalid_json") from exc
    if not isinstance(data, dict) or canonical_bytes(data) != raw:
        raise ValueError("sweep_event_noncanonical")
    return data


class Phase2SweepJournal(AbstractContextManager):
    """Single-writer, immutable per-source start/end events.

    create=True creates a new state directory and refuses existing state.
    create=False validates all prior events, including any unresolved starts,
    before allowing another attempt. Concurrent writers fail before any
    callbacks can issue HTTP requests.
    """

    def __init__(self, path: Path, *, context: dict, create: bool):
        self.root = Path(path).absolute()
        self.context = context
        self.create = create
        self._lock_fd = None
        self._state: dict[str, dict] = {}

    def __enter__(self):
        _check_ancestors(self.root)
        if self.create:
            self.root.parent.mkdir(parents=True, exist_ok=True)
            self.root.mkdir(mode=0o700)
            (self.root / "events").mkdir()
        elif not self.root.is_dir() or not (self.root / "events").is_dir():
            raise ValueError("sweep_journal_missing")
        if (not isinstance(self.context, dict)
                or self.context.get("schema_version") != 1
                or not isinstance(self.context.get("source_ids"), list)):
            raise ValueError("sweep_context_invalid")
        lock = self.root / ".lock"
        if lock.is_symlink():
            raise ValueError("sweep_journal_lock_symlink")
        fd = os.open(str(lock), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError("sweep_journal_already_running") from exc
            self._lock_fd = fd
            if self.create:
                _write_once(self.root / "context.json", self.context)
            if _read_json(self.root / "context.json") != self.context:
                raise ValueError("sweep_context_changed")
            self._validate_events()
            return self
        except BaseException:
            if self._lock_fd is not None:
                self._lock_fd = None
            os.close(fd)
            raise

    def __exit__(self, exc_type, exc, tb):
        if self._lock_fd is not None:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
            os.close(self._lock_fd)
            self._lock_fd = None
        return False

    @staticmethod
    def _stem(sid: str) -> str:
        if not isinstance(sid, str) or not _ID.fullmatch(sid):
            raise ValueError("invalid_canonical_sweep_source_id")
        return sha256(sid.encode("utf-8")).hexdigest()

    def _validate_events(self):
        folder = self.root / "events"
        if folder.is_symlink():
            raise ValueError("sweep_events_symlink_forbidden")
        files = sorted(folder.iterdir())
        starts, results = {}, {}
        for entry in files:
            if (entry.is_symlink() or not entry.is_file()
                    or not re.fullmatch(r"[0-9a-f]{64}\.(start|result)\.json", entry.name)):
                raise ValueError("sweep_unexpected_event")
            payload = _read_json(entry)
            sid = payload.get("source_id")
            stem = self._stem(sid)
            kind = entry.name.split(".")[1]
            if (stem != entry.name.split(".")[0] or payload.get("schema_version") != 1
                    or sid not in self.context["source_ids"]
                    or payload.get("kind") != kind
                    or not isinstance(payload.get("at_utc"), str)):
                raise ValueError("sweep_event_identity_mismatch")
            try:
                at = datetime.fromisoformat(payload["at_utc"])
            except ValueError as exc:
                raise ValueError("sweep_event_timestamp_invalid") from exc
            if at.tzinfo is None:
                raise ValueError("sweep_event_timestamp_timezone_missing")
            table = starts if kind == "start" else results
            table[sid] = payload
        for sid, result in results.items():
            start = starts.get(sid)
            if (start is None
                    or result.get("start_sha256") != sha256(canonical_bytes(start)).hexdigest()
                    or result.get("status") not in {"success", "failed"}
                    or not _SAFE_REASON.fullmatch(result.get("reason") or "none")
                    or type(result.get("received")) is not int
                    or type(result.get("versions_added")) is not int
                    or not 0 <= result["received"] <= 10**9
                    or not 0 <= result["versions_added"] <= 10**9):

                raise ValueError("sweep_result_integrity_invalid")
        self._state = {
            sid: {"status": "started_without_result" if sid not in results
                  else results[sid]["status"],
                  "reason": results.get(sid, {}).get("reason"),
                  "received": results.get(sid, {}).get("received"),
                  "versions_added": results.get(sid, {}).get("versions_added")}
            for sid in starts
        }

    def already_attempted(self, sid: str) -> dict | None:
        return self._state.get(sid)

    def mark_started(self, sid: str):
        if self._lock_fd is None or sid not in self.context["source_ids"]:
            raise ValueError("sweep_journal_not_authorized")
        if sid in self._state:
            raise ValueError("sweep_source_already_attempted")
        _write_once(self.root / "events" / (self._stem(sid) + ".start.json"), {
            "schema_version": 1, "kind": "start", "source_id": sid,
            "at_utc": datetime.now(timezone.utc).isoformat(),
        })
        self._state[sid] = {"status": "started_without_result"}

    def mark_result(self, sid: str, *, status: str, reason: str = "none",
                    received: int = 0, versions_added: int = 0):
        if self._lock_fd is None or sid not in self._state:
            raise ValueError("sweep_journal_not_started")
        if (self._state[sid]["status"] != "started_without_result"
                or status not in {"success", "failed"}
                or not _SAFE_REASON.fullmatch(reason)
                or type(received) is not int or not 0 <= received <= 10**9
                or type(versions_added) is not int
                or not 0 <= versions_added <= 10**9):
            raise ValueError("sweep_journal_invalid_result")
        source = self.root / "events" / (self._stem(sid) + ".start.json")
        _write_once(self.root / "events" / (self._stem(sid) + ".result.json"), {
            "schema_version": 1, "kind": "result", "source_id": sid,
            "at_utc": datetime.now(timezone.utc).isoformat(),
            "start_sha256": sha256(source.read_bytes()).hexdigest(),
            "status": status, "reason": reason,
            "received": received, "versions_added": versions_added,
        })
        self._state[sid] = {
            "status": status, "reason": reason,
            "received": received, "versions_added": versions_added,
        }

    def summary(self) -> dict:
        states = {state: sum(item["status"] == state
                             for item in self._state.values())
                  for state in ("success", "failed", "started_without_result")}
        return {
            "journal_path": str(self.root),
            "tracked_attempts": len(self._state),
            "attempt_statuses": states,
            "inflight_requires_review": sorted(
                sid for sid, item in self._state.items()
                if item["status"] == "started_without_result"),
            "success_is_not_original_verification": True,
            "no_automatic_failed_or_inflight_retries": True,
        }


def sweep_context(source_ids: list[str], policy_registry_sha256: str,
                  approved_contract_sha256: str) -> dict:
    """Unchanging authorization boundary; evidence status is evaluated afresh."""
    unique = sorted(set(source_ids))
    if len(unique) != len(source_ids) or any(not _ID.fullmatch(s) for s in unique):
        raise ValueError("sweep_canonical_source_ids_invalid")
    if (not _HASH.fullmatch(policy_registry_sha256)
            or not _HASH.fullmatch(approved_contract_sha256)):
        raise ValueError("sweep_contract_sha256_invalid")
    return {
        "schema_version": 1,
        "source_ids": unique,
        "publisher_policy_sha256": policy_registry_sha256,
        "approved_research_contract_sha256": approved_contract_sha256,
        "scientific_certification": False,
    }
