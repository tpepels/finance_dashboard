"""Independent saved figures, atomically persisted with optimistic revisions.

The API validates figure capabilities before calling this store. The store
validates its own durable envelope and record identity; a corrupt envelope is
never interpreted as an empty collection. A stable adjacent lock file covers
each complete read/modify/replace operation across threads and processes.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile
import threading
from uuid import UUID, uuid4


class SavedViewError(ValueError):
    """A saved-view request has invalid storage fields."""


class SavedViewConflict(SavedViewError):
    """Another editor has already changed the requested revision."""


class SavedViewNotFound(SavedViewError):
    """The requested saved figure no longer exists."""


class SavedViewUnavailable(SavedViewError):
    """The store cannot be safely read or written; preserve it for recovery."""


_PATH_LOCKS: dict[Path, threading.RLock] = {}
_PATH_LOCKS_GUARD = threading.Lock()
_RECORD_FIELDS = {"id", "name", "analysis_id", "figure_id", "spec", "method_version", "revision"}


def _text(value, field: str, *, maximum: int = 120) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise SavedViewError(f"{field} must be nonempty text of at most {maximum} characters")
    return value.strip()


def _analysis_id(value) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z][0-9]{2}", value):
        raise SavedViewError("analysis_id must be a canonical analysis identifier, such as C01")
    return value


def _view_id(value) -> str:
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError
    except ValueError:
        raise SavedViewError("saved-view id must be a canonical UUID") from None
    return value


def _revision(value) -> int:
    if type(value) is not int or value < 1:
        raise SavedViewError("revision must be a positive integer")
    return value


def _spec(value) -> dict:
    if not isinstance(value, dict):
        raise SavedViewError("spec must be a normalized figure object")
    figure = _text(value.get("figure_id"), "figure_id", maximum=1000)
    if figure != value["figure_id"]:
        raise SavedViewError("figure_id must not have surrounding whitespace")
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > 64:
            raise SavedViewError("spec exceeds the supported JSON nesting depth")
        if isinstance(item, dict):
            if any(not isinstance(key, str) for key in item):
                raise SavedViewError("spec object fields must be strings")
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
        elif item is not None and not isinstance(item, (str, bool, int, float)):
            raise SavedViewError("spec must contain finite JSON values")
    try:
        # This both detaches nested mutable values and refuses non-JSON values,
        # circular references, and NaN/infinity in otherwise validated specs.
        return json.loads(json.dumps(value, allow_nan=False))
    except (ValueError, TypeError, OverflowError, RecursionError):
        raise SavedViewError("spec must contain finite JSON values") from None


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object field")
        result[key] = value
    return result


def _nonfinite_constant(value):
    raise ValueError("nonfinite JSON number")


class SavedViewStore:
    def __init__(self, path: Path | None = None):
        selected = path if path is not None else Path(os.environ.get("FINANCE_SAVED_VIEWS", "/data/saved-views.json"))
        self.path = Path(selected).expanduser().resolve()
        self._lock_path = self.path.with_name(self.path.name + ".lock")
        with _PATH_LOCKS_GUARD:
            self._thread_lock = _PATH_LOCKS.setdefault(self.path, threading.RLock())

    @contextmanager
    def _locked(self, *, create: bool = False):
        with self._thread_lock:
            try:
                if not create and not self.path.parent.exists():
                    yield
                    return
                if create:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                with self._lock_path.open("a+b") as lock:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                    try:
                        yield
                    finally:
                        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            except OSError as exc:
                raise SavedViewUnavailable(f"Saved views at {self.path} could not be accessed: {exc}") from exc

    def _read(self) -> list[dict]:
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object,
                                  parse_constant=_nonfinite_constant)
            if (not isinstance(document, dict) or set(document) != {"version", "items"}
                    or type(document["version"]) is not int or document["version"] != 1
                    or not isinstance(document["items"], list)):
                raise ValueError("unsupported saved-view envelope")
            records, ids = [], set()
            for raw in document["items"]:
                if not isinstance(raw, dict) or set(raw) != _RECORD_FIELDS:
                    raise ValueError("malformed saved-view record")
                record = {"id": _view_id(raw["id"]), "name": _text(raw["name"], "name"),
                          "analysis_id": _analysis_id(raw["analysis_id"]), "spec": _spec(raw["spec"]),
                          "figure_id": raw["figure_id"], "method_version": _text(raw["method_version"], "method_version"),
                          "revision": _revision(raw["revision"])}
                if (record["id"] in ids or record["figure_id"] != record["spec"]["figure_id"]
                        or record != raw):
                    raise ValueError("duplicate or inconsistent saved-view record")
                ids.add(record["id"])
                records.append(record)
            return records
        except FileNotFoundError:
            return []
        except (OSError, ValueError, TypeError, UnicodeError, RecursionError) as exc:
            raise SavedViewUnavailable(
                f"Saved views at {self.path} are invalid or unreadable; preserve the file and repair or restore it: {exc}") from exc

    def _write(self, records: list[dict]) -> None:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent,
                                             prefix=f".{self.path.name}.", suffix=".tmp", delete=False) as handle:
                temporary = Path(handle.name)
                json.dump({"version": 1, "items": records}, handle, indent=2, allow_nan=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(self.path)
            directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def list(self) -> list[dict]:
        with self._locked():
            return copy.deepcopy(self._read())

    def create(self, name: str, analysis_id: str, spec: dict, method_version: str = "1") -> dict:
        clean_spec = _spec(spec)
        record = {"id": str(uuid4()), "name": _text(name, "name"), "analysis_id": _analysis_id(analysis_id),
                  "figure_id": clean_spec["figure_id"], "spec": clean_spec,
                  "method_version": _text(method_version, "method_version"), "revision": 1}
        with self._locked(create=True):
            records = self._read()
            while any(item["id"] == record["id"] for item in records):
                record["id"] = str(uuid4())
            self._write([*records, record])
        return copy.deepcopy(record)

    @staticmethod
    def _find(records: list[dict], view_id: str, revision: int) -> dict:
        record = next((item for item in records if item["id"] == view_id), None)
        if record is None:
            raise SavedViewNotFound("This saved figure no longer exists; reload the saved figures")
        if record["revision"] != revision:
            raise SavedViewConflict("This saved figure changed in another editor; reload it before saving or deleting")
        return record

    def update(self, view_id: str, name: str, spec: dict, revision: int, method_version: str = "1") -> dict:
        view_id, revision = _view_id(view_id), _revision(revision)
        name, clean_spec = _text(name, "name"), _spec(spec)
        method_version = _text(method_version, "method_version")
        with self._locked():
            records = self._read()
            record = self._find(records, view_id, revision)
            record.update(name=name, spec=clean_spec, figure_id=clean_spec["figure_id"],
                          method_version=method_version, revision=revision + 1)
            self._write(records)
            return copy.deepcopy(record)

    def delete(self, view_id: str, revision: int) -> None:
        view_id, revision = _view_id(view_id), _revision(revision)
        with self._locked():
            records = self._read()
            self._find(records, view_id, revision)
            self._write([item for item in records if item["id"] != view_id])
