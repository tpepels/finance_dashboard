"""Release identity, transient diagnostic reset and immutable-evidence safety."""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import json
import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from finance_dashboard.developer_logs import read_events, record_event, recent_jobs
from finance_dashboard.runtime_release import (
    activate_release, build_info, calculate_build, job_in_current_release,
    release_info,
)

A = {"version": "0.2.0", "build": "1111222233334444",
     "release_id": "0.2.0+1111222233334444"}
B = {"version": "0.2.0", "build": "5555666677778888",
     "release_id": "0.2.0+5555666677778888"}
AT_A = "2026-11-13T10:00:00+00:00"
AT_B = "2026-11-13T11:00:00+00:00"


class ReleaseStateTests(unittest.TestCase):
    def test_fingerprint_covers_backend_frontend_and_definitions_not_cache(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            pkg = root / "package"
            pkg.mkdir()
            (pkg / "main.py").write_text("x=1\n")
            (root / "site").mkdir()
            (root / "site" / "index.html").write_text("<main>old</main>")
            (root / "definitions").mkdir()
            (root / "definitions" / "chart.json").write_text('{"a":1}')
            first = calculate_build(package_dir=pkg, application_root=root)
            self.assertRegex(first["release_id"], r"^0\.2\.0\+[0-9a-f]{16}$")
            self.assertEqual(first, calculate_build(package_dir=pkg, application_root=root))
            (pkg / "__pycache__").mkdir()
            (pkg / "__pycache__" / "main.pyc").write_bytes(b"not-a-release")
            self.assertEqual(first, calculate_build(package_dir=pkg, application_root=root))
            (root / "site" / "index.html").write_text("<main>new</main>")
            second = calculate_build(package_dir=pkg, application_root=root)
            self.assertNotEqual(first["release_id"], second["release_id"])
            (pkg / "main.py").write_text("x=2\n")
            self.assertNotEqual(second["release_id"],
                                calculate_build(package_dir=pkg, application_root=root)["release_id"])

    def test_numeric_version_increases_for_every_distinct_image_but_not_restart(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "maintenance" / "active-release.json"
            events = root / "maintenance" / "events.jsonl"
            first_image = {"version": "0.2.0", "build": "aaaaaaaaaaaaaaaa",
                           "release_id": "0.2.0+aaaaaaaaaaaaaaaa"}
            next_image = {"version": "0.2.0", "build": "bbbbbbbbbbbbbbbb",
                          "release_id": "0.2.0+bbbbbbbbbbbbbbbb"}
            third_image = {"version": "0.2.0", "build": "cccccccccccccccc",
                           "release_id": "0.2.0+cccccccccccccccc"}
            with patch("finance_dashboard.runtime_release._state_path", return_value=state):
                with patch("finance_dashboard.runtime_release.build_info",
                           return_value=first_image):
                    first = activate_release(state_path=state, diagnostics_path=events,
                                             activated_at=AT_A)
                    self.assertEqual(first["version"], "0.2.1")
                    self.assertEqual(first["release_id"], "0.2.1+aaaaaaaaaaaaaaaa")
                    self.assertEqual(first["build_number"], 1)
                    self.assertEqual(release_info()["release_id"], first["release_id"])
                    events.write_text("keep-if-restarted")
                    restart = activate_release(state_path=state, diagnostics_path=events,
                                               activated_at=AT_B)
                    self.assertFalse(restart["changed"])
                    self.assertEqual(restart["version"], "0.2.1")
                    self.assertEqual(events.read_text(), "keep-if-restarted")
                with patch("finance_dashboard.runtime_release.build_info",
                           return_value=next_image):
                    second = activate_release(state_path=state, diagnostics_path=events,
                                              activated_at=AT_B)
                    self.assertEqual(second["version"], "0.2.2")
                    self.assertEqual(second["build_number"], 2)
                    self.assertEqual(events.read_text(), "")
                    self.assertEqual(release_info()["release_id"], "0.2.2+bbbbbbbbbbbbbbbb")
                with patch("finance_dashboard.runtime_release.build_info",
                           return_value=third_image):
                    third = activate_release(state_path=state, diagnostics_path=events,
                                             activated_at="2026-11-13T12:00:00+00:00")
                    self.assertEqual(third["version"], "0.2.3")
                    self.assertEqual(third["build_number"], 3)
            saved = json.loads(state.read_text())
            self.assertEqual(saved["build_number"], 3)
            self.assertEqual(saved["version"], "0.2.3")
            self.assertEqual(saved["image_build"], "cccccccccccccccc")

    def test_automatic_release_does_not_go_backward_after_source_rollback(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "release.json"
            events = root / "events.jsonl"
            newer = {"version": "0.3.0", "build": "aaaaaaaaaaaaaaaa",
                     "release_id": "0.3.0+aaaaaaaaaaaaaaaa"}
            rolled_back = {"version": "0.2.0", "build": "bbbbbbbbbbbbbbbb",
                           "release_id": "0.2.0+bbbbbbbbbbbbbbbb"}
            with patch("finance_dashboard.runtime_release.build_info", return_value=newer):
                initial = activate_release(
                    state_path=state, diagnostics_path=events, activated_at=AT_A)
            self.assertEqual(initial["version"], "0.3.1")
            with patch("finance_dashboard.runtime_release.build_info", return_value=rolled_back):
                rollback = activate_release(
                    state_path=state, diagnostics_path=events, activated_at=AT_B)
            self.assertEqual(rollback["version"], "0.3.2")

    def test_legacy_release_migrates_to_numbered_release_without_resetting_data(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "active-release.json"
            events = root / "events.jsonl"
            activate_release(identity=A, state_path=state, diagnostics_path=events,
                             activated_at=AT_A)
            with patch("finance_dashboard.runtime_release.build_info", return_value=B):
                updated = activate_release(state_path=state, diagnostics_path=events,
                                           activated_at=AT_B)
            self.assertEqual(updated["version"], "0.2.1")
            self.assertEqual(updated["build_number"], 1)

    def test_deliberate_rebuild_of_identical_sources_uses_build_nonce(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            pkg = root / "pkg"
            pkg.mkdir()
            (pkg / "module.py").write_text("enabled = True")
            with patch.dict(os.environ, {"FINANCE_BUILD_NONCE": "build-a"}):
                first = calculate_build(package_dir=pkg, application_root=root)
                self.assertEqual(first, calculate_build(package_dir=pkg, application_root=root))
            with patch.dict(os.environ, {"FINANCE_BUILD_NONCE": "build-b"}):
                second = calculate_build(package_dir=pkg, application_root=root)
            self.assertNotEqual(first["build"], second["build"])
            self.assertEqual(first["version"], second["version"])
            with patch.dict(os.environ, {"FINANCE_BUILD_NONCE": "not-a-valid-nonce!"}):
                with self.assertRaisesRegex(ValueError, "invalid_build_nonce"):
                    calculate_build(package_dir=pkg, application_root=root)

    def test_first_activation_clears_legacy_events_but_not_scientific_evidence(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / "maintenance" / "active-release.json"
            journal = root / "maintenance" / "diagnostics.jsonl"
            evidence = root / "source-evidence" / "icio" / "original.zip"
            evidence.parent.mkdir(parents=True)
            evidence.write_bytes(b"immutable-original")
            journal.parent.mkdir(parents=True)
            with patch.dict(os.environ, {"FINANCE_MAINTENANCE_STATE": str(
                    root / "maintenance" / "jobs.json")}):
                record_event("macro", "source_failed", level="error", reason="provider_failed")
                self.assertEqual(len(read_events()), 1)
                first = activate_release(identity=A, state_path=state,
                    diagnostics_path=journal, activated_at=AT_A)
                self.assertTrue(first["changed"])
                self.assertEqual(read_events(), [])
                self.assertEqual(journal.stat().st_mode & 0o777, 0o600)
                self.assertEqual(state.stat().st_mode & 0o777, 0o600)
                self.assertEqual(evidence.read_bytes(), b"immutable-original")
                record_event("macro", "source_deferred", level="warning",
                             reason="source_policy_deferred")
                self.assertEqual(len(read_events()), 1)
                again = activate_release(identity=A, state_path=state,
                    diagnostics_path=journal, activated_at=AT_B)
                self.assertFalse(again["changed"])
                self.assertEqual(again["activated_at"], AT_A)
                self.assertEqual(len(read_events()), 1)
                changed = activate_release(identity=B, state_path=state,
                    diagnostics_path=journal, activated_at=AT_B)
                self.assertTrue(changed["changed"])
                self.assertEqual(read_events(), [])
                self.assertEqual(evidence.read_bytes(), b"immutable-original")
                marker = json.loads(state.read_text())
                self.assertEqual(marker["release_id"], B["release_id"])
                self.assertEqual(marker["activated_at"], AT_B)

    def test_active_release_filters_past_job_reports_without_deleting_journal(self):
        jobs = [
            {"id": "new", "action": "sync_history", "status": "complete",
             "created_at": "2026-11-13T11:30:00+00:00"},
            {"id": "old", "action": "sync_history", "status": "failed",
             "created_at": "2026-11-12T11:30:00+00:00"},
        ]
        self.assertTrue(job_in_current_release(jobs[0]["created_at"], active_since=AT_B))
        self.assertFalse(job_in_current_release(jobs[1]["created_at"], active_since=AT_B))
        self.assertFalse(job_in_current_release("2026-11-12T12:00:00", active_since=AT_B))
        self.assertEqual([x["id"] for x in recent_jobs(jobs, since=AT_B)], ["new"])
        self.assertEqual(len(jobs), 2)

    def test_release_reset_rejects_diagnostic_symlinks(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "protected.txt"
            target.write_text("must survive")
            journal = root / "diagnostics.jsonl"
            journal.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "symlink"):
                activate_release(identity=A, state_path=root / "release.json",
                                 diagnostics_path=journal, activated_at=AT_A)
            self.assertEqual(target.read_text(), "must survive")
            self.assertFalse((root / "release.json").exists())

    def test_debug_api_and_csv_source_report_use_exact_running_version(self):
        from fastapi.testclient import TestClient
        from sqlalchemy import create_engine
        from sqlalchemy.pool import StaticPool
        from finance_dashboard.api import create_app
        from finance_dashboard.database import Base

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "immutable-build.json"
            manifest.write_text(json.dumps({"schema_version": 1, **A}))
            with patch.dict(os.environ, {
                "FINANCE_RELEASE_MANIFEST": str(manifest),
                "FINANCE_MAINTENANCE_STATE": str(root / "maintenance" / "jobs.json"),
                "FINANCE_ORIGINAL_IMPORT_JOURNAL": str(root / "maintenance" / "original-imports.json"),
                "FINANCE_ORIGINAL_UPLOAD_DIR": str(root / "incoming"),
                "FINANCE_SOURCE_EVIDENCE_DIR": str(root / "evidence"),
                "FINANCE_DASHBOARD_UI_DIR": "",
                "FINANCE_AUTO_REFRESH": "0",
            }):
                build_info.cache_clear()
                try:
                    activation = activate_release(activated_at=AT_A)
                    self.assertEqual(activation["version"], "0.2.1")
                    expected_release_id = activation["release_id"]
                    record_event("sync", "finished", status="complete", action="sync_history")
                    legacy = {"id":"pre-release", "action":"sync_current", "status":"complete",
                              "created_at":"2026-11-12T10:00:00+00:00"}
                    (root / "maintenance" / "jobs.json").write_text(json.dumps({
                        "version": 1, "jobs": [legacy]}))
                    (root / "maintenance" / "original-imports.json").write_text(json.dumps({
                        "version": 1, "jobs": [{**legacy, "filename":"2011-2015_EXT.zip"}]}))
                    engine = create_engine("sqlite+pysqlite:///:memory:",
                        connect_args={"check_same_thread": False}, poolclass=StaticPool)
                    Base.metadata.create_all(engine)
                    try:
                        with TestClient(create_app(engine)) as client:
                            status = client.get("/api/diagnostics")
                            self.assertEqual(status.status_code, 200)
                            self.assertEqual(status.json()["release"]["release_id"], expected_release_id)
                            self.assertEqual(status.json()["status"]["release_id"], expected_release_id)
                            self.assertEqual(status.json()["console"][-1]["level"], "info")
                            developer = client.get("/api/developer-log")
                            self.assertEqual(developer.status_code, 200)
                            self.assertEqual(developer.json()["release"]["activated_at"], AT_A)
                            self.assertEqual(developer.json()["events"][-1]["event"], "finished")
                            coverage = client.get("/api/source-coverage")
                            self.assertEqual(coverage.status_code, 200)
                            self.assertEqual(coverage.json()["release"]["release_id"], expected_release_id)
                            maintenance = client.get("/api/maintenance").json()
                            imports = client.get("/api/originals").json()
                            self.assertEqual(maintenance["release"]["release_id"], expected_release_id)
                            self.assertEqual(imports["release"]["release_id"], expected_release_id)
                            self.assertEqual(maintenance["jobs"], [])
                            self.assertEqual(imports["jobs"], [])
                            self.assertTrue((root / "maintenance" / "jobs.json").is_file())
                            self.assertTrue((root / "maintenance" / "original-imports.json").is_file())
                            self.assertEqual(client.get("/api/diagnostics/download").status_code, 202)
                            prep = client.post("/api/diagnostics/prepare",
                                               headers={"X-GCM-Action": "dashboard"})
                            self.assertEqual(prep.status_code, 202)
                            deadline = time.monotonic() + 15
                            state = None
                            while time.monotonic() < deadline:
                                state = client.get("/api/diagnostics/export-status").json()
                                if state["state"] != "preparing":
                                    break
                                time.sleep(.05)
                            self.assertEqual(state["state"], "ready", state)
                            export = client.get("/api/diagnostics/export-file")
                            self.assertEqual(export.status_code, 200)
                            from urllib.parse import unquote
                            self.assertIn(expected_release_id,
                                          unquote(export.headers["content-disposition"]))
                            with ZipFile(BytesIO(export.content)) as archive:
                                meta = json.loads(archive.read("diagnostics/release.json"))
                                self.assertEqual(meta["release_id"], expected_release_id)
                                self.assertTrue(meta["immutable_evidence_preserved"])
                                self.assertIn(expected_release_id, archive.read("README.txt").decode())
                                self.assertEqual(json.loads(archive.read(
                                    "diagnostics/status.json"))["release_id"], expected_release_id)
                                self.assertIn("diagnostics/icio-accounting-failures.csv",
                                              archive.namelist())
                                failure_manifest = json.loads(archive.read(
                                    "diagnostics/icio-accounting-failures-manifest.json"))
                                self.assertTrue(failure_manifest["complete_for_exported_matrices"])
                                self.assertEqual(failure_manifest["failure_equations_exported"], 0)
                                self.assertIn(expected_release_id, archive.read(
                                    "diagnostics/icio-accounting-failures-manifest.json").decode())
                                self.assertIn("signed_residual_usd_million", archive.read(
                                    "diagnostics/icio-accounting-failures.csv").decode())
                    finally:
                        engine.dispose()
                finally:
                    build_info.cache_clear()


if __name__ == "__main__":
    unittest.main()
