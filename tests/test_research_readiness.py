"""Input representations and all-analysis decisions cannot manufacture acceptance."""
import copy
import unittest

from finance_dashboard.catalog import load_documents
from finance_dashboard.research_corpus import load_research_corpus, research_corpus_report, validate_research_corpus


class ResearchReadinessTests(unittest.TestCase):
    def test_every_role_has_a_representation_and_structured_roles_are_not_missing_scalars(self):
        document = load_research_corpus()
        registry = load_documents()[0]["series"]
        report = research_corpus_report(document, series_registry=registry)
        self.assertEqual(document["schema_version"], 4)
        self.assertEqual(validate_research_corpus(document, registry), [])
        roles = [r for a in report["analyses"] for r in a["requirements"]]
        self.assertEqual(len(roles), 179)
        for role in roles:
            self.assertIn(role["input_type"], {"scalar_history", "matrix", "positions", "entity_mapping",
                "filing_panel", "events", "allocation", "policy", "fx_history", "accounting_panel", "scenario_parameter"})
            self.assertIn("resolution", role)
        g06 = next(a for a in report["analyses"] if a["id"] == "G06")
        matrix = next(r for r in g06["requirements"] if r["role"] == "intermediate_transactions")
        self.assertEqual(matrix["input_type"], "matrix")
        self.assertEqual(matrix["resolution"]["category"], 3)
        self.assertNotEqual(matrix["requirement_status"], "missing_scalar")
        summary = report["role_resolution_summary"]
        self.assertEqual(summary["role_count"], 179)
        self.assertEqual(summary["scalar_roles"] + summary["structured_roles"], 179)
        self.assertLess(summary["unbound_scalar_roles"], 88)

    def test_readiness_matrix_covers_35_and_preserves_original_blockers(self):
        report = research_corpus_report(load_research_corpus(), series_registry=load_documents()[0]["series"])
        self.assertEqual(len(report["readiness_matrix"]), 37)
        for row in report["readiness_matrix"]:
            self.assertIn(row["decision"], {"complete", "conditional", "blocked", "deferred"})
            self.assertNotEqual(row["decision"], "complete")
            self.assertTrue(row["reasons"])
            self.assertIn("original", row)
            self.assertIn("fallback", row)
            self.assertFalse(row["production_integration_ready"])

    def test_verified_fund_fallback_is_conditional_and_never_certifies_index_universe(self):
        report = research_corpus_report(load_research_corpus(), series_registry=load_documents()[0]["series"],
            artifact_evidence={"sec_holdings": {"original_source_hash_verified": True,
                "bounded_data_verified": True, "source_count": 28, "full_history_verified": False}})
        row = next(row for row in report["readiness_matrix"] if row["id"] == "G01")
        self.assertEqual(row["original"]["decision"], "blocked")
        self.assertEqual(row["fallback"]["decision"], "conditional")
        self.assertEqual(row["fallback"]["verified_structured_alternatives"], ["sec_holdings"])
        self.assertFalse(row["original"]["accepted"])
        self.assertFalse(row["production_integration_ready"])

    def test_unknown_or_scalar_artifact_representation_cannot_hide_missing_source(self):
        document = copy.deepcopy(load_research_corpus())
        role = document["analyses"][0]["comparison_contract"]["original_requirements"][0]
        role["input_type"] = "invented"
        self.assertTrue(any("input representation" in e for e in validate_research_corpus(document, load_documents()[0]["series"])))
        role["input_type"] = "scalar_history"
        role["artifact_ids"] = ["fake"]
        self.assertTrue(any("artifact" in e for e in validate_research_corpus(document, load_documents()[0]["series"])))

    def test_native_weekly_and_fine_wealth_bindings_keep_real_periods(self):
        from finance_dashboard.comparative_corpus import _native_period, _regular_grid
        from datetime import date
        self.assertTrue(_native_period(date(2026, 10, 30), "W"))
        self.assertFalse(_native_period(date(2026, 10, 29), "W"))
        self.assertEqual(_regular_grid(date(2026, 10, 16), date(2026, 10, 30), "W"),
                         {date(2026, 10, 16), date(2026, 10, 23), date(2026, 10, 30)})
        self.assertEqual(_regular_grid(date(2026, 10, 17), date(2026, 10, 30), "W"),
                         {date(2026, 10, 23), date(2026, 10, 30)})
        document = load_research_corpus()
        analyses = {a["id"]: a for a in document["analyses"]}
        for ident, expected in {"F04": {"nfci", "adjusted_nfci"},
                                "L05": {"net_worth_top_point1", "net_worth_next_point9"},
                                "F05": {"national_government_debt_gdp"}}.items():
            for role in analyses[ident]["comparison_contract"]["original_requirements"]:
                if role["role"] in expected:
                    self.assertTrue(role["series_ids"])

    def test_five_source_rounded_wealth_groups_keep_their_own_rounding_bound(self):
        from finance_dashboard.comparative_corpus import _check_values
        ids = ["wealth.us." + group + "_share" for group in
               ("top_point1", "next_point9", "next9", "middle40", "bottom50")]
        row = {"period": "2026-04-01", "values": dict(zip(ids, ["15", "17.5", "36.1", "28.9", "2.7"]))}
        result = _check_values("share_partition_100", [row], ids)
        self.assertTrue(result["passed"])
        self.assertEqual(result["tolerance"], "0.25")
        row["values"][ids[-1]] = "2.8"
        self.assertFalse(_check_values("share_partition_100", [row], ids)["passed"])

    def test_empty_native_count_history_fails_closed_without_empty_range_crash(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from finance_dashboard.source_reconciliation import _reconcile_values
        sid = "concentration.global.msci_acwi_constituent_count"
        with TemporaryDirectory() as root, patch("finance_dashboard.msci_concentration_originals.read_msci_concentration_originals",
                return_value=({}, {"constituent_count_values": {}})):
            proof = _reconcile_values({sid: {}}, "sqlite", root)
        self.assertFalse(proof["passed"])
        self.assertEqual(proof["series"][0]["failure_code"], "source_empty")

    def test_retained_sector_gva_is_unconnected_candidate_not_missing_source_discovery(self):
        registry = load_documents()[0]["series"]
        original = {"original_source_hash_verified": True, "required_variable_coverage": {
            "gross_value_added": {"source_coverage": {"profit.oecd38.corporate_gross_surplus_gdp": {
                "S11": {"country_year_pairs": 943, "geographies_ever_reported": 33}}}}}}
        def role(evidence):
            report = research_corpus_report(load_research_corpus(), series_registry=registry,
                                           artifact_evidence={"corporate_accounts": evidence})
            return next(r for a in report["analyses"] if a["id"] == "L03" for r in a["requirements"] if r["role"] == "gross_value_added")
        candidate = role(original)
        self.assertEqual(candidate["resolution"]["category"], 1)
        self.assertFalse(candidate["resolution"]["connected"])
        self.assertFalse(candidate["resolution"]["exact_role_satisfied"])
        self.assertEqual(candidate["series_ids"], [])
        self.assertFalse(candidate["accepted"])
        self.assertEqual(role({**original, "original_source_hash_verified": False})["resolution"]["category"], 5)
