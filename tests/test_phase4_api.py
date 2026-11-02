"""Phase 4 source-validated API smoke with a clean local SQLite database."""
from datetime import date
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
        self.engine = create_engine("sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.env = patch.dict(os.environ, {
            "FINANCE_AUTO_REFRESH": "0",
            "FINANCE_INCLUDE_MARKETS": "0",
            "FINANCE_AUTO_BACKUP": "0",
        })
        self.env.start()
        self.client_ctx = TestClient(create_app(self.engine))
        self.client = self.client_ctx.__enter__()

    def tearDown(self):
        self.client_ctx.__exit__(None, None, None)
        self.env.stop()
        self.engine.dispose()

    def test_risk_catalog_and_empty_regional_diagnostics(self):
        catalog = self.client.get("/api/risk")
        self.assertEqual(catalog.status_code, 200)
        self.assertTrue(catalog.json()["indicators"])
        self.assertIn("no composite", catalog.json()["method"].lower())
        us = self.client.get("/api/risk/us")
        self.assertEqual(us.status_code, 200)
        self.assertEqual(us.json()["scope"], "us")
        self.assertTrue(all(x["status"] == "no_data" for x in us.json()["indicators"]))
        self.assertEqual(self.client.get("/api/risk/antarctica").status_code, 404)
        self.assertEqual(self.client.get(
            "/api/risk/us?start=2026-12-01&end=2026-01-01").status_code, 422)

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
