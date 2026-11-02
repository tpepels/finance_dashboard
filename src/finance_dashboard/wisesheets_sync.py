"""No-key synchronization of the existing *validated aggregate* from GitHub.

The Wisesheets API is queried only by the separate quota-bounded monthly
GitHub Actions collector. The home-server container never crawls companies
or spends an additional Wisesheets request; it reads the already committed
aggregate, and retains the last valid local snapshot when offline.
"""
from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import tempfile

import httpx

from .wisesheets import load_sec_profit_snapshot, WisesheetsError

# Fixed owned GitHub repository path; never supply provider token or an
# arbitrary user-defined URL to this downloader.
VERIFIED_AGGREGATE_URL = (
    "https://raw.githubusercontent.com/tpepels/finance_dashboard/"
    "main/data/wisesheets/sec_filer_profit.json"
)
MAX_SNAPSHOT_BYTES = 256_000


def snapshot_target() -> Path:
    return Path(os.environ.get(
        "WISESHEETS_SNAPSHOT_PATH", "/data/wisesheets/sec_filer_profit.json"))


def sync_wisesheets_snapshot(*, destination: Path | None = None,
                             client: httpx.Client | None = None) -> bool:
    """Install a newer verified aggregate atomically; never regress on failure.

    Returns True only when a newer, validated snapshot was installed.
    Source download must remain below 256 KB and is not an authenticated
    Wisesheets API call. Existing snapshots are not replaced with old/bad
    data, even when GitHub is temporarily unavailable.
    """
    target = Path(destination) if destination is not None else snapshot_target()
    existing = load_sec_profit_snapshot(target)
    own = client is None
    client = client or httpx.Client(timeout=12, follow_redirects=False)
    try:
        response = client.get(VERIFIED_AGGREGATE_URL,
                              headers={"Accept": "application/json"})
        if response.status_code != 200 or len(response.content) > MAX_SNAPSHOT_BYTES:
            raise WisesheetsError("Verified GitHub aggregate unavailable or oversized")
        try:
            raw = response.content.decode("utf-8")
            parsed = json.loads(raw)
        except (ValueError, UnicodeError):
            raise WisesheetsError("Verified aggregate is not JSON") from None
        if not isinstance(parsed, dict) or not isinstance(parsed.get("observations"), list):
            raise WisesheetsError("Incomplete GitHub SEC aggregate")
        if not (1 <= len(parsed["observations"]) <= 10):
            raise WisesheetsError("Unexpected SEC fiscal-year sample size")

        target.parent.mkdir(parents=True, exist_ok=True)
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", prefix=".wisesheets-",
                suffix=".json", dir=target.parent, delete=False
            ) as file:
                file.write(raw)
                tmp_path = Path(file.name)
            validated = load_sec_profit_snapshot(tmp_path)
            if validated is None:
                raise WisesheetsError("Downloaded Wisesheets aggregate did not validate")
            next_time = datetime.fromisoformat(validated["source_snapshot_at_utc"])
            if existing is not None:
                old_time = datetime.fromisoformat(existing["source_snapshot_at_utc"])
                if next_time <= old_time:
                    return False
            os.replace(tmp_path, target)
            tmp_path = None
            return True
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
    finally:
        if own:
            client.close()
