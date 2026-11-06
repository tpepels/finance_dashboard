"""Integrated official native candidate scopes and revision-gate projection."""
import corpus_counts
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
        self.assertEqual(candidates["unbound_scalar_roles"], corpus_counts.UNBOUND_SCALAR_ROLES)
        d1 = next(
            row for row in candidates["role_candidates"]
            if row["analysis_id"] == "L01" and
            row["role"] == "oecd_matched_value_added")
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
        self.assertFalse(candidates["scientific_analysis_certified"])

    def test_bound_survey_gini_leaves_no_native_discovery_and_nearby_inputs_are_not_bindings(self):
        inventory = unbound_original_source_discovery(
            self.document, self.catalog,
            {"wiid": {"original_source_hash_verified": True}})
        self.assertEqual(DOCUMENTED_NATIVE_DISCOVERY, {})
        self.assertFalse(any(row["analysis_id"] == "L07" for row in inventory["role_candidates"]))
        # F01 nominal_gdp was descoped (2026-11-06): BIS publishes the ratio itself.
        self.assertFalse(any(row["analysis_id"] == "F01" and row["role"] == "nominal_gdp"
                             for row in inventory["role_candidates"]))
        for row in inventory["role_candidates"]:
            self.assertTrue(all(ref["rejected_as_direct_original_role_binding"]
                                for ref in row.get("related_existing_catalog_inputs_not_equivalent", [])))
        self.assertEqual(inventory["automatically_bound_scalar_series"], 0)

    def test_survey_gini_binds_world_bank_survey_series_not_wid_shares(self):
        gini = next(r for a in self.document["analyses"] if a["id"] == "L07"
                    for r in a["comparison_contract"]["original_requirements"] if r["role"] == "wiid_gini")
        self.assertEqual(len(gini["series_ids"]), 5)
        self.assertTrue(all(sid.endswith(".gini_survey_wdi") for sid in gini["series_ids"]))
        sources = {row["id"]: row for row in self.catalog}
        self.assertTrue(all(sources[sid]["source_key"].endswith("/SI.POV.GINI") for sid in gini["series_ids"]))
        self.assertFalse(any(".pretax_income." in sid for sid in gini["series_ids"]))

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
