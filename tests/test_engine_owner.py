"""P04 and P05 on the engine: sensitivities and rebalancing rules computed from the owner's inputs."""
from datetime import date, datetime, timezone
import unittest

from engine_fixtures import monthly
from finance_dashboard.engine.analyses import DEFINITIONS, P04, P05, simulate
from finance_dashboard.engine.acceptance import snapshot_from_report
from finance_dashboard.engine.bundle import build_bundle
from finance_dashboard.engine.export import export_text
from finance_dashboard.owner_inputs import EXAMPLE


class OwnerEngineTests(unittest.TestCase):
    def test_p05_bundle_and_export_disclose_hedging_cashflows_and_tax_funding(self):
        at = datetime(2026, 11, 11, tzinfo=timezone.utc)
        # This accepted snapshot is a controlled software fixture, not a corpus assessment.
        snapshot = snapshot_from_report({"analyses": [{"id": "P05", "acceptance": {
            "state": "accepted", "blocking_roles": [], "limitations": [], "requirements": [
                {"role": role, "series_ids": [sid], "state": "accepted", "accepted": True, "limitations": []}
                for role, sid in P05.inputs.items()]}}]}, at)
        bundle = build_bundle(P05, points={}, snapshot=snapshot, corpus_analysis={"title": "Replay"},
                              catalog_series={}, view={"today": "2026-11-11"}, computed_at=at,
                              artifacts={"owner_inputs": EXAMPLE})
        limitations = {item["code"]: item for item in bundle["limitations"]}
        expected = {"replay_hedging_scope": "unhedged", "replay_transaction_order": "withdrawal",
                    "simplified_tax_funding": "cost basis"}
        exported = export_text(bundle)
        for code, meaning in expected.items():
            with self.subTest(code=code):
                self.assertIn(code, limitations)
                item = limitations[code]
                self.assertEqual(item["source"], "method")
                self.assertIn(meaning, item["text"])
                self.assertIn(item["text"], exported)

    def test_sixty_forty_literal_return_is_102_before_flows_and_costs(self):
        result = simulate({"equity": {(2020, 1): 0.10}, "bonds": {(2020, 1): -0.10}}, [(2020, 1)],
                          {"equity": 0.6, "bonds": 0.4}, rule="never", months_between=12, band_pp=5,
                          cost_bps=0, start=100, monthly_contribution=0, annual_withdrawal_pct=0)
        # EUR 60 becomes 66; EUR 40 becomes 36.
        self.assertAlmostEqual(result["final"], 102.0)
        self.assertEqual(result["costs"], 0.0)
        self.assertEqual(result["taxes"], 0.0)

    def test_literal_sensitivities_separate_bond_value_from_portfolio_impact(self):
        owner = {**EXAMPLE, "allocation": {"equity": 0.6, "bonds": 0.4, "gold": 0}, "bond_duration_years": 7}
        mix = P04.compute({}, {}, {"owner_inputs": owner}).values
        shocks = {row["key"]: row["impact_pct"] for row in mix["shocks"]}
        self.assertAlmostEqual(shocks["equities_down"], -12.0)
        self.assertAlmostEqual(shocks["rates_up"], -2.8)
        bonds = P04.compute({}, {}, {"owner_inputs": {**owner, "allocation": {"equity": 0, "bonds": 1, "gold": 0}}}).values
        self.assertAlmostEqual(bonds["shocks"][0]["impact_pct"], -7.0)

    def test_calendar_threshold_and_never_rules_have_hand_calculated_paths(self):
        # First month: 60*1.10 + 40*0.90 = 102. Rebalancing transfers 4.8.
        # At 100 bps, the single-sided turnover fee is 0.048, leaving 101.952.
        returns = {"equity": {(2020, 1): 0.1}, "bonds": {(2020, 1): -0.1}}
        for rule, interval, band, fee, final, count, costs in (
            ("never", 1, 4, 100, 102.0, 0, 0.0),
            ("calendar", 2, 4, 100, 102.0, 0, 0.0),
            ("calendar", 1, 4, 0, 102.0, 1, 0.0),
            ("calendar", 1, 4, 100, 101.952, 1, 0.048),
            ("threshold", 12, 5, 100, 102.0, 0, 0.0),
            ("threshold", 12, 4, 100, 101.952, 1, 0.048),
        ):
            with self.subTest(rule=rule, interval=interval, band=band, fee=fee):
                result = simulate(returns, [(2020, 1)], {"equity": 0.6, "bonds": 0.4}, rule=rule,
                                  months_between=interval, band_pp=band, cost_bps=fee, start=100,
                                  monthly_contribution=0, annual_withdrawal_pct=0)
                self.assertAlmostEqual(result["final"], final)
                self.assertAlmostEqual(result["costs"], costs)
                self.assertEqual(result["rebalances"], count)

    def test_cash_flows_follow_returns_then_contribution_then_withdrawal(self):
        # 100 earns 10%, then receives 10, then withdraws 1% of 120.
        result = simulate({"equity": {(2020, 1): 0.1}}, [(2020, 1)], {"equity": 1}, rule="never",
                          months_between=12, band_pp=5, cost_bps=0, start=100,
                          monthly_contribution=10, annual_withdrawal_pct=0.12)
        self.assertAlmostEqual(result["final"], 118.8)

    def test_contributions_add_cost_basis_before_a_taxable_rebalance(self):
        # Start with 50 per asset; equity doubles in month 1. Two contributions
        # of 100 add 100 to each asset and its basis. Before the month-2 trade,
        # equity is 200 (basis 150), bonds 150. Selling 25 realises 6.25;
        # 25% tax is 1.5625, deducted from total 350.
        result = simulate({"equity": {(2020, 1): 1.0, (2020, 2): 0.0},
                           "bonds": {(2020, 1): 0.0, (2020, 2): 0.0}}, [(2020, 1), (2020, 2)],
                          {"equity": 0.5, "bonds": 0.5}, rule="calendar", months_between=2, band_pp=5,
                          cost_bps=0, start=100, monthly_contribution=100, annual_withdrawal_pct=0,
                          tax_mode="realised_gains", tax_rate=0.25)
        self.assertAlmostEqual(result["path"][0][1], 250.0)
        self.assertAlmostEqual(result["taxes"], 1.5625)
        self.assertAlmostEqual(result["final"], 348.4375)
        self.assertEqual(result["rebalances"], 1)

    def test_withdrawal_tax_only_charges_the_gain_share_of_the_sale(self):
        # 100 doubles to 200; withdrawal is 10, of which 5 is gain.
        # The simplified 25% realised-gain charge is 1.25.
        result = simulate({"equity": {(2020, 1): 1.0}}, [(2020, 1)], {"equity": 1}, rule="never",
                          months_between=12, band_pp=5, cost_bps=0, start=100,
                          monthly_contribution=0, annual_withdrawal_pct=0.6,
                          tax_mode="realised_gains", tax_rate=0.25)
        self.assertAlmostEqual(result["taxes"], 1.25)
        self.assertAlmostEqual(result["final"], 188.75)

    def test_losses_have_no_tax_credit(self):
        result = simulate({"equity": {(2020, 1): -0.5}, "bonds": {(2020, 1): 0.0}}, [(2020, 1)],
                          {"equity": 0.5, "bonds": 0.5}, rule="calendar", months_between=1, band_pp=5,
                          cost_bps=0, start=100, monthly_contribution=0, annual_withdrawal_pct=0,
                          tax_mode="realised_gains", tax_rate=0.25)
        # The bond sale has zero gain; equity loss is unrealised and earns no credit.
        self.assertAlmostEqual(result["final"], 75.0)
        self.assertEqual(result["taxes"], 0.0)

    def test_exhausted_capital_stays_zero_through_withdrawal_tax_and_rebalancing(self):
        months = [(2020, m) for m in range(1, 13)]
        returns = {"equity": {key: (-1.0 if key == (2020, 1) else 1.0) for key in months}}
        for tax_mode in ("none", "realised_gains", "yearly_on_value"):
            with self.subTest(tax_mode=tax_mode):
                result = simulate(returns, months, {"equity": 1}, rule="calendar", months_between=1,
                                  band_pp=5, cost_bps=500, start=100, monthly_contribution=0,
                                  annual_withdrawal_pct=1, tax_mode=tax_mode, tax_rate=0.6)
                self.assertEqual(result["final"], 0.0)
                self.assertEqual([value for _, value in result["path"]], [0.0] * 12)
                self.assertEqual(result["max_drawdown"], -1.0)
                self.assertEqual(result["taxes"], 0.0)
                self.assertEqual(result["rebalances"], 0)

    def test_p05_uses_only_the_latest_common_run_after_a_missing_month(self):
        points = {role: [] for role in P05.inputs}
        points["equity"] = monthly((2020, 1), [100, 110, 999, 121, 133.1], skip=(2020, 3))
        points["usd_per_eur"] = monthly((2020, 1), [1, 1, 1, 1, 1])
        owner = {**EXAMPLE, "allocation": {"equity": 1, "bonds": 0, "gold": 0},
                 "start_value_eur": 100, "trading_cost_bps": 0}
        values = P05.compute(points, {"today": "2020-06-01"}, {"owner_inputs": owner}).values
        self.assertEqual(values["period"], {"from": "2020-05", "to": "2020-05", "months": 1})
        for rule in values["rules"]:
            self.assertEqual([month for month, _ in rule["path"]], ["2020-05"])
            self.assertAlmostEqual(rule["final"], 110.0)

    def test_p05_translates_native_usd_level_and_ratio_returns_into_euros(self):
        # Equity USD 100 -> 120, FX USD/EUR 2 -> 3 gives -20% in EUR.
        # A native 0.05 bond return means +5%, giving -30% in EUR.
        # The 60/40 portfolio therefore becomes 48 + 28 = 76.
        points = {role: [] for role in P05.inputs}
        points["equity"] = monthly((2020, 1), [100, 120])
        points["bonds"] = monthly((2020, 1), [0, 0.05])
        points["usd_per_eur"] = monthly((2020, 1), [2, 3])
        owner = {**EXAMPLE, "allocation": {"equity": 0.6, "bonds": 0.4, "gold": 0},
                 "bonds_hedged": False, "start_value_eur": 100, "trading_cost_bps": 0}
        values = P05.compute(points, {"today": "2020-03-01"}, {"owner_inputs": owner}).values
        self.assertEqual(values["bond_leg"], "us_in_eur")
        self.assertEqual(values["period"]["months"], 1)
        for rule in values["rules"]:
            self.assertAlmostEqual(rule["final"], 76.0)

    def test_p04_first_order_sensitivities_of_the_owners_mix(self):
        self.assertIs(DEFINITIONS["P04"], P04)
        owner = {**EXAMPLE, "allocation": {"equity": 0.6, "bonds": 0.3, "gold": 0.1}, "bond_duration_years": 7,
                 "equity_hedged_share": 0.0, "equity_euro_share": 0.1, "bonds_hedged": True}
        values = P04.compute({role: [] for role in P04.inputs}, {}, {"owner_inputs": owner}).values
        shocks = {s["key"]: s for s in values["shocks"]}
        self.assertAlmostEqual(shocks["rates_up"]["impact_pct"], -0.3 * 7 * 1)
        self.assertAlmostEqual(shocks["dollar_down"]["impact_pct"], -(0.6 * 0.9 * 10 + 0.1 * 10))
        self.assertAlmostEqual(shocks["equities_down"]["impact_pct"], -12.0)
        self.assertTrue(values["is_example"] is False or values["is_example"] is True)

    def test_simulation_rebalances_by_rule_charges_costs_and_withdraws(self):
        months = [(2020, m) for m in range(1, 13)]
        returns = {"equity": {k: 0.05 for k in months}, "bonds": {k: 0.0 for k in months}, "gold": {k: 0.0 for k in months}}
        weights = {"equity": 0.5, "bonds": 0.5, "gold": 0.0}
        never = simulate(returns, months, weights, rule="never", months_between=12, band_pp=5, cost_bps=0,
                         start=100.0, monthly_contribution=0.0, annual_withdrawal_pct=0.0)
        self.assertEqual(never["rebalances"], 0)
        self.assertAlmostEqual(never["final"], 50 * 1.05 ** 12 + 50)
        band = simulate(returns, months, weights, rule="threshold", months_between=12, band_pp=5, cost_bps=100,
                        start=100.0, monthly_contribution=0.0, annual_withdrawal_pct=0.0)
        self.assertGreater(band["rebalances"], 0)
        self.assertGreater(band["costs"], 0)
        withdraw = simulate(returns, months, weights, rule="never", months_between=12, band_pp=5, cost_bps=0,
                            start=100.0, monthly_contribution=0.0, annual_withdrawal_pct=0.12)
        self.assertLess(withdraw["final"], never["final"])
        self.assertEqual(len(withdraw["path"]), 12)

    def test_tax_on_realised_gains_is_charged_only_when_gains_are_sold(self):
        months = [(2020, m) for m in range(1, 13)]
        returns = {"equity": {k: 0.05 for k in months}, "bonds": {k: 0.0 for k in months}, "gold": {k: 0.0 for k in months}}
        weights = {"equity": 0.5, "bonds": 0.5, "gold": 0.0}
        common = dict(months_between=12, band_pp=5, cost_bps=0, start=100.0, monthly_contribution=0.0, annual_withdrawal_pct=0.0)
        untaxed = simulate(returns, months, weights, rule="threshold", **common)
        taxed = simulate(returns, months, weights, rule="threshold", tax_mode="realised_gains", tax_rate=0.25, **common)
        self.assertGreater(taxed["taxes"], 0)
        self.assertLess(taxed["final"], untaxed["final"])
        held = simulate(returns, months, weights, rule="never", tax_mode="realised_gains", tax_rate=0.25, **common)
        self.assertEqual(held["taxes"], 0)

    def test_yearly_tax_on_value_is_charged_every_twelve_months(self):
        months = [(2020, m) for m in range(1, 13)] + [(2021, m) for m in range(1, 13)]
        returns = {a: {k: 0.0 for k in months} for a in ("equity", "bonds", "gold")}
        result = simulate(returns, months, {"equity": 1.0, "bonds": 0.0, "gold": 0.0}, rule="never", months_between=12,
                          band_pp=5, cost_bps=0, start=100.0, monthly_contribution=0.0, annual_withdrawal_pct=0.0,
                          tax_mode="yearly_on_value", tax_rate=0.02)
        self.assertAlmostEqual(result["taxes"], 2 + 1.96)
        self.assertAlmostEqual(result["final"], 100 * 0.98 * 0.98)

    def test_p05_compares_three_rules_on_euro_returns(self):
        self.assertIs(DEFINITIONS["P05"], P05)
        n = 30
        points = {role: [] for role in P05.inputs}
        points["equity"] = monthly((2010, 1), [100 * (1.01 ** i) for i in range(n)])
        points["gold"] = monthly((2010, 1), [1000.0 + i for i in range(n)])
        points["bonds"] = monthly((2010, 1), [0.002] * n)
        points["usd_per_eur"] = monthly((2010, 1), [1.2] * n)
        points["bund_yield"] = monthly((2010, 1), [3.0] * n)
        values = P05.compute(points, {"today": "2026-11-09"}, {"owner_inputs": EXAMPLE}).values
        self.assertEqual([r["key"] for r in values["rules"]], ["never", "calendar", "threshold"])
        self.assertEqual(values["period"]["months"], n - 1)
        self.assertTrue(values["is_example"])


