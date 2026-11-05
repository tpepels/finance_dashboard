"""Country/year accounting evidence: coverage gaps, revisions and unit safety."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from finance_dashboard.stan_originals import (
    STAN_DATAFLOW_ID, STAN_VERIFIED_PORTUGAL_MEASURES,
    store_stan_original,
)
from finance_dashboard.stan_research import (
    audit_stan_originals, audit_stan_scope, summarize_scope_coverage,
)

HEADER = (
    "DATAFLOW,FREQ,REF_AREA,ACTIVITY,MEASURE,PRICE_BASE,UNIT_MEASURE,"
    "TIME_PERIOD,OBS_VALUE,OBS_STATUS,UNIT_MULT,CURRENCY\n"
)
CORE = ("B1G", "D1", "P51C", "D29X39")
NET = ("B1G", "D1", "B2N_B3_N", "P51C", "D29X39")


def original(rows, *, country="PRT"):
    return (HEADER + "".join(
        f"{STAN_DATAFLOW_ID},A,{country},{activity},{measure},V,XDC,"
        f"{year},{value},{status},{mult},{currency}\n"
        for activity, measure, year, value, status, mult, currency in rows
    )).encode()


def core_rows(*, b1g="120.00", year=2020, activity="C",
              status="A", multiplier="6", currency="EUR"):
    values = [
        ("B1G", b1g), ("D1", "70.00"),
        ("P51C", "12.00"), ("D29X39", "3.00"),
    ]
    return [
        (activity, measure, year, value, status, multiplier, currency)
        for measure, value in values
    ]


class SourceCompletenessTests(unittest.TestCase):
    def test_year_by_measure_coverage_is_not_overstated(self):
        rows = core_rows(year=2001)
        rows += [("C", "B1G", 2002, "125", "E", "6", "EUR")]
        rows += [("C", "D1", 2002, "", "E", "6", "EUR")]
        result = summarize_scope_coverage(original(rows), measures=CORE)
        self.assertEqual(result["observed_year_count"], 2)
        self.assertEqual(result["min_year"], 2001)
        self.assertEqual(result["max_year"], 2002)
        self.assertEqual(result["per_measure"]["B1G"]["numeric_observations"], 2)
        self.assertEqual(result["per_measure"]["D1"]["numeric_observations"], 1)
        self.assertEqual(result["per_measure"]["D1"]["missing_source_values"], 1)
        self.assertEqual(result["per_measure"]["D1"]["last_observed_year"], 2001)
        self.assertEqual(result["source_status_flag_counts"]["E"], 2)
        self.assertEqual(result["per_year"]["2002"]["numeric"], 1)
        self.assertEqual(result["per_year"]["2002"]["measure_counts"]["B1G"], 1)
        self.assertTrue(result["observations_not_additively_aggregated"])

    def test_unit_and_currency_change_is_exposed(self):
        rows = core_rows(year=2001)
        rows += core_rows(year=2002, currency="PTE", multiplier="3")
        report = summarize_scope_coverage(original(rows), measures=CORE)
        units = report["per_measure"]["B1G"]["published_unit_currency_pairs"]
        self.assertEqual(len(units), 2)
        self.assertIn({"unit_multiplier": "6", "currency": "EUR"}, units)
        self.assertIn({"unit_multiplier": "3", "currency": "PTE"}, units)

    def test_mixed_currency_identity_is_not_calculated(self):
        rows = core_rows()
        rows.append(("C", "B2N_B3_N", 2020, "35.00", "A", "6", "PTE"))
        result = audit_stan_scope(original(rows), measures=NET)
        net = result["identity_checks"]["net_surplus_and_mixed_income"]
        self.assertEqual(net["eligible_matched_industry_years"], 0)
        self.assertEqual(net["incompatible_or_unreported_unit_groups"], 1)
        self.assertEqual(net["outside_printed_precision_bounds"], 0)

    def test_source_status_flag_change_is_not_misreported_as_numeric_change(self):
        with TemporaryDirectory() as t:
            root = Path(t)
            original_scope = original(core_rows())
            updated_scope = original(
                core_rows(status="E") +
                [("C", "B2N_B3_N", 2020, "35.00", "E", "6", "EUR")])
            store_stan_original(
                original_scope, country="PRT", start_year=1970, root=root,
                measures=STAN_VERIFIED_PORTUGAL_MEASURES)
            store_stan_original(
                updated_scope, country="PRT", start_year=1970, root=root,
                measures=NET)
            report = audit_stan_originals(root, countries=("PRT",))
            comparison = report["country_audits"][0]["cross_scope_reconciliation"]
            self.assertEqual(comparison["compared_scope_pairs"], 1)
            pair = comparison["comparisons"][0]
            self.assertEqual(pair["same_measure_industry_year_overlap"], 4)
            self.assertEqual(pair["numeric_value_disagreements_same_unit"], 0)
            self.assertEqual(pair["equal_value_same_unit"], 4)
            self.assertEqual(pair["source_flag_changes"], 4)
            self.assertFalse(pair["release_vintage_agreement_established"])
            self.assertFalse(comparison["cross_scope_values_merged"])


class IndependentOriginalComparisonTests(unittest.TestCase):
    def test_same_measure_revision_is_detected_without_cross_source_identity(self):
        with TemporaryDirectory() as t:
            root = Path(t)
            store_stan_original(
                original(core_rows()), country="PRT",
                start_year=1970, root=root,
                measures=STAN_VERIFIED_PORTUGAL_MEASURES)
            new_rows = core_rows(b1g="125.00") + [
                ("C", "B2N_B3_N", 2020, "40.00", "A", "6", "EUR")
            ]
            store_stan_original(
                original(new_rows), country="PRT",
                start_year=1970, root=root, measures=NET)
            report = audit_stan_originals(root, countries=("PRT",))
            result = report["country_audits"][0]
            compare = result["cross_scope_reconciliation"]["comparisons"][0]
            self.assertEqual(compare["same_measure_industry_year_overlap"], 4)
            self.assertEqual(compare["numeric_value_disagreements_same_unit"], 1)
            self.assertEqual(compare["incompatible_or_unreported_units"], 0)
            self.assertEqual(compare["examples"][0]["measure"], "B1G")
            self.assertEqual(
                {compare["examples"][0]["left_value"],
                 compare["examples"][0]["right_value"]},
                {"120.00", "125.00"})
            self.assertFalse(report["cross_scope_join_performed"])
            self.assertFalse(result["cross_scope_reconciliation"][
                "identities_computed_from_joined_scopes"])
            self.assertEqual(result["scope_audits"][0]["identity_checks"][
                "net_surplus_and_mixed_income"]["eligible_matched_industry_years"], 0)

    def test_cross_original_currency_incompatibility_is_counted(self):
        with TemporaryDirectory() as t:
            root = Path(t)
            store_stan_original(
                original(core_rows()), country="PRT", start_year=1970,
                root=root, measures=STAN_VERIFIED_PORTUGAL_MEASURES)
            store_stan_original(
                original(core_rows(currency="PTE") +
                         [("C", "B2N_B3_N", 2020, "35.00", "A", "6", "PTE")]),
                country="PRT", start_year=1970, root=root, measures=NET)
            report = audit_stan_originals(root, countries=("PRT",))
            compare = report["country_audits"][0][
                "cross_scope_reconciliation"]["comparisons"][0]
            self.assertEqual(compare["incompatible_or_unreported_units"], 4)
            self.assertEqual(compare["numeric_value_disagreements_same_unit"], 0)
            self.assertEqual(compare["source_flag_changes"], 0)


if __name__ == "__main__":
    unittest.main()
