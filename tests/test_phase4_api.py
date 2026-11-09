"""Phase 4 source-validated API smoke with a clean local SQLite database."""
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import os
from unittest.mock import patch
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from finance_dashboard.api import create_app
from finance_dashboard.database import Base


class Phase4ApiTests(unittest.TestCase):
    def setUp(self):
        self.sources = TemporaryDirectory()
        self.addCleanup(self.sources.cleanup)
        self.source_root = Path(self.sources.name)
        self.engine = create_engine("sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.env = patch.dict(os.environ, {
            "FINANCE_AUTO_REFRESH": "0",
            "FINANCE_INCLUDE_MARKETS": "0",
            "FINANCE_AUTO_BACKUP": "0",
            "FINANCE_BACKUP_DIR": str(self.source_root / "backups"),
            "FINANCE_VINTAGE_DIR": str(self.source_root / "vintages"),
            "FINANCE_HOLDINGS_DIR": str(self.source_root / "holdings"),
            "FINANCE_SURPLUS_DIR": str(self.source_root / "surplus"),
            "WISESHEETS_SNAPSHOT_PATH": str(self.source_root / "earnings.json"),
        })
        self.env.start()
        self.client_ctx = TestClient(create_app(self.engine))
        self.client = self.client_ctx.__enter__()

    def tearDown(self):
        self.client_ctx.__exit__(None, None, None)
        self.env.stop()
        self.engine.dispose()

    def test_pre_engine_research_and_risk_endpoints_are_retired(self):
        for path in ("/api/research", "/api/research/labour_share", "/api/risk", "/api/risk/us"):
            self.assertEqual(self.client.get(path).status_code, 404, path)
        self.assertEqual(self.client.get("/api/research-corpus").status_code, 200)

    def test_actual_instrument_registry_and_missing_market_data_are_explained(self):
        listed = self.client.get("/api/markets")
        self.assertEqual(listed.status_code, 200)
        self.assertGreaterEqual(listed.json()["count"], 24)
        response = self.client.post("/api/market/compare",
            json={"instrument_ids": ["vt", "gld"], "currency": "EUR"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "no_data")
        self.assertEqual(set(response.json()["missing_instruments"]), {"vt", "gld"})
        self.assertEqual(response.json()["instruments"], [])
        self.assertEqual(self.client.post("/api/market/compare", json={
            "instrument_ids": ["vwce.de", "vt"], "currency": "USD",
        }).status_code, 422)
        self.assertEqual(self.client.post("/api/market/compare", json={
            "instrument_ids": ["vt", "vt"], "currency": "EUR",
        }).status_code, 422)
        self.assertEqual(self.client.post("/api/market/compare", json={
            "instrument_ids": ["vt", "gld"], "weights_pct": {"vt": 40, "gld": 50},
        }).status_code, 422)
        self.assertEqual(self.client.post("/api/market/compare", json={
            "instrument_ids": ["vt", "unregistered"], "currency": "EUR",
        }).status_code, 404)

    def test_source_readiness_distinguishes_env_configuration_and_on_disk_evidence(self):
        with patch.dict(os.environ, {
            "FRED_API_KEY": "a" * 32,
            "WISESHEETS_API_KEY": "secret",
            "SEC_USER_AGENT": "Research Group contact@example.org",
            "FINANCE_INCLUDE_MARKETS": "1",
            "FINANCE_SEC_HOLDINGS_REFRESH": "1",
        }):
            result = self.client.get("/api/operations")
            self.assertEqual(result.status_code, 200)
            readiness = result.json()["source_setup"]
            self.assertTrue(readiness["fred_key_format_valid"])
            self.assertTrue(readiness["wisesheets_key_present"])
            self.assertTrue(readiness["sec_contact_present"])
            self.assertTrue(readiness["market_collection_enabled"])
            self.assertTrue(readiness["nport_collection_enabled"])
            self.assertEqual(readiness["sec_nport_reports_stored"], 0)
            self.assertNotIn("secret", result.text)
            self.assertNotIn("contact@example.org", result.text)
            self.assertNotIn("a" * 32, result.text)
            reports = self.source_root / "holdings" / "vt"
            reports.mkdir(parents=True)
            (reports / "2026-03-31--test-report.json").write_text("{}")
            stored = self.client.get("/api/operations")
            self.assertEqual(stored.status_code, 200)
            self.assertEqual(stored.json()["source_setup"]["sec_nport_reports_stored"], 1)

    def test_operations_excludes_secrets_and_source_raw_errors(self):
        status = self.client.get("/api/operations")
        self.assertEqual(status.status_code, 200)
        data = status.json()
        self.assertGreaterEqual(data["catalog_series"], 49)
        self.assertEqual(data["sources_with_at_least_one_observation"], 0)
        self.assertEqual(data["market_instruments_with_prices"], 0)
        self.assertFalse(data["optional_market_refresh_configured"])
        self.assertFalse(data["automatic_backups_configured"])
        self.assertFalse(any("KEY" in key for key in data))


if __name__ == "__main__":
    unittest.main()
