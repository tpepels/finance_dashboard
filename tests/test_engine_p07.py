"""P07 on the engine: identical numbers to the decision endpoint it replaces."""
from datetime import date
import json
from pathlib import Path
import unittest

from sqlalchemy.orm import Session

from engine_fixtures import memory_engine, monthly, seed
from finance_dashboard.engine.analyses import DEFINITIONS, P07, p07_hedging
from finance_dashboard.engine.runner import load_points


GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "engine_golden.json").read_text())


def series(values, start=(2020, 1)):
    return {(d.year, d.month): (d, v) for d, v in monthly(start, values)}


TODAY = date(2026, 11, 6)


def p07_fixture():
    return {
        "fx.usd_per_eur.ecb": monthly((2024, 11), [1.05 + 0.01 * i for i in range(25)]),
        "equity.world.msci_acwi_netr_usd": monthly((2024, 11), [100 * 1.01 ** i for i in range(25)],
                                                   skip=(2025, 3)),
        "policy_rate.ea.ecb_dfr": monthly((2024, 11), [3.0 - 0.05 * i for i in range(25)]),
        "policy_rate.us.fed_effective": monthly((2024, 11), [4.5 - 0.03 * i for i in range(25)]),
        "prices.ea.hicp_index_2025": monthly((2024, 11), [100 + 0.2 * i for i in range(23)]),
    }


class P07EngineTests(unittest.TestCase):
    def test_unhedged_and_hedged_eur_returns(self):
        result = p07_hedging(series([1.0, 1.1]), series([100.0, 110.0]), series([2.0, 2.0]),
                             series([5.0, 5.0]), series([100.0, 101.0]))
        row = result["rows"][0]
        self.assertAlmostEqual(row["eur_unhedged"], 1.10 / 1.10 - 1)
        self.assertAlmostEqual(row["hedge_carry"], -3.0 / 1200)
        self.assertAlmostEqual(row["eur_hedged"], 1.10 * (1 - 3.0 / 1200) - 1)
        self.assertAlmostEqual(row["eur_inflation"], 0.01)
        self.assertEqual(result["nominal"]["eur_hedged"]["months"], 1)

    def test_missing_month_breaks_the_cumulative_run(self):
        equity = series([100, 101, 102, 103])
        del equity[(2020, 2)]
        rates = series([0.0] * 4)
        result = p07_hedging(series([1.0] * 4), equity, rates, rates, {})
        self.assertEqual([r["month"] for r in result["rows"]], ["2020-04"])
        self.assertIsNone(result["real_period"])

    def test_definition_declares_todays_inputs(self):
        self.assertIs(DEFINITIONS["P07"], P07)
        self.assertEqual(P07.inputs, {"usd_per_eur": "fx.usd_per_eur.ecb",
                                      "equity_netr_usd": "equity.world.msci_acwi_netr_usd",
                                      "eur_short_rate": "policy_rate.ea.ecb_dfr",
                                      "usd_short_rate": "policy_rate.us.fed_effective",
                                      "ea_hicp": "prices.ea.hicp_index_2025"})

    def test_incomplete_current_month_is_excluded(self):
        engine = memory_engine()
        data = p07_fixture()
        data["equity.world.msci_acwi_netr_usd"].append((date(2026, 11, 5), 999.0))
        seed(engine, data)
        with Session(engine) as session:
            values = P07.compute(load_points(session, P07), {"today": TODAY}).values
        self.assertNotIn("2026-11", [row["month"] for row in values["rows"]])

    def test_wealth_from_100_matches_the_panel_it_replaces(self):
        rows = [{"month": "2026-01", "eur_unhedged": 0.1, "eur_hedged": 0.0, "eur_inflation": 0.1},
                {"month": "2026-02", "eur_unhedged": 0.1, "eur_hedged": 0.0, "eur_inflation": None}]
        from finance_dashboard.engine.analyses import p07_wealth
        wealth = p07_wealth(rows)
        self.assertEqual(wealth["real"]["eur_unhedged"], [["2026-01", 100.0]])
        self.assertAlmostEqual(wealth["nominal"]["eur_unhedged"][1][1], 121.0)

    def test_identical_numbers_to_the_decision_endpoint(self):
        # Golden values captured from the retired /api/decision/P07 on this fixture.
        old = GOLDEN["P07"]
        engine = memory_engine()
        seed(engine, p07_fixture())
        with Session(engine) as session:
            new = P07.compute(load_points(session, P07), {"today": TODAY})
        values = json.loads(json.dumps(new.values))
        values.pop("wealth")
        self.assertEqual({"analysis_id": "P07", **values}, old)
        self.assertGreater(len(old["rows"]), 12)


if __name__ == "__main__":
    unittest.main()
