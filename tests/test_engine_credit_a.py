"""F01, F02, F04 on the engine: credit against trend, debt-service change, market stress within its history."""
from datetime import date
import unittest

from finance_dashboard.engine.analyses import DEFINITIONS, F01, F02, F04, now_and_years_ago


def quarterly(start_year, values):
    return [(date(start_year + i // 4, 1 + 3 * (i % 4), 1), v) for i, v in enumerate(values)]


class CreditEngineTests(unittest.TestCase):
    def test_now_and_years_ago(self):
        points = quarterly(2020, [10.0 + i for i in range(25)])      # 2020Q1 .. 2026Q1
        result = now_and_years_ago(points, 5)
        self.assertEqual((result["latest"], result["as_of"]), (34.0, "2026-01-01"))
        self.assertEqual((result["back"], result["back_as_of"]), (14.0, "2021-01-01"))

    def test_f01_ratio_trend_gap_per_economy(self):
        self.assertIs(DEFINITIONS["F01"], F01)
        points = {role: [] for role in F01.inputs}
        points["ratio:US"] = quarterly(2015, [150.0 + i * 0.5 for i in range(45)])
        points["trend:US"] = quarterly(2015, [155.0] * 45)
        points["gap:US"] = quarterly(2015, [-5.0] * 45)
        values = F01.compute(points, {}).values
        us = next(r for r in values["economies"] if r["area"] == "US")
        self.assertAlmostEqual(us["ratio"], 172.0)
        self.assertAlmostEqual(us["trend"], 155.0)
        self.assertAlmostEqual(us["gap"], -5.0)
        self.assertAlmostEqual(us["ratio_change_5y"], 10.0)
        self.assertNotIn("JP", [r["area"] for r in values["economies"]])
        self.assertEqual(len(values["history"]["US"]["ratio"]), 45)

    def test_f02_burden_now_against_five_years_ago(self):
        self.assertIs(DEFINITIONS["F02"], F02)
        points = {role: [] for role in F02.inputs}
        points["private:US"] = quarterly(2018, [15.0] * 13 + [16.0] * 20)   # step after 2021Q1
        points["households:US"] = quarterly(2018, [9.0] * 33)
        values = F02.compute(points, {}).values
        rows = {(r["series"], r["area"]): r for r in values["rows"]}
        self.assertAlmostEqual(rows[("private", "US")]["change"], 1.0)
        self.assertAlmostEqual(rows[("households", "US")]["change"], 0.0)
        self.assertAlmostEqual(rows[("private", "US")]["own_mean"], (15 * 13 + 16 * 20) / 33)

    def test_f04_stress_within_its_own_history_and_additive_parts(self):
        self.assertIs(DEFINITIONS["F04"], F04)
        self.assertIn("stress.us.high_yield_oas_fred_archive", F04.inputs.values())   # full history: archive + current FRED
        self.assertNotIn("credit.us.baa_10y_spread", F04.inputs.values())             # the former fallback is no longer an accepted input
        day = date(2026, 11, 3)
        points = {role: [] for role in F04.inputs}
        points["ofr_fsi"] = [(date(2026, 11, 2), 0.0), (day, -1.484)]
        for part, value in {"credit": -0.842, "equity_valuation": -0.458, "funding": -0.129,
                            "safe_assets": -0.292, "volatility": 0.237}.items():
            points[f"fsi_part:{part}"] = [(day, value)]
        points["nfci"] = [(date(2026, 10, 23), -0.5), (date(2026, 10, 30), -0.4)]
        values = F04.compute(points, {}).values
        gauges = {g["key"]: g for g in values["gauges"]}
        self.assertAlmostEqual(gauges["ofr_fsi"]["latest"], -1.484)
        self.assertEqual(gauges["nfci"]["observations"], 2)
        parts = values["fsi_parts"]
        self.assertEqual(parts["date"], "2026-11-03")
        self.assertAlmostEqual(sum(p["value"] for p in parts["categories"]), -1.484)


if __name__ == "__main__":
    unittest.main()
