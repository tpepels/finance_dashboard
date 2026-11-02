"""Optional PostgreSQL integration test; runs automatically with TEST_POSTGRES_URL."""
import os
from datetime import date
from decimal import Decimal
import unittest

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from finance_dashboard.bis import FetchedSeries
from finance_dashboard.database import Base, ObservationVersion
from finance_dashboard.service import IngestionService, current_observations


class FakeProvider:
    def __init__(self):
        self.value = Decimal("2.50")

    def fetch(self, sid, start):
        return FetchedSeries(
            sid, "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/D.XM",
            None, {date(2026, 10, 1): self.value},
        )


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URL"), "Requires temporary PostgreSQL test database")
class PostgresTests(unittest.TestCase):
    def test_transaction_revision_and_readback(self):
        engine = create_engine(os.environ["TEST_POSTGRES_URL"])
        # Dedicated ephemeral test database only.
        Base.metadata.create_all(engine)
        sid = "policy_rate.ea.bis"
        provider = FakeProvider()
        svc = IngestionService(engine, provider)
        try:
            self.assertEqual(svc.refresh(sid, today=date(2026, 11, 2))["versions_added"], 1)
            self.assertEqual(svc.refresh(sid, today=date(2026, 11, 2))["versions_added"], 0)
            provider.value = Decimal("2.75")
            self.assertEqual(svc.refresh(sid, today=date(2026, 11, 2))["versions_added"], 1)
            with Session(engine) as session:
                versions = current_observations(session, sid)
                self.assertEqual(versions[0].value, Decimal("2.75"))
                self.assertEqual(session.scalar(select(func.count()).select_from(ObservationVersion)), 2)
        finally:
            Base.metadata.drop_all(engine)
            engine.dispose()
