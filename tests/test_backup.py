"""SQLite/WAL backup and manifest retention without stopping source readers."""
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
import os
from unittest.mock import patch

from finance_dashboard.backup import backup_local, verify_manifest, _hash


class LocalBackupTests(unittest.TestCase):
    def test_existing_background_refresh_schedules_one_daily_backup_without_worker(self):
        from finance_dashboard.standalone import refresh_loop
        class OneCycle:
            def is_set(self):
                return False
            def wait(self, _seconds):
                return True
        with patch.dict(os.environ, {
            "FINANCE_AUTO_BACKUP": "1",
            "FINANCE_BACKUP_DIR": "/data/backups",
            "FINANCE_BACKUP_KEEP": "14",
        }):
            with (
                patch("finance_dashboard.worker.refresh_all", return_value=0) as macro,
                patch("finance_dashboard.backup.backup_local") as backup,
                patch("finance_dashboard.backup.source_database_path",
                      return_value=Path("/data/finance.sqlite3"))
            ):
                refresh_loop(None, OneCycle(), interval_seconds=86400,
                             include_markets=False, refresh_wisesheets=False)
                self.assertEqual(macro.call_count, 1)
                self.assertEqual(backup.call_count, 1)
                self.assertEqual(backup.call_args.kwargs["keep"], 14)

    def test_wal_online_copy_is_consistent_and_retains_local_source(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "finance.sqlite3"
            con = sqlite3.connect(db)
            try:
                con.execute("PRAGMA journal_mode=WAL")
                con.execute("CREATE TABLE facts (id INTEGER PRIMARY KEY, value TEXT)")
                con.execute("INSERT INTO facts VALUES (1, 'verified')")
                con.commit()
                result = backup_local(root / "backup", source_db=db)
                dest = root / "backup" / result["database"]["file"]
                self.assertEqual(result["database"]["sha256"], _hash(dest))
                self.assertEqual(sqlite3.connect(dest).execute(
                    "SELECT value FROM facts").fetchone()[0], "verified")
                # Source remains writable while backup is performed.
                con.execute("INSERT INTO facts VALUES (2, 'new')")
                con.commit()
                self.assertEqual(sqlite3.connect(dest).execute(
                    "SELECT COUNT(*) FROM facts").fetchone()[0], 1)
                self.assertEqual(con.execute("SELECT COUNT(*) FROM facts").fetchone()[0], 2)
            finally:
                con.close()

    def test_sec_snapshot_manifest_and_retention_do_not_remove_unrelated(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "db.sqlite3"
            con = sqlite3.connect(db)
            con.execute("CREATE TABLE x (a INTEGER)")
            con.commit()
            con.close()
            earnings = root / "earnings.json"
            earnings.write_text(json.dumps({
                "id": "profit.us_sec_filers.world_gdp_share",
                "source_snapshot_at_utc": "2026-11-02T12:00:00Z",
            }))
            out = root / "backups"
            out.mkdir()
            (out / "unrelated.txt").write_text("retain me")
            first = backup_local(out, source_db=db, earnings_snapshot=earnings, keep=1)
            self.assertIn("sha256", first["earnings_snapshot"])
            second = backup_local(out, source_db=db, earnings_snapshot=earnings, keep=1)
            manifests = list(out.glob("finance-*Z.json"))
            self.assertEqual(len(manifests), 1)
            self.assertEqual((out / "unrelated.txt").read_text(), "retain me")
            self.assertTrue((out / second["database"]["file"]).is_file())
            self.assertTrue((out / second["earnings_snapshot"]["file"]).is_file())
            manifest = list(out.glob("finance-*Z.json"))[0]
            self.assertTrue(verify_manifest(manifest)["verified"])
            backup_db = out / second["database"]["file"]
            backup_db.write_bytes(backup_db.read_bytes() + b"corrupted")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                verify_manifest(manifest)

    def test_malformed_snapshot_cannot_replace_verified_database_backup(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "db.sqlite3"
            sqlite3.connect(db).close()
            invalid = root / "bad-snapshot.json"
            invalid.write_text('{"id":"not-sec"}')
            with self.assertRaises(ValueError):
                backup_local(root / "backups", source_db=db,
                             earnings_snapshot=invalid)
            self.assertFalse(list((root / "backups").glob("finance-*Z.json")))
            self.assertFalse(list((root / "backups").glob("finance-*.sqlite3")))


if __name__ == "__main__":
    unittest.main()
