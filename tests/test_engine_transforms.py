"""Engine transforms: named, with recorded formulas; nothing filled."""
from datetime import date
import unittest

from finance_dashboard.engine.transforms import (TRANSFORMS, applied, complete_months, contiguous_tail,
                                                 index_100, month_end, own_history, percentile)


class EngineTransformTests(unittest.TestCase):
    def test_month_end_takes_last_observation_and_contiguity_stops_at_gaps(self):
        ends = month_end([(date(2020, 1, 2), 1.0), (date(2020, 1, 31), 2.0), (date(2020, 3, 1), 3.0)])
        self.assertEqual(ends[(2020, 1)], (date(2020, 1, 31), 2.0))
        self.assertEqual(contiguous_tail(ends), [(2020, 3)])

    def test_incomplete_current_month_is_excluded(self):
        ends = month_end([(date(2026, 10, 30), 1.0), (date(2026, 11, 5), 2.0)])
        self.assertEqual(list(complete_months(ends, date(2026, 11, 6))), [(2026, 10)])

    def test_own_history_position(self):
        result = own_history([(date(2020, 1, 1), 1.0), (date(2020, 2, 1), 3.0), (date(2020, 3, 1), 2.0)])
        self.assertEqual(result["latest"], 2.0)
        self.assertAlmostEqual(result["own_mean"], 2.0)
        self.assertAlmostEqual(result["own_percentile"], 0.5)
        self.assertIsNone(own_history([]))

    def test_percentile_interpolates_linearly(self):
        self.assertAlmostEqual(percentile([0.0, 1.0, 2.0, 3.0], 0.5), 1.5)
        self.assertIsNone(percentile([], 0.5))

    def test_index_100_compounds_without_inventing_months(self):
        levels = index_100([("2026-01", 0.1), ("2026-02", -0.5)])
        self.assertEqual([month for month, _ in levels], ["2026-01", "2026-02"])
        self.assertAlmostEqual(levels[0][1], 110.0)
        self.assertAlmostEqual(levels[1][1], 55.0)

    def test_every_transform_has_a_formula_and_unknown_names_fail(self):
        self.assertEqual(set(TRANSFORMS), {"month_end", "complete_months", "contiguous_tail", "monthly_return",
                                           "return_summary", "own_history", "index_100",
                                           "overlapping_window_percentiles", "fx_translation", "hedge_carry",
                                           "real_deflation", "earnings_yield", "valuation_residual_range",
                                           "year_on_year_change", "yield_difference", "percent_to_fraction",
                                           "threshold_band", "drawdown", "calibration_points",
                                           "cycle_position", "log_change", "own_range_window",
                                           "cross_section_sd", "matched_pairs",
                                           "now_and_year_ago", "matched_day",
                                           "now_and_years_ago", "additive_parts", "matched_ratio",
                                           "rank_correlation", "real_per_hour_index", "share_of_total",
                                           "pearson_correlation", "drawdown_episodes",
                                           "first_order_shock", "rebalancing_simulation",
                                           "signal_timing", "recovery_to_peak", "par_bond_return",
                                           "splice_identical", "native_icio_direct_final_demand"})
        self.assertTrue(all(TRANSFORMS[name].strip() for name in TRANSFORMS))
        self.assertEqual(applied("month_end")["formula"], TRANSFORMS["month_end"])
        with self.assertRaises(KeyError):
            applied("interpolate")


if __name__ == "__main__":
    unittest.main()
