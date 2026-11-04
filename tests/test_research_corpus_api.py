"""Phase 2 source-evidence API integration: never turn a stored source into a validated analysis."""
from datetime import date, datetime, timezone
from decimal import Decimal
import os
from unittest.mock import patch
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from finance_dashboard.api import create_app
from finance_dashboard.database import Base, SeriesRow, IngestionRun, ObservationVersion


class Phase2ResearchCorpusApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.env = patch.dict(os.environ, {
            "FINANCE_AUTO_REFRESH": "0", "FINANCE_INCLUDE_MARKETS": "0",
            "FINANCE_AUTO_BACKUP": "0",
        })
        self.env.start()
        self.ctx = TestClient(create_app(self.engine))
        self.client = self.ctx.__enter__()

    def tearDown(self):
        self.ctx.__exit__(None, None, None)
        self.env.stop()
        self.engine.dispose()

    def test_35_questions_and_no_fabricated_completeness(self):
        response = self.client.get("/api/research-corpus")
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["analysis_count"], 35)
        self.assertEqual(result["method_source_count"], 49)
        self.assertEqual(result["fully_validated_analysis_count"], 0)
        self.assertEqual(result["analysis_with_any_stored_macro_observations"], 0)
        self.assertTrue(result["observations_checked"])
        self.assertEqual(len({x["id"] for x in result["analyses"]}), 35)
        self.assertIn("G06", {x["id"] for x in result["analyses"]})
        self.assertNotIn("C04", {x["id"] for x in result["analyses"]})

    def test_fallback_detail_and_404(self):
        response = self.client.get("/api/research-corpus/P02")
        self.assertEqual(response.status_code, 200)
        item = response.json()
        self.assertFalse(item["comparative_corpus_validated"])
        self.assertTrue(item["fallbacks"])
        self.assertTrue(all(x["stored_periods"] == 0
                            for x in item["linked_existing_series"]))
        self.assertEqual(self.client.get("/api/research-corpus/UNKNOWN").status_code, 404)

    def test_existing_observation_is_not_validated_comparative_analysis(self):
        when = datetime.now(timezone.utc)
        with Session(self.engine) as session, session.begin():
            session.add(SeriesRow(id="recession.us.sahm", provider="FRED",
                source_key="SAHMREALTIME", updated_at=when))
            session.add(IngestionRun(id="phase2-sahm", series_id="recession.us.sahm",
                started_at=when, ended_at=when, status="success",
                observations_received=1, versions_added=1))
            session.add(ObservationVersion(series_id="recession.us.sahm",
                period=date(2026, 8, 1), value=Decimal("0.2"),
                first_seen_at=when, ingestion_run_id="phase2-sahm"))
        result = self.client.get("/api/research-corpus/C02")
        self.assertEqual(result.status_code, 200)
        entry = result.json()
        self.assertEqual(entry["existing_references_with_observations"], 1)
        self.assertFalse(entry["comparative_corpus_validated"])
        # The current C02 source inventory names the official recession
        # chronology without using the NBER abbreviation; test the actual
        # methodological requirement rather than obsolete wording.
        self.assertIn("US recession chronology", entry["outstanding_evidence"])
        self.assertIn("release-time revisions", entry["outstanding_evidence"])


if __name__ == "__main__":
    unittest.main()
