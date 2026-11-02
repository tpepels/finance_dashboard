"""Publisher-defined risk evidence, stale handling and nonpredictive empirical rank."""
from datetime import date
from decimal import Decimal as D
import unittest

from finance_dashboard.risk_diagnostics import (
    DIAGNOSTICS, interpret, diagnostic_catalog, read_diagnostics
)


def item(key):
    return next({**s, "frequency":
                 "M" if key == "us_sahm" or key == "us_cape_rank"
                 else "D" if key == "us_yield_inversion" else "Q"}
                for s in DIAGNOSTICS if s["id"] == key)


class Phase4RiskTests(unittest.TestCase):
    def test_sahm_at_half_point_is_source_recession_onset_criterion(self):
        source = item("us_sahm")
        rows = [(date(2026,7,1), D("0.49")),
                (date(2026,8,1), D("0.50")),
                (date(2026,9,1), D("0.51"))]
        result = interpret(source, rows, today=date(2026,10,1))
        self.assertEqual(result["status"], "observed")
        self.assertTrue(result["threshold_crossed"])
        self.assertEqual(result["consecutive_source_observations"], 2)
        self.assertEqual(result["latest"]["date"], "2026-09-01")
        self.assertIsNone(result["historical_rank_pct"])
        self.assertIn("not a forecast", result["caveat"])

    def test_treasury_curve_negative_is_inversion_but_not_probability(self):
        result = interpret(item("us_yield_inversion"),
            [(date(2026,10,20), D("-0.4")), (date(2026,10,21), D("-0.1")),
             (date(2026,10,22), D("0.05"))],
            today=date(2026,10,23))
        self.assertFalse(result["threshold_crossed"])
        self.assertEqual(result["consecutive_source_observations"], 0)
        self.assertEqual(result["threshold"], "0")

    def test_gap_does_not_count_disconnected_quarters_as_consecutive(self):
        result = interpret(item("us_credit"),
            [(date(2025,1,1), D("3.5")), (date(2025,4,1), D("3.0")),
             (date(2026,7,1), D("2.5"))], today=date(2026,8,1))
        self.assertEqual(result["consecutive_source_observations"], 1)
        self.assertTrue(result["threshold_crossed"])

    def test_stale_observations_display_value_but_have_no_active_signal(self):
        result = interpret(item("us_sahm"),
                           [(date(2024,1,1), D("1.2"))],
                           today=date(2026,11,2))
        self.assertEqual(result["status"], "stale")
        self.assertIsNone(result["threshold_crossed"])
        self.assertEqual(result["consecutive_source_observations"], 0)
        self.assertEqual(result["latest"]["value"], "1.2")

    def test_rank_needs_real_sample_and_is_not_pretended_historical_vintage(self):
        rows = [(date(2000 + i, 1, 1), D(str(i))) for i in range(24)]
        result = interpret(item("us_cape_rank"), rows, today=date(2026,1,1))
        self.assertEqual(result["historical_rank_pct"], "100.00")
        self.assertEqual(result["rank_sample_count"], 24)
        self.assertIn("revised", result["rank_method"])
        self.assertIsNone(result["threshold_crossed"])

    def test_invalid_future_nonfinite_and_unknown_source_handled(self):
        result = interpret(item("us_credit"),
            [(date(2027,1,1), D("10")), (date(2026,10,1), D("NaN"))],
            today=date(2026,11,2))
        self.assertEqual(result["status"], "no_data")
        self.assertIsNone(result["latest"])
        self.assertEqual(diagnostic_catalog()["scopes"], ["world","us","europe","japan"])


if __name__ == "__main__":
    unittest.main()
