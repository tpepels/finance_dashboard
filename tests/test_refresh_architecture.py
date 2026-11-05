"""Provider-neutral refresh execution and durable deferred-run semantics."""
from datetime import date
import unittest
from unittest.mock import Mock, patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from finance_dashboard.catalog import load_documents
from finance_dashboard.database import (
    Base, IngestionRun, MarketIngestionRun, FxIngestionRun,
    ObservationVersion, MarketPriceVersion, FxRateVersion,
)
from finance_dashboard.market_service import MarketIngestionService
from finance_dashboard.service import IngestionService
from finance_dashboard.source_policy import PolicyDeferred
from finance_dashboard.source_coverage import build_coverage
from finance_dashboard.market import instruments
from finance_dashboard.worker import RefreshTask, execute_refresh_tasks


class FailPolicySource:
    def fetch(self, *args, **kwargs):
        raise PolicyDeferred("fred-v1", "publisher_cooldown", 9999999999)


class RefreshArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)

    def tearDown(self):
        self.engine.dispose()

    def test_macro_deferral_preserves_record_without_observation(self):
        sid = "policy_rate.us.fed_upper"
        with self.assertRaises(PolicyDeferred):
            IngestionService(self.engine, FailPolicySource()).refresh(sid, full=True)
        with Session(self.engine) as session:
            entry = session.scalars(select(IngestionRun)).one()
            self.assertEqual(entry.status, "deferred")
            self.assertEqual(entry.error, "source_policy_deferred")
            self.assertEqual(session.query(ObservationVersion).count(), 0)
        status = build_coverage(
            self.engine, load_documents()[0]["series"], instruments())
        item = next(row for row in status["items"] if row["id"] == sid)
        self.assertEqual(item["state"], "collection_deferred")
        self.assertEqual(item["last_failure_code"], "source_policy_deferred")

    def test_market_and_currency_defer_without_erasures(self):
        service = MarketIngestionService(
            self.engine, market_client=FailPolicySource(),
            fx_client=FailPolicySource())
        with self.assertRaises(PolicyDeferred):
            service.refresh_instrument("vt")
        with self.assertRaises(PolicyDeferred):
            service.refresh_fx("USD")
        with Session(self.engine) as session:
            self.assertEqual(session.scalars(select(MarketIngestionRun)).one().status,
                             "deferred")
            self.assertEqual(session.scalars(select(FxIngestionRun)).one().status,
                             "deferred")
            self.assertEqual(session.query(MarketPriceVersion).count(), 0)
            self.assertEqual(session.query(FxRateVersion).count(), 0)

    def test_one_execution_path_for_macro_market_fx_and_policy_deferral(self):
        progress, executed, logged = [], [], []
        def successful(label):
            executed.append(label)
            return {"status": "success"}
        def deferred():
            executed.append("macro")
            raise PolicyDeferred("oecd-sdmx", "rolling_window_limit", 9999999999)
        tasks = [
            RefreshTask("fx", "USD", lambda: successful("fx"), "FX:USD"),
            RefreshTask("macro", "research.test", deferred, "research.test"),
            RefreshTask("markets", "vt", lambda: successful("market"), "vt"),
        ]
        with patch("finance_dashboard.worker.record_event",
                   side_effect=lambda *args, **kwargs:
                       logged.append((args, kwargs))):
            failures = execute_refresh_tasks(
                tasks, progress=lambda done, total, label:
                    progress.append((done, total, label)))
        self.assertEqual(failures, 1)
        self.assertEqual(executed, ["fx", "macro", "market"])
        self.assertEqual(progress, [
            (1, 3, "FX:USD"), (2, 3, "research.test"), (3, 3, "vt"),
        ])
        self.assertEqual(len(logged), 1)
        self.assertEqual(logged[0][0][1], "source_deferred")
        self.assertEqual(logged[0][1]["reason"], "source_policy_deferred")

    def test_cancelled_batch_does_not_execute_sources(self):
        stop = Mock()
        stop.is_set.return_value = True
        task = RefreshTask(
            "macro", "blocked", Mock(side_effect=AssertionError("ran")), "blocked")
        self.assertEqual(execute_refresh_tasks([task], stopped=stop), 0)
        task.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
