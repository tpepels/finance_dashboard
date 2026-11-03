"""Acceptance tests for all macro, market and FX histories, without live network."""
from datetime import date, datetime, timezone
from decimal import Decimal
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from finance_dashboard.api import create_app
from finance_dashboard.catalog import load_documents
from finance_dashboard.database import (
    Base, SeriesRow, IngestionRun, ObservationVersion, MarketInstrumentRow,
    MarketIngestionRun, MarketPriceVersion, FxIngestionRun, FxRateVersion,
)
from finance_dashboard.market import instruments
from finance_dashboard.source_coverage import build_coverage


NOW = datetime(2026, 11, 3, tzinfo=timezone.utc)


class SourceCoverageTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.catalog = load_documents()[0]["series"]
        self.registry = instruments()

    def tearDown(self):
        self.engine.dispose()

    def add_macro(self, sid, status="success", recorded=True, when=date(2025, 1, 1), error=None):
        definition = next(row for row in self.catalog if row["id"] == sid)
        with Session(self.engine) as session, session.begin():
            session.add(SeriesRow(id=sid, provider=definition["provider"],
                source_key=definition["source_key"], updated_at=NOW))
            session.add(IngestionRun(id="run-"+sid, series_id=sid,
                status=status, started_at=NOW, ended_at=NOW, requested_from=None,
                observations_received=1 if recorded else 0, versions_added=1 if recorded else 0,
                error=error))
            if recorded:
                session.add(ObservationVersion(series_id=sid, period=when,
                    value=Decimal("0.58"), first_seen_at=NOW, ingestion_run_id="run-"+sid))

    def test_returns_exactly_all_53_macro_24_market_and_three_currency_sources(self):
        with patch.dict(os.environ, {"FINANCE_INCLUDE_MARKETS":"0"}):
            report = build_coverage(self.engine, self.catalog, self.registry, asof=date(2026, 11, 3))
        self.assertEqual(report["summary"]["macro"]["total"], len(self.catalog))
        self.assertEqual(report["summary"]["macro"]["total"], 53)
        self.assertEqual(report["summary"]["markets"]["total"], 24)
        self.assertEqual(report["summary"]["fx"]["total"], 3)
        self.assertEqual(len(report["items"]), 80)
        self.assertEqual(len({(x["family"],x["id"]) for x in report["items"]}), 80)
        self.assertTrue(all(x["stored_periods"] == 0 for x in report["items"]))
        self.assertTrue(all(x["latest_source_date"] is None for x in report["items"]))
        self.assertEqual(report["summary"]["macro"]["not_ingested"], 53)
        self.assertEqual(report["summary"]["markets"]["collection_disabled"], 24)
        self.assertEqual(report["summary"]["fx"]["collection_disabled"], 3)

    def test_failed_macro_refresh_does_not_hide_retained_observations(self):
        self.add_macro("labour.de.pwt_labour_share", status="failed", recorded=True,
                       error="HTTPStatusError: api_key=SHOULD_NOT_APPEAR")
        self.add_macro("labour.fr.pwt_labour_share", status="failed", recorded=False,
                       error="HTTPStatusError")
        result = build_coverage(self.engine, self.catalog, self.registry, asof=date(2026,11,3))
        rows = {row["id"]:row for row in result["items"]}
        germany = rows["labour.de.pwt_labour_share"]
        france = rows["labour.fr.pwt_labour_share"]
        self.assertEqual(germany["stored_periods"], 1)
        self.assertEqual(germany["latest_source_date"], "2025-01-01")
        self.assertEqual(germany["state"], "refresh_failed_with_data")
        self.assertEqual(france["state"], "collection_failed")
        self.assertEqual(france["stored_periods"], 0)
        self.assertNotIn("SHOULD_NOT_APPEAR", str(result))
        self.assertNotIn("api_key=", str(result))

    def test_last_observed_date_and_period_count_deduplicate_revisions(self):
        sid = "labour.us.pwt_labour_share"
        self.add_macro(sid, when=date(2023,1,1))
        with Session(self.engine) as session, session.begin():
            session.add(ObservationVersion(series_id=sid, period=date(2023,1,1),
                value=Decimal("0.59"), first_seen_at=NOW, ingestion_run_id="run-"+sid))
        report = build_coverage(self.engine,self.catalog,self.registry,asof=date(2026,11,3))
        row=next(item for item in report["items"] if item["id"]==sid)
        self.assertEqual(row["stored_periods"],1)
        self.assertEqual(row["oldest_source_date"],"2023-01-01")
        self.assertEqual(row["latest_source_date"],"2023-01-01")
        self.assertEqual(row["state"],"stale")

    def test_market_and_fx_are_reported_with_actual_observation_dates(self):
        with Session(self.engine) as session, session.begin():
            session.add(MarketInstrumentRow(id="vt",symbol=self.registry["vt"]["source_symbol"],
                exchange_mic=self.registry["vt"]["exchange_mic"],currency="USD",updated_at=NOW))
            session.add(MarketIngestionRun(id="market-1", instrument_id="vt",
                started_at=NOW,ended_at=NOW,status="success",requested_from=None,
                observations_received=2,versions_added=2))
            session.add(MarketPriceVersion(instrument_id="vt",day=date(2026,10,30),
                close=Decimal("110"),adjusted_close=Decimal("110"),
                volume=0,first_seen_at=NOW,ingestion_run_id="market-1"))
            session.add(FxIngestionRun(id="fx-1",currency="USD",started_at=NOW,
                ended_at=NOW,status="success",observations_received=1,versions_added=1))
            session.add(FxRateVersion(currency="USD",day=date(2026,11,2),
                foreign_per_eur=Decimal("1.12"),first_seen_at=NOW,ingestion_run_id="fx-1"))
        with patch.dict(os.environ,{"FINANCE_INCLUDE_MARKETS":"1"}):
            report=build_coverage(self.engine,self.catalog,self.registry,asof=date(2026,11,3))
        market=next(x for x in report["items"] if x["id"]=="vt")
        fx=next(x for x in report["items"] if x["family"]=="fx" and x["id"]=="USD")
        self.assertEqual((market["stored_periods"],market["latest_source_date"],market["state"]),
                         (1,"2026-10-30","available"))
        self.assertEqual((fx["stored_periods"],fx["latest_source_date"],fx["state"]),
                         (1,"2026-11-02","available"))

    def test_readonly_api_contains_complete_coverage_without_credentials(self):
        with patch.dict(os.environ,{"FINANCE_AUTO_REFRESH":"0","FRED_API_KEY":"a"*32,
                                     "WISESHEETS_API_KEY":"SENSITIVE_KEY"}):
            with TestClient(create_app(self.engine)) as client:
                response=client.get("/api/source-coverage")
        self.assertEqual(response.status_code,200)
        payload=response.json()
        self.assertEqual(len(payload["items"]),80)
        self.assertEqual(payload["summary"]["macro"]["total"],53)
        self.assertNotIn("SENSITIVE_KEY", response.text)
        self.assertNotIn("a"*32, response.text)


if __name__=="__main__":
    unittest.main()
