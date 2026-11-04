"""Contract tests for global imbalances, observed US activity and the wealth groups."""
from datetime import date
from decimal import Decimal
import unittest
from unittest.mock import patch

import httpx

from finance_dashboard.providers import ProviderRouter
from finance_dashboard.catalog import load_documents, validate


class Phase2OriginalSourceDefinitions(unittest.TestCase):
    def test_source_catalog_remains_coherent(self):
        series,charts=load_documents()
        self.assertEqual(validate(series,charts),[])
        self.assertEqual(len(series["series"]),85)
        ids={x["id"] for x in series["series"]}
        for required in ("wealth.us.top1_share","wealth.us.bottom50_share",
                         "external.us.current_account_gdp","activity.us.real_gdp_level",
                         "recession.us.nber_indicator"):
            self.assertIn(required,ids)

    def test_exact_four_group_dfa_wealth_share_sources(self):
        expected={
            "wealth.us.top1_share":"WFRBST01134",
            "wealth.us.next9_share":"WFRBSN09161",
            "wealth.us.middle40_share":"WFRBSN40188",
            "wealth.us.bottom50_share":"WFRBSB50215",
        }
        series,_=load_documents()
        by_id={x["id"]:x for x in series["series"]}
        for ident,fred in expected.items():
            self.assertEqual(by_id[ident]["source_key"],fred)
            self.assertEqual(by_id[ident]["frequency"],"Q")
            self.assertEqual(by_id[ident]["unit"],"percent")

    def test_fred_quarterly_group_retrieval_keeps_separate_originals(self):
        allowed={"WFRBST01134","WFRBSN09161","WFRBSN40188","WFRBSB50215"}
        def handler(req):
            self.assertIn(req.url.params["series_id"],allowed)
            return httpx.Response(200,json={"observations":[
                {"date":"2025-10-01","value":"25.2"}]})
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            router=ProviderRouter(client=client)
            try:
                with patch.dict("os.environ",{"FRED_API_KEY":"a"*32}):
                    for ident in ("wealth.us.top1_share","wealth.us.next9_share",
                                  "wealth.us.middle40_share","wealth.us.bottom50_share"):
                        self.assertEqual(router.fetch(ident).observations,
                                         {date(2025,10,1):Decimal("25.2")})
            finally:
                router.close()

    def test_imf_account_balances_are_not_current_year_forecasts(self):
        def handler(req):
            self.assertIn("BCA_NGDPD",str(req.url))
            return httpx.Response(200,json={"values":{"BCA_NGDPD":{"USA":{
                "2024":-3.2,"2025":-3.9,"2026":-4.0}}}})
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            router=ProviderRouter(client=client)
            try:
                with patch("finance_dashboard.providers.date") as when:
                    when.today.return_value=date(2026,11,4)
                    when.side_effect=lambda *args:date(*args)
                    result=router.fetch("external.us.current_account_gdp").observations
                self.assertEqual(result,{date(2024,1,1):Decimal("-3.2"),
                                         date(2025,1,1):Decimal("-3.9")})
                self.assertNotIn(date(2026,1,1),result)
            finally:
                router.close()


if __name__=="__main__":
    unittest.main()
