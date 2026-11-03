"""Consistent online SQLite/Wisesheets backup for the one-container local server.

SQLite WAL files must not be copied raw while the writer is active. Python's
sqlite3 backup uses SQLite's consistent online-backup API, validates the copy,
and installs it atomically. Backups under /data are *not* off-site backups.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tarfile
from tempfile import NamedTemporaryFile

from sqlalchemy.engine import make_url


def source_database_path() -> Path:
    value = os.environ.get("DATABASE_URL", "")
    if not value.startswith("sqlite"):
        raise ValueError("Local one-container backup requires SQLite DATABASE_URL")
    database = make_url(value).database
    if not database or database == ":memory:":
        raise ValueError("Persistent database filename required")
    return Path(database)


def _hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _temp_in(parent: Path, suffix: str) -> Path:
    with NamedTemporaryFile(prefix=".finance-backup-", suffix=suffix,
                            dir=parent, delete=False) as temp:
        return Path(temp.name)


def _valid_database(path: Path) -> None:
    with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)) as read:
        row = read.execute("PRAGMA integrity_check").fetchone()
        if row is None or row[0] != "ok":
            raise ValueError("SQLite backup failed integrity_check")


def backup_local(output_dir: Path, *, source_db: Path | None = None,
                 earnings_snapshot: Path | None = None,
                 keep: int = 14,
                 evidence_roots: dict[str, Path] | None = None) -> dict:
    """Return a verified backup manifest, deleting only older OWNED backups."""
    if keep < 1 or keep > 365:
        raise ValueError("Backup retention must be 1..365")
    source = source_db or source_database_path()
    if not source.is_file():
        raise ValueError("Database file not initialized")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    if evidence_roots is None:
        evidence_roots = {
            "vintages": Path(os.environ.get("FINANCE_VINTAGE_DIR", "/data/vintages")),
            "holdings": Path(os.environ.get("FINANCE_HOLDINGS_DIR", "/data/holdings")),
            "surplus": Path(os.environ.get("FINANCE_SURPLUS_DIR", "/data/surplus")),
            "maintenance": Path(os.environ.get(
                "FINANCE_MAINTENANCE_STATE", "/data/maintenance/jobs.json")).parent,
        }
    if set(evidence_roots) - {"vintages", "holdings", "surplus", "maintenance"}:
        raise ValueError("Unrecognized local evidence directory")
    # Microsecond suffix protects repeated manual runs and concurrent calls.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    prefix = "finance-" + stamp
    database_target = out / (prefix + ".sqlite3")
    manifest_path = out / (prefix + ".json")
    temporary_db = _temp_in(out, ".sqlite3")
    created = []
    try:
        with closing(sqlite3.connect(f"file:{source}?mode=ro", uri=True, timeout=30)) as original:
            with closing(sqlite3.connect(temporary_db, timeout=30)) as destination:
                original.backup(destination, pages=128, sleep=0.05)
        _valid_database(temporary_db)
        os.replace(temporary_db, database_target)
        created.append(database_target)
        manifest = {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "method": "SQLite sqlite3 backup API, integrity_check passed",
            "database": {
                "file": database_target.name,
                "bytes": database_target.stat().st_size,
                "sha256": _hash(database_target),
            },
            "earnings_snapshot": None,
            "evidence_archive": None,
            "note": ("Copy this bundle off-site. A backup kept only within the "
                     "same /data volume does not survive failure of that disk."),
        }
        if earnings_snapshot is not None and earnings_snapshot.is_file():
            snapshot_target = out / (prefix + ".sec-filer.json")
            temp_snapshot = _temp_in(out, ".json")
            try:
                # The existing writer installs whole snapshots via atomic rename.
                with earnings_snapshot.open("rb") as inp, temp_snapshot.open("wb") as dest:
                    shutil.copyfileobj(inp, dest)
                data = json.loads(temp_snapshot.read_text(encoding="utf-8"))
                if data.get("id") != "profit.us_sec_filers.world_gdp_share":
                    raise ValueError("Unexpected SEC filer snapshot identity")
                os.replace(temp_snapshot, snapshot_target)
                created.append(snapshot_target)
                manifest["earnings_snapshot"] = {
                    "file": snapshot_target.name,
                    "bytes": snapshot_target.stat().st_size,
                    "sha256": _hash(snapshot_target),
                    "collection_timestamp": data.get("source_snapshot_at_utc"),
                }
            finally:
                temp_snapshot.unlink(missing_ok=True)
        # Also back up source vintages, SEC N-PORT filings/mapping and imported
        # audited industry accounts. These live outside SQLite and were missing
        # from the earlier database-only backup implementation.
        archive_target = out / (prefix + ".evidence.tar.gz")
        temporary_archive = _temp_in(out, ".tar.gz")
        try:
            files = []
            for name, base in sorted(evidence_roots.items()):
                if not base.is_dir() or base.is_symlink():
                    continue
                for entry in sorted(base.rglob("*")):
                    if (not entry.is_file() or entry.is_symlink()
                        or entry.name.startswith(".")
                        or any(part.startswith(".") for part in entry.relative_to(base).parts)):
                        continue
                    files.append((entry, name + "/" + entry.relative_to(base).as_posix()))
            if files:
                with tarfile.open(temporary_archive, mode="w:gz") as archive:
                    for entry, archive_name in files:
                        archive.add(entry, arcname=archive_name, recursive=False)
                with tarfile.open(temporary_archive, mode="r:gz") as archive:
                    if len(archive.getmembers()) != len(files):
                        raise ValueError("Evidence archive file count mismatch")
                os.replace(temporary_archive, archive_target)
                created.append(archive_target)
                manifest["evidence_archive"] = {
                    "file": archive_target.name,
                    "bytes": archive_target.stat().st_size,
                    "sha256": _hash(archive_target),
                    "source_files": len(files),
                    "source_roots": sorted({archive_name.split("/")[0]
                                            for _, archive_name in files}),
                }
        finally:
            temporary_archive.unlink(missing_ok=True)
        temporary_manifest = _temp_in(out, ".json")
        try:
            temporary_manifest.write_text(json.dumps(manifest, indent=2) + "\n",
                                          encoding="utf-8")
            os.replace(temporary_manifest, manifest_path)
        finally:
            temporary_manifest.unlink(missing_ok=True)
        # Only prune verified bundles owned by this application, never raw user files.
        manifests = sorted(out.glob("finance-*.json"), reverse=True)
        manifests = [p for p in manifests if p.name.endswith("Z.json")
                     and p.is_file() and not p.is_symlink()]
        for outdated in manifests[keep:]:
            try:
                old = json.loads(outdated.read_text(encoding="utf-8"))
                for item in (old.get("database"), old.get("earnings_snapshot"),
                             old.get("evidence_archive")):
                    if not isinstance(item, dict):
                        continue
                    candidate = out / item.get("file", "")
                    if (candidate.parent == out and not candidate.is_symlink()
                        and candidate.name.startswith("finance-")
                        and (candidate.suffix in (".sqlite3", ".json")
                             or candidate.name.endswith(".evidence.tar.gz"))):
                        candidate.unlink(missing_ok=True)
                outdated.unlink(missing_ok=True)
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                # A malformed manifest must not destroy unrelated files.
                continue
        return manifest
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    finally:
        temporary_db.unlink(missing_ok=True)


def verify_manifest(path: Path) -> dict:
    """Verify a complete backup bundle without trusting paths in a manifest."""
    manifest_path = Path(path)
    contents = json.loads(manifest_path.read_text(encoding="utf-8"))
    for field in ("database", "earnings_snapshot", "evidence_archive"):
        record = contents.get(field)
        if record is None:
            if field == "database":
                raise ValueError("Missing backup database metadata")
            continue
        if not isinstance(record, dict) or not isinstance(record.get("file"), str):
            raise ValueError("Malformed backup bundle")
        filename = record["file"]
        valid_suffix = {
            "database": ".sqlite3",
            "earnings_snapshot": ".sec-filer.json",
            "evidence_archive": ".evidence.tar.gz",
        }[field]
        if (Path(filename).name != filename or not filename.startswith("finance-")
            or not filename.endswith(valid_suffix)):
            raise ValueError("Backup bundle file name invalid")
        file_path = manifest_path.parent / filename
        if not file_path.is_file() or file_path.is_symlink():
            raise ValueError("Missing or symbolic-link backup component")
        if _hash(file_path) != record.get("sha256"):
            raise ValueError("Backup SHA-256 mismatch")
        if field == "database":
            _valid_database(file_path)
        elif field == "earnings_snapshot":
            if json.loads(file_path.read_text(encoding="utf-8")).get("id") != (
                "profit.us_sec_filers.world_gdp_share"):
                raise ValueError("Invalid SEC backup identity")
        else:
            with tarfile.open(file_path, mode="r:gz") as archive:
                members = archive.getmembers()
                if len(members) != record.get("source_files"):
                    raise ValueError("Evidence backup member count mismatch")
                for member in members:
                    parts = Path(member.name).parts
                    if (not member.isfile() or len(parts) < 2 or
                        parts[0] not in {"vintages", "holdings", "surplus", "maintenance"} or
                        ".." in parts or member.name.startswith("/")):
                        raise ValueError("Unsafe or unexpected evidence backup member")
    return {
        "verified": True,
        "manifest": manifest_path.name,
        "components": [k for k in ("database", "earnings_snapshot", "evidence_archive")
                       if contents.get(k) is not None],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verified SQLite online backup")
    parser.add_argument("--output-dir", default="/data/backups")
    parser.add_argument("--keep", type=int, default=14)
    parser.add_argument("--verify-manifest", default=None,
                        help="Verify SHA-256 and integrity of an existing backup manifest")
    args = parser.parse_args()
    if args.verify_manifest:
        print(json.dumps(verify_manifest(Path(args.verify_manifest)), indent=2))
        return
    db = source_database_path()
    snapshot = Path(os.environ.get(
        "WISESHEETS_SNAPSHOT_PATH", "/data/wisesheets/sec_filer_profit.json"))
    manifest = backup_local(Path(args.output_dir), source_db=db,
                            earnings_snapshot=snapshot, keep=args.keep)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
