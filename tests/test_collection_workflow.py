"""Collection lifecycle, persistence and non-blocking diagnostic regressions."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Lock
from unittest.mock import patch
from zipfile import ZipFile
import time
import unittest

from finance_dashboard.collection_workflow import CollectionWorkflow, SourceHealthCache
from finance_dashboard.diagnostic_exports import DiagnosticExportManager


def wait_for(predicate, timeout=4):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if predicate():
            return True
        time.sleep(.01)
    return False


SPECS = {
    "wid-world": {
        "title": "WID.world", "roles": [
            {"id": "data", "label": "WID observations",
             "download_url": "https://wid.world/bulk_download/WID_data_WO.csv",
             "accept": ".csv", "max_bytes": 10_000},
            {"id": "metadata", "label": "WID metadata",
             "download_url": "https://wid.world/bulk_download/WID_metadata_WO.csv",
             "accept": ".csv", "max_bytes": 10_000},
        ],
    },
}


class StubManual:
    def __init__(self):
        self.lock = Lock()
        self.jobs = []
        self.next_id = 0
        self.fetch_calls = 0

    def fetch(self, browser=None):
        self.fetch_calls += 1
        self.next_id += 1
        ident = f"{self.next_id:032x}"
        with self.lock:
            self.jobs.append({
                "id": ident, "dataset": "wid-world", "status": "downloading",
                "error_code": None, "phase": "downloading",
                "downloaded": {}, "attempts": [], "sources": [],
                "failed_roles": {},
            })
        return {"jobs": [{"dataset": "wid-world", "job_id": ident}], "skipped": {}}


class StubMaintenance:
    def __init__(self):
        self.jobs = []
        self.calls = 0

    def submit(self, action, options, *, valid_sources, valid_markets):
        self.calls += 1
        job = {"id": f"repair-{self.calls}", "status": "running",
               "action": action, "completed": 6, "total": 17}
        self.jobs = [job]
        return job

    def list(self):
        return {"jobs": self.jobs, "active_job_id": self.jobs[0]["id"] if self.jobs else None}


class CollectionWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_collection_is_idempotent_while_active_and_recovers_manual_fallback_after_restart(self):
        manual = StubManual()
        maintenance = StubMaintenance()
        path = self.root / "collection.json"
        with patch("finance_dashboard.manual_sources.source_specs", return_value=SPECS):
            manager = CollectionWorkflow(manual, maintenance, path=path,
                                         valid_sources=set(), valid_markets=set())
            started = manager.start({"language": "en-US", "cookie": "excluded"})
            self.assertEqual(started["state"], "running", started)
            self.assertEqual(started["counts"]["total"], 1)
            self.assertEqual(started["repair"]["completed"], 6)
            self.assertEqual(started["sources"][0]["status"], "downloading")
            again = manager.start()
        self.assertEqual(again["id"], started["id"])
        self.assertEqual(manual.fetch_calls, 1)
        self.assertEqual(maintenance.calls, 1)
        with manual.lock:
            manual.jobs[0].update(
                status="manual_required", phase="waiting_for_manual_files",
                error_code="publisher_files_unavailable",
                failed_roles={"metadata": "publisher_http_403"})
        maintenance.jobs[0]["status"] = "complete"
        recovered = CollectionWorkflow(manual, maintenance, path=path,
                                       valid_sources=set(), valid_markets=set())
        snapshot = recovered.status()
        self.assertEqual(snapshot["id"], started["id"])
        self.assertFalse(snapshot["running"])
        self.assertEqual(snapshot["state"], "needs_attention")
        self.assertEqual(len(snapshot["manual_files"]), 1)
        self.assertEqual(snapshot["manual_files"][0]["name"], "WID metadata")
        self.assertEqual(snapshot["manual_files"][0]["role"], "metadata")
        with manual.lock:
            manual.jobs[0].update(status="complete", failed_roles={})
        self.assertEqual(recovered.status()["state"], "complete")
        with patch("finance_dashboard.manual_sources.source_specs", return_value=SPECS):
            new_run = recovered.start()
        self.assertNotEqual(new_run["id"], started["id"])
        self.assertEqual(manual.fetch_calls, 2)

    def test_health_build_is_non_blocking_and_snapshot_survives_restart(self):
        entered, release = Event(), Event()
        called = []
        def expensive():
            entered.set()
            release.wait(3)
            called.append(1)
            return {"asof": "2026-11-14", "summary": {
                "macro": {"total": 3, "with_data": 2, "needs_attention": 1},
                "markets": {"total": 1, "with_data": 1, "needs_attention": 0},
                "fx": {"total": 1, "with_data": 1, "needs_attention": 0}}}
        cache = SourceHealthCache(expensive, path=self.root / "health.json")
        start = time.monotonic()
        status = cache.status()
        self.assertLess(time.monotonic() - start, 1)
        self.assertEqual(status["state"], "refreshing")
        self.assertTrue(entered.wait(2))
        self.assertIsNone(status["snapshot"])
        release.set()
        self.assertTrue(wait_for(lambda: cache.status()["state"] == "ready"))
        self.assertEqual(cache.status()["snapshot"]["sources"]["with_data"], 4)
        restarted = SourceHealthCache(expensive, path=self.root / "health.json")
        self.assertEqual(restarted.status()["snapshot"]["sources"]["total"], 5)
        self.assertEqual(len(called), 1)

    def test_export_preparation_is_nonblocking_persistent_and_cached(self):
        entered, release = Event(), Event()
        calls = []
        def expensive_zip():
            entered.set()
            release.wait(3)
            calls.append(1)
            data = BytesIO()
            with ZipFile(data, "w") as archive:
                archive.writestr("diagnostics/source-coverage.json", "{}")
                archive.writestr("diagnostics/source-audit.csv", "source,status\n")
            return data.getvalue()
        archive = self.root / "export.zip"
        state = self.root / "export.json"
        manager = DiagnosticExportManager(
            expensive_zip, zip_path=archive, state_path=state, lifetime=900)
        before = time.monotonic()
        pending = manager.prepare()
        self.assertLess(time.monotonic() - before, 1)
        self.assertEqual(pending["state"], "preparing")
        self.assertFalse(pending["ready"])
        self.assertTrue(entered.wait(2))
        self.assertIsNone(manager.ready_file())
        release.set()
        self.assertTrue(wait_for(lambda: manager.status()["ready"]))
        self.assertEqual(manager.status()["state"], "ready")
        self.assertTrue(archive.is_file())
        with ZipFile(archive) as document:
            self.assertIn("diagnostics/source-audit.csv", document.namelist())
        after_restart = DiagnosticExportManager(
            expensive_zip, zip_path=archive, state_path=state, lifetime=900)
        self.assertTrue(after_restart.status()["ready"])
        self.assertEqual(after_restart.prepare()["id"], pending["id"])
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
