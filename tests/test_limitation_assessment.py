"""Source and scientific limitations are inventoried without inventing freshness."""
from __future__ import annotations

from datetime import datetime, timezone
import unittest

from finance_dashboard.engine.acceptance import AcceptanceSnapshot
from finance_dashboard.limitation_assessment import assess_limitations


def source(sid, state, *, latest=None, refresh="success", with_data=3):
    return {
        "family": "macro", "id": sid, "name": sid, "provider": "TEST",
        "frequency": "A", "state": state, "observation_state": (
            "stale" if latest == "2020-01-01" else "current"),
        "latest_source_date": latest, "published_through": None,
        "stored_periods": with_data, "expected_lag_days": 450,
        "last_attempt_state": refresh, "last_failure_code": None,
        "refresh_state": refresh, "research_questions": ["C01"],
        "next_action": "Check original evidence.",
    }


DOC = {"analyses": [{"id": "C01", "title": "Activity"},
                    {"id": "G06", "title": "Global value chains"}]}


class LimitationAssessmentTests(unittest.TestCase):
    def _coverage(self):
        return {
            "asof": "2026-11-14",
            "items": [
                source("macro.old", "stale", latest="2020-01-01"),
                source("macro.publisher_checked", "source_checked_no_newer_data",
                       latest="2020-01-01", refresh="deferred"),
                source("macro.deferred_current", "available",
                       latest="2026-10-01", refresh="deferred"),
                source("macro.missing", "not_ingested", latest=None, with_data=0),
                source("macro.current", "available", latest="2026-10-01"),
            ],
        }

    def _snapshot(self):
        return AcceptanceSnapshot(datetime(2026, 11, 14, tzinfo=timezone.utc), {
            "C01": {"state": "conditional", "limitations": [{
                "code": "latest_revised_values_not_real_time",
                "series_id": "macro.old"}], "blocking_roles": [],
                "requirements": [{
                    "role": "leading_indicator", "state": "accepted",
                    "limitations": [{"code": "latest_revised_values_not_real_time",
                                     "series_id": "macro.old"}],
                    "series_ids": ["macro.old"],
                }]},
            "G06": {"state": "deferred", "limitations": [{
                "code": "exact_original_inputs_missing_or_partial",
                "series_id": "macro.missing"}],
                "blocking_roles": ["source_matrix"], "requirements": []},
        })

    def test_reports_all_relevant_states_without_claiming_every_deferred_is_stale(self):
        report = assess_limitations(
            coverage=self._coverage(), document=DOC, snapshot=self._snapshot(),
            accounting={"failure_equations_exported": 19,
                        "annual_matrices_without_complete_failure_ledger": []},
            release={"release_id": "0.2.1+test"})
        self.assertEqual(report["scientific_acceptance"]["state"], "ready")
        self.assertEqual(report["counts"]["research_questions_evaluated"], 2)
        findings = report["findings"]
        self.assertEqual(len([f for f in findings if f["provenance"] == "source_coverage"]), 4)
        current = next(f for f in findings if f["source_ids"] == ["macro.deferred_current"])
        self.assertEqual(current["status"], "monitor")
        self.assertEqual(current["category"], "source_refresh_deferred")
        stale = next(f for f in findings if f["source_ids"] == ["macro.old"] and
                     f["provenance"] == "source_coverage")
        self.assertEqual(stale["severity"], "medium")
        missing = next(f for f in findings if f["source_ids"] == ["macro.missing"] and
                       f["provenance"] == "source_coverage")
        self.assertEqual(missing["severity"], "high")
        self.assertTrue(any(f["category"] == "potentially_outdated_hardcoded_statement" and
                            f["analysis_ids"] == ["G06"] and
                            f["evidence"]["automatic_outdatedness_confirmed"] is False
                            for f in findings))
        self.assertTrue(any(f["category"] == "source_accounting_integrity"
                            and f["evidence"]["failure_equations_exported"] == 19
                            for f in findings))
        # A role limitation and its copied analysis limitation count only once.
        revised = [f for f in findings if f["provenance"] == "phase2_acceptance"
                   and "latest_revised_values_not_real_time" in f["id"]]
        self.assertEqual(len(revised), 1)
        self.assertEqual(revised[0]["analysis_ids"], ["C01"])
        self.assertTrue(any(f["category"] == "research_evidence_gap" and
                            f["analysis_ids"] == ["G06"] for f in findings))
        self.assertEqual(report["counts"]["total"], len(findings))

    def test_no_acceptance_snapshot_is_unknown_not_research_complete(self):
        report = assess_limitations(coverage=self._coverage(), document=DOC)
        self.assertEqual(report["scientific_acceptance"]["state"], "unavailable")
        self.assertEqual(report["counts"]["research_questions_evaluated"], 0)
        self.assertEqual(report["questions"], [])
        self.assertFalse(any(f["provenance"] == "phase2_acceptance" for f in report["findings"]))
        self.assertTrue(any(f["provenance"] == "registered_method_limitation"
                            for f in report["findings"]))

    def test_missing_compute_definition_is_reported_as_implementation_gap(self):
        document = {"analyses": [{"id": "Z99", "title": "Unimplemented question"}]}
        report = assess_limitations(coverage={"items": []}, document=document)
        missing = [row for row in report["findings"]
                   if row["category"] == "analysis_implementation_missing"]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["analysis_ids"], ["Z99"])
        self.assertEqual(missing[0]["severity"], "high")

    def test_unregistered_phase2_code_survives_as_a_reported_audit_failure(self):
        snapshot = AcceptanceSnapshot(datetime(2026, 11, 14, tzinfo=timezone.utc), {
            "C01": {"state": "conditional", "limitations": [{
                "code": "this_code_is_not_registered"}], "blocking_roles": [],
                "requirements": []},
        })
        report = assess_limitations(coverage=self._coverage(), document=DOC,
                                    snapshot=snapshot)
        self.assertEqual(report["scientific_acceptance"]["state"], "failed")
        self.assertTrue(any(row["category"] == "limitation_assessment_failure"
                            for row in report["findings"]))
        self.assertTrue(any(row["provenance"] == "source_coverage"
                            for row in report["findings"]))

    def test_method_register_does_not_mutate_or_promote_scientific_acceptance(self):
        snap = self._snapshot()
        data = dict(snap.analyses)
        _ = assess_limitations(coverage=self._coverage(), document=DOC, snapshot=snap)
        self.assertEqual(snap.analyses, data)
        self.assertEqual(snap.analyses["G06"]["state"], "deferred")


if __name__ == "__main__":
    unittest.main()
