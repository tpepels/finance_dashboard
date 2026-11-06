"""Immutable native original-file registration for 28 unbound structured roles."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from finance_dashboard.catalog import load_documents
from finance_dashboard.phase2_native_role_originals import (
    native_role_original_evidence, read_native_role_original,
    register_native_role_original,
)
from finance_dashboard.research_corpus import (
    load_research_corpus, research_corpus_report,
)


class NativeOriginalRoleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = load_research_corpus()
        cls.catalog = load_documents()[0]["series"]

    @staticmethod
    def sample(root):
        path = Path(root) / "native-events.csv"
        path.write_text(
            "event_id,event_date,impact\n"
            "recession-a,2020-03-01,1.5\n"
            "shock-b,2022-03-01,\n", encoding="utf-8")
        return path

    def register(self, root, path, document=None):
        return register_native_role_original(
            document or self.document, root=Path(root) / "evidence",
            analysis_id="F07", role="fund_funding_mismatch",
            original=path,
            fields=["event_id", "event_date", "impact"],
            key_fields=["event_id"], numeric_fields=["impact"],
            date_field="event_date")

    def test_empty_corpus_lists_all_28_unbound_structured_roles(self):
        with TemporaryDirectory() as temp:
            evidence = native_role_original_evidence(
                self.document, Path(temp))
            self.assertEqual(evidence["unbound_structured_roles"], 25)
            self.assertEqual(evidence["hash_verified_partial_roles"], 0)
            self.assertEqual(evidence["invalid_archived_roles"], [])
            self.assertFalse(evidence["scientific_analysis_certified"])

    def test_register_native_rows_and_retrieve_hash_and_receipts(self):
        with TemporaryDirectory() as temp:
            source = self.sample(temp)
            result = self.register(temp, source)
            self.assertEqual(result["status"],
                             "hash_verified_native_structured_original_partial")
            self.assertTrue(result["original_source_hash_verified"])
            self.assertEqual(result["native_facts"]["record_count"], 2)
            self.assertEqual(result["native_facts"]["missing_numeric_values_not_imputed"], 1)
            self.assertEqual(result["native_facts"]["numeric_values_reported"], 1)
            self.assertEqual(result["native_facts"]["earliest_record_date"], "2020-03-01")
            self.assertFalse(result["first_publication_verified"])
            self.assertFalse(result["original_role_accepted"])
            second = self.register(temp, source)
            self.assertEqual(second["original_versions"], 1)
            self.assertEqual(second["retrieval_receipts"], 2)
            evidence = native_role_original_evidence(
                self.document, Path(temp) / "evidence")
            self.assertEqual(evidence["hash_verified_partial_roles"], 1)
            self.assertEqual(evidence["unbound_structured_roles"], 25)
            self.assertEqual(evidence["invalid_archived_roles"], [])

    def test_registered_native_file_reaches_scientific_gate_without_false_acceptance(self):
        with TemporaryDirectory() as temp:
            source = self.sample(temp)
            self.register(temp, source)
            evidence = native_role_original_evidence(
                self.document, Path(temp) / "evidence")
            report = research_corpus_report(
                self.document, series_registry=self.catalog,
                native_role_evidence=evidence)
            role = next(
                r for a in report["analyses"] if a["id"] == "F07"
                for r in a["requirements"]
                if r["role"] == "fund_funding_mismatch")
            self.assertTrue(role["attached_native_original"][
                "original_source_hash_verified"])
            self.assertEqual(role["resolution"]["availability"], "available_partial")
            self.assertEqual(role["resolution"]["category"], 3)
            gates = {item["id"]: item["state"] for item in role["checks"]}
            self.assertEqual(gates["source_binding"], "incomplete")
            self.assertEqual(gates["original_source_values"], "incomplete")
            self.assertEqual(gates["temporal_evidence"], "incomplete")
            self.assertFalse(role["accepted"])
            self.assertEqual(report["fully_validated_analysis_count"], 0)
            self.assertEqual(
                report["structured_native_roles_with_hash_verified_partial_originals"],
                1)

    def test_duplicate_keys_and_nonfinite_values_are_rejected_before_archiving(self):
        with TemporaryDirectory() as temp:
            path = self.sample(temp)
            path.write_text(
                "event_id,event_date,impact\n"
                "recession-a,2020-03-01,1.5\n"
                "recession-a,2021-01-01,3\n")
            with self.assertRaisesRegex(ValueError, "duplicated"):
                self.register(temp, path)
            path.write_text(
                "event_id,event_date,impact\n"
                "recession-a,2020-03-01,NaN\n")
            with self.assertRaisesRegex(ValueError, "nonfinite"):
                self.register(temp, path)
            self.assertFalse((Path(temp) / "evidence").exists())

    def test_tamper_and_approval_changes_fail_closed_with_unchanged_files(self):
        with TemporaryDirectory() as temp:
            source = self.sample(temp)
            self.register(temp, source)
            original = next(
                (Path(temp) / "evidence").glob(
                    "native-role-originals/F07/fund_funding_mismatch/*/original.csv"))
            original.write_text("event_id,event_date,impact\nchanged,2020-03-01,7\n")
            with self.assertRaises(ValueError):
                read_native_role_original(
                    self.document, root=Path(temp) / "evidence",
                    analysis_id="F07", role="fund_funding_mismatch")
            evidence = native_role_original_evidence(
                self.document, Path(temp) / "evidence")
            self.assertEqual(evidence["invalid_archived_roles"],
                             ["F07:fund_funding_mismatch"])
        with TemporaryDirectory() as temp:
            self.register(temp, self.sample(temp))
            changed = deepcopy(self.document)
            role = next(r for a in changed["analyses"] if a["id"] == "F07"
                        for r in a["comparison_contract"]["original_requirements"]
                        if r["role"] == "fund_funding_mismatch")
            role["description"] += " edited"
            with self.assertRaisesRegex(ValueError, "contract"):
                read_native_role_original(
                    changed, root=Path(temp) / "evidence",
                    analysis_id="F07", role="fund_funding_mismatch")

    def test_does_not_allow_scalar_source_substitution(self):
        with TemporaryDirectory() as temp:
            source = self.sample(temp)
            with self.assertRaises(ValueError):
                register_native_role_original(
                    self.document, root=Path(temp) / "evidence",
                    analysis_id="F01", role="nominal_gdp",
                    original=source, fields=["event_id","event_date","impact"],
                    key_fields=["event_id"])


if __name__ == "__main__":
    unittest.main()
