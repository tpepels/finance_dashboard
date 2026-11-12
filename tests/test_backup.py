"""SQLite/WAL backup and manifest retention without stopping source readers."""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
import unittest
import os
import io
from hashlib import sha256
from unittest.mock import patch

from finance_dashboard.backup import backup_local, verify_manifest, _hash


class LocalBackupTests(unittest.TestCase):
    def test_retention_keeps_unverifiable_old_bundle_without_breaking_new_backup(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "finance.sqlite3"
            sqlite3.connect(db).close()
            out = root / "backups"
            old = backup_local(out, source_db=db, evidence_roots={})
            old_manifest = next(out.glob("finance-*Z.json"))
            invalid = out / old["database"]["file"]
            invalid.write_bytes(b"not a SQLite database")
            old["database"]["sha256"] = _hash(invalid)
            old["database"]["bytes"] = invalid.stat().st_size
            old_manifest.write_text(json.dumps(old))
            current = backup_local(out, source_db=db, evidence_roots={}, keep=1)
            self.assertTrue(invalid.exists())
            self.assertTrue(old_manifest.exists())
            new_manifest = out / current["database"]["file"].replace(".sqlite3", ".json")
            self.assertTrue(verify_manifest(new_manifest)["verified"])

    def test_policy_state_integrity_is_checked_even_when_bundle_hashes_match(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "finance.sqlite3"
            sqlite3.connect(db).close()
            ledger = root / "policy.sqlite3"
            with sqlite3.connect(ledger) as connection:
                connection.execute("CREATE TABLE requests (value INTEGER)")
            manifest = backup_local(root / "backups", source_db=db, evidence_roots={},
                policy_db_path=ledger)
            manifest_path = next((root / "backups").glob("finance-*Z.json"))
            archive_path = manifest_path.parent / manifest["application_state"]["file"]
            payload = b"invalid sqlite payload"
            member_name = "source-policy/rate-ledger.sqlite3"
            with tarfile.open(archive_path, "w:gz") as archive:
                member = tarfile.TarInfo(member_name)
                member.size = len(payload)
                archive.addfile(member, io.BytesIO(payload))
            metadata = manifest["application_state"]
            metadata["sha256"] = _hash(archive_path)
            metadata["bytes"] = archive_path.stat().st_size
            metadata["components"]["source_policy"] = {
                "member": member_name, "bytes": len(payload), "sha256": sha256(payload).hexdigest()}
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaises((ValueError, sqlite3.DatabaseError)):
                verify_manifest(manifest_path)

    def test_restore_keeps_owner_saved_views_and_committed_policy_wal(self):
        from finance_dashboard.backup import restore_backup
        from finance_dashboard.source_policy_ledger import SourcePolicyGate
        from finance_dashboard.source_policy_types import PolicyDeferred
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "finance.sqlite3"
            sqlite3.connect(db).close()
            owner = root / "owner-inputs.json"
            owner.write_text('{"version":1,"portfolio":{"capital":12345}}')
            views = root / "saved-views.json"
            views.write_text('{"version":1,"records":[{"id":"one","revision":2}]}')
            ledger = root / "source-policy" / "rate-ledger.sqlite3"
            gate = SourcePolicyGate(state_path=ledger, clock=lambda: 1000)
            connection = gate._connection()
            try:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("PRAGMA wal_autocheckpoint=0")
                connection.execute("INSERT INTO requests VALUES ('fred-v1', 999)")
                connection.execute("INSERT INTO policy_state VALUES ('fred-v1', 0, 4600, 429)")
                self.assertGreater(Path(str(ledger) + "-wal").stat().st_size, 0)
                bundle = root / "backups"
                manifest = backup_local(bundle, source_db=db, evidence_roots={},
                    owner_inputs_path=owner, saved_views_path=views, policy_db_path=ledger)
                manifest_path = next(bundle.glob("finance-*Z.json"))
                target = root / "different-installation"
                result = restore_backup(manifest_path, target)
                self.assertTrue(result["restored"])
                self.assertEqual((target / "owner-inputs.json").read_bytes(), owner.read_bytes())
                self.assertEqual((target / "saved-views.json").read_bytes(), views.read_bytes())
                restored = SourcePolicyGate(state_path=target / "source-policy/rate-ledger.sqlite3",
                    clock=lambda: 1000, max_wait_seconds=0)
                self.assertEqual(restored.availability("fred-v1")["retry_at"], 4600)
                with self.assertRaises(PolicyDeferred):
                    restored.reserve(restored.registry.by_id["fred-v1"])
                self.assertEqual(restored.report()["requests_recorded"], 1)
                self.assertEqual(manifest["application_state"]["version"], 1)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 1)
            finally:
                connection.close()

    def test_tampered_state_is_rejected_before_restore_creates_target(self):
        from finance_dashboard.backup import restore_backup
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "finance.sqlite3"
            sqlite3.connect(db).close()
            owner = root / "owner-inputs.json"
            owner.write_text('{"version":1}')
            manifest = backup_local(root / "backups", source_db=db, evidence_roots={},
                owner_inputs_path=owner)
            manifest_path = next((root / "backups").glob("finance-*Z.json"))
            archive = manifest_path.parent / manifest["application_state"]["file"]
            archive.write_bytes(archive.read_bytes() + b"tampered")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                restore_backup(manifest_path, root / "restored")
            self.assertFalse((root / "restored").exists())
            self.assertEqual(owner.read_text(), '{"version":1}')

    def test_rehashed_state_with_changed_member_cannot_bypass_member_hash(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "finance.sqlite3"
            sqlite3.connect(db).close()
            owner = root / "owner-inputs.json"
            owner.write_text('{"version":1}')
            manifest = backup_local(root / "backups", source_db=db, evidence_roots={},
                owner_inputs_path=owner)
            manifest_path = next((root / "backups").glob("finance-*Z.json"))
            archive_path = manifest_path.parent / manifest["application_state"]["file"]
            with tarfile.open(archive_path, "w:gz") as archive:
                payload = b'{"version":999}'
                member = tarfile.TarInfo("owner-inputs.json")
                member.size = len(payload)
                archive.addfile(member, io.BytesIO(payload))
            manifest["application_state"]["sha256"] = _hash(archive_path)
            manifest["application_state"]["bytes"] = archive_path.stat().st_size
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "member|SHA-256"):
                verify_manifest(manifest_path)

    def test_historical_manifest_restores_evidence_and_refuses_populated_target(self):
        from finance_dashboard.backup import restore_backup
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "finance.sqlite3"
            with sqlite3.connect(db) as connection:
                connection.execute("CREATE TABLE facts (value TEXT)")
                connection.execute("INSERT INTO facts VALUES ('retained')")
            evidence = root / "source-evidence"
            evidence.mkdir()
            (evidence / "original.csv").write_text("year,value\n2024,2\n")
            manifest = backup_local(root / "backups", source_db=db,
                evidence_roots={"source-evidence": evidence})
            manifest.pop("application_state", None)
            manifest.pop("format_version", None)
            manifest_path = next((root / "backups").glob("finance-*Z.json"))
            manifest_path.write_text(json.dumps(manifest))
            self.assertTrue(verify_manifest(manifest_path)["verified"])
            target = root / "new-empty-target"
            target.mkdir()
            restore_backup(manifest_path, target)
            self.assertEqual((target / "source-evidence/original.csv").read_text(), "year,value\n2024,2\n")
            with sqlite3.connect(target / "finance.sqlite3") as connection:
                self.assertEqual(connection.execute("SELECT value FROM facts").fetchone()[0], "retained")
            with self.assertRaisesRegex(ValueError, "empty"):
                restore_backup(manifest_path, target)
            self.assertEqual((target / "source-evidence/original.csv").read_text(), "year,value\n2024,2\n")

    @unittest.skipUnless(os.name == "posix", "Read-only WAL permissions require POSIX")
    def test_large_readonly_wal_source_finishes_without_restarting_each_batch(self):
        with TemporaryDirectory() as temp:
            root=Path(temp)
            root.chmod(0o755)
            source=root/"readonly-source"
            source.mkdir()
            out=root/"backup"
            out.mkdir(mode=0o777)
            out.chmod(0o777)
            db=source/"history.sqlite3"
            live=root/"live.sqlite3"
            writer=sqlite3.connect(live)
            writer.execute("PRAGMA journal_mode=WAL")
            writer.execute("CREATE TABLE facts (value BLOB)")
            writer.executemany("INSERT INTO facts VALUES (zeroblob(4096))",[()]*512)
            writer.commit()
            writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            # A copied/checkpointed WAL database retains sidecars without a
            # live writable shared-memory owner, as on the recovery volume.
            for suffix in ("", "-wal", "-shm"):
                (source/(db.name+suffix)).write_bytes(Path(str(live)+suffix).read_bytes())
            writer.close()
            for file in source.iterdir():
                file.chmod(0o444)
            source.chmod(0o555)
            try:
                code=("import os; "+
                    ("os.setgroups([]); os.setgid(65534); os.setuid(65534); " if os.geteuid()==0 else "")+
                    "from pathlib import Path; from finance_dashboard.backup import backup_local; "+
                    "backup_local(Path("+repr(str(out))+"), source_db=Path("+repr(str(db))+"), evidence_roots={})")
                try:
                    result=subprocess.run([sys.executable,"-c",code],capture_output=True,text=True,timeout=5)
                except subprocess.TimeoutExpired:
                    self.fail("Read-only WAL backup restarted instead of advancing beyond its first batch")
                self.assertEqual(result.returncode,0,result.stderr)
                backup=next(out.glob("finance-*Z.sqlite3"))
                with sqlite3.connect(backup) as restored:
                    self.assertEqual(restored.execute("SELECT COUNT(*) FROM facts").fetchone()[0],512)
            finally:
                source.chmod(0o755)
                for file in source.iterdir():
                    file.chmod(0o600)

    @unittest.skipUnless(os.name == "posix", "Read-only volume permissions require POSIX")
    def test_sealed_wal_backup_verifies_on_readonly_media(self):
        # A copied standalone WAL-mode database has no live WAL. Verification
        # must also work on a read-only backup volume without creating sidecars.
        with TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / "readonly-volume"
            folder.mkdir()
            db = folder / "sealed backup.sqlite3"
            with sqlite3.connect(db) as connection:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("CREATE TABLE source (value INTEGER)")
                connection.execute("INSERT INTO source VALUES (42)")
            connection.close()
            root.chmod(0o755)
            db.chmod(0o444)
            folder.chmod(0o555)
            try:
                # Root bypasses normal file permissions. Drop privileges only
                # in the child so the test exercises genuinely read-only media.
                code = ("import os; " +
                    ("os.setgroups([]); os.setgid(65534); os.setuid(65534); " if os.geteuid() == 0 else "") +
                    "from pathlib import Path; from finance_dashboard.backup import _valid_database; " +
                    "_valid_database(Path(" + repr(str(db)) + "))")
                result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(sorted(p.name for p in folder.iterdir()), [db.name])
            finally:
                folder.chmod(0o755)

    def test_original_source_files_and_metadata_survive_verified_backup(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "database.sqlite3"
            sqlite3.connect(db).close()
            evidence = root / "source-evidence"
            bundle = evidence / "wid" / "WO" / "content-hash"
            bundle.mkdir(parents=True)
            originals = {
                "WID_data_WO.csv": b"country;variable;percentile;year;value\nWO;sptincj992;p90p100;2023;0.5\n",
                "WID_metadata_WO.csv": b"country;variable;unit\nWO;sptincj992;share\n",
                "manifest.json": b'{"first_publication_vintage_verified":false}',
            }
            for name, payload in originals.items():
                (bundle / name).write_bytes(payload)
            with patch.dict(os.environ, {
                "FINANCE_SOURCE_EVIDENCE_DIR": str(evidence),
                "FINANCE_VINTAGE_DIR": str(root / "empty-vintages"),
                "FINANCE_HOLDINGS_DIR": str(root / "empty-holdings"),
                "FINANCE_SURPLUS_DIR": str(root / "empty-surplus"),
                "FINANCE_MAINTENANCE_STATE": str(root / "empty-maintenance" / "jobs.json"),
            }):
                manifest = backup_local(root / "backups", source_db=db)
            self.assertIsNotNone(manifest["evidence_archive"])
            self.assertEqual(manifest["evidence_archive"]["source_roots"], ["source-evidence"])
            archive_path = root / "backups" / manifest["evidence_archive"]["file"]
            with tarfile.open(archive_path, "r:gz") as archive:
                for name, expected in originals.items():
                    member = "source-evidence/wid/WO/content-hash/" + name
                    self.assertEqual(archive.extractfile(member).read(), expected)
            manifest_path = next((root / "backups").glob("finance-*Z.json"))
            self.assertTrue(verify_manifest(manifest_path)["verified"])

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

    def test_scheduled_refresh_yields_to_browser_sync_after_current_source(self):
        from finance_dashboard.standalone import refresh_loop, manual_sync_pending

        class OneCycle:
            def is_set(self):
                return False
            def wait(self, _seconds):
                return True

        seen = []
        def macro(_engine, *, stopped, skip_complete_pinned):
            self.assertTrue(skip_complete_pinned)
            seen.append("macro")
            self.assertFalse(stopped.is_set())
            manual_sync_pending.set()
            self.assertTrue(stopped.is_set())
            return 0

        manual_sync_pending.clear()
        try:
            with patch.dict(os.environ, {
                "FINANCE_AUTO_BACKUP": "1",
                "FINANCE_SEC_HOLDINGS_REFRESH": "0",
                "FINANCE_VINTAGE_REFRESH": "0",
            }), patch("finance_dashboard.worker.refresh_all",
                     side_effect=macro), patch(
                         "finance_dashboard.worker.refresh_market_all"
                     ) as market, patch(
                         "finance_dashboard.backup.backup_local"
                     ) as backup:
                refresh_loop(None, OneCycle(), interval_seconds=86400,
                             include_markets=True, refresh_wisesheets=False)
                self.assertEqual(seen, ["macro"])
                market.assert_not_called()
                backup.assert_not_called()
        finally:
            manual_sync_pending.clear()

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

    def test_backup_includes_and_verifies_alfred_sec_oecd_and_maintenance_evidence(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "database.sqlite3"
            sqlite3.connect(db).close()
            roots = {name: root / name for name in ("vintages","holdings","surplus","maintenance")}
            for path in roots.values():
                path.mkdir()
            (roots["vintages"] / "USREC").mkdir()
            (roots["vintages"] / "USREC" / "2008-01-31.json").write_text(
                '{"series_id":"USREC","asof":"2008-01-31"}')
            (roots["holdings"] / "sec_funds.json").write_text('[]')
            (roots["surplus"] / "oecd_iot_2025_normalized.json").write_text('{"records":[]}')
            (roots["maintenance"] / "jobs.json").write_text(
                '{"version":1,"jobs":[{"id":"test","status":"running"}]}')
            manifest = backup_local(root / "backups", source_db=db,
                                    evidence_roots=roots)
            archive_path = root / "backups" / manifest["evidence_archive"]["file"]
            self.assertEqual(manifest["evidence_archive"]["source_files"], 4)
            with tarfile.open(archive_path, "r:gz") as archive:
                self.assertEqual(sorted(archive.getnames()), [
                    "holdings/sec_funds.json",
                    "maintenance/jobs.json",
                    "surplus/oecd_iot_2025_normalized.json",
                    "vintages/USREC/2008-01-31.json"])
            manifest_path = next((root / "backups").glob("finance-*Z.json"))
            self.assertIn("evidence_archive",
                verify_manifest(manifest_path)["components"])
            archive_path.write_bytes(archive_path.read_bytes() + b"x")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                verify_manifest(manifest_path)

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
