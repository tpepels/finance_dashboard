"""Phase 4 API rejects unsupported claims without source files."""
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


class UnresolvedScienceApiTests(unittest.TestCase):
    def test_empty_source_caches_never_claim_historical_values(self):
        with TemporaryDirectory() as tmp:
            with patch.dict(os.environ,{
                "FINANCE_AUTO_REFRESH":"0",
                "FINANCE_VINTAGE_DIR":str(Path(tmp)/"vintages"),
                "FINANCE_HOLDINGS_DIR":str(Path(tmp)/"holdings"),
                "FINANCE_SURPLUS_DIR":str(Path(tmp)/"surplus"),
            }):
                engine=create_engine("sqlite+pysqlite:///:memory:",
                     connect_args={"check_same_thread":False},poolclass=StaticPool)
                Base.metadata.create_all(engine)
                try:
                    with TestClient(create_app(engine)) as api:
                        vintages=api.get("/api/vintages")
                        self.assertEqual(vintages.status_code,200)
                        self.assertTrue(all(s["count"]==0 for s in vintages.json()["series"]))
                        self.assertEqual(api.get("/api/vintages/T10Y3M?asof=2008-01-31").status_code,404)
                        backtest=api.get("/api/vintage/backtest?horizon_months=12")
                        self.assertEqual(backtest.status_code,200)
                        self.assertEqual(backtest.json()["status"],"insufficient_vintages")
                        self.assertIsNone(backtest.json()["evaluation"])
                        self.assertEqual(api.get("/api/vintage/backtest?horizon_months=15").status_code,422)
                        holdings=api.get("/api/holdings/vt")
                        self.assertEqual(holdings.status_code,200)
                        self.assertEqual(holdings.json()["status"],"no_dated_holdings")
                        self.assertEqual(api.get("/api/holdings/aapl").status_code,422)
                        self.assertEqual(api.get("/api/holdings/not-a-fund").status_code,404)
                        available=api.get("/api/marx")
                        self.assertEqual(available.status_code,200)
                        self.assertEqual(available.json()["status"],"not_ingested")
                        self.assertEqual(api.get("/api/marx/US/2020").status_code,404)
                        self.assertEqual(api.get("/api/marx/US/2020?scenario=fiction").status_code,422)
                finally:
                    engine.dispose()


if __name__=="__main__":
    unittest.main()
