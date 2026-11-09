"""L01, L02, L03, L05, L07 on the engine: pay and productivity, value-added split, profit rate, wealth and income shares."""
from datetime import date
import unittest

from finance_dashboard.engine.analyses import DEFINITIONS, L01, L02, L03, L05, L07


def annual(start, values):
    return [(date(start + i, 1, 1), v) for i, v in enumerate(values)]


def quarterly(start_year, values):
    return [(date(start_year + i // 4, 1 + 3 * (i % 4), 1), v) for i, v in enumerate(values)]


class LabourEngineTests(unittest.TestCase):
    def test_l01_real_productivity_and_real_pay_indexed_at_a_common_base(self):
        self.assertIs(DEFINITIONS["L01"], L01)
        points = {role: [] for role in L01.inputs}
        points["va:DE"] = annual(1995, [100.0, 121.0])
        points["va_price:DE"] = annual(1995, [100.0, 110.0])
        points["hours:DE"] = annual(1995, [10.0, 10.0])
        points["pay:DE"] = annual(1995, [60.0, 66.0])
        values = L01.compute(points, {}).values
        de = next(r for r in values["economies"] if r["area"] == "DE")
        self.assertEqual((de["base_year"], de["latest_year"]), ("1995", "1996"))
        self.assertAlmostEqual(de["productivity"], 110.0)     # (121/110)/10 against (100/100)/10
        self.assertAlmostEqual(de["pay"], 100.0)              # (66/110)/10 against (60/100)/10
        self.assertEqual(len(values["history"]["DE"]["productivity"]), 2)

    def test_l01_us_bls_row_deflates_pay_by_the_same_sector_price(self):
        points = {role: [] for role in L01.inputs}
        points["bls_productivity"] = quarterly(1995, [100.0, 104.0])
        points["bls_hourly_comp"] = quarterly(1995, [100.0, 103.0])
        points["bls_deflator"] = quarterly(1995, [100.0, 101.0])
        values = L01.compute(points, {}).values
        bls = next(r for r in values["economies"] if r["area"] == "US_BLS")
        self.assertAlmostEqual(bls["productivity"], 104.0)
        self.assertAlmostEqual(bls["pay"], 100 * 103 / 101)

    def test_l02_value_added_split_adds_up_with_an_explicit_remainder(self):
        self.assertIs(DEFINITIONS["L02"], L02)
        points = {role: [] for role in L02.inputs}
        for key, v in {"gva": 1000.0, "comp": 600.0, "gos": 350.0, "cfc": 150.0, "taxes": 60.0, "subsidies": 10.0}.items():
            points[f"{key}:FR"] = annual(2024, [v])
        values = L02.compute(points, {}).values
        fr = next(r for r in values["economies"] if r["area"] == "FR")
        parts = {p["key"]: p["share"] for p in fr["parts"]}
        self.assertAlmostEqual(parts["compensation"], 60.0)
        self.assertAlmostEqual(parts["net_operating_surplus"], 20.0)
        self.assertAlmostEqual(parts["depreciation"], 15.0)
        self.assertAlmostEqual(parts["net_production_taxes"], 5.0)
        self.assertAlmostEqual(sum(parts.values()), 100.0)
        self.assertAlmostEqual(values["history"]["FR"]["labour_share"][0][1], 60.0)

    def test_l03_net_profit_rate_first_and_latest(self):
        self.assertIs(DEFINITIONS["L03"], L03)
        points = {role: [] for role in L03.inputs}
        points["gos:US"] = annual(2000, [300.0, 330.0])
        points["cfc:US"] = annual(2000, [100.0, 110.0])
        points["capital:US"] = annual(2000, [2000.0, 2000.0])
        values = L03.compute(points, {}).values
        us = next(r for r in values["economies"] if r["area"] == "US")
        self.assertAlmostEqual(us["first"], 10.0)
        self.assertAlmostEqual(us["latest"], 11.0)

    def test_l05_wealth_shares_first_and_latest(self):
        self.assertIs(DEFINITIONS["L05"], L05)
        points = {role: [] for role in L05.inputs}
        for key, (a, b) in {"top_point1": (9, 14), "next_point9": (14, 17), "next9": (37, 36), "middle40": (36, 30), "bottom50": (4, 3)}.items():
            points[key] = quarterly(1989, [a, b])
        values = L05.compute(points, {}).values
        self.assertEqual([g["key"] for g in values["groups"]], ["top_point1", "next_point9", "next9", "middle40", "bottom50"])
        self.assertEqual((values["first_date"], values["latest_date"]), ("1989-01-01", "1989-04-01"))
        self.assertEqual(values["groups"][0]["latest"], 14)

    def test_l07_income_shares_1980_and_latest(self):
        self.assertIs(DEFINITIONS["L07"], L07)
        points = {role: [] for role in L07.inputs}
        points["top1:US"] = annual(1975, [0.10] * 5 + [0.11] * 40 + [0.205])
        points["bottom50:US"] = annual(1975, [0.20] * 45 + [0.13])
        values = L07.compute(points, {}).values
        us = next(r for r in values["economies"] if r["area"] == "US")
        self.assertAlmostEqual(us["top1_then"], 11.0)
        self.assertEqual(us["then_year"], "1980")
        self.assertAlmostEqual(us["top1_latest"], 20.5)
        self.assertAlmostEqual(us["bottom50_latest"], 13.0)


if __name__ == "__main__":
    unittest.main()
