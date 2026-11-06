"""Regression evidence transitions and receipt-backed sweep upstream identity."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from finance_dashboard.catalog import load_documents
from finance_dashboard.phase2_research_transitions import (
    compact_research_transitions, research_evidence_transitions,
)
from finance_dashboard.phase2_sweep_journal import (
    Phase2SweepJournal, sweep_context,
)
from finance_dashboard.phase2_workflow import run_source_acquisition_batch
from finance_dashboard.research_corpus import (
    load_research_corpus, research_corpus_report,
)
from finance_dashboard.source_policy_types import PolicyViolation
from finance_dashboard.research_operating import emit_operating_report


class ScientificTransitionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = research_corpus_report(
            load_research_corpus(), series_registry=load_documents()[0]["series"])

    def test_full_35_analysis_gate_transition_and_blocked_to_conditional(self):
        before = deepcopy(self.base)
        after = deepcopy(before)
        analysis = next(
            row for row in after["analyses"]
            if row["readiness"]["decision"] == "blocked")
        analysis["readiness"]["decision"] = "conditional"
        check = next(
            item for role in analysis["requirements"]
            for item in role["checks"] if item["state"] != "passed"
        )
        gate = check["id"]
        check["state"] = "passed"
        result = research_evidence_transitions(before, after)
        self.assertEqual(result["analysis_count"], 35)
        self.assertEqual(result["readiness_improvements"], [analysis["id"]])
        self.assertEqual(result["readiness_regressions"], [])
        self.assertEqual(result["newly_passed_gates"][gate], 1)
        self.assertEqual(len(result["changed_analyses"]), 1)
        self.assertEqual(result["accepted_after"], 0)
        self.assertTrue(result["no_evidence_or_certification_created"])
        compact = compact_research_transitions(result)
        self.assertEqual(compact["changed_analysis_count"], 1)
        self.assertEqual(compact["changed_analyses"][0]["readiness_direction"],
                         "improved")

    def test_gate_regression_is_reported_without_predicting_economic_acceptance(self):
        old = deepcopy(self.base)
        new = deepcopy(old)
        analysis = next(
            row for row in new["analyses"]
            if any(item["state"] == "passed" for role in row["requirements"]
                   for item in role["checks"]))
        original = next(row for row in old["analyses"] if row["id"] == analysis["id"])
        original["readiness"]["decision"] = "conditional"
        analysis["readiness"]["decision"] = "blocked"
        passed = next(
            item for role in analysis["requirements"] for item in role["checks"]
            if item["state"] == "passed"
        )
        passed["state"] = "incomplete"
        report = research_evidence_transitions(old, new)
        self.assertEqual(report["readiness_regressions"], [analysis["id"]])
        self.assertEqual(report["lost_passed_gates"][passed["id"]], 1)
        self.assertEqual(report["changed_analyses"][0][
            "lost_verified_gate_count"], 1)

    def test_reports_are_identical_without_new_evidence(self):
        report = research_evidence_transitions(self.base, deepcopy(self.base))
        self.assertEqual(report["readiness_improvement_count"], 0)
        self.assertEqual(report["readiness_regression_count"], 0)
        self.assertEqual(report["gate_state_changes"], {})
        self.assertEqual(report["changed_analyses"], [])

    def test_changed_contract_and_duplicated_gates_are_rejected(self):
        after = deepcopy(self.base)
        after["analyses"].pop()
        with self.assertRaisesRegex(ValueError, "membership"):
            research_evidence_transitions(self.base, after)
        after = deepcopy(self.base)
        after["analyses"][0]["requirements"][0]["role"] = "altered"
        with self.assertRaisesRegex(ValueError, "role_contract"):
            research_evidence_transitions(self.base, after)
        after = deepcopy(self.base)
        check = after["analyses"][0]["requirements"][0]["checks"][0]
        after["analyses"][0]["requirements"][0]["checks"].append(deepcopy(check))
        with self.assertRaisesRegex(ValueError, "duplicate_research_gate"):
            research_evidence_transitions(self.base, after)

    def test_operating_brief_projection_retains_all_scientific_transition_counts(self):
        after = deepcopy(self.base)
        after["analyses"][0]["readiness"]["decision"] = "conditional"
        transitions = research_evidence_transitions(self.base, after)
        result = emit_operating_report(
            {"research_transitions": transitions}, details=False)
        self.assertEqual(result["research_transitions"]["analysis_count"], 35)
        self.assertIn("changed_analysis_count", result["research_transitions"])
        self.assertNotIn("gate_changes",
                         result["research_transitions"]["changed_analyses"][0])


class JournalUpstreamIdentityTests(unittest.TestCase):
    CONTEXT = sweep_context(["a", "b"], "0" * 64, "1" * 64)

    def test_new_event_retains_verified_actual_policy_origin(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "sweep"
            with Phase2SweepJournal(root, context=self.CONTEXT,
                                    create=True) as journal:
                report = run_source_acquisition_batch([
                    {"id": "a", "state": "acquisition_candidate",
                     "publisher_policy": "oecd-documents",
                     "provider": "OECD_CLI"},
                    {"id": "b", "state": "acquisition_candidate",
                     "publisher_policy": "fred-v1",
                     "provider": "FRED"}],
                    lambda sid, *, full: (
                        (_ for _ in ()).throw(PolicyViolation(
                            "oecd-sdmx", "direct_network_origin_not_confirmed"))
                        if sid == "a" else {
                            "status": "success", "received": 10,
                            "versions_added": 0}),
                    stop_scope="publisher", journal=journal)
                self.assertEqual(report["succeeded"], 1)
                failure = journal.already_attempted("a")
                self.assertEqual(failure["verified_upstream_policy"], "oecd-sdmx")
                self.assertEqual(failure["verified_policy_stop"],
                                 "source_policy_denied")
            with Phase2SweepJournal(root, context=self.CONTEXT,
                                    create=False) as journal:
                self.assertEqual(journal.summary()["verified_upstream_policy_stops"],
                                 {"oecd-sdmx": 1})
                self.assertEqual(journal.summary()["failure_categories"],
                                 {"source_policy_denied": 1})

    def test_legacy_event_retains_backward_compatibility_without_inferred_origin(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "sweep"
            with Phase2SweepJournal(root, context=self.CONTEXT,
                                    create=True) as journal:
                journal.mark_started("a")
                journal.mark_result(
                    "a", status="failed", reason="source_policy_denied")
            with Phase2SweepJournal(root, context=self.CONTEXT,
                                    create=False) as journal:
                self.assertIsNone(journal.already_attempted("a")[
                    "verified_upstream_policy"])
                self.assertEqual(journal.summary()["failure_categories"], {
                    "source_policy_denied": 1,
                })

    def test_malformed_claimed_verified_policy_identity_is_rejected(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "sweep"
            with Phase2SweepJournal(root, context=self.CONTEXT,
                                    create=True) as journal:
                journal.mark_started("a")
                with self.assertRaisesRegex(ValueError, "invalid_result"):
                    journal.mark_result(
                        "a", status="success", reason="none",
                        verified_upstream_policy="oecd-sdmx",
                        verified_policy_stop="source_policy_denied")
                journal.mark_result(
                    "a", status="failed", reason="source_policy_denied",
                    verified_upstream_policy="oecd-sdmx",
                    verified_policy_stop="source_policy_denied")
            import json
            event = next((root / "events").glob("*.result.json"))
            data = json.loads(event.read_text())
            data["verified_upstream_policy"] = "unregistered/bad"
            event.write_text(json.dumps(
                data, sort_keys=True, separators=(",", ":")))
            with self.assertRaisesRegex(ValueError, "identity_invalid"):
                with Phase2SweepJournal(root, context=self.CONTEXT,
                                        create=False):
                    pass


if __name__ == "__main__":
    unittest.main()
