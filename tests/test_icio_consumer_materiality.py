"""Recorded size of the publisher residuals in the matrices L04 reads."""
import copy
import unittest

from finance_dashboard.icio import PUBLISHER_MATRICES
from finance_dashboard.icio_dependency_audit import (
    classify_icio_dependencies, consumer_materiality, load_consumer_materiality,
)
from finance_dashboard.limitation_assessment import assess_limitations


def summary_with_other_edition_failure():
    return {"archives": [{"filename": "ICIO2018_2015.zip", "edition": "2018",
                          "table": "extended", "archive_sha256": "a" * 64,
                          "native_years": [{"year": 2015, "original_member_sha256": "b" * 64,
                                            "row_failures": 3, "column_failures": 0,
                                            "output_vector_mismatches": 0,
                                            "accounting_passed": False}]}]}


class ConsumerMaterialityTests(unittest.TestCase):
    def test_recorded_evidence_covers_every_pinned_year_and_hash(self):
        record = load_consumer_materiality()
        self.assertEqual({row["year"] for row in record["years"]}, set(PUBLISHER_MATRICES))
        self.assertTrue(all(row["sha_matches_pin"] for row in record["years"]))
        verdict = consumer_materiality(record)
        self.assertTrue(verdict["verified"])
        self.assertLessEqual(verdict["max_relative_row_residual"], 0.001)
        self.assertEqual(verdict["max_relative_node"], "ISL_L")

    def test_missing_year_wrong_hash_or_large_residual_is_not_verified(self):
        record = load_consumer_materiality()
        missing = copy.deepcopy(record); missing["years"].pop()
        wrong = copy.deepcopy(record); wrong["years"][0]["sha_matches_pin"] = False
        large = copy.deepcopy(record); large["years"][0]["max_relative"] = "2.0e-3"
        for broken in (missing, wrong, large, None):
            self.assertFalse(consumer_materiality(broken)["verified"])

    def test_dependency_audit_reports_consumer_materiality(self):
        report = classify_icio_dependencies(summary_with_other_edition_failure())
        self.assertTrue(report["consumer_materiality"]["verified"])
        self.assertEqual(report["counts"]["failing_other_matrices"], 1)

    def test_finding_is_documented_only_with_verified_materiality_and_no_failing_consumer(self):
        deps = classify_icio_dependencies(summary_with_other_edition_failure())
        accounting = {"failure_equations_exported": 3,
                      "annual_matrices_without_complete_failure_ledger": []}
        def finding(dependencies):
            report = assess_limitations(coverage={"items": []}, document={"analyses": [{"id": "L04"}]},
                                        accounting=accounting, icio_dependencies=dependencies,
                                        release={"release_id": "test"})
            return next(f for f in report["findings"] if f["id"] == "scientific-integrity:icio-accounting")
        documented = finding(deps)
        self.assertEqual(documented["status"], "documented")
        self.assertEqual(documented["severity"], "information")
        self.assertIn("0.089", documented["detail"])
        unverified = copy.deepcopy(deps); unverified["consumer_materiality"]["verified"] = False
        self.assertEqual(finding(unverified)["status"], "needs_evidence")
        consumer = copy.deepcopy(deps); consumer["counts"]["failing_exact_consumer_matrices"] = 1
        self.assertEqual(finding(consumer)["status"], "needs_evidence")


if __name__ == "__main__":
    unittest.main()
