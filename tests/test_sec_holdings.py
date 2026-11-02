"""SEC N-PORT primary filing identity, reporting/availability and coverage tests."""
from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from finance_dashboard.sec_holdings import (
    HoldingsError, parse_nport, store_snapshot, list_holdings
)

URL = "https://www.sec.gov/Archives/edgar/data/1234567/000123456726000123/primary_doc.xml"
ACCESSION = "0001234567-26-000123"


def submission(form="NPORT-P", cik=1234567, time="2026-05-21T17:12:15"):
    return {"cik":cik, "filings":{"recent":{
        "accessionNumber":[ACCESSION], "form":[form],
        "acceptanceDateTime":[time], "filingDate":["2026-05-21"],
    }}}


def xml(pct_second="30.0", country="JP", series="S000000001"):
    return ("""
<edgarSubmission xmlns="urn:sec:edgar:nport">
  <headerData><submissionType>NPORT-P</submissionType>
    <filerInfo><seriesClassInfo><seriesId>""" + series + """</seriesId>
    </seriesClassInfo></filerInfo></headerData>
  <formData><genInfo><repPdDate>2026-03-31</repPdDate></genInfo>
    <invstOrSecs><invstOrSec><valUSD>7000</valUSD><pctVal>70</pctVal>
      <payoffProfile>Long</payoffProfile><invCountry>US</invCountry></invstOrSec>
      <invstOrSec><valUSD>3000</valUSD><pctVal>""" + pct_second + """</pctVal>
      <payoffProfile>Long</payoffProfile><invCountry>""" + country + """</invCountry>
      </invstOrSec></invstOrSecs></formData>
</edgarSubmission>""").encode()


class SecHoldingTests(unittest.TestCase):
    def parse(self, **kw):
        return parse_nport(xml(),instrument_id=kw.get("fund","vt"),
            accession=kw.get("accession",ACCESSION),
            filing_url=kw.get("url",URL),
            sec_metadata=kw.get("metadata",submission()),
            expected_series_id=kw.get("series","S000000001"))

    def test_primary_filing_has_valid_issuer_country_weights_and_public_date(self):
        record=self.parse()
        self.assertEqual(record["holdings_date"],"2026-03-31")
        self.assertTrue(record["available_at_utc"].startswith("2026-05-23"))
        self.assertIn("conservative", record["availability_time_quality"])
        self.assertEqual(record["classified_long_nav_percent"],"100.0")
        self.assertTrue(record["complete_share_of_nav"])
        self.assertEqual(record["countries"][0]["country"],"US")
        self.assertEqual(record["countries"][1]["country"],"JP")
        self.assertIn("NOT",record["country_semantics"])

    def test_rejects_unmatched_accession_series_form_and_non_us_etf(self):
        with self.assertRaisesRegex(HoldingsError,"accession"):
            self.parse(accession="0001234567-26-000124")
        with self.assertRaisesRegex(HoldingsError,"series"):
            self.parse(series="S000000002")
        with self.assertRaisesRegex(HoldingsError,"NPORT"):
            self.parse(metadata=submission(form="13F-HR"))
        with self.assertRaisesRegex(HoldingsError,"US ETFs"):
            self.parse(fund="vwce.de")
        with self.assertRaisesRegex(HoldingsError,"CIK"):
            self.parse(metadata=submission(cik=1234568))

    def test_derivative_issuer_is_not_inferred_as_underlying_country_exposure(self):
        filing=xml().replace(
            b"<payoffProfile>Long</payoffProfile><invCountry>JP",
            b"<assetCat>DE</assetCat><payoffProfile>Long</payoffProfile><invCountry>JP",
        )
        result=parse_nport(filing,instrument_id="vt",accession=ACCESSION,
            filing_url=URL,sec_metadata=submission(),
            expected_series_id="S000000001")
        self.assertEqual(result["classified_long_nav_percent"],"70")
        self.assertEqual(result["positions_excluded_short_or_derivative"],1)
        self.assertEqual([x["country"] for x in result["countries"]],["US"])
        self.assertFalse(result["complete_share_of_nav"])

    def test_filing_received_later_is_absent_from_historical_asof_query(self):
        record=self.parse()
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            path=store_snapshot(record,root=root)
            self.assertEqual(store_snapshot(record,root=root),path)
            early=list_holdings(root,"vt",asof=date(2026,4,1))
            self.assertEqual(early["status"],"no_dated_holdings")
            late=list_holdings(root,"vt",asof=date(2026,6,1))
            self.assertEqual(len(late["records"]),1)
            self.assertEqual(late["records"][0]["accession"],ACCESSION)

    def test_coverage_never_invents_100_percent_from_incomplete_country_data(self):
        record=parse_nport(xml(pct_second="30.0",country="NOT_SPECIFIED"),
            instrument_id="vt",accession=ACCESSION,filing_url=URL,
            sec_metadata=submission(),expected_series_id="S000000001")
        self.assertEqual(record["classified_long_nav_percent"],"70")
        self.assertEqual(record["unclassified_long_nav_percent"],"30.0")
        self.assertFalse(record["complete_share_of_nav"])


if __name__=="__main__":
    unittest.main()
