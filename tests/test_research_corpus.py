"""Phase 2 full scientific-membership and provenance proof tests; offline."""
import copy
import unittest

from finance_dashboard.catalog import load_documents
from finance_dashboard.research_corpus import (
    load_research_corpus, research_corpus_report, validate_research_corpus,
)


class ResearchCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = load_research_corpus()
        cls.series, _ = load_documents()

    def test_complete_35_and_49_verified_reference_contracts(self):
        self.assertEqual([], validate_research_corpus(
            self.document, self.series["series"]))
        self.assertEqual(len(self.document["analyses"]), 35)
        self.assertEqual(len(self.document["original_sources"]), 49)
        self.assertEqual(len({r["id"] for r in self.document["analyses"]}), 35)

    def test_every_question_has_explicit_unverified_evidence_until_proven(self):
        for item in self.document["analyses"]:
            self.assertEqual(item["evidence_status"],
                             "not_empirically_verified_for_phase2")
            self.assertTrue(item["primary_method_sources"])
            self.assertTrue(item["outstanding_evidence"])
            self.assertTrue(all(value is None for value in
                                item["coverage"].values()))

    def test_all_four_difficult_targets_have_original_fallback_methods(self):
        targets = {r["id"]: r for r in self.document["analyses"]}
        for ident in ("G01", "G03", "P01", "P02"):
            options = targets[ident]["fallback_options"]
            self.assertTrue(options)
            self.assertTrue(all(x["valid_concept"] for x in options))
            self.assertTrue(all(not x["data_verified"] for x in options))

    def test_reject_duplicate_or_removed_question(self):
        edited = copy.deepcopy(self.document)
        edited["analyses"][1]["id"] = edited["analyses"][0]["id"]
        issues = validate_research_corpus(edited, self.series["series"])
        self.assertTrue(any("duplicate analysis" in x for x in issues))
        self.assertTrue(any("expected all 35" in x for x in issues))

    def test_reject_unapproved_id_with_unchanged_family_count(self):
        edited = copy.deepcopy(self.document)
        original = edited["analyses"][0]["id"]
        self.assertTrue(original.startswith("C"))
        edited["analyses"][0]["id"] = "C07"
        issues = validate_research_corpus(edited, self.series["series"])
        self.assertTrue(any("expected all 35" in issue for issue in issues))
        self.assertTrue(any(original in issue and "C07" in issue for issue in issues))

    def test_reject_fake_primary_source_and_existing_series(self):
        edited = copy.deepcopy(self.document)
        edited["analyses"][0]["primary_method_sources"] = ["S99"]
        edited["analyses"][0]["existing_series_references"].append("imaginary")
        issues = validate_research_corpus(edited, self.series["series"])
        self.assertTrue(any("unknown source" in x for x in issues))
        self.assertTrue(any("pre-existing series" in x for x in issues))

    def test_reject_false_complete_without_observations(self):
        edited = copy.deepcopy(self.document)
        edited["analyses"][0]["evidence_status"] = "fully_validated_comparative_corpus"
        issues = validate_research_corpus(edited, self.series["series"])
        self.assertTrue(any("requires actual dated source evidence" in x for x in issues))

    def test_source_rows_are_not_comparative_validation(self):
        observed = {"items": [{
            "family": "macro",
            "id": "rates.us.treasury_10y_3m_spread",
            "stored_periods": 350, "oldest_source_date": "2000-01-01",
            "latest_source_date": "2026-09-01", "stored_versions": 351,
            "state": "available",
        }]}
        report = research_corpus_report(self.document, observed)
        self.assertEqual(report["analysis_count"], 35)
        self.assertEqual(report["method_source_count"], 49)
        self.assertEqual(report["fully_validated_analysis_count"], 0)
        recession = next(x for x in report["analyses"] if x["id"] == "C02")
        self.assertEqual(recession["existing_references_with_observations"], 1)
        self.assertFalse(recession["comparative_corpus_validated"])

    def test_alfred_publication_snapshots_are_not_local_ingestion_timestamps(self):
        observed = {"items": [{
            "family":"macro", "id":"bond.us.nominal_10y",
            "stored_periods":300, "oldest_source_date":"2024-01-01",
            "latest_source_date":"2026-10-30", "stored_versions":300,
            "state":"available",
        }]}
        vintages = {"series":[{"series_id":"DGS10", "count":3,
            "populated_vintage_count":2,
            "first_populated_asof":"2026-08-31",
            "last_populated_asof":"2026-09-30"}]}
        output = research_corpus_report(
            self.document, observed,
            vintages=vintages, series_registry=self.series["series"])
        self.assertTrue(output["alfred_publication_vintages_checked"])
        self.assertEqual(output["alfred_sources_with_populated_asof"],1)
        m02 = next(x for x in output["analyses"] if x["id"] == "M02")
        original = next(x for x in m02["linked_existing_series"]
                        if x["series_id"] == "bond.us.nominal_10y")
        self.assertEqual(original["original_source_asof"]["asof_snapshot_files"],3)
        self.assertEqual(original["original_source_asof"]["populated_asof_snapshots"],2)
        self.assertTrue(original["original_source_asof"]["source_publication_vintage_verified"])
        self.assertFalse(m02["comparative_corpus_validated"])
        # The latest observed economic period is never misrepresented as
        # the date it first became available to a researcher.
        self.assertNotEqual(original["latest_source_date"],
                            original["original_source_asof"]["last_populated_asof"])

    def test_no_database_evidence_is_not_zero_population(self):
        report = research_corpus_report(self.document)
        self.assertFalse(report["observations_checked"])
        self.assertEqual(report["analysis_with_any_stored_macro_observations"], 0)
        item = report["analyses"][0]["linked_existing_series"][0]
        self.assertIsNone(item["stored_periods"])


if __name__ == "__main__":
    unittest.main()
