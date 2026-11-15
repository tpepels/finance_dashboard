"""Exact-source Piketty research formulas, population and missing-data gates."""
from datetime import date
import unittest

from finance_dashboard.piketty_research import piketty_findings


def points(rows):
    return [(date(year, 1, 1), value) for year, value in rows]


def source_fixture():
    raw = {}
    def add(suffix, rows, *, area="US"):
        raw[f"piketty:{area}:{suffix}"] = points(rows)
    for group, vals in {
        "income:top1": [(2024, .19), (2025, .20)],
        "income:top10": [(2024, .48), (2025, .49)],
        "income:bottom50": [(2024, .13), (2025, .12)],
        "wealth:top1": [(2024, .30), (2025, .31)],
        "wealth:top10": [(2024, .72), (2025, .73)],
        "wealth:bottom50": [(2024, -.015), (2025, -.02)],
        "income_avg:all": [(2023, 100), (2024, 110), (2025, 121)],
        "income_avg:bottom50": [(2023, 60), (2024, 65), (2025, 70)],
        "income_avg:middle40": [(2023, 120), (2024, 132), (2025, 145)],
        "income_avg:top10": [(2023, 220), (2024, 247), (2025, 280)],
        "income_avg:top1": [(2023, 350), (2024, 400), (2025, 470)],
        "ratio:national": [(2024, 6), (2025, 6.2)],
        "ratio:private": [(2024, 7), (2025, 7.3)],
        "ratio:public": [(2024, -1), (2025, -1.1)],
        "macro:net_national_income": [(2023, 100), (2024, 110), (2025, 121)],
        "macro:net_national_wealth": [(2023, 500), (2024, 550), (2025, 600)],
        "macro:net_capital_income": [(2024, 15), (2025, 17)],
        "macro:factor_capital_share": [(2024, .3), (2025, .31)],
        "macro:national_housing_assets": [(2024, 240), (2025, 270)],
        "macro:national_business_assets": [(2024, 180), (2025, 190)],
    }.items():
        add(group, vals)
    return raw


