"""Acceptance snapshot: analysis state, per-input provenance, cached evaluation."""
from datetime import datetime, timezone
import unittest

from finance_dashboard.engine.acceptance import (AcceptanceCache, AcceptanceUnavailable, UnacceptedInput,
                                                 analysis_phase2, input_provenance, snapshot_from_report)

REVISED = {"code": "latest_revised_values_not_real_time", "series_id": "returns.us.shiller_real_total_return"}


def role(name, series_ids, limitations=(), state="accepted", **extra):
    return {"role": name, "series_ids": list(series_ids), "state": state, "accepted": state == "accepted",
            "limitations": list(limitations), **extra}


REPORT = {"analyses": [
    {"id": "P06", "acceptance": {"state": "conditional", "requirements": [
        role("us_cape", ["valuation.us.cape"], [{"code": "dimensions_as_declared_in_catalogue",
                                               "series_ids": ["valuation.us.cape"]}])],
        "limitations": [{"code": "dimensions_as_declared_in_catalogue", "series_ids": ["valuation.us.cape"]}],
        "blocking_roles": []}},
    {"id": "V05", "acceptance": {"state": "accepted", "requirements": [
        role("matched_equity_total_return", ["returns.us.shiller_real_total_return"], [REVISED])],
        "limitations": [REVISED], "blocking_roles": []}},
    {"id": "F04", "acceptance": {"state": "conditional", "requirements": [
        role("hy_spread", ["stress.us.high_yield_oas"], state="unavailable_with_fallback",
             fallback_evaluation={"series_ids": ["stress.us.baa_spread"]})],
        "limitations": [], "blocking_roles": []}},
    {"id": "X01", "acceptance": {"state": "blocked", "requirements": [
        role("thing", ["blocked.series"], state="blocked")], "limitations": [], "blocking_roles": ["thing"]}},
    {"id": "G03", "acceptance": {"state": "deferred", "requirements": [],
        "limitations": [{"code": "deferred_research_extension", "detail": "no free data"}], "blocking_roles": []}},
]}
AT = datetime(2026, 11, 8, tzinfo=timezone.utc)


class AcceptanceSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.snap = snapshot_from_report(REPORT, AT)

    def test_own_role_is_preferred(self):
        result = input_provenance(self.snap, "P06", "valuation.us.cape")
        self.assertEqual(result["accepted_under"], {"analysis_id": "P06", "role": "us_cape"})
        self.assertTrue(result["limitations"][0]["text"])

    def test_borrowed_input_names_its_accepting_analysis_and_carries_its_limitations(self):
        result = input_provenance(self.snap, "P06", "returns.us.shiller_real_total_return")
        self.assertEqual(result["accepted_under"], {"analysis_id": "V05", "role": "matched_equity_total_return"})
        self.assertEqual(result["limitations"][0]["code"], "latest_revised_values_not_real_time")
        self.assertTrue(result["limitations"][0]["text"])

    def test_fallback_series_is_accepted_under_its_role(self):
        result = input_provenance(self.snap, "P06", "stress.us.baa_spread")
        self.assertEqual(result["accepted_under"], {"analysis_id": "F04", "role": "hy_spread"})

    def test_series_accepted_nowhere_or_only_in_blocked_analysis_is_refused(self):
        with self.assertRaises(UnacceptedInput):
            input_provenance(self.snap, "P06", "unknown.series")
        with self.assertRaises(UnacceptedInput):
            input_provenance(self.snap, "P06", "blocked.series")

    def test_analysis_state_and_detail_only_limitations(self):
        deferred = analysis_phase2(self.snap, "G03")
        self.assertEqual(deferred["state"], "deferred")
        self.assertEqual(deferred["evaluated_at"], AT.isoformat())
        self.assertEqual(deferred["limitations"][0]["detail"], "no free data")
        self.assertTrue(deferred["limitations"][0]["text"])
        self.assertEqual(analysis_phase2(self.snap, "X01")["open_gates"], ["thing"])
        self.assertEqual(analysis_phase2(self.snap, "NOPE")["state"], "not_checked")

    def test_cache_reuses_within_ttl_and_reloads_after(self):
        now = [0.0]
        calls = []

        def loader():
            calls.append(1)
            return self.snap
        cache = AcceptanceCache(loader, ttl_seconds=60, clock=lambda: now[0])
        cache.get(); cache.get()
        self.assertEqual(len(calls), 1)
        now[0] = 61.0
        cache.get()
        self.assertEqual(len(calls), 2)

    def test_failed_evaluation_is_unavailable_and_retried(self):
        attempts = []

        def loader():
            attempts.append(1)
            raise OSError("evidence directory missing")
        cache = AcceptanceCache(loader, ttl_seconds=60, clock=lambda: 0.0)
        with self.assertRaises(AcceptanceUnavailable):
            cache.get()
        with self.assertRaises(AcceptanceUnavailable):
            cache.get()
        self.assertEqual(len(attempts), 2)


if __name__ == "__main__":
    unittest.main()
