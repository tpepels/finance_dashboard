"""Original-source candidates and revised scientific temporal evidence."""
import corpus_counts
from copy import deepcopy
import unittest

from finance_dashboard.catalog import load_documents
from finance_dashboard.phase2_unbound_sources import (
    concise_unbound_discovery, unbound_original_source_discovery,
)
from finance_dashboard.research_corpus import (
    load_research_corpus, research_corpus_report,
)


class IndependentNativeRoleDiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = load_research_corpus()
        cls.catalog = load_documents()[0]["series"]

    def test_all_21_roles_are_reviewed_without_invented_scalar_bindings(self):
        report = unbound_original_source_discovery(
            self.document, self.catalog, {})
        self.assertEqual(report["unbound_scalar_roles"], corpus_counts.UNBOUND_SCALAR_ROLES)
        self.assertEqual(report["automatically_bound_scalar_series"], 0)
        self.assertEqual(
            report["roles_with_reviewed_publisher_candidates"] +
            report["roles_requiring_new_publisher_discovery"] +
            report["roles_with_named_native_original_artifact"], corpus_counts.UNBOUND_SCALAR_ROLES)
        # L07's survey Gini is bound (World Bank PIP), so it is no longer an unbound candidate.
        self.assertFalse(any(r["analysis_id"] == "L07" and r["role"] == "wiid_gini"
                             for r in report["role_candidates"]))
        self.assertTrue(any(
            r["related_existing_catalog_inputs_not_equivalent"]
            for r in report["role_candidates"]))
        self.assertTrue(report["no_missing_observations_interpolated"])

    def test_one_retained_scope_is_source_data_not_scalar_method_certification(self):
        native = {"stan": {
            "status": "verified_original_stan_partial",
            "original_source_hash_verified": True,
        }}
        readiness = {"country_readiness": [{
            "country": "PRT", "status": "same_scope_identity_diagnostic_available",
            "per_scope_coverage": [{
                "scope": "A.PRT", "requested_since": 1970,
                "original_response_sha256": "a" * 64,
                "measure_observations": {
                    "B1G": 15, "D1": 15, "B2N_B3_N": 5, "P51C": 12,
                },
                "year_spans_by_measure": {
                    "B1G": [2000, 2020], "D1": [2000, 2020],
                    "B2N_B3_N": [2000, 2020], "P51C": [2000, 2020],
                },
            }],
        }]}
        metadata = {
            "status": "verified_publisher_structure",
            "historical_candidates_present": ["B2N_B3_N"],
        }
        report = unbound_original_source_discovery(
            corpus_counts.with_unbound_l01_candidates(self.document), self.catalog, native,
            stan_readiness=readiness, stan_structure=metadata)
        # L02's surplus is bound to OECD sector accounts; STAN remains a candidate for L01's industry match.
        source = next(
            x for row in report["role_candidates"]
            if row["analysis_id"] == "L01" and
            row["role"] == "oecd_matched_value_added"
            for x in row["publisher_candidates"])
        self.assertEqual(
            source["original_numeric_scope_evidence"]["observed_countries"],
            ["PRT"])
        self.assertEqual(
            source["original_numeric_scope_evidence"][
                "max_numeric_rows_in_one_original_scope"], 15)
        self.assertFalse(source["official_source_measure_verified_for_role"])

        summary = concise_unbound_discovery(report)
        self.assertEqual(summary["unbound_scalar_roles"], corpus_counts.UNBOUND_WITH_L01_LEADS)
        self.assertGreater(sum(r["original_native_observed_scope_count"]
                              for r in summary["outstanding_roles"]), 0)

        evaluated = research_corpus_report(
            corpus_counts.with_unbound_l01_candidates(self.document), series_registry=self.catalog,
            unbound_source_evidence=report)
        role = next(
            r for a in evaluated["analyses"] if a["id"] == "L01"
            for r in a["requirements"]
            if r["role"] == "oecd_matched_value_added")
        gates = {x["id"]: x for x in role["checks"]}
        self.assertEqual(gates["source_binding"]["state"], "incomplete")
        self.assertEqual(gates["native_dimensions"]["state"], "incomplete")
        self.assertEqual(gates["original_source_values"]["state"], "incomplete")
        self.assertEqual(role["resolution"]["availability"],
                         "original_native_partial")
        self.assertFalse(role["accepted"])
        self.assertEqual(evaluated["fully_validated_analysis_count"], 0)

    def test_alfred_revision_windows_reach_temporal_gate_without_source_release_claim(self):
        source = "DGS10"
        revisions = {"series": {
            source: {
                "series_id": source,
                "verified_windows": 2,
                "verified_observation_revision_rows": 18,
                "invalid_or_conflicting_windows": 0,
            },
        }, "verified_windows": 2, "invalid_or_conflicting_windows": 0}
        report = research_corpus_report(
            self.document, series_registry=self.catalog,
            alfred_revision_proof=revisions)
        self.assertTrue(report["alfred_original_revision_inventory_checked"])
        self.assertEqual(report["alfred_verified_source_revision_windows"], 2)
        matches = [
            (analysis, role, item)
            for analysis in report["analyses"]
            for role in analysis["requirements"]
            for item in role["checks"]
            if item["id"] == "temporal_evidence"
            and any(x["alfred_source_key"] == source
                    for x in item.get("verified_original_revision_sources", []))
        ]
        self.assertTrue(matches)
        for _, role, gate in matches:
            self.assertEqual(gate["state"], "incomplete")
            self.assertEqual(gate["observation_first_release_dates_verified"], 0)
            self.assertFalse(role["first_publication_verified"])
            self.assertFalse(role["accepted"])
        linked = [
            x for analysis in report["analyses"]
            for x in analysis["linked_sources"]
            if x["original_source_asof"] and
            x["original_source_asof"]["original_fred_id"] == source
        ]
        self.assertTrue(linked)
        self.assertTrue(all(x["original_source_asof"][
            "official_revision_windows_verified"] == 2 for x in linked))
        self.assertEqual(report["fully_validated_analysis_count"], 0)


if __name__ == "__main__":
    unittest.main()
