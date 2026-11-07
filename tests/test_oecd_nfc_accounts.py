"""OECD Table 14 non-financial corporate accounts: exact series capture and strict reader."""
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import httpx

from finance_dashboard.constructed_source_reconciliation import _oecd_nfc
from finance_dashboard.providers import ProviderRouter
from finance_dashboard.source_capture import SourceAcquisition
from finance_dashboard.source_reconciliation import EvidenceError

HEADER = ("DATAFLOW,FREQ,REF_AREA,SECTOR,COUNTERPART_SECTOR,ACCOUNTING_ENTRY,TRANSACTION,INSTR_ASSET,EXPENDITURE,"
          "UNIT_MEASURE,VALUATION,PRICE_BASE,TRANSFORMATION,TABLE_IDENTIFIER,TIME_PERIOD,OBS_VALUE,UNIT_MULT,CURRENCY\n")
ROW = "OECD.SDD.NAD:DSD_NASEC10@DF_TABLE14(1.1),A,USA,S11,S1,D,D1,_Z,_Z,XDC,S,V,N,T0800,{year},{value},6,USD\n"
BODY = HEADER + ROW.format(year=2023, value=8000000) + ROW.format(year=2024, value=8566433)
DEFINITION = {"id": "test.us.nfc_d1", "provider": "OECD_NFC_ACCOUNTS", "source_key": "USA/D1", "frequency": "A",
              "unit": "million_local_currency", "currency": "USD", "status": "mapped", "geography": "US",
              "source_url": "https://data-explorer.oecd.org/", "name": "t", "theme": "labour_capital",
              "measurement": "t", "revision_policy": "revisable", "rights": "review_required", "notes": "t"}
URL = ("https://sdmx.oecd.org/public/rest/data/OECD.SDD.NAD,DSD_NASEC10@DF_TABLE14,1.1/"
       "A.USA.S11.S1.D.D1._Z._Z.XDC.S.V.N.T0800?format=csvfile")


class OecdNfcAccountsTests(unittest.TestCase):
    def test_capture_records_exact_series_url_and_reader_verifies_it(self):
        with TemporaryDirectory() as temp:
            with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=BODY))) as http:
                router = ProviderRouter(http)
                router.definitions[DEFINITION["id"]] = DEFINITION
                result = SourceAcquisition(router, Path(temp)).fetch(DEFINITION["id"])
            self.assertEqual(result.observations[date(2024, 1, 1)], Decimal("8566433"))
            manifest = json.loads(next(Path(temp).glob("responses/*/*/manifest.json")).read_text())
            url = manifest["sources"][0]["url"]
        self.assertEqual(_oecd_nfc(BODY.encode(), url, DEFINITION)[date(2023, 1, 1)], Decimal("8000000"))

    def test_reader_rejects_other_series_currency_or_partial_windows(self):
        for body, url, definition in (
                (BODY.replace(",USA,", ",DEU,"), URL, DEFINITION),
                (BODY.replace(",USD\n", ",EUR\n"), URL, DEFINITION),
                (BODY.replace(",6,USD", ",3,USD"), URL, DEFINITION),
                (BODY, URL + "&startPeriod=2020", DEFINITION),
                (BODY, URL, {**DEFINITION, "source_key": "USA/B2N"})):
            with self.subTest(url=url[-30:], key=definition["source_key"]), self.assertRaises(EvidenceError):
                _oecd_nfc(body.encode(), url, definition)
        with self.assertRaises(EvidenceError):
            _oecd_nfc(BODY.replace("8566433", "-1").encode(), URL, DEFINITION)


STOCK_HEADER = ("DATAFLOW,FREQ,REF_AREA,SECTOR,COUNTERPART_SECTOR,ACCOUNTING_ENTRY,TRANSACTION,INSTR_ASSET,EXPENDITURE,"
                "UNIT_MEASURE,VALUATION,PRICE_BASE,TRANSFORMATION,TABLE_IDENTIFIER,TIME_PERIOD,OBS_VALUE,UNIT_MULT,CURRENCY\n")
STOCK_ROW = "OECD.SDD.NAD:DSD_NASEC10@DF_TABLE9B(1.1),A,DEU,S11,S1,A,_Z,N11N,_Z,XDC,_Z,V,N,T2600,{year},{value},6,EUR\n"
STOCK_BODY = STOCK_HEADER + STOCK_ROW.format(year=2022, value=4906473) + STOCK_ROW.format(year=2024, value=5346248)
STOCK = {**DEFINITION, "id": "test.de.nfc_n11n", "source_key": "DEU/N11N", "currency": "EUR", "geography": "DEU"}
STOCK_URL = ("https://sdmx.oecd.org/public/rest/data/OECD.SDD.NAD,DSD_NASEC10@DF_TABLE9B,1.1/"
             "A.DEU.S11.S1.A._Z.N11N._Z.XDC._Z.V.N.T2600?format=csvfile")


class OecdNfcBalanceSheetTests(unittest.TestCase):
    def test_net_fixed_assets_come_from_table_9b_with_their_own_dimensions(self):
        with TemporaryDirectory() as temp:
            seen = []
            def handler(request):
                seen.append(str(request.url))
                return httpx.Response(200, text=STOCK_BODY)
            with httpx.Client(transport=httpx.MockTransport(handler)) as http:
                router = ProviderRouter(http)
                router.definitions[STOCK["id"]] = STOCK
                result = SourceAcquisition(router, Path(temp)).fetch(STOCK["id"])
            self.assertEqual(seen, [STOCK_URL])
            self.assertEqual(result.observations[date(2024, 1, 1)], Decimal("5346248"))
        self.assertEqual(_oecd_nfc(STOCK_BODY.encode(), STOCK_URL, STOCK)[date(2022, 1, 1)], Decimal("4906473"))

    def test_stock_reader_rejects_flows_other_assets_and_negative_stocks(self):
        for body, url in ((STOCK_BODY.replace(",N11N,", ",N1N,"), STOCK_URL),
                          (STOCK_BODY.replace(",A,_Z,N11N", ",D,_Z,N11N"), STOCK_URL),
                          (STOCK_BODY, STOCK_URL.replace("DF_TABLE9B", "DF_TABLE14")),
                          (STOCK_BODY.replace("4906473", "-1"), STOCK_URL)):
            with self.subTest(body=body[-60:], url=url[-40:]), self.assertRaises(EvidenceError):
                _oecd_nfc(body.encode(), url, STOCK)


if __name__ == "__main__":
    unittest.main()
