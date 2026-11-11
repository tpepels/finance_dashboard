"""C02 (yield curve and Sahm rule side by side), C05 (depth and persistence of recessions), G03 (gated)."""
from datetime import date
import unittest

from engine_fixtures import monthly
from finance_dashboard.engine.analyses import C02, C05, DEFINITIONS, G03, recovery


def months_from(start, flags):
    return monthly(start, [1.0 if f else 0.0 for f in flags])


class C02Tests(unittest.TestCase):
    def setUp(self):
        # 48 months from 2000-01; recession months 2002-01..2002-06 (index 24-29).
        self.n = 48
        self.nber = months_from((2000, 1), [24 <= i <= 29 for i in range(self.n)])
        spread = [1.0] * self.n
        for i in range(10, 14):      # inverted 2000-11 .. 2001-02: 14 months before the recession
            spread[i] = -0.3
        for i in range(40, 43):      # inverted 2003-05 .. 2003-07, no recession follows in the data
            spread[i] = -0.2
        self.spread = monthly((2000, 1), spread)
        sahm = [0.1] * self.n
        for i in range(27, 34):      # triggers 2002-04, three months after the recession starts
            sahm[i] = 0.6
        self.sahm = monthly((2000, 1), sahm)

    def compute(self, announcements=None):
        points = {"spread": self.spread, "sahm": self.sahm, "nber": self.nber}
        chron = {"announcements": announcements or [], "retrospective_cycles": []}
        return C02.compute(points, {"today": "2004-06-01"}, {"nber_chronology": chron}).values

    def test_signals_are_placed_on_each_recession_timeline(self):
        self.assertIs(DEFINITIONS["C02"], C02)
        values = self.compute([{"announcement_date": "2003-01-15", "classification": "determination",
                                "turning_point": "peak", "event_month": "2001-12"}])
        episode = values["recessions"][0]
        self.assertEqual(episode["start"], "2002-01")
        self.assertEqual(episode["curve_inverted"], {"month": "2000-11", "offset": -14})
        self.assertEqual(episode["sahm_triggered"], {"month": "2002-04", "offset": 3})
        self.assertEqual(episode["announced"], {"date": "2003-01-15", "offset": 12})

    def test_inversions_without_a_following_recession_are_listed_not_scored(self):
        values = self.compute()
        self.assertEqual(values["false_alarms"]["curve"], [{"start": "2003-05", "months": 3, "open": True}])
        self.assertNotIn("agreement", values)
        self.assertEqual(values["now"]["sahm"]["value"], 0.1)
        self.assertEqual(values["now"]["threshold"], 0.5)


class C05Tests(unittest.TestCase):
    def test_recovery_measures_depth_and_months_to_regain_the_peak(self):
        levels = {(2000, m): v for m, v in zip(range(1, 13), [100, 101, 102, 99, 95, 94, 96, 99, 101, 102, 103, 103])}
        result = recovery(levels, (2000, 4), (2000, 6))
        self.assertAlmostEqual(result["depth"], 94 / 102 - 1)
        self.assertEqual(result["trough"], "2000-06")
        self.assertEqual(result["months_to_recover"], 7)     # 2000-10 regains 102, counted from the 2000-03 peak level month
        self.assertIsNone(recovery({(2000, 1): 100, (2000, 2): 90}, (2000, 2), (2000, 2))["months_to_recover"])

    def test_episodes_per_recession_with_shock_context(self):
        self.assertIs(DEFINITIONS["C05"], C05)
        n = 36
        nber = months_from((2019, 1), [14 <= i <= 15 for i in range(n)])       # 2020-03..2020-04
        level = [100.0] * 14 + [85.0, 80.0] + [90.0, 95.0, 99.0, 101.0] + [102.0] * 16
        points = {"nber": nber, "industrial_production": monthly((2019, 1), level),
                  "payrolls": monthly((2019, 1), level), "gdp": []}
        events = [{"id": "covid", "date": "2020-03-11", "label": "WHO pandemic", "category": "pandemic_shock"}]
        values = C05.compute(points, {"today": "2022-01-01"}, {"shock_events": events}).values
        covid = values["episodes"][-1]
        self.assertEqual(covid["start"], "2020-03")
        self.assertAlmostEqual(covid["measures"]["industrial_production"]["depth"], -0.2)
        self.assertEqual(covid["shocks"], [{"date": "2020-03-11", "label": "WHO pandemic"}])
        self.assertIsNone(covid["measures"]["gdp"])


