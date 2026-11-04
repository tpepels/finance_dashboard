"""Coverage reads use covering indexes without changing append-only history."""
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.orm import Session

from finance_dashboard.database import (
    Base, FxIngestionRun, FxRateVersion, IngestionRun, MarketIngestionRun,
    MarketInstrumentRow, MarketPriceVersion, ObservationVersion, SeriesRow,
)
from finance_dashboard.source_coverage import _counts


CASES = (
    (ObservationVersion, "series_id", "period", ("coverage.a", "coverage.b"),
     "ix_observation_versions_series_period"),
    (MarketPriceVersion, "instrument_id", "day", ("vt", "bnd"),
     "ix_market_price_versions_instrument_day"),
    (FxRateVersion, "currency", "day", ("USD", "GBP"),
     "ix_fx_rate_versions_currency_day"),
)


class SourceCoverageIndexTests(unittest.TestCase):
    def _seed(self, engine):
        now = datetime(2026, 11, 4, tzinfo=timezone.utc)
        with engine.begin() as conn:
            for sid in ("coverage.a", "coverage.b"):
                conn.execute(SeriesRow.__table__.insert(), {
                    "id": sid, "provider": "TEST", "source_key": sid,
                    "updated_at": now,
                })
                conn.execute(IngestionRun.__table__.insert(), {
                    "id": sid, "series_id": sid, "started_at": now,
                    "status": "success", "observations_received": 0,
                    "versions_added": 0,
                })
            for instrument in ("vt", "bnd"):
                conn.execute(MarketInstrumentRow.__table__.insert(), {
                    "id": instrument, "symbol": instrument,
                    "exchange_mic": "TEST", "currency": "USD", "updated_at": now,
                })
                conn.execute(MarketIngestionRun.__table__.insert(), {
                    "id": instrument, "instrument_id": instrument,
                    "started_at": now, "status": "success",
                    "observations_received": 0, "versions_added": 0,
                })
            for currency in ("USD", "GBP"):
                conn.execute(FxIngestionRun.__table__.insert(), {
                    "id": currency, "currency": currency, "started_at": now,
                    "status": "success", "observations_received": 0,
                    "versions_added": 0,
                })
            for model, key, period, ids, _ in CASES:
                for ident, day, value in (
                    (ids[0], date(2026, 1, 1), 1),
                    (ids[0], date(2026, 1, 1), 2),
                    (ids[0], date(2026, 1, 3), 3),
                    (ids[1], date(2026, 1, 2), 4),
                ):
                    row = {key: ident, period: day, "first_seen_at": now,
                           "ingestion_run_id": ident}
                    if model is ObservationVersion:
                        row["value"] = value
                    elif model is MarketPriceVersion:
                        row.update(close=value, adjusted_close=value, volume=10)
                    else:
                        row["foreign_per_eur"] = value
                    conn.execute(model.__table__.insert(), row)

    def _rows(self, engine):
        with engine.connect() as conn:
            return {model.__tablename__: conn.execute(
                select(model.__table__).order_by(model.id)).all()
                for model, *_ in CASES}

    def _assert_counts_and_covering_indexes(self, engine):
        for model, key_name, period_name, ids, index_name in CASES:
            with self.subTest(table=model.__tablename__):
                indexes = {item["name"]: item for item in
                           inspect(engine).get_indexes(model.__tablename__)}
                self.assertIn(index_name, indexes)
                self.assertEqual(indexes[index_name]["column_names"],
                                 [key_name, period_name])
                self.assertFalse(indexes[index_name]["unique"])
                self.assertIn(f"ix_{model.__tablename__}_{key_name}", indexes)
                self.assertIn(f"ix_{model.__tablename__}_{period_name}", indexes)
                emitted = []

                def capture(conn, cursor, statement, parameters, context, executemany):
                    emitted.append((statement, parameters))

                event.listen(engine, "before_cursor_execute", capture)
                try:
                    with Session(engine) as session:
                        actual = _counts(session, model, getattr(model, key_name),
                                         getattr(model, period_name))
                finally:
                    event.remove(engine, "before_cursor_execute", capture)
                self.assertEqual(actual, {
                    ids[0]: (2, date(2026, 1, 1), date(2026, 1, 3), 3),
                    ids[1]: (1, date(2026, 1, 2), date(2026, 1, 2), 1),
                })
                self.assertEqual(len(emitted), 1)
                statement, parameters = emitted[0]
                with engine.connect() as conn:
                    plan = conn.exec_driver_sql(
                        "EXPLAIN QUERY PLAN " + statement, parameters).all()
                self.assertTrue(any("USING COVERING INDEX " + index_name in row[3]
                                    for row in plan), plan)

    def test_fresh_metadata_covers_coverage_queries_and_preserves_revisions(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        self._seed(engine)
        self._assert_counts_and_covering_indexes(engine)

    def test_existing_sqlite_upgrade_downgrade_preserves_rows_and_old_indexes(self):
        with TemporaryDirectory() as tmp:
            url = f"sqlite+pysqlite:///{Path(tmp) / 'coverage.sqlite3'}"
            config = Config("alembic.ini")
            with patch.dict(os.environ, {"DATABASE_URL": url}):
                command.upgrade(config, "20261102_04")
                engine = create_engine(url)
                try:
                    self._seed(engine)
                    original_rows = self._rows(engine)
                    original_indexes = {
                        model.__tablename__: inspect(engine).get_indexes(model.__tablename__)
                        for model, *_ in CASES}
                    command.upgrade(config, "head")
                    self._assert_counts_and_covering_indexes(engine)
                    self.assertEqual(self._rows(engine), original_rows)
                    command.downgrade(config, "20261102_04")
                    self.assertEqual(self._rows(engine), original_rows)
                    for table, indexes in original_indexes.items():
                        self.assertEqual(inspect(engine).get_indexes(table), indexes)
                    command.upgrade(config, "head")
                    self._assert_counts_and_covering_indexes(engine)
                    self.assertEqual(self._rows(engine), original_rows)
                finally:
                    engine.dispose()


if __name__ == "__main__":
    unittest.main()
