"""Durable, secret-free traceback evidence for failed collection after deployment."""
from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from finance_dashboard.failure_journal import read_failures, record_failure
from finance_dashboard.runtime_release import activate_release


A = {"version":"0.2.9", "build":"1234567890abcdef",
     "release_id":"0.2.9+1234567890abcdef"}
B = {"version":"0.2.10", "build":"fedcba0987654321",
     "release_id":"0.2.10+fedcba0987654321"}


def internal_exception():
    # Dynamic code's raw filename is intentionally credential-bearing.
    # It must never reach exported diagnostic provenance.
    module = {"__name__":"finance_dashboard.simulated_collector",
              "__builtins__":__builtins__}
    exec(compile('def boom():\n  raise RuntimeError("SECRET_TOKEN=abc123 https://secret.host/?api_key=abc123")\n',
                 "/home/private/SECRET_TOKEN=abc123/source.py", "exec"), module)
    try:
        module["boom"]()
    except RuntimeError as exc:
        return exc
    raise AssertionError("exception not raised")


class DurableFailureJournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "maintenance" / "failure-journal.json"
        patcher = patch.dict(os.environ, {
            "FINANCE_FAILURE_JOURNAL_PATH": str(self.path),
            "FINANCE_MAINTENANCE_STATE": str(self.root / "maintenance" / "jobs.json"),
        })
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_retains_exact_safe_application_code_path_without_secrets(self):
        exc = internal_exception()
        with patch("finance_dashboard.runtime_release.release_info",
                   return_value=A):
            result = record_failure("macro", "rotation_query", exc,
                                    series_id="piketty.us.real_pretax_average.all")
        self.assertTrue(result["persisted"])
        self.assertEqual(result["stage"], "rotation_query")
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        journal = read_failures()
        self.assertEqual(journal["state"], "ready")
        row = journal["failures"][0]
        self.assertEqual(row["release_id"], A["release_id"])
        self.assertEqual(row["exception_type"], "RuntimeError")
        self.assertEqual(row["stage"], "rotation_query")
        self.assertEqual(row["count"], 1)
        self.assertEqual(row["example_series_ids"],
                         ["piketty.us.real_pretax_average.all"])
        self.assertTrue(any(frame["module"]=="finance_dashboard.simulated_collector"
                            and frame["function"]=="boom" and frame["line"]==2
                            for frame in row["frames"]))
        for forbidden in ("SECRET_TOKEN", "abc123", "secret.host", "/home/private",
                          "api_key", "RuntimeError("):
            self.assertNotIn(forbidden, json.dumps(journal))

    def test_same_signature_aggregates_and_still_tracks_separate_source_samples(self):
        exc=internal_exception()
        with patch("finance_dashboard.runtime_release.release_info", return_value=A):
            first=record_failure("macro","execute_source_task",exc,series_id="source.first")
            second=record_failure("macro","execute_source_task",exc,series_id="source.second")
        self.assertEqual(first["id"],second["id"])
        rows=read_failures()["failures"]
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["count"],2)
        self.assertEqual(rows[0]["example_series_ids"],["source.first","source.second"])

    def test_previous_release_failure_survives_event_truncation(self):
        exc=internal_exception()
        with patch("finance_dashboard.runtime_release.release_info",return_value=A):
            record_failure("scheduler","macro",exc)
        state=self.root/"maintenance"/"active-release.json"
        events=self.root/"maintenance"/"diagnostics.jsonl"
        events.write_text("old events")
        activate_release(identity=A,state_path=state,diagnostics_path=events,
                         activated_at="2026-11-14T21:50:00+00:00")
        self.assertEqual(events.read_text(),"")
        activate_release(identity=B,state_path=state,diagnostics_path=events,
                         activated_at="2026-11-14T22:59:00+00:00")
        journal=read_failures()
        self.assertEqual(journal["failures"][0]["release_id"],A["release_id"])
        self.assertEqual(journal["failures"][0]["stage"],"macro")
        with patch("finance_dashboard.runtime_release.release_info",return_value=B):
            record_failure("scheduler","backup",exc)
        self.assertEqual({r["release_id"] for r in read_failures()["failures"]},
                         {A["release_id"],B["release_id"]})

    def test_invalid_or_symlink_journal_reports_failure_explicitly_without_overwrite(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.path.write_text('{"secret": "KEEP_ME", "failures": []}')
        self.assertEqual(read_failures()["state"],"invalid")
        self.assertNotIn("KEEP_ME",json.dumps(read_failures()))
        result=record_failure("macro","planner",internal_exception())
        self.assertFalse(result["persisted"])
        self.assertIn("KEEP_ME",self.path.read_text())
        self.path.unlink()
        target=self.root/"protected"
        target.write_text("do-not-overwrite")
        self.path.symlink_to(target)
        result=record_failure("macro","planner",internal_exception())
        self.assertFalse(result["persisted"])
        self.assertEqual(target.read_text(),"do-not-overwrite")
        self.assertEqual(read_failures()["state"],"invalid")

    def test_exception_cause_database_code_and_http_status_are_typed_only(self):
        class SecretDatabaseError(Exception):
            sqlite_errorname="SQLITE_BUSY"
        exc=RuntimeError("secret password")
        exc.orig=SecretDatabaseError("DATABASE_URL=hidden")
        exc.response=type("Response",(),{"status_code":503})()
        with patch("finance_dashboard.runtime_release.release_info",return_value=A):
            record_failure("macro","rotation_query",exc)
        row=read_failures()["failures"][0]
        self.assertEqual(row["codes"]["sqlite_errorname"],"SQLITE_BUSY")
        self.assertEqual(row["codes"]["http_status"],503)
        self.assertEqual(row["causes"],["SecretDatabaseError"])
        self.assertNotIn("hidden",json.dumps(row))
        self.assertNotIn("password",json.dumps(row))


if __name__=="__main__":
    unittest.main()
