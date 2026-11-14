"""Durable operator collection sessions with non-blocking status reads.

A collection owns one orchestration identity. The existing publisher queue
and maintenance executor remain responsible for the work; this layer reads
their durable journals without running SQL in its status request path.
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

from .runtime_release import release_info


def _path(env: str, name: str) -> Path:
    root = Path(os.environ.get("FINANCE_MAINTENANCE_STATE", "/data/maintenance/jobs.json")).parent
    return Path(os.environ.get(env, str(root / name)))


def _read_json(path: Path, max_bytes: int = 1_000_000) -> dict | None:
    try:
        if path.is_symlink() or path.stat().st_size > max_bytes:
            return None
        document = json.loads(path.read_text(encoding="utf-8"))
        return document if isinstance(document, dict) else None
    except (OSError, ValueError, UnicodeError):
        return None


def _write_json(path: Path, document: dict) -> None:
    if path.is_symlink():
        raise ValueError("Data collection journal cannot be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8",
                                prefix=".collection-", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(document, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


_TERMINAL = {"complete", "partial", "failed", "interrupted", "manual_required", "skipped"}
_ACTIVE = {"queued", "downloading", "running", "deferred", "waiting", "cancelling"}


class CollectionWorkflow:
    def __init__(self, manual, maintenance, *, valid_sources: set[str],
                 valid_markets: set[str], path: Path | None = None):
        self.manual, self.maintenance = manual, maintenance
        self.valid_sources, self.valid_markets = valid_sources, valid_markets
        self.path = path or _path("FINANCE_DATA_COLLECTION_STATE", "data-collection.json")
        self.lock = Lock()
        self._repair_worker: Thread | None = None
        saved = _read_json(self.path)
        self.current = saved if saved and saved.get("schema_version") == 1 else None
        if self.current and self.current.get("phase") == "starting":
            # An interrupted orchestration cannot remain 'starting' forever
            # across restarts. Recover jobs that were queued before the crash.
            with self.manual.lock:
                recent = list(reversed(self.manual.jobs))
            for entry in self.current.get("entries", []):
                if entry.get("job_id"):
                    continue
                job = next((item for item in recent
                            if item.get("dataset") == entry.get("dataset")
                            and item.get("created_at", "") >=
                                self.current.get("started_at", "~")), None)
                if job:
                    entry["job_id"] = job["id"]
                else:
                    entry["initial"] = "skipped"
                    entry["reason"] = "collection_start_interrupted"
            self.current["phase"] = "failed"
            self.current["startup_error"] = "collection_start_interrupted"
            if not self.current.get("maintenance_job_id"):
                self.current["maintenance_initial"] = "interrupted"
            _write_json(self.path, self.current)
        if (self.current and self.current.get("maintenance_initial") == "waiting"
                and not self.current.get("maintenance_job_id")
                and self.current.get("phase") == "started"):
            self._ensure_repair_worker()

    def _ensure_repair_worker(self):
        """Deferred repair remains durable while unrelated maintenance is busy."""
        if self._repair_worker is None or not self._repair_worker.is_alive():
            current_id = self.current["id"]
            self._repair_worker = Thread(
                target=self._retry_repair, args=(current_id,),
                daemon=True, name="gcm-collection-repair")
            self._repair_worker.start()

    def _retry_repair(self, collection_id: str):
        from .maintenance import BusyMaintenance
        while True:
            with self.lock:
                record = self.current
                if (record is None or record["id"] != collection_id
                        or record.get("maintenance_job_id")
                        or record.get("phase") != "started"):
                    return
            try:
                job = self.maintenance.submit(
                    "repair_source_health", {},
                    valid_sources=self.valid_sources, valid_markets=self.valid_markets)
            except BusyMaintenance:
                time.sleep(2)
                continue
            except Exception:
                with self.lock:
                    if self.current and self.current["id"] == collection_id:
                        self.current["startup_error"] = "source_repair_submission_failed"
                        self.current["maintenance_initial"] = "failed"
                        _write_json(self.path, self.current)
                return
            with self.lock:
                if self.current and self.current["id"] == collection_id:
                    self.current["maintenance_job_id"] = job["id"]
                    self.current["maintenance_initial"] = job["status"]
                    _write_json(self.path, self.current)
            return

    def start(self, browser: dict | None = None) -> dict:
        from .manual_sources import source_specs
        from .maintenance import BusyMaintenance
        from .publisher_downloads import safe_browser_profile

        with self.lock:
            if self.current is not None and self._status_unlocked()["running"]:
                return self._status_unlocked()

            specs = source_specs()
            record = {
                "schema_version": 1, "id": uuid4().hex,
                "started_at": _utc(), "release": release_info()["release_id"],
                "phase": "starting", "entries": [
                    {"dataset": name, "label": spec["title"],
                     "manual_roles": [dict(r) for r in spec.get("manual_files", spec["roles"])],
                     "job_id": None, "initial": "queued"}
                    for name, spec in specs.items()],
                "maintenance_job_id": None, "maintenance_initial": "queued",
                "startup_error": None,
            }
            self.current = record
            _write_json(self.path, record)
            try:
                queued = self.manual.fetch(browser=safe_browser_profile(browser))
                assignments = {item["dataset"]: item["job_id"] for item in queued["jobs"]}
                # An outstanding human-upload job belongs in the new run;
                # skipping it would hide its actionable fallback links.
                with self.manual.lock:
                    for job in reversed(self.manual.jobs):
                        if (job["dataset"] not in assignments and
                                job["status"] == "manual_required"):
                            assignments[job["dataset"]] = job["id"]
                for row in record["entries"]:
                    row["job_id"] = assignments.get(row["dataset"])
                    if row["job_id"] is None:
                        row["initial"] = "skipped"
                        row["reason"] = queued["skipped"].get(row["dataset"], "not_scheduled")
                _write_json(self.path, record)
                try:
                    job = self.maintenance.submit(
                        "repair_source_health", {},
                        valid_sources=self.valid_sources, valid_markets=self.valid_markets)
                    record["maintenance_job_id"] = job["id"]
                    record["maintenance_initial"] = job["status"]
                except BusyMaintenance:
                    record["maintenance_initial"] = "waiting"
                record["phase"] = "started"
            except Exception:
                record["phase"] = "failed"
                record["startup_error"] = "collection_start_failed"
                if not record.get("maintenance_job_id"):
                    record["maintenance_initial"] = "failed"
                with self.manual.lock:
                    recent = list(reversed(self.manual.jobs))
                for row in record["entries"]:
                    if row.get("job_id"):
                        continue
                    job = next((item for item in recent
                                if item.get("dataset") == row["dataset"]
                                and item.get("created_at", "") >= record["started_at"]), None)
                    if job:
                        row["job_id"] = job["id"]
                    else:
                        row["initial"] = "skipped"
                        row["reason"] = "collection_start_failed"
            _write_json(self.path, record)
            if (record["phase"] == "started" and
                    record["maintenance_initial"] == "waiting"):
                self._ensure_repair_worker()
            return self._status_unlocked()

    def status(self) -> dict:
        with self.lock:
            return self._status_unlocked()

    def _status_unlocked(self) -> dict:
        # Never call manual.status(), original importer scans or SQL here.
        record = self.current
        if record is None:
            return {"id": None, "state": "idle", "running": False,
                    "started_at": None, "counts": {"total": 0, "finished": 0,
                    "completed": 0, "skipped": 0, "active": 0, "failed": 0,
                    "manual_required": 0}, "sources": [], "manual_files": [],
                    "repair": None, "startup_error": None, "release": release_info()}
        with self.manual.lock:
            ids = {row["job_id"] for row in record["entries"] if row["job_id"]}
            jobs = {item["id"]: item for item in self.manual.jobs if item["id"] in ids}
        operation = self.maintenance.list()
        repair = next((item for item in operation["jobs"]
                       if item.get("id") == record["maintenance_job_id"]), None)
        if repair is None and record["maintenance_job_id"]:
            repair = {"status": "interrupted", "completed": 0, "total": None}
        elif repair is None:
            repair = {"status": record["maintenance_initial"], "completed": 0, "total": None}

        sources, manual_files = [], []
        for entry in record["entries"]:
            job = jobs.get(entry["job_id"])
            status = (job.get("status", "interrupted") if job is not None
                      else "interrupted" if entry["job_id"] else entry["initial"])
            row = {"dataset": entry["dataset"], "label": entry["label"],
                   "status": status, "job_id": entry["job_id"],
                   "reason": job.get("error_code") if job else entry.get("reason"),
                   "phase": job.get("phase") if job else None,
                   "retry_at_unix": job.get("retry_at_unix") if job else None,
                   "completed_files": len(job.get("downloaded") or {}) if job else 0,
                   "attempted_files": len(job.get("attempts") or []) if job else 0,
                   "completed_sources": sum(i.get("status") == "success"
                                            for i in job.get("sources", [])) if job else 0}
            sources.append(row)
            if status == "manual_required" and job:
                roles = {item["id"]: item for item in entry["manual_roles"]}
                for role_id, reason in sorted(job.get("failed_roles", {}).items()):
                    role = roles.get(role_id)
                    if role is None:
                        continue
                    manual_files.append({
                        "job_id": job["id"], "dataset": entry["dataset"],
                        "source": entry["label"], "role": role_id,
                        "name": role["label"], "url": role["download_url"],
                        "reason": reason, "accept": role["accept"],
                        "max_bytes": role["max_bytes"],
                    })
        counts = {
            "total": len(sources),
            "finished": sum(row["status"] in _TERMINAL for row in sources),
            "completed": sum(row["status"] == "complete" for row in sources),
            "skipped": sum(row["status"] == "skipped" for row in sources),
            "active": sum(row["status"] in _ACTIVE for row in sources),
            "failed": sum(row["status"] in ("failed", "partial", "interrupted")
                          for row in sources),
            "manual_required": sum(row["status"] == "manual_required" for row in sources),
        }
        repair_running = repair["status"] in _ACTIVE
        running = (record["phase"] == "starting" or counts["active"] > 0 or repair_running)
        state = ("running" if running else
                 "failed" if record.get("startup_error") else
                 "needs_attention" if (counts["failed"] or counts["manual_required"] or
                     repair["status"] in ("failed", "partial", "blocked", "interrupted"))
                 else "complete")
        return {"id": record["id"], "state": state, "running": running,
                "started_at": record["started_at"], "release": release_info(),
                "counts": counts, "sources": sources, "manual_files": manual_files,
                "repair": {key: repair.get(key) for key in
                           ("status", "completed", "total", "stage", "current_item", "error_code")},
                "startup_error": record.get("startup_error")}


class SourceHealthCache:
    """Database-wide source coverage is always computed off the status path."""

    def __init__(self, build, *, path: Path | None = None):
        self.build = build
        self.path = path or _path("FINANCE_DATA_HEALTH_CACHE", "data-health.json")
        self.lock = Lock()
        self.cached = _read_json(self.path, max_bytes=16000)
        self.running = False
        self.last_attempt = 0.0
        self.last_error: str | None = None

    def status(self, *, refresh: bool = False) -> dict:
        with self.lock:
            now = time.time()
            try:
                age = now - float(self.cached.get("calculated_unix", 0)) if self.cached else float("inf")
            except (ValueError, TypeError):
                age = float("inf")
            # Recompute after a collection completes, but always off the
            # HTTP path. Manual requests cannot spawn unbounded workers.
            due = (refresh and now - self.last_attempt >= 5) or age > 60
            if not self.running and now - self.last_attempt >= (5 if refresh else 30) and due:
                self.running = True
                self.last_attempt = now
                Thread(target=self._rebuild, name="gcm-data-health", daemon=True).start()
            return {"state": "refreshing" if self.running else
                    "ready" if self.cached else "unavailable",
                    "snapshot": self.cached, "error": self.last_error}

    def _rebuild(self) -> None:
        try:
            summary = self.build()
            groups = []
            for key, title in (("macro", "Economic data"), ("markets", "Market prices"),
                               ("fx", "Exchange rates")):
                group = summary.get("summary", {}).get(key, {})
                groups.append({"id": key, "label": title,
                               "total": int(group.get("total", 0)),
                               "with_data": int(group.get("with_data", 0)),
                               "attention": int(group.get("needs_attention", 0))})
            snapshot = {"asof": summary.get("asof"),
                        "calculated_at": _utc(), "calculated_unix": time.time(),
                        "groups": groups,
                        "sources": {"total": sum(row["total"] for row in groups),
                                    "with_data": sum(row["with_data"] for row in groups),
                                    "needs_attention": sum(row["attention"] for row in groups)}}
            _write_json(self.path, snapshot)
            with self.lock:
                self.cached, self.last_error = snapshot, None
        except Exception:
            with self.lock:
                self.last_error = "source_coverage_unavailable"
        finally:
            with self.lock:
                self.running = False
