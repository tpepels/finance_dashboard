"""Economic acceptance tests for distributional wages and CPI/asset relationships.

Tests use source-shaped dates, not synthetic series promoted into research
catalogues. Production outputs must remain source-gated and labelled.
"""
from datetime import date
from math import sin
import unittest

from finance_dashboard.distribution_research import wage_distribution
from finance_dashboard.inflation_research import _analysis, inflation_assets


class WageInflationIntegrityTests(unittest.TestCase):
    def test_real_federal_minimum_wage_is_hourly_and_never_compared_to_weekly_median(self):
        cpi=[(date(2024,month,1),100.) for month in range(1,13)]
        cpi.extend((date(2025,month,1),125.) for month in range(1,13))
        data=wage_distribution({
            "p10":[(date(2024,1,1),400),(date(2025,1,1),500)],
            "p50":[(date(2024,1,1),1000),(date(2025,1,1),1100)],
            "p90":[(date(2024,1,1),1900),(date(2025,1,1),2300)],
            "us_federal_min":[(date(2024,1,1),7.25),(date(2025,1,1),7.25)],
            "us_cpi":cpi,
        })
        minimum=dict(data["us"]["real_federal_minimum_hourly_1982_84_usd"])
        self.assertAlmostEqual(minimum["2024-01-01"],7.25)
        self.assertAlmostEqual(minimum["2025-01-01"],5.8)
        self.assertTrue(data["us"]["federal_minimum_to_weekly_median_computable"] is False)

    def test_unhedged_eur_bond_return_uses_month_end_fx_and_complete_12_months(self):
        dates=[date(2023+i//12,1+i%12,1) for i in range(30)]
        points={
            "us_cpi":[(d,100.*(1.002**i)) for i,d in enumerate(dates)],
            "ea_hicp":[(d,100.*(1.002**i)) for i,d in enumerate(dates)],
            "us_bond_returns":[(d,.01) for d in dates],
            "usd_per_eur":[(date(d.year,d.month,27),1.2) for d in dates],
        }
        out=inflation_assets(points,today=date(2026,1,1))
        usd=out["assets"]["us_treasury_hypothetical_total_return_usd"]
        eur=out["assets"]["us_treasury_hypothetical_total_return_eur"]
        self.assertEqual(usd["quote_currency"],"USD")
        self.assertEqual(eur["quote_currency"],"EUR")
        self.assertEqual(eur["measurement"],"compounded_yield_modelled_monthly_simple_return")
        matched=set(tuple(x) for x in usd["nominal_yoy"]) & set(tuple(x) for x in eur["nominal_yoy"])
        self.assertTrue(matched)

    def test_quarterly_housing_uses_actual_country_inflation_not_euro_average(self):
        dates=[date(2019+i//12,1+i%12,1) for i in range(72)]
        quarters=[date(2019+i//4,1+3*(i%4),1) for i in range(24)]
        national=[(d,100*(1.004**i)) for i,d in enumerate(dates)]
        points={
            "de_hicp":national,
            "pt_hicp":national,
            "ea_hicp":[(d,100*(1.002**i)) for i,d in enumerate(dates)],
            "housing:de":[(d,100*(1.012**i)) for i,d in enumerate(quarters)],
            "housing:pt":[(d,100*(1.012**i)) for i,d in enumerate(quarters)],
        }
        out=inflation_assets(points,today=date(2026,1,1))
        for country in ("de","pt"):
            self.assertTrue(out["housing"][country]["consumer_inflation_matched"])
            self.assertTrue(out["housing"][country]["real_yoy"])
            self.assertIsNone(out["housing"][country]["excluded_reason"])
        self.assertNotEqual(
            out["housing"]["de"]["real_yoy"][0][1],
            out["housing"]["ea"]["real_yoy"][0][1] if out["housing"]["ea"]["real_yoy"] else None)

    def test_serial_dependence_bootstrap_is_deterministic_and_withheld_for_small_n(self):
        from finance_dashboard.inflation_research import _block_bootstrap_ci
        values=[(sin(t/7.)+t/100., sin(t/7.+.3)+t/100.) for t in range(144)]
        first=_block_bootstrap_ci(values,12)
        self.assertEqual(first,_block_bootstrap_ci(values,12))
        self.assertIsNotNone(first)
        self.assertTrue(-1<=first[0]<=first[1]<=1)
        self.assertIsNone(_block_bootstrap_ci(values[:23],12))
        result=_analysis({t:a for t,(a,b) in enumerate(values)},
                         {t:b for t,(a,b) in enumerate(values)})
        self.assertEqual(result["block_bootstrap_95pct_ci"],first)
        self.assertEqual(result["confidence_method"],"circular_moving_block_bootstrap")

    def test_inflation_shock_regime_is_separate_from_recovery_period(self):
        a={year*12+month:float(year-2000)+month/100
           for year in range(2015,2027) for month in range(12)}
        b={t:v*1.1+(t%7) for t,v in a.items()}
        result=_analysis(a,b)
        regimes={(r["start"],r["end"]):r for r in result["regimes"]}
        self.assertIn((2021,2023),regimes)
        self.assertIn((2024,9999),regimes)
        self.assertEqual(regimes[(2021,2023)]["n"],36)


if __name__ == "__main__":
    unittest.main()
