"""G05 and G06 on the engine: external balances and supply-chain exposure."""
from datetime import date
import unittest

from finance_dashboard.engine.analyses import DEFINITIONS, G05, G06


def annual(start, values):
    return [(date(start + i, 1, 1), v) for i, v in enumerate(values)]


class GlobalEngineTests(unittest.TestCase):
    def test_g05_current_account_and_net_position_as_share_of_gdp(self):
        self.assertIs(DEFINITIONS["G05"], G05)
        points = {role: [] for role in G05.inputs}
        points["ca_gdp:US"] = annual(2023, [-3.3, -3.9, -4.0])
        points["niip:US"] = annual(2023, [-20e12, -24e12, -26e12])
        points["gdp:US"] = annual(2023, [27e12, 29e12, 30e12])
        values = G05.compute(points, {}).values
        us = next(r for r in values["economies"] if r["area"] == "US")
        self.assertEqual((us["current_account_gdp"], us["current_account_year"]), (-4.0, "2025"))
        self.assertAlmostEqual(us["net_position_gdp"], -26 / 30 * 100)
        self.assertEqual(us["net_position_year"], "2025")
        self.assertEqual(len(values["history"]["US"]["net_position_gdp"]), 3)

    def test_g06_foreign_demand_share_first_and_latest(self):
        self.assertIs(DEFINITIONS["G06"], G06)
        points = {role: [] for role in G06.inputs}
        points["share:DE"] = annual(1995, [25.0, 26.0, 30.0])
        values = G06.compute(points, {}).values
        de = next(r for r in values["economies"] if r["area"] == "DE")
        self.assertEqual((de["first"], de["first_year"], de["latest"], de["latest_year"]), (25.0, "1995", 30.0, "1997"))

    def test_g06_keeps_publisher_tiva_separate_from_native_icio_diagnostics(self):
        points = {role: [] for role in G06.inputs}
        points["share:PT"] = annual(2021, [32.5, 33.1])
        original = {"years": [{
            "edition": "2025", "year": 2021,
            "source": "2016-2022_EXT.zip",
            "accounting_passed": None,
            "structure_verified": True,
            "accounting_basis": "source_structure_only_accounts_not_published",
            "countries": {"PRT": {"direct_foreign_final_demand_usd_million": "8000"}}}],
            "not_equivalent_to_oecd_tiva_ffd_dva": True}
        bundle = G06.compute(points, {}, {"icio_native_direct": original})
        self.assertEqual(bundle.values["history"]["PT"], [["2021-01-01", 32.5], ["2022-01-01", 33.1]])
        self.assertIs(bundle.values["native_icio_direct"], original)
        self.assertNotIn("direct_foreign_final_demand_usd_million", bundle.values["history"])
        self.assertEqual(bundle.transforms[0]["name"], "native_icio_direct_final_demand")


    def test_g06_leontief_matches_original_year_and_preserves_signed_discrepancy(self):
        points = {role: [] for role in G06.inputs}
        points["share:PT"] = annual(2021, [30.0, 33.0])
        native = {"years": [{
            "edition": "2025", "year": 2022, "source": "2016-2022_EXT.zip",
            "source_sha256": "d" * 64, "accounting_passed": None,
            "structure_verified": True,
            "countries": {"PRT": {"direct_foreign_final_demand_usd_million": "3000"}},
            "tiva_reconstruction": {
                "method": "ICIO_Leontief_FFD_DVA_v1", "max_relative_residual": 1e-12,
                "selected_country_values": {
                    "PRT": {"status": "reconstructed_unreconciled",
                            "ffd_dva_usd_million": 12000,
                            "value_added_usd_million": 36000,
                            "share_pct": 100 / 3}}}}],
            "not_equivalent_to_oecd_tiva_ffd_dva": True}
        results = G06.compute(points, {}, {"icio_native_direct": native}).values
        self.assertEqual(results["history"]["PT"], [["2021-01-01", 30.0], ["2022-01-01", 33.0]])
        row = results["native_icio_value_added"][0]["countries"]["PT"]
        self.assertAlmostEqual(row["signed_difference_pp"], (100 / 3) - 33.0)
        self.assertEqual(row["share_comparison"], "outside_0_001pp")
        self.assertNotEqual(row["share_pct"], results["economies"][0]["latest"])

    def test_g06_reconstruction_does_not_splice_old_editions_into_published_data(self):
        points = {role: [] for role in G06.inputs}
        points["share:US"] = annual(2021, [30.0])
        native = {"years": [{
            "edition": "2021", "year": 2021, "source": "ICIO2021_2015-2018.zip",
            "source_sha256": "a" * 64, "accounting_passed": None,
            "structure_verified": True, "countries": {},
            "tiva_reconstruction": {
                "selected_country_values": {"USA": {
                    "status": "reconstructed_unreconciled", "share_pct": 25.0}}}}]}
        result = G06.compute(points, {}, {"icio_native_direct": native})
        self.assertEqual(result.values["history"]["US"], [["2021-01-01", 30.0]])
        self.assertEqual(result.values["native_icio_value_added"][0]["countries"]["US"]["share_comparison"],
                         "not_current_edition")
        self.assertIn("native_icio_leontief_ffd_dva", [t["name"] for t in result.transforms])



if __name__ == "__main__":
    unittest.main()
