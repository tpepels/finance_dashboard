"""Monthly Wisesheets collection runs inside one Docker process, no GitHub."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from finance_dashboard.wisesheets_local import (
    metadata_path, refresh_local_wisesheets, FAILED_RETRY_AFTER
)
from finance_dashboard.wisesheets import load_sec_profit_snapshot

DATA_FILE = Path(__file__).resolve().parents[1] / "data/wisesheets/sec_filer_profit.json"


class LocalWisesheetsTests(unittest.TestCase):
    def test_absent_key_disables_collection_without_any_api_request(self):
        with patch.dict(os.environ, {"WISESHEETS_API_KEY": ""}):
            with patch("finance_dashboard.wisesheets_local.WisesheetsClient") as client:
                self.assertEqual(refresh_local_wisesheets(), "disabled")
                client.assert_not_called()

    def test_collect_once_then_throttle_restarts_and_preserve_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "wisesheets/sec_filer_profit.json"
            now = datetime.now(timezone.utc)
            payload = json.loads(DATA_FILE.read_text())
            payload["source_snapshot_at_utc"] = now.isoformat()
            with patch.dict(os.environ, {"WISESHEETS_API_KEY": "local-secret"}):
                with patch("finance_dashboard.wisesheets_local.WisesheetsClient") as client, \
                    patch("finance_dashboard.wisesheets_local.collect_wisesheets", return_value=payload) as collector:
                    self.assertEqual(refresh_local_wisesheets(now=now, destination=dest), "updated")
                    self.assertTrue(metadata_path(dest).exists())
                    self.assertEqual(load_sec_profit_snapshot(dest)["id"],
                                     "profit.us_sec_filers.world_gdp_share")
                    self.assertEqual(refresh_local_wisesheets(now=now + timedelta(hours=1),
                                                              destination=dest), "current")
                    self.assertEqual(collector.call_count, 1)
                    self.assertEqual(client.return_value.close.call_count, 1)
            self.assertNotIn("local-secret", dest.read_text())
            self.assertNotIn("local-secret", metadata_path(dest).read_text())

    def test_failure_survives_container_restarts_and_obeys_retry_cooldown(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "earnings.json"
            now = datetime.now(timezone.utc)
            with patch.dict(os.environ, {"WISESHEETS_API_KEY": "local-secret"}):
                with patch("finance_dashboard.wisesheets_local.WisesheetsClient",
                           side_effect=RuntimeError("secret provider error")) as client:
                    self.assertEqual(refresh_local_wisesheets(now=now, destination=dest), "failed")
                    self.assertEqual(refresh_local_wisesheets(now=now + timedelta(days=1),
                                                              destination=dest), "deferred")
                    self.assertEqual(refresh_local_wisesheets(now=now + FAILED_RETRY_AFTER
                                                                  + timedelta(seconds=1),
                                                              destination=dest), "failed")
                    self.assertEqual(client.call_count, 2)
            self.assertFalse(dest.exists())
            self.assertNotIn("secret", metadata_path(dest).read_text())

if __name__ == "__main__":
    unittest.main()
