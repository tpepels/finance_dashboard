"""Offline original-source BIS property price dimensions, units and parser tests."""
from datetime import date
from decimal import Decimal
import unittest

import httpx
from finance_dashboard.bis import ProviderError
from finance_dashboard.bis_property import parse_bis_property, PROPERTY_SOURCES, BIS_SPP_ROOT, BIS_CPP_ROOT
from finance_dashboard.providers import ProviderRouter


def fixture(flow, key):
    names = {
        "SPP": ("FREQ", "REF_AREA", "VALUE", "UNIT_MEASURE"),
        "CPP": ("FREQ", "REF_AREA", "COVERED_AREA", "RE_TYPE",
                "RE_VINTAGE", "COMPILING_ORG", "PRICED_UNIT", "ADJUST_CODED"),
    }[flow]
    periods = ["2024", "2025"] if key.startswith("A.") else ["2024-Q1", "2024-Q2"]
    return {
        "meta": {"prepared": "2026-11-01T05:00:00Z"},
        "data": {"structure": {"dimensions": {
            "series": [{"id": name, "values": [{"id": value}]}
                       for name, value in zip(names, key.split("."))],
            "observation": [{"id": "TIME_PERIOD",
                             "values": [{"id": p} for p in periods]}]
        }}, "dataSets": [{"series": {":".join("0" for _ in names): {
            "observations": {"0": ["101.2"], "1": ["103.8"]}
        }}}]},
    }


class PropertySeriesTests(unittest.TestCase):
    def test_distinct_residential_and_commercial_original_sources(self):
        self.assertEqual(len(PROPERTY_SOURCES), 8)
        obs, _ = parse_bis_property(
            fixture("SPP","Q.DE.R.628"),
            flow="SPP",original_key="Q.DE.R.628")
        self.assertEqual(obs[date(2024,4,1)],Decimal("103.8"))
        annual, _ = parse_bis_property(
            fixture("CPP","A.PT.0.A.0.1.6.0"),
            flow="CPP",original_key="A.PT.0.A.0.1.6.0")
        self.assertEqual(annual[date(2025,1,1)],Decimal("103.8"))

    def test_invalid_sector_or_frequency_rejected(self):
        with self.assertRaisesRegex(ProviderError,"mismatch"):
            parse_bis_property(fixture("SPP","Q.US.R.628"),
                               flow="SPP",original_key="Q.DE.R.628")
        bad=fixture("SPP","Q.US.R.628")
        bad["data"]["structure"]["dimensions"]["series"][2]["id"]="VALUE_BAD"
        with self.assertRaisesRegex(ProviderError,"dimensions"):
            parse_bis_property(bad,flow="SPP",original_key="Q.US.R.628")
        with self.assertRaisesRegex(ProviderError,"Unapproved"):
            parse_bis_property(bad,flow="SPP",original_key="Q.FR.N.628")

    def test_correct_provider_url_and_calendar(self):
        def handler(req):
            self.assertTrue(str(req.url).startswith(BIS_SPP_ROOT))
            self.assertIn("/Q.PT.R.628",str(req.url))
            self.assertEqual(req.url.params["startPeriod"],"2024-Q1")
            return httpx.Response(200,json=fixture("SPP","Q.PT.R.628"))
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            router=ProviderRouter(client=client)
            try:
                result=router.fetch("property.pt.real_residential.bis",
                                   start=date(2024,1,1))
                self.assertEqual(len(result.observations),2)
                self.assertIsNotNone(result.prepared_at)
            finally:
                router.close()

    def test_commercial_source_is_annual_not_quarterly(self):
        def handler(req):
            self.assertTrue(str(req.url).startswith(BIS_CPP_ROOT))
            self.assertIn("/A.PT.0.A.0.1.6.0",str(req.url))
            self.assertEqual(req.url.params["startPeriod"],"2024")
            return httpx.Response(200,json=fixture("CPP","A.PT.0.A.0.1.6.0"))
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            router=ProviderRouter(client=client)
            try:
                rows=router.fetch("property.pt.commercial_all.bis",date(2024,1,1))
                self.assertEqual(len(rows.observations),2)
            finally:
                router.close()


if __name__=="__main__":
    unittest.main()
