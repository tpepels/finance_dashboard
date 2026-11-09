"""P06 and F03 on the engine: identical numbers to the decision endpoints they replace."""
from datetime import date
import json
from pathlib import Path
import unittest

from sqlalchemy.orm import Session

from engine_fixtures import memory_engine, monthly, seed
from finance_dashboard.engine.analyses import DEFINITIONS, F03, P06, f03_credit, p06_expected_returns
from finance_dashboard.engine.runner import load_points


GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "engine_golden.json").read_text())


def series(values, start=(2020, 1)):
    return {(d.year, d.month): (d, v) for d, v in monthly(start, values)}


def p06_fixture():
    months = 12 * 12
    return {
        "valuation.us.cape": monthly((2010, 1), [20 + 0.05 * i for i in range(months)]),
        "returns.us.shiller_real_total_return": monthly((2010, 1), [1.004 ** i * (1 + 0.01 * (i % 7))
                                                                    for i in range(months)]),
        "valuation.world.global_earnings_yield": [(date(2026, 3, 31), 5.1), (date(2026, 9, 30), 4.8)],
        "bond.us.nominal_10y": monthly((2026, 1), [4.1, 4.2, 4.0]),
        "bond.us.real_10y": monthly((2026, 1), [1.8, 1.9, 1.7]),
        "bond.ea.aaa_10y_spot": monthly((2026, 1), [2.6, 2.7, 2.5]),
        "prices.ea.hicp_index_2025": monthly((2024, 10), [98 + 0.2 * i for i in range(14)]),
    }


def f03_fixture():
    quarterly = [(date(2000 + i // 4, 1 + 3 * (i % 4), 1), -4 + 0.3 * i) for i in range(40)]
    return {**{sid: quarterly for sid in F03.inputs.values() if sid.startswith("credit_gap")},
            **{sid: [(day, 12 + v / 10) for day, v in quarterly] for sid in F03.inputs.values()
               if sid.startswith("debt_service")}}


class P06F03EngineTests(unittest.TestCase):
    def test_equity_range_from_realised_minus_starting_earnings_yield(self):
        months = 12 * 10 + 1
        result = p06_expected_returns(series([20.0] * months), series([1.06 ** (i / 12) for i in range(months)]),
                                      {}, {"us_nominal_10y": (date(2026, 1, 1), 4.0),
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
        rows = {r["area"]: r for r in f03_credit(gaps, dsr)["rows"]}
        self.assertEqual(rows["US"]["gap_guide_band"], "above_10pp")
        self.assertEqual(rows["PT"]["gap_guide_band"], "between_2_and_10pp")
        self.assertEqual(rows["US"]["private_dsr"]["own_percentile"], 0.0)
        self.assertAlmostEqual(rows["US"]["private_dsr"]["deviation_from_own_mean"], -1.0)
        self.assertIsNone(rows["PT"]["private_dsr"])

    def test_definitions_declare_todays_inputs(self):
        self.assertIs(DEFINITIONS["P06"], P06)
        self.assertIs(DEFINITIONS["F03"], F03)
        self.assertEqual(P06.inputs["us_real_total_return"], "returns.us.shiller_real_total_return")
        self.assertEqual(sorted(k for k in F03.inputs if k.startswith("credit_gap:")),
                         ["credit_gap:CN", "credit_gap:DE", "credit_gap:EA", "credit_gap:JP", "credit_gap:PT",
                          "credit_gap:US"])
        self.assertEqual(sorted(k for k in F03.inputs if k.startswith("private_dsr:")),
                         ["private_dsr:CN", "private_dsr:DE", "private_dsr:JP", "private_dsr:PT", "private_dsr:US"])

    def test_every_derived_value_has_a_named_transform(self):
        # A reader must be able to recompute each derived value from the inputs and this list.
        p06 = {t["name"] for t in P06.compute({role: [] for role in P06.inputs}, {}).transforms}
        self.assertTrue({"month_end", "percent_to_fraction", "earnings_yield", "valuation_residual_range",
                         "year_on_year_change", "yield_difference", "real_deflation"} <= p06)
        f03 = {t["name"] for t in F03.compute({role: [] for role in F03.inputs}, {}).transforms}
        self.assertEqual(f03, {"own_history", "threshold_band"})
        self.assertIn("calibration_points", p06)

    def test_calibration_points_pair_starting_yield_with_realised_return(self):
        months = 12 * 10 + 1
        cape = series([20.0] * months)
        real_tr = series([1.06 ** (i / 12) for i in range(months)])
        from finance_dashboard.engine.analyses import calibration_points
        points = calibration_points(cape, real_tr, 10)
        self.assertEqual(len(points), 1)
        start, earnings_yield, realised = points[0]
        self.assertEqual(start, "2020-01")
        self.assertAlmostEqual(earnings_yield, 0.05)
        self.assertAlmostEqual(realised, 0.06, places=6)

    def test_p06_identical_numbers_to_the_decision_endpoint(self):
        # Golden values captured from the retired /api/decision/P06 on this fixture.
        old = GOLDEN["P06"]
        engine = memory_engine()
        seed(engine, p06_fixture())
        with Session(engine) as session:
            new = P06.compute(load_points(session, P06), {})
        values = dict(new.values)
        history = values.pop("history")
        self.assertEqual(json.loads(json.dumps({"analysis_id": "P06", **values, **new.estimates})), old)
        self.assertEqual(len(history["calibration"]), old["equity_us"]["calibration_windows"])
        self.assertEqual(history["cape"][-1][1], old["equity_us"]["cape"])
        self.assertGreater(old["equity_us"]["calibration_windows"], 12)
        self.assertIn("ea_aaa_10y_real_trailing", old["bonds"])

    def test_f03_identical_numbers_to_the_decision_endpoint(self):
        # Golden values captured from the retired /api/decision/F03 on this fixture.
        old = GOLDEN["F03"]
        engine = memory_engine()
        seed(engine, f03_fixture())
        with Session(engine) as session:
            new = F03.compute(load_points(session, F03), {})
        values = dict(new.values)
        history = values.pop("history")
        self.assertEqual(json.loads(json.dumps({"analysis_id": "F03", **values})), old)
        us = history["US"]
        self.assertEqual(len(us["credit_gap"]), 40)
        self.assertEqual(us["credit_gap_range"]["min"], min(v for _, v in us["credit_gap"]))
        self.assertEqual(us["private_dsr_range"]["max"], max(v for _, v in us["private_dsr"]))
        self.assertIsNone(new.estimates)
        self.assertEqual(len(old["rows"]), 6)


if __name__ == "__main__":
    unittest.main()
