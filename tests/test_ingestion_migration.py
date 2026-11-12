"""Existing SQLite histories survive the new original-receipt schema migration."""
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import sqlite3
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class IngestionEvidenceMigrationTests(unittest.TestCase):
    def test_prior_sqlite_database_upgrades_without_losing_observations(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "existing.sqlite3"
            env = {
                **os.environ,
                "FINANCE_DASHBOARD_ROOT": str(ROOT),
                "DATABASE_URL": "sqlite+pysqlite:///" + str(path),
            }
            def alembic(revision):
                run = subprocess.run(
                    [sys.executable, "-m", "alembic", "-c", "alembic.ini",
                     "upgrade", revision],
                    cwd=ROOT, env=env, capture_output=True, text=True,
                    timeout=60, check=False)
                self.assertEqual(run.returncode, 0, run.stderr[-2500:])
            alembic("20261104_05")
            with sqlite3.connect(path) as con:
                names = {col[1] for col in con.execute(
                    "PRAGMA table_info(ingestion_runs)")}
                self.assertNotIn("evidence_kind", names)
                con.execute(
                    "INSERT INTO series (id,provider,source_key,updated_at)"
                    " VALUES (?,?,?,?)",
                    ("bond.us.nominal_10y","FRED","DGS10",
                     "2026-10-30 12:00:00"))
                con.execute(
                    "INSERT INTO ingestion_runs "
                    "(id,series_id,started_at,status,observations_received,"
                    "versions_added) VALUES (?,?,?,?,?,?)",
                    ("legacy-run","bond.us.nominal_10y",
                     "2026-10-30 12:00:00","success",1,1))
                con.execute(
                    "INSERT INTO observation_versions "
                    "(series_id,period,value,first_seen_at,ingestion_run_id)"
                    " VALUES (?,?,?,?,?)",
                    ("bond.us.nominal_10y","2024-01-02",3.95,
                     "2026-10-30 12:00:00","legacy-run"))
                con.commit()
            alembic("head")
            alembic("head")  # repeat startup is idempotent
            with sqlite3.connect(path) as con:
                names = {col[1] for col in con.execute(
                    "PRAGMA table_info(ingestion_runs)")}
                self.assertTrue({"evidence_kind", "evidence_scope",
                                 "evidence_bundle_digest",
                                 "evidence_receipt_name"} <= names)
                run = con.execute(
                    "SELECT status,observations_received,versions_added,"
                    "evidence_kind,evidence_scope,evidence_bundle_digest,"
                    "evidence_receipt_name FROM ingestion_runs WHERE id=?",
                    ("legacy-run",)).fetchone()
                self.assertEqual(run, ("success",1,1,None,None,None,None))
                points = con.execute(
                    "SELECT period,value,ingestion_run_id FROM observation_versions"
                ).fetchall()
                self.assertEqual(points, [("2024-01-02",3.95,"legacy-run")])



class RetiredGoldSourceMigrationTests(unittest.TestCase):
    def setUp(self):
        from sqlalchemy import create_engine
        from finance_dashboard.database import Base
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)

    def tearDown(self):
        self.engine.dispose()

    def test_failed_only_corgano_binding_migrates_without_losing_old_run(self):
        from datetime import date
        from decimal import Decimal
        from sqlalchemy.orm import Session
        from finance_dashboard.database import SeriesRow, IngestionRun, now_utc
        from finance_dashboard.service import IngestionService
        from finance_dashboard.bis import FetchedSeries

        with Session(self.engine) as session, session.begin():
            session.add(SeriesRow(
                id="gold.usd.spot", provider="CORGANO_SPOT",
                source_key="api/v1/latest:data.price_usd",
                updated_at=now_utc()))
            session.add(IngestionRun(
                id="legacy-gold-failure", series_id="gold.usd.spot",
                started_at=now_utc(), ended_at=now_utc(), status="failed",
                observations_received=0, versions_added=0,
                error="provider_failed"))
        class Gold:
            def fetch(self, sid, start):
                return FetchedSeries(
                    sid, "https://api.gold-api.com/price/XAU", None,
                    {date(2026, 11, 12): Decimal("4092.22")})
        done = IngestionService(self.engine, Gold()).refresh(
            "gold.usd.spot", today=date(2026, 11, 12))
        self.assertEqual(done["status"], "success")
        with Session(self.engine) as session:
            row = session.get(SeriesRow, "gold.usd.spot")
            self.assertEqual(row.provider, "GOLD_API_SPOT")
            self.assertEqual(row.source_key, "price/XAU:price:updatedAt:USD")
            self.assertEqual(session.get(IngestionRun, "legacy-gold-failure").status, "failed")

    def test_old_successful_corgano_observations_require_separate_migration(self):
        from datetime import date
        from decimal import Decimal
        from sqlalchemy.orm import Session
        from finance_dashboard.database import SeriesRow, IngestionRun, ObservationVersion, now_utc
        from finance_dashboard.service import IngestionService

        with Session(self.engine) as session, session.begin():
            session.add(SeriesRow(
                id="gold.usd.spot", provider="CORGANO_SPOT",
                source_key="api/v1/latest:data.price_usd", updated_at=now_utc()))
            session.add(IngestionRun(
                id="corgano-success", series_id="gold.usd.spot",
                started_at=now_utc(), status="success",
                observations_received=1, versions_added=1))
            session.add(ObservationVersion(
                series_id="gold.usd.spot", period=date(2026, 10, 31),
                value=Decimal("3900.25"), first_seen_at=now_utc(),
                ingestion_run_id="corgano-success"))
        class Network:
            def fetch(self, *args):
                raise AssertionError("must reject method mixing before HTTP")
        with self.assertRaisesRegex(ValueError, "explicit migration"):
            IngestionService(self.engine, Network()).refresh("gold.usd.spot")
        with Session(self.engine) as session:
            self.assertEqual(session.get(SeriesRow, "gold.usd.spot").provider,
                             "CORGANO_SPOT")



if __name__ == "__main__":
    unittest.main()
