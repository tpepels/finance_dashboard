"""F05, F06, F07 on the engine: leverage by sector, property within its history, nonbank leverage."""
from datetime import date
import unittest

from finance_dashboard.engine.analyses import DEFINITIONS, F05, F06, F07, matched_ratio


def quarterly(start_year, values):
    return [(date(start_year + i // 4, 1 + 3 * (i % 4), 1), v) for i, v in enumerate(values)]


class CreditBEngineTests(unittest.TestCase):
    def test_matched_ratio(self):
        a = quarterly(2025, [10.0, 20.0, 30.0])
        b = quarterly(2025, [2.0, 4.0])
        self.assertEqual(matched_ratio(a, b), [["2025-01-01", 5.0], ["2025-04-01", 5.0]])

    def test_f05_sector_stack_and_bank_leverage(self):
        self.assertIs(DEFINITIONS["F05"], F05)
        points = {role: [] for role in F05.inputs}
        points["household:US"] = quarterly(2025, [70.0, 71.0])
        points["corporate:US"] = quarterly(2025, [75.0, 76.0])
        points["government:US"] = [(date(2025, 1, 1), 120.0)]
        points["bank_assets"] = quarterly(2025, [1000.0, 1100.0])
        points["bank_equity"] = quarterly(2025, [100.0, 110.0])
        values = F05.compute(points, {}).values
        us = next(r for r in values["economies"] if r["area"] == "US")
        self.assertEqual((us["household"], us["corporate"], us["as_of"]), (71.0, 76.0, "2025-04-01"))
        self.assertEqual((us["government"], us["government_year"]), (120.0, "2025"))
        self.assertAlmostEqual(values["bank"]["equity_to_assets"], 10.0)
        self.assertNotIn("JP", [r["area"] for r in values["economies"]])

    def test_f06_property_within_its_own_history(self):
        self.assertIs(DEFINITIONS["F06"], F06)
        points = {role: [] for role in F06.inputs}
        points["residential:US"] = quarterly(2015, [100.0 + i for i in range(45)])
        values = F06.compute(points, {}).values
        us = next(r for r in values["residential"] if r["area"] == "US")
        self.assertEqual((us["latest"], us["min"], us["max"]), (144.0, 100.0, 144.0))
        self.assertAlmostEqual(us["change_5y_pct"], 100 * (144 / 124 - 1))

    def test_f07_nonbank_leverage(self):
        self.assertIs(DEFINITIONS["F07"], F07)
        points = {role: [] for role in F07.inputs}
        points["broker_assets"] = quarterly(2025, [4000.0])
        points["broker_equity"] = quarterly(2025, [200.0])
        points["broker_liabilities"] = quarterly(2025, [3800.0])
        points["broker_repo"] = quarterly(2025, [1900.0])
        values = F07.compute(points, {}).values
        self.assertAlmostEqual(values["latest"]["broker_leverage"], 20.0)
        self.assertAlmostEqual(values["latest"]["repo_share"], 50.0)
        self.assertEqual(values["history"]["broker_leverage"], [["2025-01-01", 20.0]])
        positions = {p["key"]: p for p in values["positions"]}
        self.assertIn('financial assets', positions['broker_leverage']['name'].lower())
        from finance_dashboard.engine.limitations import method_limitations
        self.assertTrue(any('financial assets' in item['text'].lower()
                            for item in method_limitations('F07')))
        self.assertEqual((positions["broker_leverage"]["min"], positions["broker_leverage"]["max"]), (20.0, 20.0))
        self.assertEqual(positions["repo_share"]["latest"], 50.0)


if __name__ == "__main__":
    unittest.main()
