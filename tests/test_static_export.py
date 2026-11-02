"""Offline static export tests: completeness, quality, and secret non-disclosure."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from finance_dashboard.bis import FetchedSeries
from finance_dashboard.static_export import export_static
from finance_dashboard.providers import ProviderRouter


class FakeRouter:
    should_fail = False

    def fetch(self, series_id, start=None):
        if self.should_fail and series_id == "bond.us.real_10y":
            raise RuntimeError("api_key=TOP_SECRET_SHOULD_NOT_LEAK")
        return FetchedSeries(
            series_id, "https://provider.invalid/?api_key=TOP_SECRET_SHOULD_NOT_LEAK",
            None, {date(2025, 1, 1): Decimal("2.500")},
        )

    def close(self):
        pass


class StaticExportTests(unittest.TestCase):
    def test_safe_manifest_and_series_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "output"
            with patch.dict(os.environ, {"FRED_API_KEY": "TOP_SECRET_SHOULD_NOT_LEAK"}):
                result = export_static(
                    root, series_ids=["policy_rate.us.fed_upper", "bond.us.real_10y"],
                    provider_factory=FakeRouter, max_workers=2, include_markets=False,
                )
            self.assertEqual(result["series_count"], 2)
            self.assertEqual(
                [v["id"] for v in result["series"]],
                ["bond.us.real_10y", "policy_rate.us.fed_upper"],
            )
            self.assertEqual(len(result["unresolved"]), 0)
            for path in root.rglob("*.json"):
                output = path.read_text()
                self.assertNotIn("TOP_SECRET_SHOULD_NOT_LEAK", output)
                self.assertNotIn("api_key=", output)
                json.loads(output)
            series = json.loads((root / "series" / "bond.us.real_10y.json").read_text())
            self.assertEqual(series["observations"], [{"date": "2025-01-01", "value": "2.500"}])
            self.assertEqual(series["frequency"], "D")
            self.assertEqual(series["source_key"], "DFII10")
            self.assertTrue((root / "charts.json").exists())

    def test_saved_sec_aggregate_is_exported_separately_from_original_global_profit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"sec_filer_profit.json"
            path.write_text(json.dumps({
                "schema_version":1,
                "id":"profit.us_sec_filers.world_gdp_share",
                "status":"partial_us_sec_reporter_coverage",
                "currency":"USD",
                "source_snapshot_at_utc":datetime.now(timezone.utc).isoformat(),
                "description":"SEC-reporting companies, NOT global.",
                "observations":[{
                    "year":2024,"world_gdp_usd":"100",
                    "sec_filer_net_income_usd":"4.5",
                    "sec_filer_income_as_pct_of_world_gdp":"4.5",
                }],
            }))
            root=Path(tmp)/"result"
            manifest=export_static(root,series_ids=["bond.us.real_10y"],
                provider_factory=FakeRouter,include_markets=False,sec_snapshot_path=path)
            self.assertEqual(manifest["supplementary_sources"][0]["status"],
                             "partial_us_sec_reporter_coverage")
            self.assertEqual(manifest["unresolved"], [])
            self.assertNotIn("profit.global.corporate_share",
                             [row["id"] for row in manifest["series"]])
            exported=json.loads((root/"supplementary"/"sec_filer_profit.json").read_text())
            self.assertEqual(exported["observations"][0]["year"],2024)
            self.assertEqual(exported["snapshot_status"],"current")

    def test_failed_source_cannot_overwrite_previous_good_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            root.mkdir()
            (root / "index.json").write_text('{"previous":"good"}')
            FakeRouter.should_fail = True
            try:
                with self.assertRaisesRegex(RuntimeError, "Static export failed"):
                    export_static(root, series_ids=["bond.us.real_10y"],
                                  provider_factory=FakeRouter, max_workers=1, include_markets=False)
                self.assertEqual((root / "index.json").read_text(), '{"previous":"good"}')
                self.assertEqual(list(root.iterdir()), [root / "index.json"])
            finally:
                FakeRouter.should_fail = False

    def test_unresolved_series_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "Unsupported or unresolved series"):
                export_static(Path(directory) / "data",
                              series_ids=["profit.global.corporate_share"],
                              provider_factory=FakeRouter, include_markets=False)

    def test_authenticated_fred_request_uses_key_but_returns_public_source_url(self):
        def handler(request):
            self.assertEqual(request.url.params.get("api_key"), "SENSITIVE_TEST_KEY")
            self.assertEqual(request.url.params["file_type"], "json")
            return httpx.Response(200, json={"observations": [
                {"date": "2025-01-01", "value": "2.0"},
                {"date": "2025-01-02", "value": "2.1"},
            ]})
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            provider = ProviderRouter(client=client)
            with patch.dict(os.environ, {"FRED_API_KEY": "SENSITIVE_TEST_KEY"}):
                record = provider.fetch("bond.us.real_10y", start=date(2025, 1, 1))
            self.assertNotIn("SENSITIVE_TEST_KEY", record.request_url)
            self.assertEqual(len(record.observations), 2)


if __name__ == "__main__":
    unittest.main()
