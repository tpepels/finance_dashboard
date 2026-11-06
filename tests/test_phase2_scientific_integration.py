"""Whole-contract unbound roles and same-scope accounting reconciliation."""
import corpus_counts
import unittest

from finance_dashboard.catalog import load_documents
from finance_dashboard.phase2_unbound_sources import (
    concise_unbound_discovery, unbound_original_source_discovery,
)
from finance_dashboard.phase2_accounting_validation import (
    compact_accounting_workplan, native_accounting_workplan,
)
from finance_dashboard.research_corpus import (
    load_research_corpus, research_corpus_report,
)
from finance_dashboard.stan_originals import STAN_DATAFLOW_ID
from finance_dashboard.stan_research import audit_stan_scope


def stan_original(values):
    header = (
        "DATAFLOW,FREQ,REF_AREA,ACTIVITY,MEASURE,PRICE_BASE,UNIT_MEASURE,"
        "TIME_PERIOD,OBS_VALUE,OBS_STATUS,UNIT_MULT,CURRENCY\n")
    return (header + "".join(
        f"{STAN_DATAFLOW_ID},A,PRT,C,{measure},V,XDC,2020,"
        f"{value},A,6,EUR\n" for measure, value in values.items())).encode()


class CompleteResearchSourceMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = load_research_corpus()
        cls.catalog = load_documents()[0]["series"]
        cls.report = research_corpus_report(
            cls.document, series_registry=cls.catalog)

    def test_all_21_unbound_source_roles_are_discovered_without_false_binding(self):
        result = unbound_original_source_discovery(
            self.document, self.catalog, {})
        self.assertEqual(result["unbound_scalar_roles"], corpus_counts.UNBOUND_SCALAR_ROLES)
        self.assertEqual(
            result["roles_with_reviewed_publisher_candidates"] +
            result["roles_requiring_new_publisher_discovery"] +
            result["roles_with_named_native_original_artifact"], corpus_counts.UNBOUND_SCALAR_ROLES)
        self.assertEqual(result["automatically_bound_scalar_series"], 0)
        all_rows = result["role_candidates"]
        self.assertTrue(all(not row["exact_scalar_series_bound"]
                            for row in all_rows))
        self.assertTrue(all(row["expected"] for row in all_rows))
        self.assertTrue(any(row["publisher_candidates"] for row in all_rows))
        self.assertTrue(any(not row["publisher_candidates"] for row in all_rows))
        summary = concise_unbound_discovery(result)
        self.assertEqual(len(summary["outstanding_roles"]), corpus_counts.UNBOUND_SCALAR_ROLES)
        self.assertFalse(summary["scientific_analysis_certified"])

    def test_net_operating_surplus_is_bound_to_published_components_not_mixed_income(self):
        sources = {row["id"]: row for row in self.catalog}
        for aid in ("L02", "L03"):
            role = next(r for a in self.document["analyses"] if a["id"] == aid
                        for r in a["comparison_contract"]["original_requirements"] if r["role"] == "net_operating_surplus")
            codes = {sources[sid]["source_key"].split("/")[1] for sid in role["series_ids"]}
            self.assertEqual(codes, {"B2G", "P51C"})
            self.assertNotIn("B2A3G", codes)

    def test_all_35_analyses_and_168_roles_keep_exact_native_release_gates(self):
        plan = native_accounting_workplan(
            self.document, self.report, {}, {
                "country_readiness": [],
                "publisher_measure_metadata": "metadata_not_acquired",
            })
        self.assertEqual(plan["analyses_checked"], corpus_counts.ANALYSES)
        self.assertEqual(plan["original_roles_checked"], corpus_counts.ROLES)
        self.assertEqual(len(plan["original_roles"]), corpus_counts.ROLES)
        self.assertEqual(plan["stan"]["countries_checked"], 0)
        self.assertTrue(all(not row["scientific_original_role_accepted"]
                            for row in plan["original_roles"]))
        self.assertFalse(plan["scientific_analysis_certified"])
        self.assertFalse(plan["cross_publisher_quantities_joined"])
        small = compact_accounting_workplan(plan)
        self.assertNotIn("original_roles", small)
        self.assertEqual(small["original_roles_with_missing_temporal_eligibility"],
                         corpus_counts.ROLES)


class STANNativeAccountingBridgeTests(unittest.TestCase):
    def test_gross_net_cfc_and_value_added_identities_on_exact_same_scope(self):
        values = {
            "B1G": "100.00", "D1": "60.00", "D29X39": "5.00",
            "P51C": "20.00", "B2N_B3_N": "15.00", "B2G_B3G": "35.00",
        }
        result = audit_stan_scope(
            stan_original(values), measures=tuple(values))
        checks = result["identity_checks"]
        self.assertEqual(
            checks["gross_minus_net_equals_consumption_of_fixed_capital"][
                "eligible_matched_industry_years"], 1)
        for name in (
                "net_surplus_and_mixed_income",
                "gross_surplus_and_mixed_income",
                "gross_minus_net_equals_consumption_of_fixed_capital"):
            self.assertEqual(checks[name]["outside_printed_precision_bounds"], 0)
            self.assertEqual(
                checks[name]["identity_status"],
                "consistent_with_printed_precision")
            self.assertFalse(checks[name]["certified_accounting_identity"])

    def test_incompatible_currency_and_original_mixed_income_do_not_pass(self):
        values = {
            "B1G": "100.00", "D1": "60.00", "D29X39": "5.00",
            "P51C": "20.00", "B2N_B3_N": "15.00", "B2G_B3G": "30.00",
        }
        bad = audit_stan_scope(
            stan_original(values), measures=tuple(values))
        bridge = bad["identity_checks"][
            "gross_minus_net_equals_consumption_of_fixed_capital"]
        self.assertEqual(bridge["outside_printed_precision_bounds"], 1)
        self.assertEqual(
            bridge["identity_status"], "residuals_exceed_printed_precision")
        self.assertFalse(bridge["certified_accounting_identity"])


if __name__ == "__main__":
    unittest.main()
