"""Bundesbank time-series downloads: exact series identity, native unit, explicit gaps."""
from datetime import date
from decimal import Decimal
import unittest

from finance_dashboard.bis import ProviderError
from finance_dashboard.bundesbank import BUNDESBANK_SERIES, bundesbank_url, parse_bundesbank_csv

SID = "bond.de.bund_10y_par_yield_month_end"
KEY = "BBSIS.M.I.ZAR.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A"


def download(rows, key=KEY, unit="percent"):
    head = [f'﻿"",{key},{key}_FLAGS',
            '"","Yields, derived from the term structure of interest rates, on listed Federal securities with annual coupon payments / residual maturity of 10.0 years / monthly data",',
            f"BBK_UNIT_ENG,{unit},", "Decimals,2,", "Time format code,P1M,", "category,ZRZS,", "unit multiplier,One,",
            "last update,2026-11-02 12:47:46,"]
    return "\n".join(head + rows) + "\n"


class BundesbankTests(unittest.TestCase):
    def test_registered_series_and_url(self):
        flow, key, frequency = BUNDESBANK_SERIES[SID]
        self.assertEqual((flow, frequency), ("BBSIS", "M"))
        self.assertEqual(bundesbank_url(flow, key), "https://api.statistiken.bundesbank.de/rest/data/BBSIS/" + key[6:])

    def test_values_by_month_with_explicit_gaps(self):
        values = parse_bundesbank_csv(download(["1972-09,7.92,", "1972-10,.,No value available", "1972-11,8.48,"]), SID)
        self.assertEqual(values, {date(1972, 9, 1): Decimal("7.92"), date(1972, 11, 1): Decimal("8.48")})
        self.assertEqual(parse_bundesbank_csv(download(["1972-09,7.92,", "1972-11,8.48,"]), SID, start=date(1972, 10, 1)),
                         {date(1972, 11, 1): Decimal("8.48")})

    def test_identity_unit_and_duplicates_are_checked(self):
        with self.assertRaises(ProviderError):
            parse_bundesbank_csv(download(["1972-09,7.92,"], key="BBSIS.M.I.ZST.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A"), SID)
        with self.assertRaises(ProviderError):
            parse_bundesbank_csv(download(["1972-09,7.92,"], unit="index"), SID)
        with self.assertRaises(ProviderError):
            parse_bundesbank_csv(download(["1972-09,7.92,", "1972-09,7.93,"]), SID)


if __name__ == "__main__":
    unittest.main()


class IndependentReaderTests(unittest.TestCase):
    DEFINITION = {"source_key": KEY, "unit": "percent", "frequency": "M"}
    URL = "https://api.statistiken.bundesbank.de/rest/data/BBSIS/M.I.ZAR.ZI.EUR.S1311.B.A604.R10XX.R.A.A._Z._Z.A?format=csv&lang=en"

    def test_reader_agrees_with_the_parser_and_rejects_other_series(self):
        from finance_dashboard.captured_sources import _bundesbank
        from finance_dashboard.source_reconciliation import EvidenceError
        body = download(["1972-09,7.92,", "1972-10,.,No value available", "1972-11,8.48,"])
        values, dimensions = _bundesbank(body, self.DEFINITION, self.URL)
        self.assertEqual(values, parse_bundesbank_csv(body, SID))
        self.assertEqual(dimensions["source_native_unit"], "percent")
        with self.assertRaises(EvidenceError):
            _bundesbank(body, self.DEFINITION, self.URL.replace("ZAR", "ZST"))
        with self.assertRaises(EvidenceError):
            _bundesbank(download(["1972-09,7.92,"], unit="index"), self.DEFINITION, self.URL)
