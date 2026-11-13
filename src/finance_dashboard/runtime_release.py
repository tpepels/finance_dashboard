"""Deterministic application release IDs and safe release-scoped diagnostics.

A build ID is derived from the distributed Python code, compiled UI,
configuration definitions and migration code. The semantic package version
alone is not sufficient: it may remain 0.2.0 over multiple deployed builds.

Only the disposable structured event journal is cleared when a *different*
build is launched. Existing database, source evidence, backups, import
journals and scientific research reports are NEVER removed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile

_RELEASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,100}$")
_MAX_STATE_BYTES = 4096


def _version() -> str:
    try:
        return version("global-capital-monitor")
    except PackageNotFoundError:
        return "0.2.0"


def calculate_build(*, package_dir: Path | None = None,
                    application_root: Path | None = None) -> dict:
    """Hash the actual deployed program, including the compiled frontend.

    Hashes are stable across ordinary restarts and unaffected by data-volume
    changes, runtime clocks, filesystem modification times and Python caches.
    """
    pkg = package_dir or Path(__file__).resolve().parent
    app = application_root or Path(os.environ.get("FINANCE_DASHBOARD_ROOT", "/app"))
    digest = sha256()
    collections = [
        ("python", pkg, {".py"}),
        ("frontend", app / "site", None),
        ("definitions", app / "definitions", None),
        ("migrations", app / "migrations", {".py"}),
    ]
    for group, folder, extensions in collections:
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            if extensions is not None and path.suffix not in extensions:
                continue
            if "__pycache__" in path.parts or path.name.startswith("."):
                continue
            digest.update((group + "/" + path.relative_to(folder).as_posix() + "\0").encode())
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
    for name in ("pyproject.toml", "uv.lock", "start.sh", "alembic.ini"):
        path = app / name
        if path.is_file() and not path.is_symlink():
            digest.update((name + "\0").encode())
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
    build = digest.hexdigest()[:16]
    package_version = _version()
    return {"version": package_version, "build": build,
            "release_id": package_version + "+" + build}


def _build_manifest_path() -> Path:
    return Path(os.environ.get("FINANCE_RELEASE_MANIFEST", "/app/release.json"))


@lru_cache(maxsize=1)
def build_info() -> dict:
    """Read the immutable image manifest, with a source-tree fallback for dev."""
    manifest = _build_manifest_path()
    try:
        if manifest.is_symlink() or manifest.stat().st_size > _MAX_STATE_BYTES:
            raise ValueError("release_manifest_invalid")
        content = json.loads(manifest.read_text(encoding="utf-8"))
        if (content.get("schema_version") != 1 or
                not isinstance(content.get("version"), str) or
                not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[a-zA-Z0-9.+-]*)",
                                 content["version"]) or
                not isinstance(content.get("build"), str) or
                not re.fullmatch(r"[0-9a-f]{16}", content["build"]) or
                content.get("release_id") != content["version"] + "+" + content["build"]):
            raise ValueError("release_manifest_invalid")
        return {key: content[key] for key in ("version", "build", "release_id")}
    except FileNotFoundError:
        return calculate_build()


def _state_path() -> Path:
    from .developer_logs import _path
    return Path(os.environ.get("FINANCE_RELEASE_STATE_PATH",
                               str(_path().parent / "active-release.json")))


def _read_state(path: Path) -> dict | None:
    try:
        if path.is_symlink() or path.stat().st_size > _MAX_STATE_BYTES:
            raise ValueError("release_state_invalid")
        data = json.loads(path.read_text(encoding="utf-8"))
        if (data.get("schema_version") == 1 and
                isinstance(data.get("release_id"), str) and
                _RELEASE_ID.fullmatch(data["release_id"]) and
                isinstance(data.get("activated_at"), str)):
            datetime.fromisoformat(data["activated_at"])
            return data
    except (FileNotFoundError, ValueError, OSError, UnicodeError, TypeError):
        return None
    return None


def release_info() -> dict:
    """Every exported diagnostic references one explicit installed build."""
    build = build_info()
    state = _read_state(_state_path())
    return {**build, "activated_at": (
        state["activated_at"] if state and state["release_id"] == build["release_id"]
        else None)}


def job_in_current_release(created_at: object, *, active_since: str | None = None) -> bool:
    """Hide obsolete operational summaries without deleting their audit journal."""
    since = active_since if active_since is not None else release_info()["activated_at"]
    if since is None:
        return True
    if not isinstance(created_at, str):
        return False
    try:
        when = datetime.fromisoformat(created_at)
        cutoff = datetime.fromisoformat(since)
        return (when.tzinfo is not None and cutoff.tzinfo is not None
                and when >= cutoff)
    except ValueError:
        return False


def _write_private(path: Path, content: bytes) -> None:
    if path.is_symlink():
        raise ValueError("release_state_symlink_refused")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(dir=path.parent, prefix=".release-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def activate_release(*, identity: dict | None = None,
                     state_path: Path | None = None,
                     diagnostics_path: Path | None = None,
                     activated_at: str | None = None) -> dict:
    """Called once before the API and scheduler start (one process/volume).

    For a changed build, old event lines are atomically discarded. Job history
    persists on disk but is omitted from current-release diagnostic views.
    A routine process/container restart with the same build is idempotent.
    """
    from .developer_logs import _path
    release = dict(identity or build_info())
    if not isinstance(release.get("release_id"), str) or not _RELEASE_ID.fullmatch(release["release_id"]):
        raise ValueError("release_identity_invalid")
    state = state_path or _state_path()
    events = diagnostics_path or _path()
    previous = _read_state(state)
    if previous is not None and previous["release_id"] == release["release_id"]:
        return {**release, "activated_at": previous["activated_at"], "changed": False}
    timestamp = activated_at or datetime.now(timezone.utc).isoformat()
    dt = datetime.fromisoformat(timestamp)
    if dt.tzinfo is None:
        raise ValueError("release_time_must_be_aware")
    # Clear old events BEFORE writing the new release marker. If interrupted
    # between writes, a retry performs the reset again, never reuses stale logs.
    _write_private(events, b"")
    marker = {"schema_version": 1, "release_id": release["release_id"],
              "activated_at": timestamp}
    _write_private(state, (json.dumps(marker, sort_keys=True) + "\n").encode())
    return {**release, "activated_at": timestamp, "changed": True}


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "activate"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.action == "build":
        if args.output is None:
            parser.error("build requires --output")
        build = calculate_build()
        _write_private(args.output, (json.dumps({"schema_version": 1, **build},
                                                sort_keys=True) + "\n").encode())
        print(build["release_id"])
    else:
        print(json.dumps(activate_release(), sort_keys=True))


if __name__ == "__main__":
    main()
