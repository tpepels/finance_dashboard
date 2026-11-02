"""Backend-only descriptive insight and exact shared-date comparison tests."""
from datetime import date, timedelta
from decimal import Decimal as D
import unittest

from finance_dashboard.insights import summarize, same_measure


def record(sid, values, frequency="D", unit="percent"):
    return ({"id": sid, "name": sid, "frequency": frequency, "unit": unit},
            [(date.fromisoformat(day), D(val)) for day, val in values])


class InsightTests(unittest.TestCase):
    def test_bis_shared_date_spread_not_nearest_neighbor_interpolation(self):
        pairs = [
            record("policy_rate.us.bis", [("2025-01-01", "2"), ("2026-01-01", "4")]),
            record("policy_rate.ea.bis", [("2025-01-01", "1"), ("2026-01-02", "3")]),
        ]
        report = summarize(pairs)
        self.assertEqual(report["matched_spread"]["date"], "2025-01-01")
        self.assertEqual(report["matched_spread"]["difference"], "1")
        self.assertEqual(report["matched_spread"]["unit"], "percentage_points")
        self.assertEqual(report["series"][0]["year_change"]["difference"], "2")
        self.assertEqual(report["series"][0]["year_change"]["from_date"], "2025-01-01")
        self.assertEqual(report["series"][1]["year_change"]["difference"], "2")

    def test_missing_annual_comparator_does_not_fake_one_year_change(self):
        dataset = record("fiscal.world.public_debt",
                         [("2020-01-01", "84.1"), ("2025-01-01", "91.4")],
                         "A")
        result = summarize([dataset])
        self.assertIsNone(result["series"][0]["year_change"])
        self.assertIsNone(result["matched_spread"])
        self.assertEqual(result["series"][0]["value"], "91.4")

    def test_same_unit_different_meaning_cannot_be_summarized_together(self):
        self.assertFalse(same_measure(
            ["labour.world.productivity_growth", "labour.world.income_share"]))
        self.assertFalse(same_measure(
            ["fiscal.world.public_debt", "policy_rate.us.bis"]))
        self.assertFalse(same_measure(
            ["gold.usd.monthly_average", "bond.us.real_10y"]))
        with self.assertRaisesRegex(ValueError, "Unrelated"):
            summarize([record("labour.world.income_share",
                              [("2025-01-01", "55")], "A"),
                       record("labour.world.productivity_growth",
                              [("2025-01-01", "2")], "A")])

    def test_real_growth_cohort_with_synchronized_source_year(self):
        a = record("gdp.real_growth.us",
                   [("2024-01-01", "3.1"), ("2025-01-01", "1.9")], "A")
        b = record("gdp.real_growth.jp",
                   [("2024-01-01", "0.1"), ("2025-01-01", "-0.5")], "A")
        report = summarize([a, b])
        self.assertEqual(report["matched_spread"]["difference"], "2.4")
        self.assertEqual(report["matched_spread"]["date"], "2025-01-01")
        self.assertEqual(report["series"][0]["year_change"]["difference"], "-1.2")
        self.assertEqual(report["series"][1]["year_change"]["difference"], "-0.6")

    def test_missing_country_blocks_partial_cohort_spread(self):
        result = summarize([
            record("policy_rate.us.bis", [("2025-01-01", "3")]),
            record("policy_rate.jp.bis", []),
            record("policy_rate.ea.bis", [("2025-01-01", "2")]),
        ])
        self.assertIsNone(result["matched_spread"])
        self.assertEqual(result["series"][1]["status"], "no_data")

    def test_empty_source_keeps_no_data_status(self):
        report = summarize([record("valuation.world.global_trailing_pe", [], "M", "ratio")])
        self.assertEqual(report["series"][0]["status"], "no_data")
        self.assertIsNone(report["matched_spread"])


if __name__ == "__main__":
    unittest.main()
