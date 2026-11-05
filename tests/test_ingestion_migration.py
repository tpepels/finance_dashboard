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


if __name__ == "__main__":
    unittest.main()
