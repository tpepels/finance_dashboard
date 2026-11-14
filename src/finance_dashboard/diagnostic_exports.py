"""Asynchronous, durable, atomic diagnostic ZIP generation.

The expensive archive builder executes off the API request path. A ready ZIP
is an immutable snapshot and can be downloaded repeatedly without rebuilding.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock, Thread
from uuid import uuid4
import json
import os
import time

from .collection_workflow import _path, _read_json, _write_json
from .runtime_release import release_info


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DiagnosticExportManager:
    def __init__(self, build, *, zip_path: Path | None = None,
                 state_path: Path | None = None, lifetime: int = 900):
        self.build = build
        self.zip_path = zip_path or _path("FINANCE_DIAGNOSTIC_EXPORT_CACHE", "diagnostic-export.zip")
        self.state_path = state_path or _path("FINANCE_DIAGNOSTIC_EXPORT_STATE", "diagnostic-export.json")
        self.lifetime = lifetime
        self.lock = Lock()
        saved = _read_json(self.state_path, 4096)
        valid = saved and saved.get("schema_version") == 1 and (
            saved.get("release_id") == release_info()["release_id"])
        self.record = saved if valid else None
        if self.record and self.record["state"] == "preparing":
            self.record = {**self.record, "state": "interrupted",
                           "error": "preparation_interrupted_by_restart"}
            _write_json(self.state_path, self.record)
        if self.record and self.record["state"] == "ready" and not self._has_file():
            self.record = {**self.record, "state": "failed", "error": "cached_zip_missing"}
        self.worker: Thread | None = None

    def _has_file(self) -> bool:
        return (self.zip_path.is_file() and not self.zip_path.is_symlink()
                and 0 < self.zip_path.stat().st_size < 512_000_000)

    def _status_unlocked(self) -> dict:
        record = self.record
        if record is None:
            return {"state": "idle", "ready": False, "id": None,
                    "prepared_at": None, "size_bytes": None, "error": None}
        ready = record["state"] == "ready" and self._has_file()
        return {"state": record["state"], "ready": ready,
                "id": record.get("id"), "prepared_at": record.get("prepared_at"),
                "started_at": record.get("started_at"),
                "size_bytes": record.get("size_bytes"),
                "error": record.get("error")}

    def status(self) -> dict:
        with self.lock:
            return self._status_unlocked()

    def prepare(self) -> dict:
        with self.lock:
            if self.record and self.record["state"] == "preparing":
                return self._status_unlocked()
            if self.record and self.record["state"] == "ready" and self._has_file():
                prepared = self.record.get("prepared_unix", 0)
                if time.time() - prepared < self.lifetime:
                    return self._status_unlocked()
            self.record = {
                "schema_version": 1, "id": uuid4().hex,
                "release_id": release_info()["release_id"],
                "state": "preparing", "started_at": _now(), "prepared_at": None,
                "prepared_unix": None, "size_bytes": None, "error": None,
            }
            _write_json(self.state_path, self.record)
            self.worker = Thread(target=self._produce, name="gcm-diagnostic-export", daemon=True)
            self.worker.start()
            return self._status_unlocked()

    def _produce(self):
        temporary = None
        try:
            content = self.build()
            if not isinstance(content, bytes) or not content.startswith(b"PK\\x03\\x04"):
                raise ValueError("invalid_debug_archive")
            if not 0 < len(content) < 512_000_000:
                raise ValueError("debug_archive_size_invalid")
            self.zip_path.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(dir=self.zip_path.parent, prefix=".debug-export-",
                                    suffix=".part", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.zip_path)
            temporary = None
            with self.lock:
                self.record.update(state="ready", prepared_at=_now(),
                                   prepared_unix=time.time(), size_bytes=len(content))
                _write_json(self.state_path, self.record)
        except Exception:
            with self.lock:
                self.record.update(state="failed", error="diagnostic_export_failed")
                _write_json(self.state_path, self.record)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def ready_file(self) -> Path | None:
        with self.lock:
            return self.zip_path if self._status_unlocked()["ready"] else None
