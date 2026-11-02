"""Local, quota-aware Wisesheets SEC earnings refresh in the existing API process.

This replaces GitHub Actions and GitHub snapshot downloading. The full
accessible SEC filing universe is collected only on a monthly schedule, not
on every container restart, page request, or daily macro refresh.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import tempfile

from .wisesheets import WisesheetsClient, collect_wisesheets, load_sec_profit_snapshot

log = logging.getLogger(__name__)
COLLECT_EVERY = timedelta(days=30)
FAILED_RETRY_AFTER = timedelta(hours=24)


def target_path() -> Path:
    return Path(os.environ.get("WISESHEETS_SNAPSHOT_PATH", "/data/wisesheets/sec_filer_profit.json"))


def metadata_path(target: Path) -> Path:
    return target.with_suffix(".refresh.json")


def _read_attempt(path: Path) -> tuple[datetime | None, bool]:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        when = datetime.fromisoformat(record["at"])
        if when.tzinfo is None:
            return None, False
        return when.astimezone(timezone.utc), record.get("success") is True
    except (OSError, TypeError, ValueError, KeyError):
        return None, False


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         prefix=".finance-", suffix=".tmp",
                                         dir=path.parent, delete=False) as stream:
            stream.write(text)
            tmp = Path(stream.name)
        os.replace(tmp, path)
        tmp = None
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def refresh_local_wisesheets(*, now: datetime | None = None,
                             destination: Path | None = None) -> str:
    """Return disabled, current, deferred, updated or failed; never expose key.

    A failed attempt is persisted before the network request to prevent a
    container crash/restart from spending the same monthly budget twice.
    """
    if not os.environ.get("WISESHEETS_API_KEY"):
        return "disabled"
    now = now or datetime.now(timezone.utc)
    target = destination or target_path()
    record = metadata_path(target)
    last_attempt, last_success = _read_attempt(record)
    existing = load_sec_profit_snapshot(target)

    # A preexisting successful snapshot may have been imported from another
    # deployment. Honor its timestamp to prevent a needless entire scan.
    if existing is not None:
        last_collected = datetime.fromisoformat(existing["source_snapshot_at_utc"])
        if now - last_collected < COLLECT_EVERY:
            return "current"
    if last_attempt is not None:
        retry = COLLECT_EVERY if last_success else FAILED_RETRY_AFTER
        if now - last_attempt < retry:
            return "deferred"

    _atomic_write(record, json.dumps({"at": now.isoformat(), "success": False}) + "\n")
    client = None
    try:
        client = WisesheetsClient()
        # Keep the provider's full-universe and account quota/rate safety
        # requirements; they are correctness and cost protections.
        snapshot = collect_wisesheets(client, min_issuers=5000, max_requests=800)
        _atomic_write(target, json.dumps(snapshot, sort_keys=True, indent=2) + "\n")
        # Reader provides an independent payload validation before claiming success.
        if load_sec_profit_snapshot(target) is None:
            raise RuntimeError("Local Wisesheets aggregate did not validate")
        _atomic_write(record, json.dumps({"at": now.isoformat(), "success": True}) + "\n")
        log.info("Local SEC earnings refresh completed: %s verified years", len(snapshot["observations"]))
        return "updated"
    except Exception:
        # No authenticated URL, response body, account information or
        # provider exception is written to logs or the result.
        log.warning("Local SEC earnings refresh failed; keeping last valid snapshot")
        return "failed"
    finally:
        if client is not None:
            client.close()
