"""A publisher rate refusal must not crash the remaining-source audit."""
from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from finance_dashboard.source_policy_types import PolicyDeferred
from finance_dashboard.worker import RefreshTask, execute_refresh_tasks


class PublisherQuotaTests(unittest.TestCase):
    def test_suppressed_sources_report_complete_bounded_diagnostics_without_crash(self):
        calls = []
        progress = []

        def deferred():
            calls.append("wid-first")
            raise PolicyDeferred("wid", "rolling_window_limit", time.time() + 90)

        def must_not_run():
            calls.append("wid-unattempted")
            raise AssertionError("Exhausted publisher must be skipped")

        def unrelated():
            calls.append("fred")
            return {"status": "success", "received": 1}

        tasks = [
            RefreshTask("macro", "inequality.world.pretax_income.top1",
                        deferred, "world-1", provider_group="WID"),
            RefreshTask("macro", "inequality.world.pretax_income.top10",
                        must_not_run, "world-2", provider_group="WID"),
            RefreshTask("macro", "inequality.world.net_personal_wealth.top10",
                        must_not_run, "world-3", provider_group="WID"),
            RefreshTask("macro", "bond.us.nominal_10y",
                        unrelated, "unrelated", provider_group="FRED"),
        ]
        with patch("finance_dashboard.worker.record_event", autospec=True) as log:
            failed = execute_refresh_tasks(tasks, progress=lambda *p: progress.append(p))
        self.assertEqual(failed, 3)
        self.assertEqual(calls, ["wid-first", "fred"])
        self.assertEqual(len(progress), 4)
        self.assertEqual(progress[-1], (4, 4, "unrelated"))
        self.assertTrue(any(
            call.args[:2] == ("macro", "stage_finished")
            and call.kwargs.get("action") == "publisher_quota_exhausted"
            and call.kwargs.get("stage") == "WID"
            and call.kwargs.get("failed") == 2
            for call in log.call_args_list))
        self.assertFalse(any(
            "provider" in call.kwargs or "sources_not_attempted" in call.kwargs
            for call in log.call_args_list))


if __name__ == "__main__":
    unittest.main()
