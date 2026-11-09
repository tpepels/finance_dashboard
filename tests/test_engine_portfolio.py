"""P02 and P03 on the engine: diversification by period, crisis drawdown episodes."""
from datetime import date
import unittest

from engine_fixtures import monthly
from finance_dashboard.engine.analyses import DEFINITIONS, P02, P03, drawdown_episodes, pearson


class PortfolioEngineTests(unittest.TestCase):
    def test_pearson(self):
        self.assertAlmostEqual(pearson([1, 2, 3], [2, 4, 6]), 1.0)
        self.assertAlmostEqual(pearson([1, 2, 3], [3, 2, 1]), -1.0)
        self.assertIsNone(pearson([1, 1, 1], [1, 2, 3]))

    def test_p02_correlations_in_euros_per_period_with_month_counts(self):
        self.assertIs(DEFINITIONS["P02"], P02)
        n = 30
        equity = monthly((2010, 1), [100 * (1.01 ** i) * (1.02 if i % 2 else 1.0) for i in range(n)])
        gold = monthly((2010, 1), [1000 * (1.01 ** i) * (1.0 if i % 2 else 1.02) for i in range(n)])
        bonds = monthly((2010, 1), [0.01 if i % 2 else -0.01 for i in range(n)])
        fx = monthly((2010, 1), [1.2] * n)
        values = P02.compute({"equity": equity, "gold": gold, "bonds": bonds, "usd_per_eur": fx}, {"today": "2026-11-09"}).values
        cells = {(c["pair"], c["period"]): c for c in values["cells"]}
        stocks_gold = cells[("stocks_gold", "2010–2019")]
        self.assertLess(stocks_gold["rho"], -0.9)
        self.assertEqual(stocks_gold["months"], n - 1)
        self.assertIsNone(cells[("stocks_gold", "2000–2009")]["rho"])
        self.assertIn("stocks_bonds", values["rolling"])

    def test_drawdown_episodes_deeper_than_threshold(self):
        levels = monthly((2020, 1), [100, 90, 70, 80, 105, 110, 108, 109])
        episodes = drawdown_episodes(levels, -0.15, recession_months={(2020, 3)})
        self.assertEqual(len(episodes), 1)
        e = episodes[0]
        self.assertEqual((e["peak"], e["trough"], e["recovery"]), ("2020-01", "2020-03", "2020-05"))
        self.assertAlmostEqual(e["depth"], -0.30)
        self.assertEqual((e["months_down"], e["months_to_recover"]), (2, 2))
        self.assertTrue(e["us_recession"])

    def test_p03_values(self):
        self.assertIs(DEFINITIONS["P03"], P03)
        points = {role: [] for role in P03.inputs}
        points["equity"] = monthly((2020, 1), [100, 90, 70, 80, 105, 110, 108, 109])
        points["recession"] = monthly((2020, 1), [0, 0, 1, 1, 0, 0, 0, 0])
        values = P03.compute(points, {"today": "2026-11-09"}).values
        self.assertEqual(len(values["episodes"]), 1)
        self.assertEqual(values["underwater"][2][0], "2020-03")


if __name__ == "__main__":
    unittest.main()
