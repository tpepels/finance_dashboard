"""Bounded read-only policy preflights, journal preservation and source proof deltas."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from finance_dashboard.phase2_sweep_journal import (
    Phase2SweepJournal, sweep_context,
)
from finance_dashboard.phase2_workflow import (
    run_source_acquisition_batch, source_evidence_delta,
)


def task(name, provider="FRED", policy="fred-v1"):
    return {"id": name, "state": "acquisition_candidate",
            "publisher_policy": policy, "provider": provider}


class VirtualClock:
    def __init__(self):
        self.value = 1000.0
        self.sleeps = []

    def __call__(self):
        return self.value

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.value += seconds

    def advance(self, seconds):
        self.value += seconds


class PreflightBatchTests(unittest.TestCase):
    def test_deferred_source_does_not_spend_attempt_or_journal_and_can_resume(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp) / "acquisition"
            ctx = sweep_context(["fred", "bis"], "0" * 64, "1" * 64)
            observed = []
            with Phase2SweepJournal(folder, context=ctx, create=True) as journal:
                result = run_source_acquisition_batch(
                    [task("fred"), task("bis", "BIS_TOTAL_CREDIT", "bis")],
                    lambda sid, *, full: observed.append(sid) or {
                        "status": "success", "received": 1,
                        "versions_added": 0},
                    max_attempts=2, stop_scope="publisher", journal=journal,
                    policy_preflight=lambda a: (
                        {"state": "deferred", "reason": "rolling_window_limit",
                         "retry_at": 2000}
                        if a["id"] == "fred" else {"state": "ready"}),
                )
                self.assertEqual(result["attempted"], 1)
                self.assertEqual(result["policy_preflight_deferred"], 1)
                self.assertEqual(observed, ["bis"])
                self.assertEqual(journal.summary()["tracked_attempts"], 1)
                self.assertEqual(result["results"][0]["status"],
                                 "deferred_policy_preflight")
            with Phase2SweepJournal(folder, context=ctx, create=False) as journal:
                result = run_source_acquisition_batch(
                    [task("fred"), task("bis", "BIS_TOTAL_CREDIT", "bis")],
                    lambda sid, *, full: observed.append(sid) or {
                        "status": "success", "received": 1,
                        "versions_added": 0},
                    max_attempts=2, stop_scope="publisher", journal=journal,
                    policy_preflight=lambda a: {"state": "ready"},
                )
                self.assertEqual(result["attempted"], 1)
                self.assertEqual(result["succeeded"], 1)
                self.assertEqual(result["results"][1]["status"],
                                 "deferred_prior_attempt")
                self.assertEqual(journal.summary()["tracked_attempts"], 2)
                self.assertEqual(observed, ["bis", "fred"])

    def test_bound_wait_schedules_other_publisher_before_waiting(self):
        clock = VirtualClock()
        starts = []
        def preflight(action):
            if action["id"] == "fred" and clock() < 1005:
                return {"state": "deferred", "reason": "minimum_spacing",
                        "retry_at": 1005.0}
            return {"state": "ready"}
        def acquire(sid, *, full):
            starts.append((sid, clock()))
            return {"status": "success", "received": 2,
                    "versions_added": 1}
        result = run_source_acquisition_batch(
            [task("fred"), task("other", "BIS_TOTAL_CREDIT", "bis")],
            acquire, max_attempts=2, stop_scope="publisher",
            policy_preflight=preflight, max_wait_seconds=10,
            clock=clock, sleep=clock.sleep)
        self.assertEqual(result["attempted"], 2)
        self.assertEqual([sid for sid, _ in starts], ["other", "fred"])
        self.assertEqual(starts[1][1], 1005.0)
        self.assertEqual(result["policy_wait_seconds"], 5.0)
        self.assertEqual(result["succeeded"], 2)
        self.assertIsNone(result["next_policy_retry_at"])

    def test_wait_budget_does_not_retry_blocked_source_or_overrun(self):
        clock = VirtualClock()
        seen = []
        tasks = [task("restricted", "OECD_CLI", "oecd-sdmx"),
                 task("future", "BIS_DSR", "bis"),
                 task("independent", "FRED", "fred-v1")]
        def peek(action):
            if action["id"] == "restricted":
                return {"state": "blocked",
                        "reason": "direct_network_origin_not_confirmed"}
            if action["id"] == "future":
                return {"state": "deferred", "reason": "rolling_window_limit",
                        "retry_at": 9000}
            return {"state": "ready"}
        result = run_source_acquisition_batch(
            tasks, lambda sid, *, full: seen.append(sid) or {
                "status": "success", "received": 1, "versions_added": 0},
            max_attempts=3, stop_scope="publisher",
            policy_preflight=peek, max_wait_seconds=4,
            clock=clock, sleep=clock.sleep)
        self.assertEqual(seen, ["independent"])
        self.assertEqual(result["attempted"], 1)
        self.assertEqual(result["policy_preflight_blocked"], 1)
        self.assertEqual(result["policy_preflight_deferred"], 1)
        self.assertEqual(result["next_policy_retry_at"], 9000)
        self.assertEqual(result["policy_wait_seconds"], 0)
        self.assertEqual(clock(), 1000)
        self.assertEqual([x["status"] for x in result["results"]], [
            "deferred_policy_blocked", "deferred_policy_preflight",
            "success"])

    def test_legacy_executor_still_does_not_require_budget_preflight(self):
        calls = []
        output = run_source_acquisition_batch(
            [task("a"), task("b")],
            lambda sid, *, full: calls.append(sid) or {
                "status": "success", "received": 4, "versions_added": 2},
            max_attempts=2)
        self.assertEqual(calls, ["a", "b"])
        self.assertEqual(output["succeeded"], 2)
        self.assertEqual(output["deferred"], 0)
        with self.assertRaises(ValueError):
            run_source_acquisition_batch(
                [task("a")], lambda sid, *, full: None,
                max_wait_seconds=2)
        with self.assertRaises(ValueError):
            run_source_acquisition_batch(
                [task("a")], lambda sid, *, full: None,
                policy_preflight=lambda a: {"state": "ready"},
                max_wait_seconds=15000)


class ProvenanceDeltaTests(unittest.TestCase):
    def test_successful_download_is_not_verified_history_and_lost_proof_reported(self):
        before = {"series": [
            {"series_id": "a", "source_values_match": True,
             "source_covers_all_stored_periods": True, "stored_periods": 100},
            {"series_id": "b", "source_values_match": True,
             "source_covers_all_stored_periods": True, "stored_periods": 20},
            {"series_id": "c", "source_values_match": False,
             "source_covers_all_stored_periods": False, "stored_periods": 1},
        ]}
        after = {"series": [
            {"series_id": "a", "source_values_match": True,
             "source_covers_all_stored_periods": True, "stored_periods": 100},
            {"series_id": "b", "source_values_match": False,
             "source_covers_all_stored_periods": False, "stored_periods": 20,
             "failure_code": "source_hash_mismatch"},
            {"series_id": "c", "source_values_match": True,
             "source_covers_all_stored_periods": True, "stored_periods": 1},
            {"series_id": "d", "source_values_match": True,
             "source_covers_all_stored_periods": False, "stored_periods": 1,
             "failure_code": "source_coverage_incomplete"},
        ]}
        batch = {"results": [
            {"series_id": "c", "status": "success"},
            {"series_id": "d", "status": "success"},
            {"series_id": "b", "status": "success"},
        ]}
        delta = source_evidence_delta(before, after, batch)
        self.assertEqual(delta["verified_before"], 2)
        self.assertEqual(delta["verified_after"], 2)
        self.assertEqual(delta["newly_verified"], ["c"])
        self.assertEqual(delta["no_longer_verified"], ["b"])
        self.assertEqual(delta["successful_but_not_verified_count"], 2)
        self.assertEqual({x["series_id"] for x in delta[
            "successful_but_not_verified"]}, {"b", "d"})
        self.assertFalse(delta["first_publication_verified"])

    def test_duplicate_source_proofs_fail_closed(self):
        proof = {"series": [{"series_id": "duplicate"},
                            {"series_id": "duplicate"}]}
        with self.assertRaises(ValueError):
            source_evidence_delta(proof, {"series": []}, {"results": []})


if __name__ == "__main__":
    unittest.main()
