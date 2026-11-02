"""Deterministic OECD-wide 38-member macro contracts; no network required."""
from datetime import date
from decimal import Decimal
from io import StringIO
import csv
import copy
import unittest

import httpx

from finance_dashboard.oecd_corporate import (
    OECD_MEMBER_ISO3, OecdSectorError, oecd_annual_data_key,
    parse_oecd_annual_sector_csv, parse_oecd_gdp_weights,
    compute_oecd_corporate_surplus,
)
from finance_dashboard.providers import ProviderRouter

HEADERS=[
    "DATAFLOW","FREQ","REF_AREA","SECTOR","COUNTERPART_SECTOR",
    "ACCOUNTING_ENTRY","TRANSACTION","INSTR_ASSET","EXPENDITURE",
    "UNIT_MEASURE","VALUATION","PRICE_BASE","TRANSFORMATION",
    "TABLE_IDENTIFIER","TIME_PERIOD","OBS_VALUE","COUNTERPART_AREA",
    "CONSOLIDATION","REF_YEAR_PRICE","CONF_STATUS","DECIMALS",
    "OBS_STATUS","UNIT_MULT","CURRENCY",
]


def input_rows():
    countries=sorted(OECD_MEMBER_ISO3)
    seen=countries[:33]
    rows=[]
    for country in seen:
        for sector,entry,transaction,amount in [
            ("S11","D","B2G",20),
            ("S12","D","B2G",5),
            ("S1","D","B1G",90),
            ("S1","C","D21X31",10),
        ]:
            rows.append({
                "DATAFLOW":"OECD.SDD.NAD:DSD_NASEC10@DF_TABLE14(1.1)",
                "FREQ":"A","REF_AREA":country,"SECTOR":sector,
                "COUNTERPART_SECTOR":"S1","ACCOUNTING_ENTRY":entry,
                "TRANSACTION":transaction,"INSTR_ASSET":"_Z",
                "EXPENDITURE":"_Z","UNIT_MEASURE":"XDC","VALUATION":"S",
                "PRICE_BASE":"V","TRANSFORMATION":"N","TABLE_IDENTIFIER":"T0800",
                "TIME_PERIOD":"2023","OBS_VALUE":str(amount),
                "COUNTERPART_AREA":"W","CONSOLIDATION":"_Z",
                "REF_YEAR_PRICE":"","CONF_STATUS":"F","DECIMALS":"2",
                "OBS_STATUS":"A","UNIT_MULT":"6","CURRENCY":"EUR",
            })
    return rows


def csv_text(rows):
    out=StringIO()
    w=csv.DictWriter(out,fieldnames=HEADERS)
    w.writeheader()
    w.writerows(rows)
    return out.getvalue()


def wdi_payload():
    return [{"page":1,"pages":1},[
        {"indicator":{"id":"NY.GDP.MKTP.CD"},"date":"2023",
         "countryiso3code":country,"value":1000000000000}
        for country in sorted(OECD_MEMBER_ISO3)
    ]]


