"""Browser upload and background import into the existing immutable ICIO store.

Raw streaming requests avoid multipart buffering and a new dependency. Only exact
recognised archive names and the pinned ReadMe are accepted. The browser never
writes directly to source-evidence, SQLite or the publisher quota ledger.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from threading import Lock, Thread
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from .developer_logs import record_event
from .icio import PUBLISHER_ARCHIVES, import_original_archive
from .icio_editions import archive_identity

MAX_UPLOAD = 2 * 1024 ** 3
README = "ReadMe_ICIO_small.xlsx"
FILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.() -]{0,119}$")


def approved_file(name: str) -> bool:
    if not FILE_NAME.fullmatch(name) or name in (".", "..") or "/" in name:
        return False
    if name == README or name in PUBLISHER_ARCHIVES:
        return True
    try:
        archive_identity(name)
        return True
    except ValueError:
        return False


class ImportSelection(BaseModel):
    filenames: list[str] = Field(min_length=1, max_length=80)


class OriginalImportManager:
    def __init__(self, root: Path | None = None, evidence: Path | None = None):
        self.root = root or Path(os.environ.get(
            "FINANCE_ORIGINAL_UPLOAD_DIR", "/data/incoming/icio-2025"))
        self.evidence = evidence or Path(os.environ.get(
            "FINANCE_SOURCE_EVIDENCE_DIR", "/data/source-evidence"))
        self.journal = Path(os.environ.get(
            "FINANCE_ORIGINAL_IMPORT_JOURNAL", "/data/maintenance/original-imports.json"))
        self.lock = Lock()
        self.active = False
        self.jobs: list[dict] = []
        try:
            previous = json.loads(self.journal.read_text())
            if isinstance(previous.get("jobs"), list):
                self.jobs = previous["jobs"][-12:]
                for job in self.jobs:
                    if job.get("status") in ("queued", "running"):
                        job["status"] = "interrupted"
        except (OSError, ValueError, TypeError):
            pass

    def running(self) -> bool:
        with self.lock:
            return self.active

    def public_status(self) -> dict:
        with self.lock:
            jobs = json.loads(json.dumps(self.jobs[-12:]))
            active = self.active
        files = []
        if self.root.is_dir() and not self.root.is_symlink():
            for item in sorted(self.root.iterdir()):
                if approved_file(item.name) and item.is_file() and not item.is_symlink():
                    files.append({"filename": item.name, "bytes": item.stat().st_size,
                                  "kind": "readme" if item.name == README else
                                          "verified_regular" if item.name in PUBLISHER_ARCHIVES else
                                          "edition_archive"})
        return {"active": active, "files": files, "jobs": list(reversed(jobs))}

    def _save(self):
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        tmp = None
        try:
            with NamedTemporaryFile(mode="w", dir=self.journal.parent,
                                    prefix=".original-import-", delete=False) as out:
                tmp = Path(out.name)
                json.dump({"version": 1, "jobs": self.jobs[-12:]}, out)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.journal)
            tmp = None
        finally:
            if tmp is not None:
                tmp.unlink(missing_ok=True)

    def submit(self, filenames: list[str], accepted):
        if len(set(filenames)) != len(filenames) or any(
                not approved_file(n) or n == README for n in filenames):
            raise ValueError("Unrecognised or duplicate original archive")
        with self.lock:
            if self.active:
                raise RuntimeError("Original import already running")
            if not all((self.root / n).is_file() and not (self.root / n).is_symlink()
                       for n in filenames):
                raise ValueError("Upload the selected originals first")
            if any(n in PUBLISHER_ARCHIVES for n in filenames):
                if not (self.root / README).is_file():
                    raise ValueError("The publisher ReadMe workbook must be uploaded first")
            self.active = True
            job = {"id": uuid4().hex, "status": "queued", "created_at":
                   datetime.now(timezone.utc).isoformat(), "filenames": list(filenames),
                   "completed": 0, "total": len(filenames), "results": [], "error_code": None}
            self.jobs.append(job)
            self.jobs = self.jobs[-12:]
            self._save()
        Thread(target=self._run, args=(job["id"], accepted), daemon=True,
               name="finance-icio-original-import").start()
        return {"id": job["id"], "status": "queued"}

    def _run(self, job_id: str, accepted):
        record_event("sync", "started", action="import_originals", status="running")
        try:
            with self.lock:
                job = next(j for j in self.jobs if j["id"] == job_id)
                job["status"] = "running"
                names = list(job["filenames"])
                self._save()
            for filename in names:
                try:
                    result = import_original_archive(
                        self.root / filename, self.evidence,
                        self.root / README if (self.root / README).is_file() else None)
                    row = {"filename": filename, "status": result["status"],
                           "edition": result["edition"], "table": result["table"],
                           "archive_sha256": result.get("archive_sha256")}
                except Exception as exc:
                    code = str(exc)
                    if not re.fullmatch(r"icio_[a-z_]{1,90}", code):
                        code = "original_import_failed"
                    row = {"filename": filename, "status": "failed", "error_code": code}
                with self.lock:
                    job["results"].append(row)
                    job["completed"] += 1
                    self._save()
            failures = sum(r["status"] == "failed" for r in job["results"])
            with self.lock:
                job["status"] = "partial" if failures else "complete"
                job["error_code"] = "original_import_partial" if failures else None
                job["finished_at"] = datetime.now(timezone.utc).isoformat()
                self._save()
            if failures != len(names):
                accepted()
            record_event("sync", "finished", action="import_originals",
                         status="partial" if failures else "complete",
                         level="warning" if failures else "info",
                         failed=failures)
        except Exception:
            with self.lock:
                job = next(j for j in self.jobs if j["id"] == job_id)
                job["status"] = "failed"
                job["error_code"] = "original_import_internal_error"
                job["finished_at"] = datetime.now(timezone.utc).isoformat()
                self._save()
            record_event("sync", "collector_failed", action="import_originals",
                         reason="internal_error", level="error")
        finally:
            with self.lock:
                self.active = False


def _guard(request: Request, marker: str | None):
    if marker != "dashboard" or request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "Dashboard action required")
    origin = request.headers.get("origin")
    if origin:
        from urllib.parse import urlsplit
        parsed = urlsplit(origin)
        if parsed.scheme not in ("http", "https") or parsed.netloc != request.headers.get("host"):
            raise HTTPException(403, "Cross-origin upload rejected")


def install_original_uploads(app: FastAPI, importer: OriginalImportManager):
    @app.get("/api/originals")
    def originals():
        return importer.public_status()

    @app.post("/api/originals/upload", status_code=201)
    async def upload_original(request: Request, filename: str,
                              x_gcm_action: str | None = Header(default=None)):
        _guard(request, x_gcm_action)
        if not approved_file(filename):
            raise HTTPException(422, "Unsupported original filename")
        size_header = request.headers.get("content-length")
        if size_header and int(size_header) > MAX_UPLOAD:
            raise HTTPException(413, "Original exceeds upload limit")
        importer.root.mkdir(parents=True, exist_ok=True)
        if importer.root.is_symlink():
            raise HTTPException(422, "Upload directory invalid")
        target = importer.root / filename
        temporary = None
        total = 0
        digest = sha256()
        try:
            with NamedTemporaryFile(dir=importer.root, prefix=".upload-",
                                    suffix=".part", delete=False) as out:
                temporary = Path(out.name)
                async for chunk in request.stream():
                    total += len(chunk)
                    if total > MAX_UPLOAD:
                        raise HTTPException(413, "Original exceeds upload limit")
                    out.write(chunk)
                    digest.update(chunk)
            if total == 0 or (filename == README and total > 10 * 1024 * 1024):
                raise HTTPException(422, "Invalid original size")
            if target.is_symlink():
                raise HTTPException(409, "Destination is not a regular file")
            if target.exists():
                existing = sha256()
                with target.open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        existing.update(block)
                if existing.digest() != digest.digest():
                    raise HTTPException(409, "A different original already uses that filename")
                return {"filename": filename, "bytes": total, "sha256": digest.hexdigest(),
                        "already_present": True}
            # Hard-link is atomic and never overwrites a concurrent upload.
            try:
                os.link(temporary, target, follow_symlinks=False)
            except FileExistsError:
                raise HTTPException(409, "File was uploaded concurrently") from None
            return {"filename": filename, "bytes": total, "sha256": digest.hexdigest()}
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @app.post("/api/originals/import", status_code=202)
    def start_import(request: Request, selection: ImportSelection,
                     x_gcm_action: str | None = Header(default=None)):
        _guard(request, x_gcm_action)
        try:
            return importer.submit(selection.filenames, app.state.acceptance.invalidate)
        except RuntimeError:
            raise HTTPException(409, "Original import already running") from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