if __name__ == "__main__":
    unittest.main()


class EuroBondTests(unittest.TestCase):
    def test_par_bond_return_reproduces_swinkels_published_values(self):
        from finance_dashboard.engine.transforms import par_bond_returns
        out = par_bond_returns({(1972, 9): 7.92, (1972, 10): 8.29, (1972, 11): 8.48, (1973, 1): 8.7})
        self.assertAlmostEqual(out[(1972, 10)], -1.8087803085468472e-2, places=15)
        self.assertAlmostEqual(out[(1972, 11)], -5.6645672829775569e-3, places=15)
        self.assertNotIn((1973, 1), out)        # a missing month breaks the chain; nothing is bridged

    def test_p05_uses_euro_bonds_for_a_euro_or_hedged_bond_holding(self):
        n = 30
        points = {role: [] for role in P05.inputs}
        points["equity"] = monthly((2010, 1), [100 * (1.01 ** i) for i in range(n)])
        points["gold"] = monthly((2010, 1), [1000.0 + i for i in range(n)])
        points["bonds"] = monthly((2010, 1), [0.002] * 12)              # the US series ends early
        points["usd_per_eur"] = monthly((2010, 1), [1.2] * n)
        points["bund_yield"] = monthly((2010, 1), [3.0] * n)
        euro = P05.compute(points, {"today": "2026-11-09"}, {"owner_inputs": {**EXAMPLE, "bonds_hedged": True}}).values
        self.assertEqual(euro["bond_leg"], "euro")
        self.assertEqual(euro["period"]["months"], n - 1)
        usd = P05.compute(points, {"today": "2026-11-09"}, {"owner_inputs": {**EXAMPLE, "bonds_hedged": False}}).values
        self.assertEqual(usd["bond_leg"], "us_in_eur")
        self.assertEqual(usd["period"]["months"], 11)
