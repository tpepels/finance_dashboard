"""Findings use independent fixtures, each observation's date and actual concept."""
import unittest

from finance_dashboard.engine.summaries import summarize


# Literal expectations deliberately do not call the engine's calculations.
CASES = [
    ("C01", {"clock": [{"area": "US", "phase": "expansion", "as_of": "2026-09"}]}, ["2026-09", "expansion"]),
    ("C02", {"now": {"spread": {"month": "2026-09", "value": -0.4}, "sahm": {"month": "2026-08", "value": 0.6}, "threshold": 0.5}}, ["-0.40", "2026-09", "0.60", "2026-08", "0.50"]),
    ("C03", {"strip": [{"area": "US", "year": "2025", "latest": 2.0}, {"area": "JP", "year": "2024", "latest": 0.8}]}, ["2.0%", "2025", "0.8%", "2024", "growth"]),
    ("C05", {"episodes": [{"start": "2020-03", "end": "2020-04", "measures": {"gdp": {"peak": "2019-10", "trough": "2020-04", "depth": -0.1, "months_to_recover": 15}}}]}, ["Real GDP", "10.0%", "2019 Q4", "2020 Q2", "15 months"]),
    ("C06", {"commodities": [{"name": "Brent crude oil", "latest": 0.125, "as_of": "2026-09"}]}, ["Brent", "+12.5%", "2026-09", "causal"]),
    ("M01", {"ladder": [{"bank": "fed", "latest": 3.8, "as_of": "2026-11-06"}, {"bank": "ecb", "latest": 2.5, "as_of": "2026-11-05"}], "gaps": {"eur_minus_usd": [["2026-10", -1.3]]}}, ["EFFR 3.80% (2026-11-06)", "deposit setting 2.50% (2026-11-05)", "-1.30 percentage points", "2026-10"]),
    ("M02", {"split": {"now": {"date": "2026-11-05", "nominal": 4.5, "real": 2.0, "breakeven": 2.5}}}, ["4.50%", "2.00%", "2.50", "2026-11-05", "risk"]),
    ("M04", {"currencies": [{"currency": "USD", "move_12m": -3.5, "move_as_of": "2026-09", "gap": -1.2, "gap_as_of": "2026-08"}]}, ["-3.5%", "2026-09", "-1.20", "2026-08", "co-movement"]),
    ("F01", {"economies": [{"area": "US", "as_of": "2026-01-01", "ratio": 150.0, "ratio_change_5y": -20.0, "ratio_5y_ago_as_of": "2021-01-01"}]}, ["150.0% of GDP", "2026 Q1", "-20.0 percentage points", "2021 Q1"]),
    ("F02", {"rows": [{"series": "private", "area": "US", "latest": 14.0, "as_of": "2026-01-01", "change": 1.5, "back_as_of": "2021-01-01"}]}, ["14.0% of income", "2026 Q1", "+1.5 percentage points", "2021 Q1"]),
    ("F03", {"rows": [{"area": "US", "credit_gap": {"latest": -5.0, "as_of": "2026-01-01"}, "private_dsr": {"latest": 14.0, "as_of": "2025-10-01", "deviation_from_own_mean": 1.0}}]}, ["-5.0 percentage points", "2026 Q1", "14.0%", "2025 Q4", "above"]),
    ("F04", {"gauges": [{"key": "nfci", "name": "NFCI", "latest": -0.5, "as_of": "2026-10-30", "own_mean": 0.0}]}, ["NFCI", "-0.50", "2026-10-30", "below"]),
    ("F05", {"economies": [{"area": "US", "as_of": "2026-01-01", "household": 60.0, "corporate": 70.0, "government": 120.0, "government_year": "2025"}]}, ["60.0%", "70.0%", "2026 Q1", "120.0%", "2025"]),
    ("F06", {"residential": [{"area": "PT", "as_of": "2026-04-01", "change_5y_pct": 25.0, "back_as_of": "2021-04-01"}]}, ["Portugal", "real residential", "+25.0%", "2021 Q2", "2026 Q2"]),
    ("F07", {"latest": {"broker_leverage": 12.5, "repo_share": 40.0, "as_of": "2026-04-01", "mmf_assets": 8_000_000, "mmf_as_of": "2026-01-01"}}, ["12.5", "40.0%", "2026 Q2", "$8.0 trillion", "2026 Q1", "mismatch"]),
    ("V01", {"gauges": [{"key": "cape", "latest": 30.0, "as_of": "2026-10-01", "own_percentile": 0.9, "own_mean": 18.0, "history_start": "1881-01-01"}, {"key": "pe", "latest": 24.0, "as_of": "2026-09-01", "own_percentile": 0.8, "history_start": "1871-01-01"}]}, ["30.0", "2026-10", "90%", "24.0", "2026-09"]),
    ("V02", {"gauges": [{"key": "q1", "name": "BEA Q1", "latest": 2.2, "as_of": "2024-01-01"}]}, ["BEA Q1", "2.20", "2024", "replacement"]),
    ("V03", {"regions": [{"region": "USA", "as_of": "2026-09-01", "trailing": 24.0, "forward": 20.0}, {"region": "JAPAN", "as_of": "2026-08-01", "trailing": 16.0, "forward": 14.0}]}, ["USA", "24.0", "2026-09", "JAPAN", "16.0", "2026-08", "sector"]),
    ("V05", {"cells": [{"horizon_years": 10, "era": "All years", "rho": 0.6, "effective_windows": 12.5, "windows": 1500, "first_start": "1881-01", "last_start": "2010-12"}]}, ["earnings yield", "10-year", "0.60", "1881-01", "2010-12", "12.5", "overlap"]),
    ("L01", {"economies": [{"area": "US", "base_year": "1995", "latest_year": "2020", "productivity": 150.0, "pay": 140.0}]}, ["1995", "2020", "50.0%", "40.0%", "compensation"]),
    ("L02", {"economies": [{"area": "US", "year": "2024", "parts": [{"key": "compensation", "share": 60.0}, {"key": "net_operating_surplus", "share": 20.0}]}]}, ["60%", "2024", "20%", "Net operating surplus", "value added"]),
    ("L03", {"economies": [{"area": "US", "first": 8.0, "first_year": "2000", "latest": 12.0, "latest_year": "2024"}]}, ["8.0%", "2000", "12.0%", "2024", "net fixed assets", "net profit"]),
    ("L04", {"countries": [{"country": "USA", "year": 2014, "methods": {"io": {"year": 2014, "surplus_value": {"min": 1.2, "max": 1.5}}}}]}, ["2014", "120%", "150%", "surplus-to-wage", "classification"]),
    ("L05", {"groups": [{"key": "top_point1", "latest": 15.0}, {"key": "next_point9", "latest": 20.0}, {"key": "bottom50", "latest": 2.0}], "latest_date": "2026-04-01"}, ["35.0%", "2.0%", "2026 Q2", "household net worth"]),
    ("L07", {"economies": [{"area": "WORLD", "then_year": "1980", "latest_year": "2023", "top1_then": 15.0, "top1_latest": 20.0, "bottom50_then": 6.0, "bottom50_latest": 8.0}]}, ["20.0%", "8.0%", "2023", "income", "wealth"]),
    ("G01", {"latest": {"date": "2026-07-31", "top10_pct": 25.0}, "published_top10": [["2026-09-01", 24.0]]}, ["25.0%", "2026-07-31", "ETF", "24.0%", "2026-09", "security"]),
    ("G02", {"date": "2026-07-31", "countries": [{"area": "US", "index_weight": 60.0, "gdp_share": 25.0, "gdp_year": "2025"}]}, ["60.0%", "2026-07-31", "25.0%", "2025", "ETF", "revenue"]),
    ("G03", {"alternatives": [{"key": "eu27_profit_share", "latest": 40.0, "as_of": "2025-01-01", "unit": "% of value added"}], "listed_earnings": {"latest": {"month": "2026-09-01", "earnings_usd_bn": 4800.0}}}, ["withheld", "implied index earnings proxy", "$4.8 trillion", "2026-09", "40.0%", "2025", "value added"]),
    ("G05", {"economies": [{"area": "US", "current_account_gdp": -4.0, "current_account_year": "2025", "net_position_gdp": -80.0, "net_position_year": "2024"}]}, ["-4.0%", "2025", "-80.0%", "2024", "GDP"]),
    ("G06", {"economies": [{"area": "DE", "first": 20.0, "first_year": "1995", "latest": 30.0, "latest_year": "2022"}]}, ["20.0%", "1995", "30.0%", "2022", "foreign final demand"]),
    ("P01", {"funds": [{"name": "Example World Fund", "date": "2026-07-31", "countries": [{"key": "US", "share": 60.0}]}]}, ["Example World Fund", "60.0%", "2026-07-31", "fund", "weights"]),
    ("P02", {"cells": [{"pair": "stocks_bonds", "period": "All years", "rho": -0.1, "months": 240, "from": "2001-01", "to": "2020-12"}]}, ["-0.10", "240", "2001-01", "2020-12", "US sovereign", "gold"]),
    ("P03", {"underwater": [["2026-10", -0.025]], "episodes": [{"peak": "2007-10", "trough": "2009-02", "depth": -0.55, "months_to_recover": 50}]}, ["2.5%", "2026-10", "55%", "2007-10", "2009-02", "50 months"]),
    ("P04", {"is_example": True, "shocks": [{"key": "rates_up", "label": "Bond yields rise by 1 percentage point", "impact_pct": -1.75}]}, ["Example", "-1.8%", "first-order", "probability"]),
    ("P05", {"is_example": True, "chosen": "threshold", "period": {"from": "2001-01", "to": "2026-10"}, "rules": [{"key": "threshold", "label": "Threshold", "final": 123_400.0, "max_drawdown": -0.25, "costs": 100.0, "taxes": 200.0}]}, ["Example", "2001-01", "2026-10", "€123,400", "25.0%", "cash flows", "surrogate"]),
    ("P06", {"equity_world_snapshot": {"as_of": "2026-09-01", "earnings_yield": 0.05}, "bonds": {"us_nominal_10y": {"as_of": "2026-11-05", "yield": 0.045}}}, ["5.0%", "2026-09", "4.50%", "2026-11-05", "forecast"]),
    ("P07", {"rows": [{"month": "2001-01"}, {"month": "2026-10"}], "nominal": {"eur_unhedged": {"annualized_return": 0.06}, "eur_hedged": {"annualized_return": 0.055}}}, ["2001-01", "2026-10", "6.0%", "5.5%", "modeled", "hedge"]),
]


