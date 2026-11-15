"""Durable, bounded, redacted exception provenance across dashboard releases.

Never store exception messages, repr(), arbitrary file paths, local variables,
SQL, HTTP URLs, credentials, cookies or provider responses.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import fcntl
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile

SCHEMA_VERSION = 1
MAX_RECORDS = 64
MAX_BYTES = 192_000
_TOKEN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.:+-]{0,119}$")
_CODE = re.compile(r"^[A-Za-z0-9_]{1,32}$")
_DEPS = ("sqlalchemy.", "httpx.", "httpcore.", "sqlite3", "psycopg.",
         "psycopg2.", "threading.", "asyncio.")


def _path() -> Path:
    from .developer_logs import _path as events_path
    return Path(os.environ.get("FINANCE_FAILURE_JOURNAL_PATH",
                               str(events_path().parent / "failure-journal.json")))


def _token(value, fallback="unavailable"):
    return value if isinstance(value, str) and _TOKEN.fullmatch(value) else fallback


def _trace(error: BaseException) -> list[dict]:
    frames = []
    tb = error.__traceback__
    while tb is not None:
        frame = tb.tb_frame
        module = frame.f_globals.get("__name__")
        if not isinstance(module, str) or not (
                module == "finance_dashboard" or module.startswith("finance_dashboard.")
                or any(module == prefix.rstrip(".") or module.startswith(prefix)
                       for prefix in _DEPS)):
            module = "external"
        frames.append({"module": _token(module),
                       "function": _token(frame.f_code.co_name),
                       "line": max(0, min(tb.tb_lineno, 1_000_000))})
        tb = tb.tb_next
    app = [f for f in frames if f["module"].startswith("finance_dashboard.")]
    last = frames[-8:]
    result = []
    for frame in [*app[-16:], *last]:
        if frame not in result:
            result.append(frame)
    return result[-16:]


def _codes(error: BaseException) -> dict:
    result = {}
    original = getattr(error, "orig", None)
    db_error = original if isinstance(original, BaseException) else error
    for attr, output in (("sqlite_errorname", "sqlite_errorname"),
                         ("sqlstate", "sqlstate"), ("pgcode", "sqlstate")):
        value = getattr(db_error, attr, None)
        if isinstance(value, str) and _CODE.fullmatch(value):
            result[output] = value
    code = getattr(error, "code", None)
    if isinstance(code, str) and _CODE.fullmatch(code):
        result["library_code"] = code
    status = getattr(getattr(error, "response", None), "status_code", None)
    if type(status) is int and 100 <= status <= 599:
        result["http_status"] = status
    return result


def _causes(error: BaseException) -> list[str]:
    names = []
    seen = {id(error)}
    current = error.__cause__ or error.__context__
    while isinstance(current, BaseException) and id(current) not in seen and len(names) < 3:
        names.append(_token(type(current).__name__))
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    original = getattr(error, "orig", None)
    if isinstance(original, BaseException):
        name = _token(type(original).__name__)
        if name not in names:
            names.append(name)
    return names[:4]


def _load(path: Path) -> tuple[str, list[dict]]:
    try:
        if path.is_symlink():
            return "invalid", []
        if not path.exists():
            return "not_created", []
        if path.stat().st_size > MAX_BYTES:
            return "invalid", []
        data = json.loads(path.read_bytes())
        if (not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION
                or not isinstance(data.get("failures"), list)
                or len(data["failures"]) > MAX_RECORDS):
            return "invalid", []
        clean = []
        for row in data["failures"]:
            if not isinstance(row, dict):
                return "invalid", []
            fields = ("id", "component", "stage", "exception_type", "release_id")
            if any(not isinstance(row.get(key), str) or not _TOKEN.fullmatch(row[key])
                   for key in fields):
                return "invalid", []
            for key in ("first_at", "last_at"):
                timestamp = datetime.fromisoformat(row[key])
                if timestamp.tzinfo is None:
                    return "invalid", []
            if type(row.get("count")) is not int or row["count"] < 1:
                return "invalid", []
            frames = row.get("frames")
            if not isinstance(frames, list) or len(frames) > 16:
                return "invalid", []
            for f in frames:
                if (not isinstance(f, dict)
                        or not _TOKEN.fullmatch(str(f.get("module", "")))
                        or not _TOKEN.fullmatch(str(f.get("function", "")))
                        or type(f.get("line")) is not int
                        or not 0 <= f["line"] <= 1_000_000):
                    return "invalid", []
            samples = row.get("example_series_ids", [])
            if (not isinstance(samples, list) or len(samples) > 8
                    or any(not isinstance(s, str) or not _TOKEN.fullmatch(s)
                           for s in samples)):
                return "invalid", []
            causes = row.get("causes", [])
            if (not isinstance(causes, list) or len(causes) > 4
                    or any(not isinstance(s, str) or not _TOKEN.fullmatch(s)
                           for s in causes)):
                return "invalid", []
            codes = row.get("codes", {})
            if not isinstance(codes, dict):
                return "invalid", []
            validated_codes = {}
            for key in ("sqlite_errorname", "sqlstate", "library_code"):
                value = codes.get(key)
                if isinstance(value, str) and _CODE.fullmatch(value):
                    validated_codes[key] = value
            http = codes.get("http_status")
            if type(http) is int and 100 <= http <= 599:
                validated_codes["http_status"] = http
            clean.append({
                **{key: row[key] for key in fields},
                "first_at": row["first_at"], "last_at": row["last_at"],
                "count": row["count"],
                "frames": [{key: f[key] for key in ("module", "function", "line")}
                           for f in frames],
                "causes": causes, "codes": validated_codes,
                "example_series_ids": samples,
            })
        return "ready", clean
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return "invalid", []


def read_failures() -> dict:
    """Expose only validated, redacted records, including previous builds."""
    state, entries = _load(_path())
    return {"schema_version": SCHEMA_VERSION, "state": state,
            "persistent_across_releases": True, "failures": entries}


def _write(path: Path, records: list[dict]) -> None:
    if path.is_symlink():
        raise OSError("failure_journal_symlink_refused")
    tmp = None
    try:
        payload = json.dumps({"schema_version": SCHEMA_VERSION, "failures": records},
                             separators=(",", ":"), sort_keys=True).encode()
        if len(payload) > MAX_BYTES:
            raise OSError("failure_journal_over_limit")
        with NamedTemporaryFile(mode="wb", dir=path.parent, prefix=".failures-",
                                delete=False) as stream:
            tmp = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
        tmp = None
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def record_failure(component: str, stage: str, error: BaseException,
                   *, series_id: str | None = None) -> dict:
    """Archive a safe error signature; return persistence state explicitly."""
    from .runtime_release import release_info
    now = datetime.now(timezone.utc).isoformat()
    try:
        release = _token(release_info()["release_id"])
    except (OSError, ValueError, KeyError, TypeError):
        release = "unavailable"
    component, stage = _token(component), _token(stage)
    frames = _trace(error)
    origin = next((f for f in reversed(frames)
                   if f["module"].startswith("finance_dashboard.")),
                  frames[-1] if frames else
                  {"module": "external", "function": "unavailable", "line": 0})
    codes, causes = _codes(error), _causes(error)
    exception_type = _token(type(error).__name__)
    fingerprint = sha256(json.dumps(
        [component, stage, exception_type, causes, origin, codes],
        sort_keys=True).encode()).hexdigest()[:20]
    entry = {
        "id": fingerprint, "release_id": release,
        "component": component, "stage": stage,
        "exception_type": exception_type, "frames": frames,
        "first_at": now, "last_at": now, "count": 1,
        "causes": causes, "codes": codes, "example_series_ids": [],
    }
    if series_id is not None and _token(series_id) != "unavailable":
        entry["example_series_ids"] = [series_id]
    path = _path()
    persisted = False
    try:
        if path.parent.is_symlink():
            raise OSError("failure_journal_directory_symlink")
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path.with_name(path.name + ".lock"),
                     os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            state, previous = _load(path)
            if state == "invalid":
                raise OSError("failure_journal_corrupt")
            found = next((old for old in previous
                          if old["id"] == fingerprint and old["release_id"] == release),
                         None)
            if found:
                found["last_at"] = now
                found["count"] += 1
                for sid in entry["example_series_ids"]:
                    if sid not in found["example_series_ids"]:
                        found["example_series_ids"] = [
                            *found["example_series_ids"], sid][:8]
                previous.remove(found)
                previous.append(found)
            else:
                previous.append(entry)
            _write(path, previous[-MAX_RECORDS:])
            persisted = True
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
    except (OSError, ValueError, TypeError):
        persisted = False
    return {"id": fingerprint, "component": component, "stage": stage,
            "exception_type": exception_type, "persisted": persisted,
            "at": now}
