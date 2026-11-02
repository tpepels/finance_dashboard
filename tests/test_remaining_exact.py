"""Exact-source derived indicators: BEA Q1, MSCI NETR and gold correlation."""
from datetime import date
from decimal import Decimal
import unittest

from finance_dashboard.remaining_sources import (
    DerivedDataError, parse_bea_q1, parse_msci_acwi, gold_acwi_rolling_correlation,
    global_output_to_labour_income_ratio,
)
from finance_dashboard.providers import ProviderRouter
from unittest.mock import patch
import httpx


class RemainingExactSourceTests(unittest.TestCase):
    def test_bea_q1_not_q2_or_q3(self):
        text = """<html><h1>Q-Type Ratios</h1><p>produced assets</p>
          <table><tr><th></th><th>Q11</th><th>Q22</th><th>Q33</th></tr>
          <tr><td>1960</td><td>0.79</td><td>0.95</td><td>1.35</td></tr>
          <tr><td>1961</td><td>0.86</td><td>1.01</td><td>1.50</td></tr>
          </table></html>"""
        result=parse_bea_q1(text,start=date(1960,1,1))
        self.assertEqual(result[date(1960,1,1)],Decimal("0.79"))
        self.assertEqual(result[date(1961,1,1)],Decimal("0.86"))
        with self.assertRaisesRegex(DerivedDataError,"ambiguous"):
            parse_bea_q1(text.replace("</html>","")+text)
        with self.assertRaisesRegex(DerivedDataError,"does not identify"):
            parse_bea_q1(text.replace("produced assets","market worth"))

    def test_msci_only_true_acwi_netr_usd(self):
        payload={"msci_index_code":"892400","index_variant_type":"NETR",
                 "ISO_currency_symbol":"USD","indexes":{"INDEX_LEVELS":[
                     {"calc_date":20260203,"level_eod":600.25},
                     {"calc_date":20260204,"level_eod":603.4}]}}
        self.assertEqual(parse_msci_acwi(payload)[date(2026,2,4)],Decimal("603.4"))
        with self.assertRaisesRegex(DerivedDataError,"identity"):
            parse_msci_acwi({**payload,"msci_index_code":"990100"})
        with self.assertRaisesRegex(DerivedDataError,"method or currency"):
            parse_msci_acwi({**payload,"index_variant_type":"STRD"})
        with self.assertRaisesRegex(DerivedDataError,"method or currency"):
            parse_msci_acwi({**payload,"ISO_currency_symbol":"EUR"})

    def test_matched_monthly_returns_and_gaps(self):
        gold={}
        acwi={}
        for i in range(56):
            yr=2020+i//12
            mo=i%12+1
            day=date(yr,mo,1)
            # Vary returns so both standard deviations are nonzero.
            level=Decimal(100+i*5+(i%7)*2)
            gold[day]=level
            acwi[date(yr,mo,6)]=level*Decimal("2")
            acwi[date(yr,mo,16)]=level*Decimal("2")
        results=gold_acwi_rolling_correlation(gold,acwi,window=36)
        self.assertTrue(results)
        for v in results.values():
            self.assertAlmostEqual(float(v),1.0,places=7)
        # Missing one monthly gold observation must not be linearly filled.
        gold.pop(date(2021,5,1))
        incomplete=gold_acwi_rolling_correlation(gold,acwi,window=36)
        self.assertLess(len(incomplete),len(results))

    def test_world_labour_hourly_productivity_pay_identity(self):
        share={date(2022,1,1):Decimal("50"),
               date(2023,1,1):Decimal("55")}
        ratio=global_output_to_labour_income_ratio(share)
        self.assertEqual(ratio[date(2022,1,1)],Decimal("2"))
        self.assertEqual(ratio[date(2023,1,1)],Decimal(100)/Decimal(55))
        self.assertLess(ratio[date(2023,1,1)],ratio[date(2022,1,1)])
        with self.assertRaisesRegex(DerivedDataError,"Invalid global"):
            global_output_to_labour_income_ratio({date(2023,1,1):Decimal(0)})

    def test_production_parser_mock_transport(self):
        def handler(req):
            if "0526-domestic-returns.htm" in str(req.url):
                rows="".join(f"<tr><td>{yr}</td><td>1.20</td><td>1.40</td><td>1.60</td></tr>"
                             for yr in range(1960,2025))
                return httpx.Response(200,text="<h1>Q-Type Ratios</h1><p>produced assets</p><table><tr><th></th><th>Q1</th><th>Q2</th><th>Q3</th></tr>"+rows+"</table>")
            if "getLevelDataForGraph" in str(req.url):
                self.assertEqual(req.url.params["index_codes"],"892400")
                self.assertEqual(req.url.params["index_variant"],"NETR")
                return httpx.Response(200,json={
                    "msci_index_code":"892400","index_variant_type":"NETR",
                    "ISO_currency_symbol":"USD",
                    "indexes":{"INDEX_LEVELS":[{"calc_date":20250102,"level_eod":560.6}]}})
            self.fail("Unexpected provider URL")
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            provider=ProviderRouter(client=client)
            try:
                self.assertEqual(provider.fetch("valuation.us.tobins_q").observations[date(1960,1,1)],Decimal("1.20"))
                self.assertEqual(provider.fetch("equity.world.msci_acwi_netr_usd").observations[date(2025,1,2)],Decimal("560.6"))
            finally:
                provider.close()


if __name__=="__main__":
    unittest.main()