class G03Tests(unittest.TestCase):
    def test_only_labelled_alternatives_never_a_listed_profit_ratio(self):
        self.assertIs(DEFINITIONS["G03"], G03)
        points = {role: [] for role in G03.inputs}
        points["eu27_profit_share"] = [(date(2024, 1, 1), 40.5)]
        points["oecd_surplus_gdp"] = [(date(2023, 1, 1), 22.0)]
        values = G03.compute(points, {}).values
        self.assertEqual([a["key"] for a in values["alternatives"]], ["eu27_profit_share", "oecd_surplus_gdp"])
        self.assertTrue(all(a["non_equivalent"] for a in values["alternatives"]))
        self.assertNotIn("listed_profit_ratio", values)

    def test_implied_index_earnings_arithmetic_and_december_gdp_comparison(self):
        points = {role: [] for role in G03.inputs}
        points["acwi_mkt_cap"] = [(date(2024, 12, 1), 80_000_000.0), (date(2025, 6, 1), 90_000_000.0)]
        points["acwi_pe"] = [(date(2024, 12, 1), 20.0), (date(2025, 6, 1), 22.5)]
        points["world_gdp"] = [(date(2024, 1, 1), 110e12), (date(2025, 1, 1), 115e12)]
        values = G03.compute(points, {}).values
        listed = values["listed_earnings"]
        self.assertEqual(listed["history"], [["2024-12-01", 4000.0], ["2025-06-01", 4000.0]])   # USD billions
        self.assertEqual(listed["share_of_gdp"], [["2024", 4000e9 / 110e12 * 100]])            # December months only
        self.assertEqual(listed["latest"]["month"], "2025-06-01")

    def test_missing_eps_population_cannot_be_presented_as_reported_company_profit(self):
        # Independent example: A has $60bn cap and $3bn normalized earnings;
        # B has $20bn cap but no EPS, so MSCI excludes B from the P/E ratio.
        # The printed P/E is 20 while total index cap/P-E is $4bn, which is
        # neither A's $3bn earnings nor verified A+B reported net profit.
        points = {role: [] for role in G03.inputs}
        points["acwi_mkt_cap"] = [(date(2024, 12, 1), 80_000.0)]  # USD millions
        points["acwi_pe"] = [(date(2024, 12, 1), 20.0)]
        points["world_gdp"] = [(date(2024, 1, 1), 2e12)]
        computed = G03.compute(points, {})
        proxy = computed.values["listed_earnings"]
        self.assertEqual(proxy["history"], [["2024-12-01", 4.0]])
        self.assertEqual(proxy["share_of_gdp"], [["2024", 0.2]])
        self.assertEqual(proxy.get("measure"), "implied_index_earnings_proxy")
        self.assertIs(proxy.get("reported_company_profit"), False)
        self.assertIs(proxy.get("cap_and_pe_population_match_verified"), False)
        self.assertEqual(proxy.get("methodology_url"),
            "https://www.msci.com/indexes/documents/methodology/0_MSCI_Fundamental_Data_Methodology_20240625.pdf")
        self.assertIn("normalized", computed.transforms[0]["params"]["note"])
        self.assertIn("unverified", computed.transforms[0]["params"]["note"])

    def test_alternatives_name_the_corpus_variants_that_supply_them(self):
        from finance_dashboard.research_corpus import load_research_corpus
        corpus = next(a for a in load_research_corpus()["analyses"] if a["id"] == "G03")
        variants = {v["id"]: set(v["series_ids"]) for v in corpus["comparison_contract"]["variants"]}
        self.assertEqual(set(G03.alternatives), set(variants))
        for variant, roles in G03.alternatives.items():
            self.assertEqual({G03.inputs[r] for r in roles}, variants[variant])


if __name__ == "__main__":
    unittest.main()


