"""Phase 2 full scientific-membership and provenance proof tests; offline."""
import corpus_counts
import copy
import os
from pathlib import Path
import subprocess
import sys
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

    def test_offline_status_does_not_import_spreadsheet_backends(self):
        """Source-contract reporting must not depend on original artifact parsers."""
        root = Path(__file__).resolve().parents[1]
        code = (
            'import sys; sys.modules["python_calamine"] = None; '
            'from finance_dashboard.research_corpus import load_research_corpus, '
            'validate_research_corpus; from finance_dashboard.catalog import load_documents; '
            'corpus = load_research_corpus(); registry, _ = load_documents(); '
            'assert len(corpus["analyses"]) == 39; '
            'assert validate_research_corpus(corpus, registry["series"]) == []'
        )
        env = dict(os.environ)
        env["PYTHONPATH"] = str(root / "src")
        result = subprocess.run(
            [sys.executable, "-c", code], cwd=root, env=env,
            capture_output=True, text=True, timeout=25, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_complete_35_and_49_verified_reference_contracts(self):
        self.assertEqual([], validate_research_corpus(
            self.document, self.series["series"]))
        self.assertEqual(len(self.document["analyses"]), corpus_counts.ANALYSES)
        self.assertEqual(len(self.document["original_sources"]), 50)
        self.assertIn("S50", {row["id"] for row in self.document["original_sources"]})
        self.assertEqual(len({r["id"] for r in self.document["analyses"]}), corpus_counts.ANALYSES)

    def test_every_question_has_requirements_instead_of_editable_certificates(self):
        for item in self.document["analyses"]:
            self.assertNotIn("evidence_status", item)
            self.assertNotIn("coverage", item)
            self.assertTrue(item["primary_method_sources"])
            self.assertTrue(item["outstanding_evidence"])
            self.assertTrue(item["comparison_contract"]["original_requirements"])

    def test_canonical_source_graph_has_no_parallel_inventory_or_stored_binding_state(self):
        self.assertEqual(self.document["schema_version"], 4)
        for item in self.document["analyses"]:
            self.assertNotIn("existing_series_references", item)
            self.assertNotIn("existing_adapter_references", item)
            self.assertIsInstance(item["context_series_ids"], list)
            for role in item["comparison_contract"]["original_requirements"]:
                self.assertNotIn("requirement_status", role)

    def test_report_derives_source_links_and_binding_state_from_canonical_bindings(self):
        document = copy.deepcopy(self.document)
        question = next(a for a in document["analyses"] if a["id"] == "C01")
        question.pop("existing_series_references", None)
        question.pop("existing_adapter_references", None)
        question["context_series_ids"] = ["gdp.real_growth.jp"]
        report = research_corpus_report(document, series_registry=self.series["series"])
        result = next(a for a in report["analyses"] if a["id"] == "C01")
        ids = {s["series_id"] for s in result["linked_sources"]}
        self.assertIn("activity.us.real_gdp_level", ids)
        self.assertIn("gdp.real_growth.jp", ids)
        self.assertEqual(result["source_reference_count"], len(ids))
        for role in result["requirements"]:
            self.assertEqual(role["requirement_status"], "mapped" if role["series_ids"] else "missing_scalar")
        self.assertFalse(next(r for r in result["requirements"] if r["role"] == "oecd_cli")["accepted"])

    def test_legacy_bindings_and_context_duplicates_are_rejected(self):
        for key, value in (("existing_series_references", []), ("existing_adapter_references", [])):
            document = copy.deepcopy(self.document)
            document["analyses"][0][key] = value
            issues = validate_research_corpus(document, self.series["series"])
            self.assertTrue(any("legacy source inventory" in issue for issue in issues), issues)
        document = copy.deepcopy(self.document)
        role = document["analyses"][0]["comparison_contract"]["original_requirements"][0]
        role["requirement_status"] = "mapped"
        self.assertTrue(any("derived requirement status" in issue for issue in
                            validate_research_corpus(document, self.series["series"])))
        document = copy.deepcopy(self.document)
        document["analyses"][0]["context_series_ids"] = ["activity.us.industrial_production"] * 2
        self.assertTrue(any("context source" in issue for issue in
                            validate_research_corpus(document, self.series["series"])))

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
        self.assertTrue(any("expected all 39" in x for x in issues))

    def test_reject_unapproved_id_with_unchanged_family_count(self):
        edited = copy.deepcopy(self.document)
        original = edited["analyses"][0]["id"]
        self.assertTrue(original.startswith("C"))
        edited["analyses"][0]["id"] = "C08"
        issues = validate_research_corpus(edited, self.series["series"])
        self.assertTrue(any("expected all 39" in issue for issue in issues))
        self.assertTrue(any(original in issue and "C08" in issue for issue in issues))

    def test_reject_fake_primary_source_and_context_series(self):
        edited = copy.deepcopy(self.document)
        edited["analyses"][0]["primary_method_sources"] = ["S99"]
        edited["analyses"][0]["context_series_ids"] = ["imaginary"]
        issues = validate_research_corpus(edited, self.series["series"])
        self.assertTrue(any("unknown source" in x for x in issues))
        self.assertTrue(any("context source" in x for x in issues))

    def test_editable_certificates_are_rejected_even_with_plausible_dated_counts(self):
        for status in ("verified_source_data", "fully_validated_comparative_corpus"):
            edited = copy.deepcopy(self.document)
            edited["analyses"][0]["evidence_status"] = status
            edited["analyses"][0]["coverage"] = {
                "first_observation": "2025-01-01", "last_observation": "2026-01-01",
                "periods_observed": 2, "publication_vintages": 5,
                "asof_utc": "2026-11-04T12:00:00Z",
            }
            issues = validate_research_corpus(edited, self.series["series"])
            self.assertTrue(any("editable evidence certificate" in issue for issue in issues), issues)
            report = research_corpus_report(edited, series_registry=self.series["series"])
            self.assertEqual(report["fully_validated_analysis_count"], 0)
            self.assertFalse(any(row["comparative_corpus_validated"] for row in report["analyses"]))

    def test_requirement_and_variant_bindings_reject_unknown_or_mismatched_sources(self):
        edited = copy.deepcopy(self.document)
        m02 = next(row for row in edited["analyses"] if row["id"] == "M02")
        m02["comparison_contract"]["original_requirements"][0]["expected"]["unit"] = "ratio"
        m02["comparison_contract"]["variants"][0]["frequency"] = "M"
        issues = validate_research_corpus(edited, self.series["series"])
        self.assertTrue(any("native unit" in issue for issue in issues), issues)
        self.assertTrue(any("native frequency" in issue for issue in issues), issues)
        m02["comparison_contract"]["original_requirements"][0]["series_ids"] = ["imaginary"]
        issues = validate_research_corpus(edited, self.series["series"])
        self.assertTrue(any("requirement source" in issue for issue in issues), issues)

    def test_source_period_counts_never_satisfy_first_publication_requirements(self):
        observed = {"items": [{"family": "macro", "id": "bond.us.nominal_10y",
            "stored_periods": 10000, "state": "available"}]}
        report = research_corpus_report(self.document, observed, series_registry=self.series["series"])
        m02 = next(row for row in report["analyses"] if row["id"] == "M02")
        requirement = next(row for row in m02["requirements"] if row["role"] == "nominal_10y_yield")
        self.assertFalse(requirement["accepted"])
        self.assertFalse(requirement["first_publication_verified"])
        self.assertEqual(report["fully_validated_analysis_count"], 0)

    def test_source_contracts_preserve_native_frequency_and_measurement_identity(self):
        registry = copy.deepcopy(self.series["series"])
        nominal = next(x for x in registry if x["id"] == "bond.us.nominal_10y")
        nominal["request_url"] = "https://provider.invalid/?api_key=PRIVATE"
        nominal["error"] = "PRIVATE upstream error"
        report = research_corpus_report(self.document, series_registry=registry)
        questions = {x["id"]: x for x in report["analyses"]}
        contract = next(x for x in questions["M02"]["linked_sources"]
                        if x["series_id"] == "bond.us.nominal_10y").get("source_contract")
        self.assertIsInstance(contract, dict)
        for question, sid, frequency in (
            ("M02", "bond.us.nominal_10y", "D"),
            ("C02", "recession.us.sahm", "M"),
            ("L05", "wealth.us.top1_share", "Q"),
            ("V02", "valuation.us.tobins_q2", "A"),
        ):
            with self.subTest(series=sid):
                link = next(x for x in questions[question]["linked_sources"]
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
        link = next(x for x in question["linked_sources"]
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
        link = next(x for x in question["linked_sources"]
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
        self.assertEqual(report["analysis_count"], corpus_counts.ANALYSES)
        self.assertEqual(report["method_source_count"], 50)
        self.assertEqual(report["fully_validated_analysis_count"], 0)
        recession = next(x for x in report["analyses"] if x["id"] == "C02")
        self.assertEqual(recession["source_references_with_observations"], 1)
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
        original = next(x for x in m02["linked_sources"]
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
        item = report["analyses"][0]["linked_sources"][0]
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
                link = next(x for x in question["linked_sources"]
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
        link = next(x for x in question["linked_sources"]
                    if x["series_id"] == "bond.us.nominal_10y")
        publication = link["original_source_asof"]
        self.assertTrue(publication.get("checked"))
        self.assertEqual(publication["asof_snapshot_files"], 0)
        self.assertEqual(publication["populated_asof_snapshots"], 0)
        self.assertIs(publication.get("first_publication_vintage_verified"), False)


if __name__ == "__main__":
    unittest.main()


class ShockEventRegisterTests(unittest.TestCase):
    def test_every_event_is_dated_sourced_and_unique(self):
        import json
        from datetime import date
        from pathlib import Path
        doc = json.loads((Path(__file__).resolve().parents[1] / "definitions" / "shock_events.json").read_text())
        ids = [e["id"] for e in doc["events"]]
        self.assertEqual(len(ids), len(set(ids)))
        for event in doc["events"]:
            date.fromisoformat(event["date"])
            self.assertTrue(event["source_url"].startswith("https://"))
            self.assertTrue(event["label"].strip())
