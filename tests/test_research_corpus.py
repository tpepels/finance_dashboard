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

    def test_verified_coverage_rejects_invalid_dates_counts_and_naive_asof(self):
        valid = {
            "first_observation": "2025-01-01", "last_observation": "2026-01-01",
            "periods_observed": 2, "publication_vintages": None,
            "asof_utc": "2026-11-04T12:00:00+00:00",
        }
        for status in ("verified_source_data", "fully_validated_comparative_corpus"):
            for field, value in (
                ("first_observation", "not-a-date"),
                ("first_observation", "2027-01-01"),
                ("last_observation", "2026-02-30"),
                ("periods_observed", True), ("periods_observed", 0),
                ("asof_utc", "not-a-timestamp"),
                ("asof_utc", "2026-11-04T12:00:00"),
            ):
                with self.subTest(status=status, field=field, value=value):
                    edited = copy.deepcopy(self.document)
                    edited["analyses"][0]["evidence_status"] = status
                    edited["analyses"][0]["coverage"] = {**valid, field: value}
                    issues = validate_research_corpus(edited, self.series["series"])
                    self.assertTrue(any("requires actual dated source evidence" in x
                                        for x in issues), issues)

    def test_verified_coverage_accepts_ordered_dates_and_aware_asof(self):
        edited = copy.deepcopy(self.document)
        edited["analyses"][0]["evidence_status"] = "verified_source_data"
        edited["analyses"][0]["coverage"] = {
            "first_observation": "2025-01-01", "last_observation": "2026-01-01",
            "periods_observed": 2, "publication_vintages": None,
            "asof_utc": "2026-11-04T12:00:00Z",
        }
        self.assertEqual([], validate_research_corpus(edited, self.series["series"]))

    def test_source_contracts_preserve_native_frequency_and_measurement_identity(self):
        registry = copy.deepcopy(self.series["series"])
        nominal = next(x for x in registry if x["id"] == "bond.us.nominal_10y")
        nominal["request_url"] = "https://provider.invalid/?api_key=PRIVATE"
        nominal["error"] = "PRIVATE upstream error"
        report = research_corpus_report(self.document, series_registry=registry)
        questions = {x["id"]: x for x in report["analyses"]}
        contract = next(x for x in questions["M02"]["linked_existing_series"]
                        if x["series_id"] == "bond.us.nominal_10y").get("source_contract")
        self.assertIsInstance(contract, dict)
        for question, sid, frequency in (
            ("M02", "bond.us.nominal_10y", "D"),
            ("C02", "recession.us.sahm", "M"),
            ("L05", "wealth.us.top1_share", "Q"),
            ("V02", "valuation.us.tobins_q2", "A"),
        ):
            with self.subTest(series=sid):
                link = next(x for x in questions[question]["linked_existing_series"]
                            if x["series_id"] == sid)
                self.assertIsInstance(link.get("source_contract"), dict)
                self.assertEqual(link["source_contract"]["frequency"], frequency)
        self.assertEqual(contract["provider"], "FRED")
        self.assertEqual(contract["source_key"], "DGS10")
        self.assertEqual(contract["source_url"], "https://fred.stlouisfed.org/series/DGS10")
        self.assertEqual(contract["geography"], "US")
        self.assertEqual(contract["unit"], "percent")
        self.assertTrue(contract["measurement"])
        self.assertEqual(contract["revision_policy"], "revisable")
        self.assertEqual(contract["rights"], "review_required")
        self.assertNotIn("PRIVATE", str(report))

    def test_coverage_provenance_and_method_sources_are_inspectable(self):
        observed = {"asof": "2026-11-04", "items": [{
            "family": "macro", "id": "bond.us.nominal_10y", "frequency": "D",
            "stored_periods": 2, "oldest_source_date": "2026-10-29",
            "latest_source_date": "2026-10-30", "stored_versions": 3,
            "additional_revisions": 1, "state": "refresh_failed_with_data",
            "unobserved_internal_periods": None, "regular_cadence_assumed": True,
            "published_through": None, "published_release": None,
            "published_release_date": None, "complete_for_pinned_release": False,
            "last_success_utc": "2026-10-31T12:00:00+00:00",
            "last_attempt_utc": "2026-11-04T12:00:00+00:00",
            "last_attempt_state": "failed", "last_failure_code": "provider_failed",
            "request_url": "https://provider.invalid/?api_key=PRIVATE",
            "error": "PRIVATE upstream error",
        }]}
        document = copy.deepcopy(self.document)
        document["original_sources"][4]["request_url"] = "PRIVATE"
        report = research_corpus_report(document, observed, series_registry=self.series["series"])
        self.assertEqual(report.get("observation_evidence_asof"), "2026-11-04")
        question = next(x for x in report["analyses"] if x["id"] == "M02")
        link = next(x for x in question["linked_existing_series"]
                    if x["series_id"] == "bond.us.nominal_10y")
        self.assertIsInstance(link.get("observation_coverage"), dict)
        coverage = link["observation_coverage"]
        self.assertEqual(coverage["stored_periods"], 2)
        self.assertEqual(coverage["additional_revisions"], 1)
        self.assertEqual(coverage["state"], "refresh_failed_with_data")
        self.assertEqual(coverage["last_success_utc"], "2026-10-31T12:00:00+00:00")
        self.assertIsNone(coverage["unobserved_internal_periods"])
        self.assertTrue(coverage["regular_cadence_assumed"])
        recession = next(x for x in report["analyses"] if x["id"] == "C02")
        self.assertIsInstance(recession.get("method_sources"), list)
        self.assertEqual(recession["method_sources"][0], {
            "id": "S05",
            "label": "Estrella & Mishkin (1995), Predicting U.S. Recessions, NBER w5379; published 1998",
            "url": "https://www.nber.org/papers/w5379",
        })
        self.assertNotIn("PRIVATE", str(report))
        self.assertFalse(question["comparative_corpus_validated"])

    def test_pinned_release_bounds_remain_source_coverage_not_publication_vintage(self):
        observed = {"asof": "2026-11-04", "items": [{
            "family": "macro", "id": "labour.us.pwt_labour_share", "frequency": "A",
            "stored_periods": 74, "oldest_source_date": "1950-01-01",
            "latest_source_date": "2023-01-01", "stored_versions": 74,
            "state": "available", "published_through": "2023-01-01",
            "published_release": "Penn World Table 11.0",
            "published_release_date": "2025-10-07", "complete_for_pinned_release": True,
            "regular_cadence_assumed": True, "unobserved_internal_periods": 0,
        }]}
        report = research_corpus_report(self.document, observed, series_registry=self.series["series"])
        question = next(x for x in report["analyses"] if x["id"] == "L02")
        link = next(x for x in question["linked_existing_series"]
                    if x["series_id"] == "labour.us.pwt_labour_share")
        self.assertIsInstance(link.get("observation_coverage"), dict)
        coverage = link["observation_coverage"]
        self.assertEqual(coverage["published_through"], "2023-01-01")
        self.assertEqual(coverage["published_release"], "Penn World Table 11.0")
        self.assertEqual(coverage["published_release_date"], "2025-10-07")
        self.assertTrue(coverage["complete_for_pinned_release"])
        self.assertFalse(link["original_source_asof"]["checked"])
        self.assertFalse(link["original_source_asof"]["first_publication_vintage_verified"])
        self.assertFalse(question["comparative_corpus_validated"])

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
        self.assertTrue(original["original_source_asof"].get("checked"))
        self.assertIs(original["original_source_asof"].get("first_publication_vintage_verified"), False)
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
        self.assertIn("source_contract", item)
        self.assertIsNone(item["source_contract"])
        self.assertIn("observation_coverage", item)
        self.assertIsNone(item["observation_coverage"])
        self.assertIn("observation_evidence_asof", report)
        self.assertIsNone(report["observation_evidence_asof"])

    def test_unchecked_vintage_inventory_does_not_claim_zero_snapshots(self):
        for inventory in (None, {"series": []}):
            with self.subTest(inventory=inventory):
                report = research_corpus_report(self.document, vintages=inventory,
                                               series_registry=self.series["series"])
                question = next(x for x in report["analyses"] if x["id"] == "M02")
                link = next(x for x in question["linked_existing_series"]
                            if x["series_id"] == "bond.us.nominal_10y")
                publication = link["original_source_asof"]
                self.assertIs(publication.get("checked"), False)
                self.assertIsNone(publication["asof_snapshot_files"])
                self.assertIsNone(publication["populated_asof_snapshots"])
                self.assertFalse(publication["source_publication_vintage_verified"])

    def test_checked_empty_vintage_inventory_reports_zero_without_first_publication_proof(self):
        report = research_corpus_report(self.document,
            vintages={"series": [{"series_id": "DGS10", "count": 0,
                                  "populated_vintage_count": 0}]},
            series_registry=self.series["series"])
        question = next(x for x in report["analyses"] if x["id"] == "M02")
        link = next(x for x in question["linked_existing_series"]
                    if x["series_id"] == "bond.us.nominal_10y")
        publication = link["original_source_asof"]
        self.assertTrue(publication.get("checked"))
        self.assertEqual(publication["asof_snapshot_files"], 0)
        self.assertEqual(publication["populated_asof_snapshots"], 0)
        self.assertIs(publication.get("first_publication_vintage_verified"), False)


if __name__ == "__main__":
    unittest.main()
