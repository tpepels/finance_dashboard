"""Integrated official native candidate scopes and revision-gate projection."""
import unittest

from finance_dashboard.catalog import load_documents
from finance_dashboard.phase2_unbound_sources import (
    DOCUMENTED_NATIVE_DISCOVERY, unbound_original_source_discovery,
)
from finance_dashboard.research_corpus import (
    load_research_corpus, research_corpus_report,
)


class NativeOriginalDiscoveryIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = load_research_corpus()
        cls.catalog = load_documents()[0]["series"]

    def test_actual_stan_scopes_enrich_candidate_not_method_certification(self):
        readiness = {
            "country_readiness": [{
                "country": "PRT",
                "status": "same_scope_identity_diagnostic_available",
                "per_scope_coverage": [{
                    "scope": "measure-B1G+D1+B2N_B3_N+P51C+D29X39",
                    "requested_since": 1970,
                    "original_response_sha256": "a" * 64,
                    "measure_observations": {
                        "B1G": 100, "D1": 100, "B2N_B3_N": 80,
                        "P51C": 98, "D29X39": 100,
                    },
                    "year_spans_by_measure": {
                        "B1G": [2000, 2020], "D1": [2000, 2020],
                        "B2N_B3_N": [2005, 2020], "P51C": [2000, 2020],
                        "D29X39": [2000, 2020],
                    },
                }],
            }],
        }
        candidates = unbound_original_source_discovery(
            self.document, self.catalog,
            {"stan": {"original_source_hash_verified": True}},
            stan_readiness=readiness,
            stan_structure={"status": "verified_publisher_structure",
                            "historical_candidates_present": ["B2N_B3_N"]})
        self.assertEqual(candidates["unbound_scalar_roles"], 18)
        d1 = next(
            row for row in candidates["role_candidates"]
            if row["analysis_id"] == "L02" and
            row["role"] == "employee_compensation")
        proof = d1["publisher_candidates"][0][
            "original_numeric_scope_evidence"]
        self.assertEqual(proof["observed_countries"], ["PRT"])
        self.assertEqual(
            proof["max_numeric_rows_in_one_original_scope"], 100)
        self.assertEqual(proof["observed_source_scope_count"], 1)
        self.assertTrue(proof["reviewed_original_scopes"][0][
            "same_retrieval_verified"])
        self.assertFalse(proof[
            "same_industry_year_alignment_to_other_inputs_verified"])
        self.assertFalse(d1["exact_scalar_series_bound"])
        surplus = next(
            row for row in candidates["role_candidates"]
            if row["analysis_id"] == "L02" and
            row["role"] == "net_operating_surplus")
        mixed = surplus["publisher_candidates"][0]
        self.assertTrue(mixed["mixed_income_separation_unverified"])
        self.assertTrue(mixed["original_numeric_scope_evidence"][
            "verified_numeric_measure_in_original_scopes"])
        self.assertFalse(mixed["official_source_measure_verified_for_role"])
        self.assertFalse(candidates["scientific_analysis_certified"])

    def test_wiid_is_documented_native_original_and_nearby_inputs_are_not_bindings(self):
        inventory = unbound_original_source_discovery(
            self.document, self.catalog,
            {"wiid": {"original_source_hash_verified": True}})
        self.assertEqual(DOCUMENTED_NATIVE_DISCOVERY[("L07","wiid_gini")],
                         "wiid")
        gini = next(
            row for row in inventory["role_candidates"]
            if row["analysis_id"] == "L07" and
            row["role"] == "wiid_gini")
        self.assertTrue(gini["documented_artifact_original_hash_verified"])
        self.assertFalse(gini["exact_scalar_series_bound"])
        # F01 nominal_gdp was descoped (2026-11-06): BIS publishes the ratio itself.
        self.assertFalse(any(row["analysis_id"] == "F01" and row["role"] == "nominal_gdp"
                             for row in inventory["role_candidates"]))
        for row in inventory["role_candidates"]:
            self.assertTrue(all(ref["rejected_as_direct_original_role_binding"]
                                for ref in row.get("related_existing_catalog_inputs_not_equivalent", [])))
        self.assertEqual(inventory["automatically_bound_scalar_series"], 0)

    def test_native_wiid_original_reaches_gini_role_but_no_scalar_is_inferred(self):
        from finance_dashboard.phase2_structured_acquisition import (
            original_artifact_matrix,
        )
        artifact = {"wiid": {
            "status": "verified_original_wiid_release_partial",
            "original_source_hash_verified": True,
            "full_history_verified": False,
            "first_publication_verified": False,
        }}
        matrix = original_artifact_matrix(self.document, artifact)
        wiid = next(x for x in matrix["artifact_workstreams"]
                    if x["artifact_id"] == "wiid")
        self.assertIn("L07", wiid["affected_analyses"])
        self.assertEqual(wiid["role_count"], 0)
        self.assertEqual(wiid["unbound_scalar_native_reference_count"], 1)
        report = research_corpus_report(
            self.document, series_registry=self.catalog,
            artifact_evidence=artifact)
        gini = next(
            role for a in report["analyses"] if a["id"] == "L07"
            for role in a["requirements"] if role["role"] == "wiid_gini")
        self.assertEqual(gini["resolution"]["category"], 1)
        self.assertEqual(gini["resolution"]["availability"],
                         "native_original_unconverted")
        self.assertFalse(gini["accepted"])
        self.assertFalse(gini["series_ids"])
        self.assertFalse(gini["first_publication_verified"])
        self.assertEqual([a["artifact_id"] for a in
                          gini["partial_artifact_evidence"]], ["wiid"])
        self.assertEqual(report["fully_validated_analysis_count"], 0)

    def test_alfred_observation_revision_originals_are_read_but_not_automatically_certified(self):
        revisions = {"series": {"T10Y3M": {
            "verified_windows": 3,
            "verified_observation_revision_rows": 120,
            "invalid_or_conflicting_windows": 0,
        }}, "verified_windows": 3,
            "invalid_or_conflicting_windows": 0}
        report = research_corpus_report(
            self.document, series_registry=self.catalog,
            alfred_revision_proof=revisions)
        self.assertTrue(report["alfred_original_revision_inventory_checked"])
        self.assertEqual(report["alfred_verified_source_revision_windows"], 3)
        c02 = next(a for a in report["analyses"] if a["id"] == "C02")
        link = next(
            l for l in c02["linked_sources"]
            if l["series_id"] == "rates.us.treasury_10y_3m_spread")
        self.assertEqual(link["original_source_asof"][
            "official_revision_windows_verified"], 3)
        self.assertEqual(link["original_source_asof"][
            "official_revision_rows_verified"], 120)
        role = next(r for r in c02["requirements"]
                    if r["role"] == "published_yield_spread")
        temporal = next(g for g in role["checks"]
                        if g["id"] == "temporal_evidence")
        self.assertEqual(temporal["state"], "incomplete")
        self.assertEqual(temporal[
            "alfred_windows_with_complete_realtime_intervals"], 3)
        self.assertEqual(temporal["observation_first_release_dates_verified"],
                         0)
        self.assertFalse(role["accepted"])
        self.assertEqual(report["fully_validated_analysis_count"], 0)


if __name__ == "__main__":
    unittest.main()
