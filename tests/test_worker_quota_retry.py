"""A scheduled refresh resumes quota-deferred sources once the window reopens."""
import time
import unittest
from unittest.mock import patch

from finance_dashboard.source_policy_types import PolicyDeferred
from finance_dashboard.worker import RefreshTask, execute_refresh_tasks, retry_quota_deferred


class Stop:
    def __init__(self):
        self.flag = False
    def is_set(self):
        return self.flag


def quota_task(sid, calls, *, defer_times, group="OECD", retry_in=0.05):
    state = {"n": 0}
    def run():
        calls.append(sid)
        state["n"] += 1
        if state["n"] <= defer_times:
            raise PolicyDeferred("oecd-sdmx", "rolling_window_limit", time.time() + retry_in)
        return {"received": 1, "versions_added": 0}
    return RefreshTask("macro", sid, run, sid, provider_group=group)


class QuotaRetryTests(unittest.TestCase):
    def test_deferred_and_suppressed_tasks_are_reported_for_retry(self):
        calls, deferred = [], []
        tasks = [quota_task("a", calls, defer_times=1), quota_task("b", calls, defer_times=0)]
        with patch("finance_dashboard.worker.record_event"):
            failed = execute_refresh_tasks(tasks, deferred=deferred)
        self.assertEqual(failed, 2)
        self.assertEqual(calls, ["a"])  # b was suppressed, never requested
        self.assertEqual([task.source_id for task, _ in deferred], ["a", "b"])
        self.assertTrue(all(retry_at > 0 for _, retry_at in deferred))

    def test_retry_serves_every_deferred_source_after_the_window(self):
        calls, deferred = [], []
        tasks = [quota_task("a", calls, defer_times=1), quota_task("b", calls, defer_times=0)]
        with patch("finance_dashboard.worker.record_event"):
            failed = execute_refresh_tasks(tasks, deferred=deferred)
            failed = retry_quota_deferred(deferred, failed, budget_seconds=5,
                                          stopped=Stop(), poll_seconds=0.01)
        self.assertEqual(failed, 0)
        self.assertEqual(calls, ["a", "a", "b"])

    def test_retry_never_waits_beyond_its_budget(self):
        calls, deferred = [], []
        tasks = [quota_task("a", calls, defer_times=9, retry_in=3600)]
        with patch("finance_dashboard.worker.record_event"):
            failed = execute_refresh_tasks(tasks, deferred=deferred)
            start = time.monotonic()
            failed = retry_quota_deferred(deferred, failed, budget_seconds=1,
                                          stopped=Stop(), poll_seconds=0.01)
        self.assertLess(time.monotonic() - start, 0.5)
        self.assertEqual(failed, 1)
        self.assertEqual(calls, ["a"])

    def test_a_manual_collection_stops_the_wait(self):
        calls, deferred = [], []
        stop = Stop()
        tasks = [quota_task("a", calls, defer_times=1, retry_in=0.5)]
        with patch("finance_dashboard.worker.record_event"):
            failed = execute_refresh_tasks(tasks, deferred=deferred)
            stop.flag = True
            failed = retry_quota_deferred(deferred, failed, budget_seconds=5,
                                          stopped=stop, poll_seconds=0.01)
        self.assertEqual(failed, 1)
        self.assertEqual(calls, ["a"])

    def test_other_deferral_reasons_are_not_retried(self):
        calls, deferred = [], []
        def run():
            calls.append("x")
            raise PolicyDeferred("oecd-sdmx", "operator_acknowledgement_required", time.time())
        with patch("finance_dashboard.worker.record_event"):
            execute_refresh_tasks([RefreshTask("macro", "x", run, "x", provider_group="OECD")],
                                  deferred=deferred)
        self.assertEqual(deferred, [])


class QuotaRetryBudgetTests(unittest.TestCase):
    def test_default_and_bounds(self):
        from finance_dashboard.standalone import quota_retry_budget
        with patch.dict("os.environ", {}, clear=False) as env:
            env.pop("FINANCE_QUOTA_RETRY_SECONDS", None)
            self.assertEqual(quota_retry_budget(), 14400)
        with patch.dict("os.environ", {"FINANCE_QUOTA_RETRY_SECONDS": "0"}):
            self.assertEqual(quota_retry_budget(), 0)
        for bad in ("-1", "50000", "soon"):
            with patch.dict("os.environ", {"FINANCE_QUOTA_RETRY_SECONDS": bad}):
                with self.assertRaises(ValueError):
                    quota_retry_budget()


if __name__ == "__main__":
    unittest.main()
