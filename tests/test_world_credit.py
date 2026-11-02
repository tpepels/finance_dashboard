"""BIS world composite: source IDs, weights, annual lags, duplicate geography."""
from datetime import date
from decimal import Decimal as D
import unittest

from finance_dashboard.world_credit import (
    GlobalCreditError, parse_bis_national_credit_gaps, parse_wdi_gdp_all,
    country_weighted_bis_gap,
)


def bis_fixture():
    return {"data":{"structure":{"dimensions":{
        "series":[
            {"id":"FREQ","values":[{"id":"Q"}]},
            {"id":"BORROWERS_CTY","values":[{"id":"US"},{"id":"JP"},{"id":"XM"}]},
            {"id":"TC_BORROWERS","values":[{"id":"P"}]},
            {"id":"TC_LENDERS","values":[{"id":"A"}]},
            {"id":"CG_DTYPE","values":[{"id":"C"}]},
        ],
        "observation":[{"id":"TIME_PERIOD","values":[{"id":"2025-Q1"}]}]}},
        "dataSets":[{"series":{
            "0:0:0:0:0":{"observations":{"0":["-10.0"]}},
            "0:1:0:0:0":{"observations":{"0":["5.0"]}},
            "0:2:0:0:0":{"observations":{"0":["999.0"]}},
        }}]}}


class BisWorldCreditTests(unittest.TestCase):
    def test_country_gap_selects_actual_minus_trend_and_excludes_euro_area(self):
        result=parse_bis_national_credit_gaps(bis_fixture(),country_codes={"US","JP"})
        self.assertEqual(result[date(2025,1,1)],{"US":D(-10),"JP":D(5)})
        self.assertNotIn("XM",result[date(2025,1,1)])

    def test_world_bank_gdp_aggregate_not_counted_twice(self):
        raw=[
            {"page":1,"pages":1},
            [
                {"indicator":{"id":"NY.GDP.MKTP.CD"},"country":{"id":"US"},
                 "countryiso3code":"USA","date":"2024","value":60},
                {"indicator":{"id":"NY.GDP.MKTP.CD"},"country":{"id":"JP"},
                 "countryiso3code":"JPN","date":"2024","value":30},
                {"indicator":{"id":"NY.GDP.MKTP.CD"},"country":{"id":"1W"},
                 "countryiso3code":"WLD","date":"2024","value":100},
                {"indicator":{"id":"NY.GDP.MKTP.CD"},"country":{"id":"XM"},
                 "countryiso3code":"EMU","date":"2024","value":20},
            ],
        ]
        countries,world=parse_wdi_gdp_all(raw,country_codes={"US","JP"})
        self.assertEqual(countries[2024],{"US":D(60),"JP":D(30)})
        self.assertEqual(world[2024],D(100))
        weighted,coverage=country_weighted_bis_gap(
            {date(2025,1,1):{"US":D(-10),"JP":D(5)}},
            countries,world)
        self.assertEqual(weighted[date(2025,1,1)],D(-5))
        self.assertEqual(coverage[date(2025,1,1)],D(90))

    def test_missing_quarter_or_insufficient_gdp_coverage_excluded(self):
        with self.assertRaisesRegex(GlobalCreditError,"coverage threshold"):
            country_weighted_bis_gap(
                {date(2025,1,1):{"US":D(-10)}},
                {2024:{"US":D(60),"JP":D(30)}},
                {2024:D(100)})
        with self.assertRaisesRegex(GlobalCreditError,"coverage threshold"):
            country_weighted_bis_gap(
                {date(2025,1,1):{"US":D(-10),"JP":D(5)}},
                {2025:{"US":D(60),"JP":D(30)}},
                {2025:D(100)})  # no prior year GDP; no look-ahead.

    def test_malformed_bis_or_paged_world_bank_rejected(self):
        with self.assertRaises(GlobalCreditError):
            parse_bis_national_credit_gaps({"data":{}},country_codes={"US","JP"})
        with self.assertRaisesRegex(GlobalCreditError,"Unpaginated"):
            parse_wdi_gdp_all([{"pages":2},[]])

if __name__=="__main__":
    unittest.main()