class OecdMacroParserTests(unittest.TestCase):
    def test_official_member_list_and_narrow_source_query(self):
        self.assertEqual(len(OECD_MEMBER_ISO3),38)
        key=oecd_annual_data_key()
        self.assertTrue(key.startswith("A."))
        for country in OECD_MEMBER_ISO3:
            self.assertIn(country,key.split(".")[1].split("+"))
        self.assertIn("S11+S12+S1",key)

    def test_corporate_components_same_country_year_and_exact_gdp(self):
        sectors=parse_oecd_annual_sector_csv(csv_text(input_rows()))
        self.assertEqual(len(sectors[2023]),33)
        self.assertEqual(sectors[2023][sorted(OECD_MEMBER_ISO3)[0]]["fc"],Decimal(5))
        values=compute_oecd_corporate_surplus(sectors,parse_oecd_gdp_weights(wdi_payload()))
        self.assertEqual(values[0][date(2023,1,1)],Decimal(25))
        self.assertEqual(values[1][date(2023,1,1)],Decimal(3300)/Decimal(38))
        self.assertEqual(values[2][date(2023,1,1)],Decimal(33))
        self.assertEqual(len(values[0]),1)

    def test_rejects_future_wrong_currency_flow_units_duplicates(self):
        cases=[
          ("wrong flow",lambda rows: rows[0].update(DATAFLOW="OECD.FAKE")),
          ("wrong frequency",lambda rows: rows[0].update(FREQ="Q")),
          ("wrong geography",lambda rows: rows[0].update(REF_AREA="BRA")),
          ("unit change",lambda rows: rows[0].update(UNIT_MEASURE="USD")),
          ("accounting unit",lambda rows: rows[0].update(UNIT_MULT="0")),
          ("mixed currency",lambda rows: rows[1].update(CURRENCY="USD")),
          ("future year",lambda rows: rows[0].update(TIME_PERIOD="2040")),
          ("infinite",lambda rows: rows[0].update(OBS_VALUE="Infinity")),
        ]
        for label,mutate in cases:
            with self.subTest(label=label):
                rows=input_rows()
                mutate(rows)
                with self.assertRaises(OecdSectorError):
                    parse_oecd_annual_sector_csv(csv_text(rows))
        rows=input_rows()
        rows.append({**rows[0],"OBS_VALUE":"999"})
        with self.assertRaisesRegex(OecdSectorError,"duplicate"):
            parse_oecd_annual_sector_csv(csv_text(rows))

    def test_rejects_incompatible_wdi_weights(self):
        payload=wdi_payload()
        self.assertEqual(len(parse_oecd_gdp_weights(payload)[2023]),38)
        payload[1][0]["indicator"]["id"]="NOT_GDP"
        with self.assertRaises(OecdSectorError):
            parse_oecd_gdp_weights(payload)
        payload=wdi_payload()
        payload[1].append(copy.deepcopy(payload[1][0]))
        with self.assertRaisesRegex(OecdSectorError,"Duplicate"):
            parse_oecd_gdp_weights(payload)

    def test_below_coverage_and_country_count_excluded(self):
        src=parse_oecd_annual_sector_csv(csv_text(input_rows()))
        gdp=parse_oecd_gdp_weights(wdi_payload())
        reduced=copy.deepcopy(src)
        for country in sorted(OECD_MEMBER_ISO3)[14:33]:
            reduced[2023].pop(country)
        with self.assertRaises(OecdSectorError):
            compute_oecd_corporate_surplus(reduced,gdp)
        with self.assertRaises(OecdSectorError):
            compute_oecd_corporate_surplus(src,{2023:dict(list(gdp[2023].items())[:12])})
        with self.assertRaises(OecdSectorError):
            compute_oecd_corporate_surplus(src,gdp,start=date(2024,1,1))


class OecdProviderTests(unittest.TestCase):
    def test_all_three_series_from_two_official_sources(self):
        seen=[]
        def handle(req):
            seen.append(str(req.url))
            if "sdmx.oecd.org" in req.url.host:
                self.assertIn("DSD_NASEC10@DF_TABLE14",str(req.url))
                self.assertEqual(req.url.params["format"],"csvfile")
                return httpx.Response(200,text=csv_text(input_rows()))
            self.assertEqual(req.url.params["format"],"json")
            return httpx.Response(200,json=wdi_payload())
        router=ProviderRouter(httpx.Client(transport=httpx.MockTransport(handle)))
        try:
            expected={
                "profit.oecd38.corporate_gross_surplus_gdp":Decimal(25),
                "profit.oecd38.corporate_gross_surplus_gdp_coverage":Decimal(3300)/Decimal(38),
                "profit.oecd38.corporate_gross_surplus_member_count":Decimal(33),
            }
            for sid,value in expected.items():
                fetched=router.fetch(sid)
                self.assertEqual(fetched.observations,{date(2023,1,1):value})
                self.assertIn("sdmx.oecd.org",fetched.request_url)
                self.assertIn("worldbank.org",fetched.request_url)
            self.assertEqual(len(seen),6)
        finally:
            router.close()


if __name__ == "__main__":
    unittest.main()
