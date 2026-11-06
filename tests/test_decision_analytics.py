"""P06/P07 decision analytics: exact arithmetic, no filled months."""
from datetime import date
import unittest

from finance_dashboard.decision_analytics import (complete_months, contiguous_tail, f03_credit, month_end,
                                                  own_history, p06_expected_returns, p07_hedging)


def series(values, start=(2020, 1)):
    out, (y, m) = {}, start
    for v in values:
        out[(y, m)] = (date(y, m, 28), v)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


class DecisionAnalyticsTests(unittest.TestCase):
    def test_month_end_takes_last_observation_and_contiguity_stops_at_gaps(self):
        ends = month_end([(date(2020, 1, 2), 1.0), (date(2020, 1, 31), 2.0), (date(2020, 3, 1), 3.0)])
        self.assertEqual(ends[(2020, 1)], (date(2020, 1, 31), 2.0))
        self.assertEqual(contiguous_tail(ends), [(2020, 3)])

    def test_incomplete_current_month_is_excluded(self):
        ends = month_end([(date(2026, 10, 30), 1.0), (date(2026, 11, 5), 2.0)])
        self.assertEqual(list(complete_months(ends, date(2026, 11, 6))), [(2026, 10)])

    def test_unhedged_and_hedged_eur_returns(self):
        equity = series([100.0, 110.0])          # +10% in USD
        fx = series([1.0, 1.1])                  # EUR strengthens 10% (USD per EUR up)
        eur, usd = series([2.0, 2.0]), series([5.0, 5.0])
        hicp = series([100.0, 101.0])
        result = p07_hedging(fx, equity, eur, usd, hicp)
        row = result["rows"][0]
        self.assertAlmostEqual(row["eur_unhedged"], 1.10 / 1.10 - 1)
        self.assertAlmostEqual(row["hedge_carry"], -3.0 / 1200)
        self.assertAlmostEqual(row["eur_hedged"], 1.10 * (1 - 3.0 / 1200) - 1)
        self.assertAlmostEqual(row["eur_inflation"], 0.01)
        self.assertEqual(result["nominal"]["eur_hedged"]["months"], 1)

    def test_missing_month_breaks_the_cumulative_run(self):
        equity = series([100, 101, 102, 103])
        del equity[(2020, 2)]
        fx = series([1.0, 1.0, 1.0, 1.0])
        rates = series([0.0] * 4)
        result = p07_hedging(fx, equity, rates, rates, {})
        self.assertEqual([r["month"] for r in result["rows"]], ["2020-04"])
        self.assertIsNone(result["real_period"])

    def test_equity_range_from_realised_minus_starting_earnings_yield(self):
        months = 12 * 10 + 1
        cape = series([20.0] * months)          # earnings yield 5%
        real_tr = series([1.06 ** (i / 12) for i in range(months)])   # 6% real per year
        result = p06_expected_returns(cape, real_tr, {}, {"us_nominal_10y": (date(2026, 1, 1), 4.0),
                                                         "us_real_10y": (date(2026, 1, 1), 1.8)}, {})
        equity = result["equity_us"]
        self.assertAlmostEqual(equity["earnings_yield"], 0.05)
        self.assertEqual(equity["calibration_windows"], 1)
        self.assertAlmostEqual(equity["range_real"]["p50"], 0.06, places=6)
        self.assertAlmostEqual(result["bonds"]["us_breakeven_10y"]["yield"], 0.022)

    def test_credit_gap_bands_and_own_history_percentiles(self):
        gaps = {"US": [(date(2020, 1, 1), -5.0), (date(2021, 1, 1), 1.0), (date(2022, 1, 1), 12.0)],
                "PT": [(date(2022, 1, 1), 3.0)]}
        dsr = {"US": [(date(2020, 1, 1), 15.0), (date(2021, 1, 1), 16.0), (date(2022, 1, 1), 14.0)]}
        result = f03_credit(gaps, dsr)
        rows = {r["area"]: r for r in result["rows"]}
        self.assertEqual(rows["US"]["gap_guide_band"], "above_10pp")
        self.assertEqual(rows["PT"]["gap_guide_band"], "between_2_and_10pp")
        self.assertEqual(rows["US"]["private_dsr"]["own_percentile"], 0.0)
        self.assertAlmostEqual(rows["US"]["private_dsr"]["deviation_from_own_mean"], -1.0)
        self.assertIsNone(rows["PT"]["private_dsr"])
        self.assertIsNone(own_history([]))


if __name__ == "__main__":
    unittest.main()
