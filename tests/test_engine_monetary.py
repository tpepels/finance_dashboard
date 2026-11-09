"""M01, M02, M04 on the engine: policy-rate ladder, yield decomposition, currencies against rate gaps."""
from datetime import date, timedelta
import math
import unittest

from engine_fixtures import monthly
from finance_dashboard.engine.analyses import (DEFINITIONS, M01, M02, M04, matched_day, monthly_difference,
                                               now_and_year_ago)


def daily(start: date, values, step=1):
    return [(start + timedelta(days=i * step), v) for i, v in enumerate(values)]


class MonetaryEngineTests(unittest.TestCase):
    def test_now_and_a_year_ago_use_the_last_observation_on_or_before(self):
        points = [(date(2025, 11, 3), 4.0), (date(2026, 3, 1), 3.5), (date(2026, 11, 5), 3.0)]
        result = now_and_year_ago(points)
        self.assertEqual((result["latest"], result["as_of"]), (3.0, "2026-11-05"))
        self.assertEqual((result["year_ago"], result["year_ago_as_of"]), (4.0, "2025-11-03"))
        self.assertAlmostEqual(result["change"], -1.0)
        self.assertIsNone(now_and_year_ago([(date(2026, 11, 5), 3.0)])["year_ago"])

    def test_monthly_difference_only_on_months_both_report(self):
        a = monthly((2026, 1), [3.0, 3.0, 2.5])
        b = monthly((2026, 1), [4.5, 4.25], skip=None)
        self.assertEqual(monthly_difference(a, b), [["2026-01", -1.5], ["2026-02", -1.25]])

    def test_matched_day_is_the_latest_date_both_series_observe(self):
        nominal = [(date(2026, 11, 5), 4.1), (date(2026, 11, 6), 4.2)]
        real = [(date(2026, 11, 4), 1.8), (date(2026, 11, 5), 1.9)]
        self.assertEqual(matched_day(nominal, real), date(2026, 11, 5))
        self.assertEqual(matched_day(nominal, real, before=date(2026, 11, 4)), None)

    def test_m01_ladder_and_gaps(self):
        self.assertIs(DEFINITIONS["M01"], M01)
        points = {role: [] for role in M01.inputs}
        points["fed"] = monthly((2025, 10), [4.3] * 4 + [3.9] * 10)
        points["ecb"] = monthly((2025, 10), [2.0] * 14)
        points["boj"] = monthly((2025, 10), [0.5] * 14)
        points["fed_lower"] = monthly((2025, 10), [4.0] * 14)
        points["fed_upper"] = monthly((2025, 10), [4.25] * 14)
        values = M01.compute(points, {"today": "2026-12-15"}).values
        ladder = {row["bank"]: row for row in values["ladder"]}
        self.assertAlmostEqual(ladder["fed"]["change"], 3.9 - 4.3)
        self.assertAlmostEqual(values["gaps"]["eur_minus_usd"][-1][1], 2.0 - 3.9)
        self.assertAlmostEqual(values["gaps"]["eur_minus_jpy"][-1][1], 1.5)
        self.assertEqual(len(values["history"]["fed_range"]), 14)

    def test_monthly_series_leave_out_the_incomplete_current_month(self):
        points = {role: [] for role in M04.inputs}
        points["usd_per_eur"] = monthly((2025, 1), [1.0] * 12 + [1.1] * 11) + [(date(2026, 12, 3), 1.3)]
        points["fed"] = monthly((2025, 1), [4.0] * 23) + [(date(2026, 12, 3), 3.0)]
        points["ecb"] = monthly((2025, 1), [2.0] * 23) + [(date(2026, 12, 3), 2.0)]
        usd = M04.compute(points, {"today": "2026-12-05"}).values["currencies"][0]
        self.assertEqual(usd["move_as_of"], "2026-11")
        self.assertEqual(usd["gap_as_of"], "2026-11")

    def test_m02_split_is_additive_on_one_market_date(self):
        self.assertIs(DEFINITIONS["M02"], M02)
        start = date(2025, 11, 1)
        points = {"nominal": daily(start, [4.5] * 8 + [4.0] * 365), "real": daily(start, [2.0] * 8 + [1.8] * 365),
                  "breakeven": daily(start, [2.5] * 8 + [2.2] * 365)}
        values = M02.compute(points, {}).values
        now, then = values["split"]["now"], values["split"]["year_ago"]
        self.assertAlmostEqual(now["real"] + now["breakeven"], now["nominal"])
        self.assertAlmostEqual(now["breakeven"], 2.2)
        self.assertAlmostEqual(then["nominal"], 4.5)
        self.assertAlmostEqual(values["split"]["published_breakeven"], 2.2)

    def test_m04_currency_moves_and_gaps(self):
        self.assertIs(DEFINITIONS["M04"], M04)
        points = {role: [] for role in M04.inputs}
        points["usd_per_eur"] = monthly((2025, 1), [1.0] * 12 + [1.1] * 12)
        points["fed"] = monthly((2025, 1), [4.0] * 24)
        points["ecb"] = monthly((2025, 1), [2.0] * 24)
        values = M04.compute(points, {}).values
        usd = next(r for r in values["currencies"] if r["currency"] == "USD")
        self.assertAlmostEqual(usd["move_12m"], 100 * math.log(1.1))
        self.assertAlmostEqual(usd["gap"], -2.0)
        self.assertEqual(usd["scatter"][0], ["2026-01", -2.0, 100 * math.log(1.1)])
        jpy = next(r for r in values["currencies"] if r["currency"] == "JPY")
        self.assertIsNone(jpy["move_12m"])


if __name__ == "__main__":
    unittest.main()
