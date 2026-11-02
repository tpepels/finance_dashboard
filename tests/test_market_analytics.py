"""Real investment proxy correlation: monthly returns, no levels or interpolation."""
import unittest
from datetime import date
from decimal import Decimal as D

from finance_dashboard.market_analytics import monthly_returns, rolling_gold_vs_global_etf


def fixture(symbol, moves, fx_shift=1):
    px=D(100)
    rows=[]
    for index,move in enumerate(moves):
        yr=2020+(index//12)
        month=1+(index%12)
        px*=D(1)+D(str(move))*D(str(fx_shift))
        rows.append({
            "date":f"{yr:04d}-{month:02d}-25",
            "adjusted_close":str(px),
            "adjusted_close_eur":str(px/D("1.2")),
        })
    return {"symbol":symbol,"observations":rows}


class AnalyticsTests(unittest.TestCase):
    def test_perfect_shared_returns_have_correlation_one(self):
        moves=[((i%7)-3)*0.002+0.003 for i in range(49)]
        gold=fixture("GLD",moves)
        world=fixture("VT",moves)
        result=rolling_gold_vs_global_etf(gold,world,months=36)
        self.assertGreater(len(result["observations"]),10)
        self.assertTrue(all(point["correlation"]==1 for point in result["observations"]))
        self.assertEqual(result["status"],"proxy_not_global_index")

    def test_return_levels_not_correlated_with_prices(self):
        p={"symbol":"GLD","observations":[
            {"date":"2025-01-31","adjusted_close":"100"},
            {"date":"2025-02-28","adjusted_close":"110"},
            {"date":"2025-03-31","adjusted_close":"99"}
        ]}
        returns=monthly_returns(p["observations"],"adjusted_close")
        self.assertAlmostEqual(returns[2025*12+2],0.1)
        self.assertAlmostEqual(returns[2025*12+3],-0.1)

    def test_skips_missing_calendar_months(self):
        moves=[((i%5)-2)*0.002+0.003 for i in range(50)]
        gold=fixture("GLD",moves)
        world=fixture("VT",moves)
        world["observations"]=[row for row in world["observations"]
            if row["date"]!="2022-02-25"]
        result=rolling_gold_vs_global_etf(gold,world,months=36)
        self.assertTrue(all(row["month"] not in ["2022-02","2022-03"]
                            for row in result["observations"]))
        self.assertLess(len(result["observations"]),
                        len(rolling_gold_vs_global_etf(gold,fixture("VT",moves),months=36)["observations"]))

    def test_currency_and_source_contracts_rejected(self):
        g=fixture("GLD",[0.01]*50)
        w=fixture("VT",[0.01]*50)
        with self.assertRaisesRegex(ValueError,"identities"):
            rolling_gold_vs_global_etf(w,g)
        with self.assertRaisesRegex(ValueError,"Only USD and EUR"):
            rolling_gold_vs_global_etf(g,w,currency="GBP")
        with self.assertRaisesRegex(ValueError,"12"):
            rolling_gold_vs_global_etf(g,w,months=3)


if __name__=="__main__":
    unittest.main()
