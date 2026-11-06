"""Phase 2 explicit historical sweep recovery and strict original gate tests."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from finance_dashboard.comparative_corpus import source_contract_digest
from finance_dashboard.phase2_sweep_journal import (
    Phase2SweepJournal, sweep_context,
)
from finance_dashboard.phase2_sweep_revisit import plan_sweep_revisit
from finance_dashboard.source_original_gate import (
    verified_original_history, verified_original_rows, runtime_source_counts,
)


def action(sid):
    return {"id": sid, "state": "acquisition_candidate",
            "publisher_policy": "fred-v1", "provider": "FRED"}


class SourceOriginalGateTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {"a": {"id": "a", "provider": "FRED", "source_key": "AAA"}}
        self.proof = {
            "series_id": "a", "stored_periods": 23,
            "source_values_match": True,
            "source_covers_all_stored_periods": True,
            "source_sha256": "a" * 64,
            "source_manifest_sha256": "b" * 64,
            "stored_observations_sha256": "c" * 64,
            "source_contract_sha256": source_contract_digest(self.catalog["a"]),
        }

    def test_canonical_fidelity_requires_exact_catalog_and_storage(self):
        self.assertTrue(verified_original_history(
            self.proof, self.catalog["a"], 23))
        bad = [
            {**self.proof, "source_sha256": None},
            {**self.proof, "source_manifest_sha256": "not-a-hash"},
            {**self.proof, "source_contract_sha256": "d" * 64},
            {**self.proof, "stored_periods": 22},
            {**self.proof, "source_values_match": False},
            {**self.proof, "source_covers_all_stored_periods": False},
        ]
        for row in bad:
            with self.subTest(row=row):
                self.assertFalse(verified_original_history(
                    row, self.catalog["a"], 23))
        self.assertFalse(verified_original_history(
            self.proof, {**self.catalog["a"], "source_key": "CHANGED"}, 23))
        self.assertFalse(verified_original_history(
            self.proof, self.catalog["a"], None))

    def test_duplicate_verified_rows_and_inconsistent_runtime_counts_fail_closed(self):
        counts = {"a": {"stored_periods": 23}}
        selected = verified_original_rows(
            {"series": [self.proof]}, self.catalog, counts)
        self.assertEqual(list(selected), ["a"])
        with self.assertRaises(ValueError):
            verified_original_rows({"series": [self.proof, self.proof]},
                                   self.catalog, counts)
        with self.assertRaisesRegex(ValueError, "stored_histories_disagree"):
            runtime_source_counts({"analyses": [
                {"linked_sources": [{"series_id": "a", "stored_periods": 23}]},
                {"linked_sources": [{"series_id": "a", "stored_periods": 22}]},
            ]})


class ExplicitRevisitTests(unittest.TestCase):
    @staticmethod
    def context():
        return sweep_context(["a", "b", "c", "d", "e", "f"],
                             "0" * 64, "1" * 64)

    @staticmethod
    def make_old_journal(root, ctx):
        with Phase2SweepJournal(root, context=ctx, create=True) as journal:
            journal.mark_started("a")
            journal.mark_result("a", status="failed", reason="provider_http_404")
            journal.mark_started("b")
            journal.mark_result("b", status="success",
                                received=100, versions_added=2)
            journal.mark_started("c")
            journal.mark_result("c", status="success",
                                received=200, versions_added=3)
            journal.mark_started("d")  # Never resolved: must not resend
            journal.mark_started("e")
            journal.mark_result("e", status="failed",
                                reason="source_policy_denied")

    def test_only_current_candidates_with_requested_prior_states_are_selected(self):
        with TemporaryDirectory() as tmp:
            old = Path(tmp) / "old"
            self.make_old_journal(old, self.context())
            # b no longer appears: its original evidence was independently
            # verified after the previous journal was written.
            candidates = [action(sid) for sid in ("a", "c", "d", "e", "f")]
            failed = plan_sweep_revisit(
                old, context=self.context(),
                acquisition_candidates=candidates)
            self.assertEqual([a["id"] for a in failed["selected_actions"]],
                             ["a", "e"])
            self.assertEqual(failed["prior_inflight_held_for_manual_review"],
                             ["d"])
            self.assertEqual(failed["failure_categories_selected"], {
                "provider_http_404": 1, "source_policy_denied": 1})
            success = plan_sweep_revisit(
                old, context=self.context(),
                acquisition_candidates=candidates,
                mode="unverified_success")
            self.assertEqual([a["id"] for a in success["selected_actions"]],
                             ["c"])
            both = plan_sweep_revisit(
                old, context=self.context(),
                acquisition_candidates=candidates, mode="both")
            self.assertEqual([a["id"] for a in both["selected_actions"]],
                             ["a", "c", "e"])
            self.assertFalse(both["original_journal_modified"])
            self.assertFalse(both["inflight_automatically_retried"])
            self.assertEqual(both["prior_requested_no_longer_unverified"], 1)
            # Purely operational diagnostics; no publisher values certified.
            self.assertFalse(both["scientific_analysis_certified"])
            # The source evidence and immutable receipt files remain unchanged.
            with Phase2SweepJournal(old, context=self.context(),
                                    create=False) as check:
                self.assertEqual(check.summary()["tracked_attempts"], 5)

    def test_task_limit_and_policy_backlog_do_not_authorize_over_budget_work(self):
        with TemporaryDirectory() as tmp:
            old = Path(tmp) / "old"
            self.make_old_journal(old, self.context())
            result = plan_sweep_revisit(
                old, context=self.context(),
                acquisition_candidates=[action(s) for s in ("a", "e")],
                max_tasks=1)
            self.assertEqual(result["selected_count"], 1)
            self.assertEqual(result["remaining_after_task_limit"], 1)
            self.assertEqual([r["id"] for r in result["selected_actions"]],
                             ["a"])

    def test_invalid_history_contract_or_corrupted_journal_is_rejected(self):
        with TemporaryDirectory() as tmp:
            old = Path(tmp) / "old"
            self.make_old_journal(old, self.context())
            with self.assertRaisesRegex(ValueError, "sweep_context_changed"):
                plan_sweep_revisit(
                    old, context=sweep_context(["a", "b", "c", "d", "e", "f"],
                                               "2" * 64, "1" * 64),
                    acquisition_candidates=[action("a")])
            with self.assertRaisesRegex(ValueError, "duplicate"):
                plan_sweep_revisit(
                    old, context=self.context(),
                    acquisition_candidates=[action("a"), action("a")])
            with self.assertRaisesRegex(ValueError, "mode"):
                plan_sweep_revisit(
                    old, context=self.context(), acquisition_candidates=[],
                    mode="everything")
            event = next((old / "events").glob("*.start.json"))
            event.write_text("CORRUPT")
            with self.assertRaises(ValueError):
                plan_sweep_revisit(
                    old, context=self.context(),
                    acquisition_candidates=[action("a")])


if __name__ == "__main__":
    unittest.main()
