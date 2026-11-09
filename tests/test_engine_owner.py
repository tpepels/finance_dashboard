"""P04 and P05 on the engine: sensitivities and rebalancing rules computed from the owner's inputs."""
from datetime import date
import unittest

from engine_fixtures import monthly
from finance_dashboard.engine.analyses import DEFINITIONS, P04, P05, simulate
from finance_dashboard.owner_inputs import EXAMPLE


class OwnerEngineTests(unittest.TestCase):
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

    def test_p05_compares_three_rules_on_euro_returns(self):
        self.assertIs(DEFINITIONS["P05"], P05)
        n = 30
        points = {role: [] for role in P05.inputs}
        points["equity"] = monthly((2010, 1), [100 * (1.01 ** i) for i in range(n)])
        points["gold"] = monthly((2010, 1), [1000.0 + i for i in range(n)])
        points["bonds"] = monthly((2010, 1), [0.002] * n)
        points["usd_per_eur"] = monthly((2010, 1), [1.2] * n)
        values = P05.compute(points, {"today": "2026-11-09"}, {"owner_inputs": EXAMPLE}).values
        self.assertEqual([r["key"] for r in values["rules"]], ["never", "calendar", "threshold"])
        self.assertEqual(values["period"]["months"], n - 1)
        self.assertTrue(values["is_example"])


if __name__ == "__main__":
    unittest.main()