class PikettyResearchTests(unittest.TestCase):
    def test_all_five_findings_use_same_area_matched_originals(self):
        report = piketty_findings(source_fixture())
        self.assertEqual(len(report["areas"]), 6)
        us = next(row for row in report["areas"] if row["area"] == "US")

        share = us["concentration"]
        self.assertEqual(share["status"], "available")
        self.assertEqual(share["concepts"]["wealth"]["percentage_shares"]["bottom50"][-1],
                         ["2025", -2.0])
        self.assertEqual(share["concepts"]["wealth"]["percentage_shares"]["middle40"][-1],
                         ["2025", 29.0])
        self.assertEqual(share["concepts"]["income"]["percentage_shares"]["top1"][-1],
                         ["2025", 20.0])

        growth = us["growth_capture"]
        self.assertEqual(growth["status"], "available")
        self.assertEqual(growth["accepted_complete_years"], [2023, 2024, 2025])
        self.assertEqual(len(growth["change_contributions"]), 2)
        self.assertAlmostEqual(growth["change_contributions"][0]["contribution_sum_pct"], 100)
        self.assertEqual(growth["real_per_adult_index"]["all"][-1], ["2025", 121.0])

        ratio = us["wealth_income"]
        self.assertEqual(ratio["percent_of_net_national_income"]["national"][-1],
                         ["2025", 620.0])
        self.assertEqual(ratio["national_minus_private_public_pp"][-1], ["2025", 0.0])

        income = us["capital_vs_growth"]
        self.assertEqual(income["status"], "available")
        r = 100 * 15 / 525
        self.assertAlmostEqual(
            income["net_capital_income_to_mean_national_wealth_pct"][0][1], r, 5)
        self.assertAlmostEqual(income["real_net_national_income_growth_pct"][0][1], 10, 5)
        self.assertAlmostEqual(
            income["accounting_net_income_yield_minus_growth_pp"][0][1], r - 10, 5)

        comp = us["composition"]
        self.assertEqual(comp["status"], "available")
        self.assertEqual(comp["composition_pct_of_national_wealth"]["housing"][-1],
                         ["2025", 45.0])
        self.assertAlmostEqual(
            sum(row[-1][1] for row in comp["composition_pct_of_national_wealth"].values()),
            100, 5)

        inherited = us["inheritance"]
        self.assertEqual(inherited["status"], "awaiting_comparable_originals")
        self.assertEqual(inherited["annual_inheritance_flow_pct"], [])
        self.assertEqual(inherited["latest_year"], None)
        self.assertEqual(report["report_reference"]["reference_year"], 2025)
        self.assertEqual(report["report_reference"]["world_income_top10_pct"], 53)
        self.assertEqual(report["report_reference"]["world_income_bottom50_pct"], 8)
        self.assertEqual(report["report_reference"]["world_wealth_bottom50_pct"], 2)
        self.assertEqual(report["report_reference"]["reconciliation"]["state"],
                         "report_reference_separate")
        self.assertEqual(share["compared_years"], [2024, 2025])
        self.assertEqual(share["latest_comparable_year"], 2025)
        self.assertAlmostEqual(
            share["concepts"]["income"]["top_to_bottom_ratios"]["top10_to_bottom50"][-1][1],
            49 / 12, 5)
        self.assertIsNone(
            share["concepts"]["wealth"]["top_to_bottom_ratios"]["top10_to_bottom50"][-1][1])
        self.assertEqual(growth["distribution_incidence"]["status"],
                         "awaiting_matched_originals")

    def test_full_growth_incidence_needs_all_twelve_real_original_percentile_groups(self):
        from finance_dashboard.piketty_research import INCIDENCE_GROUPS
        data=source_fixture()
        for index,(group,_,_) in enumerate(INCIDENCE_GROUPS):
            first=100+10*index
            data[f"piketty:US:income_distribution:{group}"]=points([
                (1980,first),(1990,first*1.05),(2025,first*(1+.1*index))])
        report=piketty_findings(data)
        incidence=report["areas"][0]["growth_capture"]["distribution_incidence"]
        self.assertEqual(incidence["status"],"available")
        self.assertEqual((incidence["reference_year"],incidence["comparison_year"]),
                         (1980,2025))
        self.assertEqual(incidence["matched_years"],3)
        self.assertEqual(len(incidence["rows"]),12)
        self.assertAlmostEqual(sum(x["population_weight"] for x in incidence["rows"]),1)
        self.assertAlmostEqual(incidence["rows"][-1]["cumulative_real_growth_pct"],110)
        # A missing publisher percentile/period cannot be interpolated to
        # complete the figure, even if other groups retain the last year.
        data["piketty:US:income_distribution:p90_99"]=points([(1980,190)])
        missing=piketty_findings(data)["areas"][0]["growth_capture"]["distribution_incidence"]
        self.assertEqual(missing["status"],"awaiting_matched_originals")
        self.assertEqual(missing["rows"],[])

    def test_income_wealth_comparisons_never_mix_different_latest_years(self):
        data=source_fixture()
        for group in ("top1","top10","bottom50"):
            data[f"piketty:US:wealth:{group}"]=points([
                (2024,{"top1":.30,"top10":.72,"bottom50":.02}[group])])
        concentration=piketty_findings(data)["areas"][0]["concentration"]
        self.assertEqual(concentration["latest_comparable_year"],2024)
        self.assertEqual(concentration["compared_years"],[2024])
        multiple=concentration["concepts"]["wealth"]["top_to_bottom_ratios"]["top10_to_bottom50"]
        self.assertEqual(multiple,[["2024",36.0]])

    def test_extreme_bottom_wealth_does_not_produce_spurious_ratios(self):
        data=source_fixture()
        for group,value in (("top1",.28),("top10",.75),("bottom50",.000003)):
            data[f"piketty:US:wealth:{group}"]=points([(2025,value)])
        x=piketty_findings(data)["areas"][0]["concentration"]
        self.assertIsNone(
            x["concepts"]["wealth"]["top_to_bottom_ratios"]["top10_to_bottom50"][-1][1])

    def test_other_countries_never_inherit_us_series(self):
        report=piketty_findings(source_fixture())
        others=[r for r in report["areas"] if r["area"] != "US"]
        for row in others:
            self.assertFalse(row["capital_vs_growth"]["accounting_net_income_yield_minus_growth_pp"])
            self.assertFalse(row["growth_capture"]["change_contributions"])
            self.assertFalse(row["wealth_income"]["matching_component_years"])
            self.assertFalse(row["composition"]["composition_pct_of_national_wealth"]["housing"])
            self.assertEqual(row["inheritance"]["status"], "awaiting_comparable_originals")

    def test_unmatched_real_income_groups_and_inconsistent_years_withhold_growth(self):
        data=source_fixture()
        data["piketty:US:income_avg:middle40"]=points([(2023, 120), (2024, 999), (2025, 145)])
        result=piketty_findings(data)["areas"][0]["growth_capture"]
        self.assertEqual(result["rejected_source_identity_years"], [2024])
        self.assertFalse(result["change_contributions"])
        self.assertEqual(result["status"], "awaiting_matched_originals")

        data=source_fixture()
        data["piketty:US:income_avg:top10"]=points([(2024, 247)])
        result=piketty_findings(data)["areas"][0]["growth_capture"]
        self.assertFalse(result["change_contributions"])
        self.assertEqual(result["accepted_complete_years"], [2024])

    def test_missing_prior_year_prevents_fictitious_return_and_growth(self):
        data=source_fixture()
        data["piketty:US:macro:net_national_wealth"]=points([(2024, 550), (2026, 650)])
        result=piketty_findings(data)["areas"][0]["capital_vs_growth"]
        self.assertEqual(result["status"], "awaiting_matched_originals")
        self.assertFalse(result["accounting_net_income_yield_minus_growth_pp"])

    def test_negative_net_wealth_and_no_forced_growth_sum_are_preserved(self):
        report=piketty_findings(source_fixture())
        concentration=report["areas"][0]["concentration"]
        self.assertAlmostEqual(
            concentration["concepts"]["wealth"]["percentage_shares"]["bottom50"][0][1],
            -1.5)
        capture=report["areas"][0]["growth_capture"]["change_contributions"]
        self.assertTrue(all(abs(row["contribution_sum_pct"]-100)<.01 for row in capture))
        self.assertIn("not a capital-gains-inclusive", report["limitations"][3])


if __name__=="__main__":
    unittest.main()
