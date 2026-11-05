"""Source-identity and parser tests for new Phase 2 monetary/commodity/BEA inputs."""
from datetime import date
from decimal import Decimal
import unittest
from unittest.mock import patch

import httpx
from finance_dashboard.providers import ProviderRouter
from finance_dashboard.bis import ProviderError
from finance_dashboard.provider_parsers import parse_pink_sheet_brent
from finance_dashboard.remaining_sources import parse_bea_q_table, DerivedDataError


class ExtendedPhase2SourcesTests(unittest.TestCase):
    def test_pink_sheet_brent_exact_column_and_units(self):
        rows=[["metadata"],["metadata"],["metadata"],[""],
              ["","Gold","Crude oil, Brent","Copper"],
              ["","($/troy oz)","($/bbl)","($/mt)"],
              ["2024M01",2020,83.2,100],["2024M02",2021,None,100],
              ["2024M03",2022,82.4,110]]
        r=parse_pink_sheet_brent(rows)
        self.assertEqual(r[date(2024,1,1)],Decimal("83.2"))
        self.assertNotIn(date(2024,2,1),r)
        self.assertEqual(len(r),2)
        with self.assertRaisesRegex(ProviderError,"per barrel"):
            parse_pink_sheet_brent([*rows[:5],["","($/troy oz)","($/mt)","($/mt)"],*rows[6:]])
        with self.assertRaisesRegex(ProviderError,"missing or ambiguous"):
            parse_pink_sheet_brent([*rows[:4],["","Gold","WTI","Copper"],*rows[5:]])

    def test_bea_q2_q3_preserves_different_original_columns(self):
        rows="".join(f"<tr><td>{year}</td><td>1.1</td><td>1.3</td><td>1.6</td></tr>" for year in range(1960,2025))
        html="<h1>Q-Type Ratios</h1><p>produced assets</p><table><tr><th></th><th>Q1</th><th>Q2</th><th>Q3</th></tr>"+rows+"</table>"
        self.assertEqual(parse_bea_q_table(html,"Q1")[date(1960,1,1)],Decimal("1.1"))
        self.assertEqual(parse_bea_q_table(html,"Q2")[date(1960,1,1)],Decimal("1.3"))
        self.assertEqual(parse_bea_q_table(html,"Q3")[date(1960,1,1)],Decimal("1.6"))
        with self.assertRaisesRegex(DerivedDataError,"Unknown"):
            parse_bea_q_table(html,"Q4")

    def test_fred_new_rates_keep_original_source_ids(self):
        def handler(req):
            ident=req.url.params["series_id"]
            self.assertIn(ident,{"DGS10","T10YIE","BAMLH0A0HYM2","VIXCLS"})
            return httpx.Response(200,json={"observations":[
                {"date":"2026-10-01","value":"4.3"}]})
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            router=ProviderRouter(client=client)
            try:
                with patch.dict("os.environ",{"FRED_API_KEY":"a"*32}):
                    for ident in ("bond.us.nominal_10y","bond.us.breakeven_10y",
                                  "stress.us.high_yield_oas","stress.us.vix"):
                        self.assertEqual(router.fetch(ident).observations[date(2026,10,1)],Decimal("4.3"))
            finally:
                router.close()

    def test_imf_prices_only_histories_not_projected_current_year(self):
        def handler(req):
            self.assertIn("PCPIPCH",str(req.url))
            return httpx.Response(200,json={"values":{"PCPIPCH":{"USA":{
                "2024":"3.1","2025":"2.7","2026":"2.0","2027":"2.1"}}}})
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            router=ProviderRouter(client=client)
            try:
                with patch("finance_dashboard.provider_adapters.date") as fake_date:
                    fake_date.today.return_value=date(2026,11,4)
                    fake_date.side_effect=lambda *v:date(*v)
                    observed=router.fetch("prices.us.imf_cpi_inflation").observations
                    self.assertEqual(observed,{date(2024,1,1):Decimal("3.1"),
                                               date(2025,1,1):Decimal("2.7")})
            finally:
                router.close()


if __name__=="__main__":
    unittest.main()