class SummaryTests(unittest.TestCase):
    def test_each_question_uses_its_own_observed_values(self):
        for ident, values, snippets in CASES:
            with self.subTest(question=ident):
                result = summarize(ident, values)
                self.assertTrue(result, ident)
                self.assertLessEqual(len(result), 2)
                text = " ".join(result)
                for snippet in snippets:
                    self.assertIn(snippet.lower(), text.lower())

    def test_c01_does_not_assign_the_latest_countrys_month_to_every_country(self):
        values = {"clock": [{"area": "US", "phase": "expansion", "as_of": "2026-09"},
                            {"area": "JP", "phase": "contraction", "as_of": "2026-08"},
                            {"area": "G7", "phase": "slowdown", "as_of": "2026-07"}]}
        text = " ".join(summarize("C01", values))
        self.assertIn("Japan", text)
        self.assertIn("2026-08", text)
        self.assertIn("2026-07", text)

    def test_m01_does_not_call_a_policy_setting_investor_cash_earnings(self):
        values = CASES[5][1]
        self.assertNotIn("cash earned", " ".join(summarize("M01", values)))

    def test_v01_separate_dates_are_not_called_the_same_month(self):
        text = " ".join(summarize("V01", CASES[15][1]))
        self.assertNotIn("same month", text)

    def test_l02_operating_surplus_is_not_after_tax_profit(self):
        text = " ".join(summarize("L02", CASES[20][1]))
        self.assertNotIn("Net profit", text)
        self.assertIn("before", text)

    def test_p01_prefers_declared_positions_to_unrelated_published_fund_examples(self):
        values = {"funds": [{"name": "Unrelated example fund", "date": "2026-11-11",
                             "countries": [{"key": "US", "share": 99.0}]}],
                  "owner_portfolio": {"as_of": None, "combine_accounts": True, "scope": "supplied_positions",
                    "positions": [{"key": "a"}, {"key": "b"}, {"key": "c"}],
                    "summary": {"accounts": [{"account": "A"}, {"account": "B"}], "total_value_eur": 1500.0,
                      "position_count": 3, "funds": [{"name": "Named thematic fund", "weight": 2 / 3},
                                                     {"name": "Mixed precious-metals fund", "weight": 1 / 3}]}}}
        text = " ".join(summarize("P01", values))
        for literal in ("€1,500", "3 positions", "2 accounts", "2 funds", "valuation date not supplied",
                        "Named thematic fund", "66.7%", "look-through"):
            self.assertIn(literal, text)
        self.assertNotIn("Unrelated example", text)
        self.assertNotIn("2026-11-11", text)

    def test_p01_never_invents_a_total_or_a_top_fund_weight(self):
        values = {"owner_portfolio": {"as_of": "2026-11-10", "positions": [{"key": "a"}],
          "summary": {"accounts": [{"account": "A"}], "total_value_eur": None, "position_count": 1,
                      "funds": [{"name": "Unpriced fund", "weight": None}]}}}
        text = " ".join(summarize("P01", values))
        self.assertIn("total value not supplied", text)
        self.assertIn("2026-11-10", text)
        self.assertNotIn("€0", text)
        self.assertNotIn("0.0%", text)

    def test_g03_new_regulator_sample_does_not_answer_the_global_original(self):
        values = {"listed_profit_coverage": {"sources": [{"year": 2025,
            "consolidated_income_issuers": 442, "filing_issuers": 671, "filing_versions": 761}]}}
        text = " ".join(summarize("G03", values))
        for literal in ("withheld", "Brazil CVM 2025", "442", "671", "unverified"):
            self.assertIn(literal, text)

    def test_withheld_empty_and_malformed_values_give_no_findings(self):
        for ident, _, _ in CASES:
            with self.subTest(question=ident):
                self.assertEqual(summarize(ident, None), [])
                self.assertEqual(summarize(ident, {}), [])
                self.assertEqual(summarize(ident, {"unexpected": []}), [])
        self.assertEqual(summarize("X99", {"value": 1}), [])
        self.assertEqual(summarize("G03", {"alternatives": [], "listed_earnings": {"latest": None}}), [])


if __name__ == "__main__":
    unittest.main()
