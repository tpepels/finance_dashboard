"""Evidence summaries: two dated sentences built only from a bundle's own values."""
import unittest

from finance_dashboard.engine.summaries import summarize


def row(area, phase, as_of="2026-09"):
    return {"area": area, "as_of": as_of, "phase": phase, "trail": []}


class SummaryTests(unittest.TestCase):
    def test_c01_counts_phases_and_names_contractions(self):
        values = {"clock": [row("US", "expansion"), row("DE", "expansion"), row("JP", "slowdown"), row("CN", "contraction"),
                            row("G7", "expansion")], "diffusion": {"6m": [["2026-09", 61.2]]}}
        first, second = summarize("C01", values)
        self.assertEqual(first, "In 2026-09 the OECD leading indicators place 2 of 4 economies in expansion, 1 in slowdown "
                                "and 1 in contraction (China).")
        self.assertEqual(second, "Across the G7, the indicator is in expansion; 61% of US industries grew over the six months to 2026-09.")

    def test_m01_rates_their_change_and_the_euro_gap(self):
        ladder = [{"bank": "fed", "latest": 3.88, "as_of": "2026-11-06", "change": 0.01},
                  {"bank": "ecb", "latest": 2.5, "as_of": "2026-11-05", "change": 0.5},
                  {"bank": "boj", "latest": 1.23, "as_of": "2026-11-06", "change": 0.75}]
        first, second = summarize("M01", {"ladder": ladder, "gaps": {"eur_minus_usd": [["2026-10", -1.38]]}})
        self.assertEqual(first, "On 2026-11-06 the Federal Reserve was at 3.88%, the ECB at 2.50% and the Bank of Japan at 1.23%.")
        self.assertEqual(second, "Over the past year the ECB moved +0.50 points, the Fed +0.01 and the Bank of Japan +0.75; "
                                 "in 2026-10 euro cash earned 1.38 points less than dollar cash.")

    def test_p03_distance_from_the_peak_and_the_deepest_fall(self):
        values = {"underwater": [["2026-10", -0.0274]], "episodes": [
            {"peak": "2001-01", "trough": "2002-09", "depth": -0.388, "months_to_recover": 27},
            {"peak": "2007-10", "trough": "2009-02", "depth": -0.551, "months_to_recover": 55}]}
        first, second = summarize("P03", values)
        self.assertEqual(first, "At the end of 2026-10 world equities (MSCI ACWI, US dollars) were 2.7% below their previous peak.")
        self.assertEqual(second, "The deepest fall in the data was 55% (2007-10 to 2009-02), regained 55 months after the low.")

    def test_unknown_or_empty_values_give_no_summary(self):
        self.assertEqual(summarize("X99", {"a": 1}), [])
        self.assertEqual(summarize("C01", {"clock": [], "diffusion": {}}), [])


if __name__ == "__main__":
    unittest.main()


class SummaryWordingTests(unittest.TestCase):
    def test_f03_says_plainly_when_no_economy_is_above_the_upper_guide(self):
        gap = lambda v: {"as_of": "2026-01-01", "latest": v}
        dsr = lambda d: {"deviation_from_own_mean": d}
        rows = [{"area": "CN", "credit_gap": gap(-5.1), "gap_guide_band": "below_2pp", "private_dsr": dsr(4.1)},
                {"area": "JP", "credit_gap": gap(5.7), "gap_guide_band": "2_to_10pp", "private_dsr": dsr(0.5)},
                {"area": "US", "credit_gap": gap(-11.3), "gap_guide_band": "below_2pp", "private_dsr": dsr(-1.2)}]
        first, second = summarize("F03", {"rows": rows})
        self.assertEqual(first, "In the BIS data to 2026-01 no economy shown has private credit more than 10 points of GDP above "
                                "its trend; it is below trend or less than 2 points above it in China and the United States.")
        self.assertEqual(second, "Debt service takes a larger share of income than its own long-run average in China and Japan, "
                                 "and a smaller share in the United States.")

    def test_v01_names_the_lowest_and_highest_readings(self):
        g = lambda key, latest, pct, start: {"key": key, "as_of": "2026-10-01", "latest": latest, "own_percentile": pct,
                                             "own_mean": 17.8, "history_start": start}
        values = {"gauges": [g("cape", 40.7, 0.99, "1881-01-01"), g("pe", 25.2, 1.0, "1871-01-01"),
                             g("excess_cape_yield", -0.1, 0.0, "2003-01-01")]}
        first, second = summarize("V01", values)
        self.assertIn("higher than 99% of months since 1881", first)
        self.assertEqual(second, "In the same month the trailing P/E was 25.2 (the highest reading since 1871) and the excess "
                                 "CAPE yield was -0.1 points (the lowest reading since 2003).")

    def test_c01_months_are_months(self):
        values = {"clock": [row("US", "expansion")], "diffusion": {"6m": [["2026-08-01", 61.2]]}}
        self.assertIn("six months to 2026-08.", summarize("C01", values)[1])
