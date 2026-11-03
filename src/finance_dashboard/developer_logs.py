"""Private, bounded diagnostic timeline for the browser developer panel.

Only explicitly typed, constrained fields are written. Never capture an
exception string, provider response body, HTTP URL, credentials or headers.
The journal is small and persists inside the existing /data/maintenance volume.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from threading import Lock

MAX_EVENTS = 400
MAX_FILE_BYTES = 1_000_000
_LOCK = Lock()
_TOKEN = re.compile(r"^[A-Za-z0-9_.:-]{1,100}$")
_SCOPES = frozenset(("sync", "macro", "markets", "fx", "alfred",
                     "sec", "earnings", "backup", "system"))
_EVENTS = frozenset(("queued", "started", "finished", "stage_finished",
                     "source_failed", "collector_failed", "cancel_requested",
                     "scheduled_warning"))
_LEVELS = frozenset(("info", "warning", "error"))
_STATUSES = frozenset(("queued", "waiting", "running", "complete", "partial",
                       "failed", "blocked", "cancelled", "interrupted", "skipped"))


def _path() -> Path:
    state = Path(os.environ.get("FINANCE_MAINTENANCE_STATE",
                               "/data/maintenance/jobs.json"))
    return Path(os.environ.get("FINANCE_DIAGNOSTICS_PATH",
                               str(state.parent / "diagnostics.jsonl")))


def _token(value: object) -> str | None:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        return None
    return value


def _nonnegative(value: object) -> int | None:
    if type(value) is int and 0 <= value <= 10_000_000:
        return value
    return None


def _sanitize(item: object) -> dict | None:
    if not isinstance(item, dict):
        return None
    level, scope, event = item.get("level"), item.get("scope"), item.get("event")
    if level not in _LEVELS or scope not in _SCOPES or event not in _EVENTS:
        return None
    timestamp = item.get("at")
    if not isinstance(timestamp, str) or len(timestamp) > 40:
        return None
    try:
        datetime.fromisoformat(timestamp)
    except ValueError:
        return None
    out = {"at": timestamp, "level": level, "scope": scope, "event": event}
    for key in ("action", "source_id", "job_id", "stage", "reason"):
        token = _token(item.get(key))
        if token is not None:
            out[key] = token
    status = item.get("status")
    if status in _STATUSES:
        out["status"] = status
    for key in ("completed", "total", "failed"):
        value = _nonnegative(item.get(key))
        if value is not None:
            out[key] = value
    http_status = item.get("http_status")
    if type(http_status) is int and 100 <= http_status <= 599:
        out["http_status"] = http_status
    return out


def read_events(*, limit: int = 200) -> list[dict]:
    """Return only validated safe fields, newest at the end."""
    limit = max(1, min(MAX_EVENTS, int(limit)))
    path = _path()
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return []
        lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    except (OSError, UnicodeError):
        return []
    events = []
    for line in lines:
        try:
            item = _sanitize(json.loads(line))
        except (ValueError, TypeError):
            continue
        if item is not None:
            events.append(item)
    return events


def record_event(scope: str, event: str, *, level: str = "info",
                 action: str | None = None, job_id: str | None = None,
                 source_id: str | None = None, stage: str | None = None,
                 status: str | None = None, reason: str | None = None,
                 completed: int | None = None, total: int | None = None,
                 failed: int | None = None, http_status: int | None = None) -> None:
    """Best-effort journal write, never allowed to break data ingestion.

    Deliberately no free-form message or exception parameter.
    """
    data = _sanitize({
        "at": datetime.now(timezone.utc).isoformat(),
        "scope": scope, "event": event, "level": level,
        "action": action, "job_id": job_id, "source_id": source_id,
        "stage": stage, "status": status, "reason": reason,
        "completed": completed, "total": total,
        "failed": failed, "http_status": http_status,
    })
    if data is None:
        return
    with _LOCK:
        path = _path()
        temp: Path | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            existing = read_events(limit=MAX_EVENTS-1)
            with NamedTemporaryFile(
                mode="w", encoding="utf-8", prefix=".diagnostics-",
                suffix=".tmp", dir=path.parent, delete=False,
            ) as stream:
                temp = Path(stream.name)
                for item in [*existing, data][-MAX_EVENTS:]:
                    stream.write(json.dumps(item, separators=(",", ":")) + "\n")
            os.chmod(temp, 0o600)
            os.replace(temp, path)
            temp = None
        except (OSError, ValueError, TypeError):
            # Diagnostics are best-effort; imports must keep running.
            pass
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)


def recent_jobs(jobs: list[dict]) -> list[dict]:
    """Drop stored maintenance parameters and any unknown provider payload."""
    output = []
    for job in jobs[:8]:
        if not isinstance(job, dict):
            continue
        entry: dict = {}
        for key in ("id", "action", "status"):
            token = _token(job.get(key))
            if token:
                entry[key] = token
        for key in ("created_at", "finished_at"):
            when = job.get(key)
            if isinstance(when, str) and len(when) <= 40:
                try:
                    datetime.fromisoformat(when)
                except ValueError:
                    continue
                entry[key] = when
        for key in ("completed", "total"):
            number = _nonnegative(job.get(key))
            if number is not None:
                entry[key] = number
        result = job.get("result")
        if isinstance(result, dict):
            parts = result.get("parts")
            if isinstance(parts, dict):
                safe_parts = {}
                for key, value in parts.items():
                    if key not in ("macro", "markets", "earnings", "alfred", "sec", "backup"):
                        continue
                    if not isinstance(value, dict):
                        continue
                    safe = {}
                    for field in ("status", "reason", "first_failed_series",
                                  "first_failed_asof"):
                        token = _token(value.get(field))
                        if token:
                            safe[field] = token
                    for field in ("failed", "missing", "downloaded", "sources", "http_status"):
                        number = _nonnegative(value.get(field))
                        if number is not None:
                            safe[field] = number
                    if isinstance(value.get("funds"), list):
                        safe["funds"] = []
                        for fund in value["funds"][:10]:
                            if not isinstance(fund, dict):
                                continue
                            row = {}
                            for field in ("id", "status", "reason"):
                                token = _token(fund.get(field))
                                if token:
                                    row[field] = token
                            for field in ("stored", "errors", "http_status"):
                                number = _nonnegative(fund.get(field))
                                if number is not None:
                                    row[field] = number
                            safe["funds"].append(row)
                    safe_parts[key] = safe
                entry["parts"] = safe_parts
        if entry:
            output.append(entry)
    return output
