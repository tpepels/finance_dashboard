"""Source and scientific limitations are inventoried without inventing freshness."""
from __future__ import annotations

from datetime import datetime, timezone
import unittest
from types import SimpleNamespace
from unittest.mock import patch

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
        self.assertEqual(report["counts"]["research_by_state"],
                         {"conditional": 1, "deferred": 1})
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
        # Phase 0 replaced G06's unqualified current-date claim with a
        # source-bound historic reference. It must no longer be flagged as
        # an outstanding hardcoded-date assertion.
        self.assertFalse(any(f["category"] == "potentially_outdated_hardcoded_statement"
                             and f["analysis_ids"] == ["G06"] for f in findings))
        self.assertTrue(any(f["category"] == "documented_method_constraint"
                            and f["analysis_ids"] == ["G06"] for f in findings))
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


    def test_other_edition_icio_failures_do_not_falsely_block_g06(self):
        report=assess_limitations(
            coverage={"items":[]},document=DOC,
            accounting={"failure_equations_exported":24869,
                        "annual_matrices_without_complete_failure_ledger":[]},
            icio_dependencies={
                "verification_scope":"other_edition_audit_metadata_only",
                "complete_publisher_reader_audit":False,
                "counts":{"consumer_exact_hash_match":0,
                          "failing_exact_consumer_matrices":0,
                          "failing_other_matrices":54,
                          "other_edition_not_directly_consumed":78,
                          "unresolved_source_identity":0},
                "consumers":{"G06":{"is_direct_icio_matrix_consumer":False}},
            })
        finding=next(item for item in report["findings"]
                     if item["category"]=="source_accounting_integrity")
        self.assertEqual(finding["analysis_ids"],[])
        self.assertEqual(finding["severity"],"high")
        self.assertEqual(finding["status"],"needs_evidence")
        self.assertEqual(finding["evidence"]["failed_other_matrices"],54)
        self.assertEqual(finding["evidence"]["failed_exact_consumer_matrices"],0)
        self.assertEqual(finding["evidence"]["consumer_scope_state"],
                         "no_failing_exact_consumer_hash_in_archive_inventory")
        self.assertFalse(finding["evidence"]["complete_publisher_reader_audit"])

    def test_icio_only_attributes_exact_failed_pinned_consumer_to_l04(self):
        doc={"analyses":[{"id":"G06","title":"TiVA"},
                         {"id":"L04","title":"Sector returns"}]}
        report=assess_limitations(
            coverage={"items":[]},document=doc,
            accounting={"failure_equations_exported":12,
                        "annual_matrices_without_complete_failure_ledger":[]},
            icio_dependencies={"complete_publisher_reader_audit":False,
                 "counts":{"failing_exact_consumer_matrices":1,
                           "failing_other_matrices":2,
                           "consumer_exact_hash_match":1}})
        finding=next(item for item in report["findings"]
                     if item["category"]=="source_accounting_integrity")
        self.assertEqual(finding["analysis_ids"],["L04"])
        self.assertEqual(finding["evidence"]["consumer_scope_state"],
                         "failing_exact_consumer_hash")
        self.assertNotIn("G06",finding["analysis_ids"])

    def test_no_acceptance_snapshot_is_unknown_not_research_complete(self):
        report = assess_limitations(coverage=self._coverage(), document=DOC)
        self.assertEqual(report["scientific_acceptance"]["state"], "unavailable")
        self.assertEqual(report["counts"]["research_questions_evaluated"], 0)
        self.assertEqual(report["questions"], [])
        self.assertFalse(any(f["provenance"] == "phase2_acceptance" for f in report["findings"]))
        self.assertTrue(any(f["provenance"] == "registered_method_limitation"
                            for f in report["findings"]))

    def test_borrowed_input_caveat_is_attributed_to_the_borrowing_question(self):
        document = {"analyses": [{"id": "Z01", "title": "Borrower"},
                                 {"id": "Z02", "title": "Lender"}]}
        snapshot = AcceptanceSnapshot(datetime(2026, 11, 14, tzinfo=timezone.utc), {
            "Z01": {"state": "accepted", "limitations": [],
                     "requirements": [], "blocking_roles": []},
            "Z02": {"state": "accepted", "limitations": [],
                     "requirements": [{
                         "role": "accepted_source", "state": "accepted",
                         "series_ids": ["example.series"],
                         "limitations": [{
                             "code": "latest_revised_values_not_real_time",
                             "series_id": "example.series"}],
                     }], "blocking_roles": []},
        })
        engines = {"Z01": SimpleNamespace(inputs={"borrowed": "example.series"}),
                   "Z02": SimpleNamespace(inputs={})}
        with patch("finance_dashboard.limitation_assessment.DEFINITIONS", engines):
            report = assess_limitations(coverage={"items": []},
                                        document=document, snapshot=snapshot)
        borrowed = [f for f in report["findings"]
                    if f["category"] == "borrowed_input_limitation"]
        self.assertEqual(len(borrowed), 1)
        self.assertEqual(borrowed[0]["analysis_ids"], ["Z01"])
        self.assertEqual(borrowed[0]["source_ids"], ["example.series"])
        self.assertEqual(borrowed[0]["evidence"]["accepted_under"]["analysis_id"], "Z02")

    def test_cached_acceptance_peek_does_not_schedule_new_evaluation(self):
        from finance_dashboard.engine.acceptance import AcceptanceCache
        scheduled = []
        cache = AcceptanceCache(self._snapshot, ttl_seconds=3600,
                                spawn=lambda task: scheduled.append(task))
        self.assertIsNone(cache.peek())
        self.assertEqual(scheduled, [])
        cache.warm()
        self.assertEqual(len(scheduled), 1)
        scheduled.pop()()
        self.assertIsNotNone(cache.peek())
        self.assertEqual(scheduled, [])

    def test_missing_supplemental_input_remains_visible_without_marking_core_unaccepted(self):
        snapshot=self._snapshot()
        snapshot.analyses["C01"]["requirements"].append({
            "role":"national_cpi","requirement_class":"supplemental",
            "state":"incomplete","series_ids":["macro.missing"],
            "limitations":[],
        })
        report=assess_limitations(coverage=self._coverage(),document=DOC,
                                  snapshot=snapshot)
        missing=[row for row in report["findings"]
                 if row["category"]=="supplemental_source_pending"]
        self.assertEqual(len(missing),1)
        self.assertEqual(missing[0]["status"],"monitor")
        self.assertEqual(missing[0]["source_ids"],["macro.missing"])
        self.assertEqual(missing[0]["analysis_ids"],["C01"])
        self.assertEqual(missing[0]["severity"],"information")

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
