"""SQLite integration tests for SQLAlchemy persistence and HTTP behavior."""
from datetime import date
from decimal import Decimal
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from finance_dashboard.api import create_app
from finance_dashboard.bis import FetchedSeries
from finance_dashboard.database import Base, IngestionRun, ObservationVersion
from finance_dashboard.service import IngestionService, current_observations

ID = "policy_rate.us.bis"


class FakeProvider:
    def __init__(self):
        self.values = {date(2026, 8, 17): Decimal("3.5"), date(2026, 8, 18): Decimal("3.625")}
        self.fail = False
        self.start = object()

    def fetch(self, series_id, start):
        self.start = start
        if self.fail:
            raise ValueError("source unavailable")
        return FetchedSeries(series_id, "https://stats.bis.org/test", None, self.values.copy())


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.provider = FakeProvider()
        self.svc = IngestionService(self.engine, self.provider)

    def tearDown(self):
        self.engine.dispose()

    def test_initial_load_idempotency_and_revision(self):
        result = self.svc.refresh(ID, today=date(2026, 9, 1))
        self.assertEqual(result["versions_added"], 2)
        self.assertIsNone(self.provider.start)
        self.assertEqual(self.svc.refresh(ID, today=date(2026, 9, 1))["versions_added"], 0)
        self.assertIsNotNone(self.provider.start)
        with Session(self.engine) as session:
            historical = current_observations(session, ID)
            original_seen = historical[1].first_seen_at
        self.provider.values[date(2026, 8, 18)] = Decimal("3.75")
        self.assertEqual(self.svc.refresh(ID, today=date(2026, 9, 1))["versions_added"], 1)
        with Session(self.engine) as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(ObservationVersion)), 3)
            self.assertEqual(current_observations(session, ID)[1].value, Decimal("3.75"))
            before = current_observations(session, ID, snapshot_at=original_seen)
            self.assertEqual(before[1].value, Decimal("3.625"))

    def test_provider_failure_preserves_data_and_records_failure(self):
        self.svc.refresh(ID, today=date(2026, 9, 1))
        self.provider.fail = True
        with self.assertRaisesRegex(ValueError, "source unavailable"):
            self.svc.refresh(ID, today=date(2026, 9, 1))
        with Session(self.engine) as session:
            self.assertEqual(len(current_observations(session, ID)), 2)
            latest = session.scalars(select(IngestionRun).order_by(IngestionRun.started_at.desc())).first()
            self.assertEqual(latest.status, "failed")

    def test_future_value_rejected_without_partial_update(self):
        self.provider.values[date(2099, 1, 1)] = Decimal("8.5")
        with self.assertRaisesRegex(ValueError, "future-dated"):
            self.svc.refresh(ID, today=date(2026, 9, 1))
        with Session(self.engine) as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(ObservationVersion)), 0)

    def test_non_bis_world_bank_uses_own_provider_and_api(self):
        from finance_dashboard.database import SeriesRow
        country_id = "gdp.real_growth.us"
        provider = FakeProvider()
        provider.values = {date(2025, 1, 1): Decimal("2.75")}
        service = IngestionService(self.engine, provider)
        result = service.refresh(country_id, today=date(2026, 11, 2))
        self.assertEqual(result["versions_added"], 1)
        with Session(self.engine) as session:
            row = session.get(SeriesRow, country_id)
            self.assertEqual(row.provider, "WORLD_BANK")
            self.assertEqual(row.source_key, "USA/NY.GDP.MKTP.KD.ZG")
        with TestClient(create_app(self.engine)) as client:
            response = client.post("/api/query", json={"series_ids": [country_id]})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["series"][0]["observations"][0]["value"], "2.7500000000")

    def test_api_query_and_status(self):
        self.svc.refresh(ID, today=date(2026, 9, 1))
        with TestClient(create_app(self.engine)) as client:
            self.assertEqual(client.get("/api/health").status_code, 200)
            data = client.post("/api/query", json={"series_ids": [ID]}).json()
            item = data["series"][0]
            self.assertEqual(item["status"], "ready")
            self.assertEqual(len(item["observations"]), 2)
            self.assertEqual(item["observations"][1]["value"], "3.6250000000")
            self.assertEqual(next(row for row in client.get("/api/data-status").json()["items"] if row["series_id"] == ID)["status"], "success")
            self.assertEqual(client.post("/api/query", json={"series_ids": ["unknown"]}).status_code, 404)
            self.assertEqual(client.post("/api/query", json={"series_ids": ["valuation.global.cape"]}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
