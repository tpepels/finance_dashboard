"""Known publisher limitations stay visible but stop counting as alarms.

Only a reviewed source whose current state still matches the recorded
limitation exactly is moved out of the attention count, and only until its
review date. Anything else counts as attention again automatically.
"""
from datetime import date
import unittest

from finance_dashboard.source_coverage import (
    KNOWN_SOURCE_LIMITATIONS, _summary, known_limitation,
)


def item(sid, state, code, stored=0):
    return {"id": sid, "family": "macro", "provider": "WID", "state": state,
            "last_failure_code": code, "stored_periods": stored,
            "refresh_state": "failed", "observation_state": "missing"}


ABSENT = "piketty.us.factor_capital_share"
UNCITED = "piketty.world.wealth_to_income.national"
BEFORE_REVIEW = date(2026, 11, 17)


class KnownSourceLimitationTests(unittest.TestCase):
    def test_registry_is_the_25_reviewed_wid_series(self):
        self.assertEqual(len(KNOWN_SOURCE_LIMITATIONS), 25)
        kinds = [entry["state"] for entry in KNOWN_SOURCE_LIMITATIONS.values()]
        self.assertEqual(kinds.count("publisher_measure_absent"), 17)
        self.assertEqual(kinds.count("collection_failed"), 8)
        for sid, entry in KNOWN_SOURCE_LIMITATIONS.items():
            self.assertTrue(sid.startswith("piketty."), sid)
            self.assertTrue(entry["reason"].strip())
            self.assertGreater(entry["review_by"], BEFORE_REVIEW)

    def test_matching_absent_measure_is_a_known_limitation(self):
        found = known_limitation(
            item(ABSENT, "publisher_measure_absent", "wid_measure_unavailable"),
            BEFORE_REVIEW)
        self.assertIsNotNone(found)
        self.assertIn("does not publish", found["reason"])

    def test_matching_uncited_world_series_is_a_known_limitation(self):
        self.assertIsNotNone(known_limitation(
            item(UNCITED, "collection_failed", "wid_metadata_invalid"), BEFORE_REVIEW))

    def test_a_different_failure_is_attention_again(self):
        for state, code in (("collection_failed", "source_transport_failed"),
                            ("collection_failed", "wid_observation_invalid"),
                            ("refresh_failed_with_data", "wid_metadata_invalid")):
            self.assertIsNone(known_limitation(item(UNCITED, state, code), BEFORE_REVIEW))

    def test_stored_data_ends_the_limitation(self):
        self.assertIsNone(known_limitation(
            item(ABSENT, "publisher_measure_absent", "wid_measure_unavailable", stored=3),
            BEFORE_REVIEW))

    def test_review_date_ends_the_limitation(self):
        entry = KNOWN_SOURCE_LIMITATIONS[ABSENT]
        self.assertIsNone(known_limitation(
            item(ABSENT, "publisher_measure_absent", "wid_measure_unavailable"),
            entry["review_by"]))

    def test_unlisted_series_is_never_a_known_limitation(self):
        self.assertIsNone(known_limitation(
            item("piketty.us.wealth_to_income.national", "collection_failed",
                 "wid_metadata_invalid"), BEFORE_REVIEW))

    def test_summary_counts_known_limitations_separately(self):
        rows = [item(ABSENT, "publisher_measure_absent", "wid_measure_unavailable"),
                item(UNCITED, "collection_failed", "wid_metadata_invalid"),
                item("piketty.us.wealth_to_income.national", "collection_failed",
                     "source_transport_failed")]
        for row in rows:
            row["known_limitation"] = known_limitation(row, BEFORE_REVIEW)
        summary = _summary(rows)
        self.assertEqual(summary["needs_attention"], 1)
        self.assertEqual(summary["known_limitations"], 2)
        self.assertEqual(summary["collection_failed"], 2)


