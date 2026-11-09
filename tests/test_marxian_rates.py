"""Marxian rates under each classification and wage definition, from SEA group sums."""
import unittest

from finance_dashboard.marxian_sectors import rates_from_sums


class MarxianRateTests(unittest.TestCase):
    def test_rates_per_country_year_and_wage_definition(self):
        sums = {("USA", 2014, "VA", "PA"): 300.0, ("USA", 2014, "COMP", "PA"): 150.0, ("USA", 2014, "LAB", "PA"): 200.0,
                ("USA", 2014, "EMP", "PA"): 110.0, ("USA", 2014, "EMPE", "PA"): 100.0, ("USA", 2014, "K", "PA"): 1000.0,
                ("USA", 2014, "K", "UA"): 500.0}
        rates = rates_from_sums(sums)
        usa = rates["USA"][2014]
        self.assertAlmostEqual(usa["surplus_value_comp"], 1.0)            # (300 - 150) / 150
        self.assertAlmostEqual(usa["surplus_value_lab"], 0.5)             # (300 - 200) / 200
        self.assertAlmostEqual(usa["surplus_value_comp_pe"], (300 - 165) / 165)
        self.assertAlmostEqual(usa["profit_rate_comp"], 0.15)             # (300 - 150) / 1000
        self.assertAlmostEqual(usa["profit_rate_lab"], 0.10)

    def test_input_output_correction_uses_the_country_year_ratio(self):
        sums = {("USA", 2014, "GO", "PA"): 500.0, ("USA", 2014, "VA", "PA"): 300.0, ("USA", 2014, "COMP", "PA"): 150.0,
                ("USA", 2014, "LAB", "PA"): 200.0, ("USA", 2014, "EMP", "PA"): 110.0, ("USA", 2014, "EMPE", "PA"): 100.0,
                ("USA", 2014, "K", "PA"): 1000.0, ("USA", 2014, "K", "UA"): 500.0}
        usa = rates_from_sums(sums, ratios={("USA", 2014): 0.7})["USA"][2014]
        marx = 0.7 * 500                                                   # WIOT.SEA.VA.PA = ratio * GO.PA
        self.assertAlmostEqual(usa["io_surplus_value_comp"], (marx - 150) / 150)
        self.assertAlmostEqual(usa["io_surplus_value_lab"], (marx - 200) / 200)
        self.assertAlmostEqual(usa["io_profit_rate_comp"], (marx - 150) / 1000)
        self.assertAlmostEqual(usa["surplus_value_comp"], 1.0)             # the SEA-only measures stay alongside
        self.assertNotIn("io_surplus_value_comp", rates_from_sums(sums)["USA"][2014])

    def test_missing_inputs_leave_the_measure_out(self):
        rates = rates_from_sums({("PRT", 2010, "VA", "PA"): 10.0})
        self.assertEqual(rates.get("PRT", {}).get(2010, {}), {})


if __name__ == "__main__":
    unittest.main()
