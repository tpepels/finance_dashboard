"""V01, V02, V03, V05 on the engine: valuation gauges, Q agreement, regional P/E, predictive strength by era."""
from datetime import date
import unittest

from engine_fixtures import monthly
from finance_dashboard.engine.analyses import DEFINITIONS, V01, V02, V03, V05, spearman


class ValuationEngineTests(unittest.TestCase):
    def test_spearman_ranks_with_ties(self):
        self.assertAlmostEqual(spearman([1, 2, 3, 4], [10, 20, 30, 40]), 1.0)
        self.assertAlmostEqual(spearman([1, 2, 3, 4], [4, 3, 2, 1]), -1.0)
        self.assertAlmostEqual(spearman([1, 1, 2], [1, 2, 3]), 0.8660254, places=6)
        self.assertIsNone(spearman([1], [2]))

    def test_v01_gauges_within_own_history(self):
        self.assertIs(DEFINITIONS["V01"], V01)
        points = {role: [] for role in V01.inputs}
        points["cape"] = monthly((2024, 1), [20.0, 25.0, 40.0])
        points["price"] = monthly((2024, 1), [100.0, 110.0, 120.0])
        points["earnings"] = monthly((2024, 1), [5.0, 5.0, 6.0])
        points["dividend"] = monthly((2024, 1), [2.0, 2.2, 2.4])
        points["real_10y"] = [(date(2024, 3, 15), 1.0), (date(2024, 3, 28), 2.0)]
        values = V01.compute(points, {}).values
        gauges = {g["key"]: g for g in values["gauges"]}
        self.assertAlmostEqual(gauges["cape"]["latest"], 40.0)
        self.assertAlmostEqual(gauges["pe"]["latest"], 20.0)
        self.assertAlmostEqual(gauges["dividend_yield"]["latest"], 2.0)
        self.assertAlmostEqual(gauges["excess_cape_yield"]["latest"], 100 / 40 - 2.0)
        self.assertEqual(gauges["excess_cape_yield"]["observations"], 1)

    def test_v02_q_measures_and_cape_side_by_side(self):
        self.assertIs(DEFINITIONS["V02"], V02)
        points = {role: [] for role in V02.inputs}
        for i, key in enumerate(("q1", "q2", "q3")):
            points[key] = [(date(2020 + y, 1, 1), 0.5 + 0.1 * y + i) for y in range(5)]
        points["cape"] = monthly((2024, 1), [30.0])
        values = V02.compute(points, {}).values
        self.assertEqual([g["key"] for g in values["gauges"]], ["q1", "q2", "q3", "cape"])
        self.assertAlmostEqual(values["gauges"][0]["own_percentile"], 1.0)

    def test_v03_trailing_and_forward_per_region(self):
        self.assertIs(DEFINITIONS["V03"], V03)
        points = {role: [] for role in V03.inputs}
        points["trailing:USA"] = monthly((2025, 1), [25.0, 27.0])
        points["forward:USA"] = monthly((2025, 1), [21.0, 22.0])
        values = V03.compute(points, {}).values
        usa = next(r for r in values["regions"] if r["region"] == "USA")
        self.assertEqual((usa["trailing"], usa["forward"], usa["as_of"]), (27.0, 22.0, "2025-02-28"))
        self.assertEqual((usa["trailing_min"], usa["trailing_max"]), (25.0, 27.0))
        self.assertNotIn("JAPAN", [r["region"] for r in values["regions"]])

    def test_v05_strength_by_horizon_and_era_with_effective_sample(self):
        self.assertIs(DEFINITIONS["V05"], V05)
        months = 12 * 40
        cape = monthly((1950, 1), [10.0 + (i % 120) / 10 for i in range(months)])
        real_tr = monthly((1950, 1), [1.004 ** i for i in range(months)])
        values = V05.compute({"cape": cape, "real_tr": real_tr, "real_10y": [], "cpi": []}, {}).values
        cells = {(c["horizon_years"], c["era"]): c for c in values["cells"]}
        ten = cells[(10, "1945–1979")]
        self.assertGreater(ten["windows"], 0)
        self.assertAlmostEqual(ten["effective_windows"], round(ten["windows"] / 120, 1))
        self.assertIsNone(cells[(10, "1881–1944")]["rho"])          # no windows before 1950 in this fixture


if __name__ == "__main__":
    unittest.main()
