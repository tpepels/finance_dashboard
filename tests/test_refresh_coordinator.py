"""Cross-process-safe ingestion coordination for SQLite and worker entrypoints."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from sqlalchemy import create_engine

from finance_dashboard.refresh_coordinator import reserve_refresh, refresh_lock_path
from finance_dashboard.worker import refresh_all, refresh_market_all


class RefreshCoordinatorTests(unittest.TestCase):
    def test_sqlite_file_uses_stable_adjacent_lock_without_modifying_db(self):
        with TemporaryDirectory() as tmp:
            file = Path(tmp) / "finance.sqlite"
            engine = create_engine("sqlite+pysqlite:///" + str(file))
            try:
                lock = refresh_lock_path(engine)
                self.assertEqual(lock, Path(tmp) / "finance.sqlite.refresh.lock")
                with reserve_refresh(engine) as acquired:
                    self.assertTrue(acquired)
                    with reserve_refresh(engine) as concurrent:
                        self.assertFalse(concurrent)
                with reserve_refresh(engine) as acquired_again:
                    self.assertTrue(acquired_again)
                self.assertTrue(lock.is_file())
            finally:
                engine.dispose()

    def test_cli_macro_refresh_does_not_bypass_active_ingestion_lock(self):
        with TemporaryDirectory() as tmp:
            engine = create_engine(
                "sqlite+pysqlite:///" + str(Path(tmp) / "finance.sqlite"))
            try:
                with reserve_refresh(engine) as acquired:
                    self.assertTrue(acquired)
                    with patch("finance_dashboard.worker.IngestionService") as service:
                        self.assertEqual(
                            refresh_all(
                                engine, series_ids={"labour.de.pwt_labour_share"}),
                            1)
                        service.assert_not_called()
            finally:
                engine.dispose()

    def test_market_refresh_uses_the_same_lock_as_macro(self):
        with TemporaryDirectory() as tmp:
            engine = create_engine(
                "sqlite+pysqlite:///" + str(Path(tmp) / "finance.sqlite"))
            try:
                with reserve_refresh(engine) as acquired:
                    self.assertTrue(acquired)
                    with patch("finance_dashboard.market.YahooMarketClient") as market, \
                         patch("finance_dashboard.market.EcbFxClient") as fx:
                        self.assertEqual(refresh_market_all(
                            engine, instrument_ids=set(), currencies={"USD"}), 1)
                        market.assert_not_called()
                        fx.assert_not_called()
            finally:
                engine.dispose()


if __name__ == "__main__":
    unittest.main()