class KnownLimitationEventTests(unittest.TestCase):
    def _run(self, source_id, message):
        from unittest.mock import patch
        from finance_dashboard.bis import ProviderError
        from finance_dashboard.worker import RefreshTask, execute_refresh_tasks

        def fail():
            raise ProviderError(message)
        task = RefreshTask("macro", source_id, fail, source_id, provider_group="WID")
        with patch("finance_dashboard.worker.record_event", autospec=True) as log:
            execute_refresh_tasks([task])
        return next(call for call in log.call_args_list if call.kwargs.get("source_id") == source_id)

    def test_recurring_reviewed_limitation_is_a_warning(self):
        event = self._run(UNCITED, "WID research age, population or original method mismatch")
        self.assertEqual(event.args[1], "source_known_limitation")
        self.assertEqual(event.kwargs["level"], "warning")
        self.assertEqual(event.kwargs["reason"], "wid_metadata_invalid")

    def test_other_failure_of_a_listed_source_is_still_an_error(self):
        event = self._run(UNCITED, "WID original data or metadata request failed")
        self.assertEqual(event.args[1], "source_failed")
        self.assertEqual(event.kwargs["level"], "error")


class KnownLimitationSnapshotTests(unittest.TestCase):
    def test_health_snapshot_lists_known_limitations_apart(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from finance_dashboard.collection_workflow import SourceHealthCache
        known = item(UNCITED, "collection_failed", "wid_metadata_invalid")
        known["known_limitation"] = known_limitation(known, BEFORE_REVIEW)
        broken = item("piketty.us.wealth_to_income.national", "collection_failed",
                      "source_transport_failed")
        broken["known_limitation"] = None
        for row in (known, broken):
            row.update(name=row["id"], latest_source_date=None, published_through=None,
                       last_attempt_state="failed", next_action="", research_questions=[])
        coverage = {"asof": "2026-11-17", "items": [known, broken],
                    "summary": {"macro": {**_summary([known, broken]), "total": 2}}}
        with TemporaryDirectory() as tmp:
            cache = SourceHealthCache(lambda: coverage, path=Path(tmp) / "health.json")
            cache._rebuild()
            snapshot = cache.cached
        self.assertEqual([row["id"] for row in snapshot["attention_items"]],
                         ["piketty.us.wealth_to_income.national"])
        self.assertEqual([row["id"] for row in snapshot["known_limitations"]], [UNCITED])
        self.assertIn("citation", snapshot["known_limitations"][0]["reason"])
        macro = next(group for group in snapshot["groups"] if group["id"] == "macro")
        self.assertEqual(macro["attention"], 1)
        self.assertEqual(macro["collection_failed"], 1)
        self.assertEqual(macro["known_limitations"], 1)
        self.assertEqual(snapshot["sources"]["needs_attention"], 1)


class KnownLimitationAssessmentTests(unittest.TestCase):
    def _report(self, row):
        from finance_dashboard.limitation_assessment import assess_limitations
        coverage = {"asof": "2026-11-17", "items": [row], "summary": {}}
        return assess_limitations(coverage=coverage,
                                  document={"analyses": [{"id": "L07", "title": "x"}]},
                                  release={"release_id": "test"})["findings"]

    def test_matching_limitation_is_documented_not_needs_evidence(self):
        row = item(UNCITED, "collection_failed", "wid_metadata_invalid")
        row["known_limitation"] = known_limitation(row, BEFORE_REVIEW)
        finding = next(f for f in self._report(row) if f["source_ids"] == [UNCITED])
        self.assertEqual(finding["status"], "documented")
        self.assertEqual(finding["severity"], "information")
        self.assertEqual(finding["category"], "documented_publisher_limitation")
        self.assertIn("2027-07-01", finding["next_action"])

    def test_same_series_without_a_match_still_needs_evidence(self):
        row = item(UNCITED, "collection_failed", "source_transport_failed")
        row["known_limitation"] = known_limitation(row, BEFORE_REVIEW)
        finding = next(f for f in self._report(row) if f["source_ids"] == [UNCITED])
        self.assertEqual(finding["status"], "needs_evidence")
        self.assertEqual(finding["severity"], "high")


if __name__ == "__main__":
    unittest.main()
