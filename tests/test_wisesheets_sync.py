"""Wisesheets GitHub aggregate sync: no provider API calls, no secret transfer."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import httpx
from sqlalchemy import create_engine

from finance_dashboard.api import create_app
from finance_dashboard.wisesheets import load_sec_profit_snapshot, WisesheetsError
from finance_dashboard.wisesheets_sync import (
    VERIFIED_AGGREGATE_URL, sync_wisesheets_snapshot, MAX_SNAPSHOT_BYTES,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def sample_snapshot(*, days_ago=0):
    payload = json.loads((REPO_ROOT / "data/wisesheets/sec_filer_profit.json").read_text())
    payload["source_snapshot_at_utc"] = (
        datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return payload


class WisesheetsSyncTests(unittest.TestCase):
    def test_remote_aggregate_atomically_installed_without_auth_headers(self):
        seen = []
        snapshot = sample_snapshot()
        def handler(request):
            seen.append(request)
            return httpx.Response(200, json=snapshot)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "wisesheets/sec_filer_profit.json"
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                self.assertTrue(sync_wisesheets_snapshot(destination=target, client=client))
            self.assertEqual(len(seen), 1)
            self.assertEqual(str(seen[0].url), VERIFIED_AGGREGATE_URL)
            self.assertIsNone(seen[0].headers.get("authorization"))
            self.assertNotIn("WISESHEETS_API_KEY", str(seen[0].url))
            self.assertEqual(load_sec_profit_snapshot(target)["id"],
                             "profit.us_sec_filers.world_gdp_share")
            self.assertEqual(len(list(target.parent.glob(".wisesheets-*"))), 0)
            with patch.dict("os.environ", {"WISESHEETS_SNAPSHOT_PATH": str(target)}):
                with TestClient(create_app(create_engine("sqlite+pysqlite:///:memory:"))) as web:
                    res = web.get("/api/earnings/sec-filers")
                    self.assertEqual(res.status_code, 200)
                    self.assertEqual(len(res.json()["observations"]), 5)

    def test_old_and_malformed_remote_data_never_replace_last_good(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "snapshot.json"
            original = sample_snapshot()
            target.write_text(json.dumps(original), encoding="utf-8")
            original_bytes = target.read_bytes()
            older = sample_snapshot(days_ago=10)
            for response in (
                httpx.Response(200, json=older),
                httpx.Response(503, text="Unreachable"),
                httpx.Response(200, text="not json"),
                httpx.Response(200, content=b"!" * (MAX_SNAPSHOT_BYTES + 1)),
                httpx.Response(200, json={"id": "forged"}),
            ):
                with self.subTest(status=response.status_code, body=len(response.content)):
                    with httpx.Client(transport=httpx.MockTransport(lambda request: response)) as client:
                        if response.status_code == 200 and "source_snapshot_at_utc" in response.text:
                            self.assertFalse(sync_wisesheets_snapshot(destination=target, client=client))
                        else:
                            with self.assertRaises(WisesheetsError):
                                sync_wisesheets_snapshot(destination=target, client=client)
                    self.assertEqual(target.read_bytes(), original_bytes)

    def test_bundled_snapshot_works_without_local_key_or_git_fetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "never-created.json"
            with patch.dict("os.environ", {"WISESHEETS_SNAPSHOT_PATH": str(missing),
                                           "WISESHEETS_API_KEY": ""}):
                snapshot = load_sec_profit_snapshot()
                self.assertIsNotNone(snapshot)
                self.assertEqual(len(snapshot["observations"]), 5)
                self.assertIn(snapshot["snapshot_status"], {"current", "stale"})


if __name__ == "__main__":
    unittest.main()
