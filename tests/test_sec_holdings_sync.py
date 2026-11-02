"""Official SEC submission sync with a verified fund CIK/series, no ticker inference."""
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import date
import json
import unittest
import httpx

from finance_dashboard.sec_holdings_sync import (
    read_verified_config,collect_configured,collect_if_due,
    SEC_FILE, PAGE, VERIFIED_DEFAULT_FUNDS, VERIFICATION_FILINGS, import_fund,
)
from finance_dashboard.sec_holdings import HoldingsError, list_holdings

ACC="0001234567-26-000123"


def payload(url):
    if "data.sec.gov" in url:
        return {"cik":1234567,"filings":{"recent":{
            "accessionNumber":[ACC],
            "form":["NPORT-P"],"filingDate":["2026-05-21"],
            "acceptanceDateTime":["2026-05-21T18:30:00"],
            "primaryDocument":["primary_doc.xml"],
        },"files":[]}}
    return None


XML=b"""<edgarSubmission><headerData><submissionType>NPORT-P</submissionType>
<filerInfo><seriesClassInfo><seriesId>S000000001</seriesId></seriesClassInfo></filerInfo>
</headerData><formData><genInfo><repPdDate>2026-03-31</repPdDate></genInfo>
<invstOrSecs><invstOrSec><pctVal>100</pctVal><valUSD>100000</valUSD>
<payoffProfile>Long</payoffProfile><invCountry>US</invCountry></invstOrSec></invstOrSecs>
</formData></edgarSubmission>"""


class SecSyncTests(unittest.TestCase):
    def test_read_only_verified_map_and_one_official_sec_filing(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            config=root/"sec_funds.json"
            config.write_text(json.dumps([{
                "instrument_id":"vt","cik":"1234567","series_id":"S000000001",
            }]))
            known=read_verified_config(config)
            self.assertEqual(known[0]["instrument_id"],"vt")
            calls=[]
            def handler(request):
                url=str(request.url)
                calls.append(url)
                if "data.sec.gov" in url:
                    return httpx.Response(200,json=payload(url))
                if url.endswith("/primary_doc.xml"):
                    return httpx.Response(200,content=XML)
                return httpx.Response(404)
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                from finance_dashboard.sec_holdings_sync import import_fund
                response=import_fund(known[0],client=client,root=root,max_filings=1)
            self.assertEqual(response["status"],"complete")
            self.assertEqual(response["stored_or_already_present"],1)
            self.assertEqual(list_holdings(root,"vt",asof=date(2026,5,21))["records"],[])
            self.assertEqual(len(list_holdings(root,"vt",asof=date(2026,5,24))["records"]),1)
            self.assertEqual(len(calls),2)

    def test_builtin_verified_funds_do_not_need_placeholder_identifiers(self):
        with TemporaryDirectory() as tmp:
            mappings = read_verified_config(Path(tmp)/"not-configured.json")
        self.assertEqual({item["instrument_id"] for item in mappings},
                         {"vt", "bnd"})
        self.assertEqual({item["series_id"] for item in mappings},
                         {"S000022482", "S000002564"})
        self.assertTrue(all("www.sec.gov/Archives/" in url
                            for url in VERIFICATION_FILINGS.values()))

    def test_limit_counts_verified_matching_fund_not_just_registrant_attempts(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            mapping={"instrument_id":"vt","cik":"1234567",
                     "series_id":"S000000001"}
            acc=["0001234567-26-00012"+str(i) for i in range(4)]
            recent={"accessionNumber":acc,
                    "form":["NPORT-P"]*4,
                    "filingDate":["2026-05-21"]*4,
                    "acceptanceDateTime":["2026-05-21T18:30:00"]*4,
                    "primaryDocument":["primary_doc.xml"]*4}
            other=XML.replace(b"S000000001",b"S000000002")
            def handler(request):
                url=str(request.url)
                if "data.sec.gov" in url:
                    return httpx.Response(200,json={"cik":1234567,
                        "filings":{"recent":recent,"files":[]}})
                if url.endswith("/primary_doc.xml"):
                    accession=url.split("/")[-2]
                    number=int(accession[-1])
                    return httpx.Response(200,content=(other if number >= 2 else XML))
                return httpx.Response(404)
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                result=import_fund(mapping,client=client,root=root,max_filings=2)
            self.assertEqual(result["attempted"],4)
            self.assertEqual(result["other_series_skipped"],2)
            self.assertEqual(result["stored_or_already_present"],2)
            self.assertTrue(result["matching_target_reached"])

    def test_unmapped_irish_fund_cannot_be_falsely_imported_as_us_sec(self):
        with TemporaryDirectory() as tmp:
            cfg=Path(tmp)/"config.json"
            cfg.write_text(json.dumps([{
                "instrument_id":"vwce.de","cik":"1234567","series_id":"S000000001",
            }]))
            with self.assertRaisesRegex(HoldingsError,"CIK/series"):
                read_verified_config(cfg)

    def test_refuses_bad_sec_document_filenames_and_missing_contact(self):
        self.assertIsNone(SEC_FILE.fullmatch("../evil.xml"))
        self.assertIsNone(PAGE.fullmatch("../../index.json"))
        with TemporaryDirectory() as tmp:
            cfg=Path(tmp)/"sec_funds.json"
            cfg.write_text(json.dumps([{
                "instrument_id":"vt","cik":"1234567","series_id":"S000000001",
            }]))
            disabled=collect_configured(config=cfg,root=Path(tmp),
                                       user_agent="")
            self.assertEqual(disabled["status"],"disabled_missing_SEC_USER_AGENT")


if __name__=="__main__":
    unittest.main()