class SpliceTests(unittest.TestCase):
    def test_archive_and_current_join_only_when_every_shared_day_agrees(self):
        from finance_dashboard.engine.transforms import splice_identical
        archive = [(date(2020, 1, 2), 5.0), (date(2023, 11, 6), 3.9), (date(2023, 11, 7), 3.8)]
        current = [(date(2023, 11, 6), 3.9), (date(2023, 11, 7), 3.8), (date(2026, 11, 5), 2.9)]
        joined, check = splice_identical(archive, current)
        self.assertEqual([d for d, _ in joined], [date(2020, 1, 2), date(2023, 11, 6), date(2023, 11, 7), date(2026, 11, 5)])
        self.assertEqual(check, {"overlap_days": 2, "differing_days": 0})
        joined, check = splice_identical(archive, [(date(2023, 11, 6), 4.0), (date(2026, 11, 5), 2.9)])
        self.assertEqual(joined, [])
        self.assertEqual(check["differing_days"], 1)

    def test_f04_shows_the_high_yield_spread_from_the_joined_history(self):
        from finance_dashboard.engine.analyses import F04
        points = {role: [] for role in F04.inputs}
        points["hy_archive"] = [(date(1997, 1, 2), 3.06), (date(2025, 11, 3), 3.04)]
        points["hy_current"] = [(date(2025, 11, 3), 3.04), (date(2026, 11, 5), 2.9)]
        values = F04.compute(points, {}).values
        hy = next(g for g in values["gauges"] if g["key"] == "high_yield")
        self.assertEqual((hy["history_start"], hy["as_of"], hy["latest"]), ("1997-01-02", "2026-11-05", 2.9))
        self.assertEqual(values["high_yield_check"], {"overlap_days": 1, "differing_days": 0})


class FirstReleaseCheckTests(unittest.TestCase):
    def test_fred_real_time_sahm_is_compared_with_the_vintage_recomputation(self):
        n = 48
        points = {"spread": monthly((2000, 1), [1.0] * n), "sahm": monthly((2000, 1), [0.1] * n),
                  "nber": months_from((2000, 1), [False] * n)}
        rtdsm = {"points": [{"vintage": "2001Q1", "month": "2001-01", "value": 0.1},
                            {"vintage": "2001Q2", "month": "2001-04", "value": 0.18},
                            {"vintage": "2009Q1", "month": "2009-01", "value": 1.0}],
                 "source_sha256": "x", "url": "https://www.philadelphiafed.org/x"}
        values = C02.compute(points, {"today": "2004-06-01"}, {"nber_chronology": {}, "rtdsm_sahm": rtdsm}).values
        check = values["first_release_check"]
        self.assertEqual((check["compared"], check["equal_at_two_decimals"]), (2, 1))
        self.assertEqual(check["differences"], [{"vintage": "2001Q2", "month": "2001-04", "recomputed": 0.18, "fred": 0.1}])
        self.assertEqual(check["points"], [["2001-01", 0.1], ["2001-04", 0.18], ["2009-01", 1.0]])


class JstContextTests(unittest.TestCase):
    def test_c05_lists_us_banking_crises_starting_around_a_recession(self):
        n = 36
        nber = months_from((2007, 1), [12 <= i <= 29 for i in range(n)])                 # 2008-01..2009-06
        level = [100.0] * 12 + [90.0] * 18 + [101.0] * 6
        points = {"nber": nber, "industrial_production": monthly((2007, 1), level), "payrolls": [], "gdp": []}
        jst = {"starts": {"USA": [1984, 2007], "ESP": [2008]}}
        values = C05.compute(points, {"today": "2012-01-01"}, {"shock_events": [], "jst_crises": jst}).values
        self.assertEqual(values["episodes"][-1]["banking_crises"], [2007])

    def test_p03_counts_economies_whose_banking_crisis_started_during_a_fall(self):
        from finance_dashboard.engine.analyses import P03
        equity = monthly((2007, 1), [100.0] * 10 + [70.0] * 14 + [110.0] * 6)
        points = {"equity": equity, "recession": monthly((2007, 1), [0.0] * 30)}
        jst = {"starts": {"USA": [2007], "ESP": [2008], "JPN": [1997]}}
        values = P03.compute(points, {"today": "2012-01-01"}, {"jst_crises": jst}).values
        episode = values["episodes"][0]
        self.assertEqual(episode["banking_crises"], ["ESP", "USA"])
