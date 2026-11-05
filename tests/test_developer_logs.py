"""Bounded and redacted developer logs exposed only as safe structured metadata."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from finance_dashboard.api import create_app
from finance_dashboard.catalog import load_documents
from finance_dashboard.database import Base
from finance_dashboard.developer_logs import record_event, read_events, recent_jobs, MAX_EVENTS


class DiagnosticJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.path = Path(self.temp.name) / "maintenance" / "jobs.json"
        self.env = patch.dict(os.environ, {
            "FINANCE_MAINTENANCE_STATE": str(self.path),
            "FINANCE_AUTO_REFRESH": "0",
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_source_failure_and_sync_lifecycle_persist_without_secrets(self):
        record_event("sync", "started", action="sync_history", job_id="aabb22",
                     status="running")
        record_event("macro", "source_failed", level="error",
                     source_id="valuation.us.cape", reason="source_invalid")
        record_event("alfred", "stage_finished", level="warning",
                     reason="fred_api_key_rejected", http_status=400,
                     status="blocked")
        record_event("macro", "source_failed", level="error",
                     source_id="valuation.us.cape", reason="api_key=VERYSECRET")
        events = read_events()
        self.assertEqual(len(events), 4)
        self.assertEqual(events[1]["reason"], "source_invalid")
        self.assertEqual(events[2]["http_status"], 400)
        self.assertNotIn("reason", events[3])
        path = self.path.parent / "diagnostics.jsonl"
        self.assertTrue(path.is_file())
        self.assertNotIn("VERYSECRET", path.read_text(encoding="utf-8"))
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_canonical_policy_deferral_is_retained_as_safe_event(self):
        record_event("macro", "source_deferred", level="warning",
                     source_id="policy_rate.us.fed_upper",
                     reason="source_policy_deferred", status="deferred")
        events = read_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "source_deferred")
        self.assertEqual(events[0]["status"], "deferred")
        self.assertEqual(events[0]["reason"], "source_policy_deferred")

    def test_event_count_is_bounded_and_oldest_are_removed(self):
        for i in range(MAX_EVENTS + 7):
            record_event("macro", "source_failed", level="warning",
                         source_id="source_%03d" % i, reason="source_invalid")
        events = read_events(limit=MAX_EVENTS)
        self.assertEqual(len(events), MAX_EVENTS)
        self.assertEqual(events[0]["source_id"], "source_007")
        self.assertEqual(events[-1]["source_id"], "source_406")

    def test_recent_job_export_omits_options_raw_results_and_urls(self):
        jobs = [{
            "id": "abc001", "action": "sync_history", "status": "partial",
            "created_at": "2026-11-03T14:00:00Z",
            "options": {"api_key": "never-report-this"},
            "result": {"provider_response": "never-report-this",
                       "parts": {
                           "alfred": {"status": "blocked",
                                      "reason": "fred_bad_request",
                                      "http_status": 400,
                                      "first_failed_series":"SAHMREALTIME",
                                      "first_failed_asof":"2000-01-31",
                                      "first_failed_reason":"fred_server_error",
                                      "failures_in_run":2,
                                      "body": "never-report-this"},
                           "sec": {"status": "partial", "funds": [{
                               "id": "vt", "status": "partial", "stored": 2,
                               "errors": 1, "examined":120, "candidates":140,
                               "unexamined":20, "first_error_reason":"sec_holdings_xml_invalid",
                               "missing_verified_xml":4, "other_series_skipped":79,
                               "url": "https://example/never-report-this",
                           }]},
                       }},
        }]
        safe = recent_jobs(jobs)
        self.assertEqual(safe[0]["parts"]["alfred"]["http_status"], 400)
        self.assertEqual(safe[0]["parts"]["alfred"]["first_failed_series"],
                         "SAHMREALTIME")
        self.assertEqual(safe[0]["parts"]["alfred"]["first_failed_asof"],
                         "2000-01-31")
        self.assertEqual(safe[0]["parts"]["alfred"]["first_failed_reason"],
                         "fred_server_error")
        self.assertEqual(safe[0]["parts"]["alfred"]["failures_in_run"],2)
        self.assertEqual(safe[0]["parts"]["sec"]["funds"][0]["stored"], 2)
        self.assertEqual(safe[0]["parts"]["sec"]["funds"][0]["unexamined"],20)
        self.assertEqual(safe[0]["parts"]["sec"]["funds"][0]["first_error_reason"],
                         "sec_holdings_xml_invalid")
        self.assertNotIn("never-report-this", json.dumps(safe))

    def test_unexpected_api_exception_logs_only_generic_error(self):
        engine = create_engine("sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread":False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        try:
            # The test-only failing endpoint must not be shadowed by the built
            # static dashboard mount (present in the production Docker image).
            with patch.dict(os.environ, {"FINANCE_DASHBOARD_UI_DIR": ""}):
                app = create_app(engine)
            @app.get("/api/test-failure")
            def _unsafe_failure():
                raise RuntimeError("user-token-secret-123")
            with TestClient(app, raise_server_exceptions=False) as client:
                result = client.get("/api/test-failure")
                self.assertEqual(result.status_code, 500)
                log = client.get("/api/developer-log").json()
            event = next(x for x in log["events"]
                         if x.get("stage") == "api")
            self.assertEqual(event["reason"], "internal_error")
            self.assertNotIn("user-token-secret-123", json.dumps(log))
            self.assertNotIn("/api/test-failure", json.dumps(log))
        finally:
            engine.dispose()

    def test_live_endpoint_contains_safe_jobs_issues_and_events(self):
        engine = create_engine("sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread":False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        try:
            record_event("macro", "source_failed", level="warning",
                         source_id="credit_gap.us.bis", reason="source_invalid")
            with TestClient(create_app(engine)) as client:
                result = client.get("/api/developer-log")
                self.assertEqual(result.status_code, 200, result.text)
                obj = result.json()
                self.assertEqual(obj["schema_version"], 1)
                self.assertIn(obj["configuration"]["fred_mode"],
                              ("authenticated_api","public_csv","public_table"))
                self.assertIsInstance(obj["configuration"]["fred_key_present"],bool)
                self.assertEqual(obj["coverage"]["registered"], len(load_documents()[0]["series"]) + 27)
                self.assertTrue(obj["issues"])
                self.assertEqual(obj["events"][-1]["source_id"], "credit_gap.us.bis")
                self.assertIsInstance(obj["jobs"], list)
                self.assertNotIn("FINANCE_MAINTENANCE_STATE", result.text)
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
