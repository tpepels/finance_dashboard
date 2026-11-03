"""Official SEC submission sync with a verified fund CIK/series, no ticker inference."""
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import date
import json
import unittest
from unittest.mock import patch
import httpx

from finance_dashboard.sec_holdings_sync import (
    read_verified_config,collect_configured,collect_if_due,check_sec_sources,
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

    def test_complete_source_exhaustion_requires_no_unverified_candidates(self):
        mapping = {"instrument_id":"vt","cik":"1234567","series_id":"S000000001"}
        def handler(request):
            url = str(request.url)
            if "data.sec.gov" in url:
                return httpx.Response(200,json=payload(url))
            if url.endswith("/primary_doc.xml"):
                return httpx.Response(200,content=XML)
            return httpx.Response(404)
        with TemporaryDirectory() as tmp:
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                result = import_fund(mapping, client=client,
                                     root=Path(tmp), max_filings=50)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["stored_or_already_present"], 1)
            self.assertFalse(result["matching_target_reached"])
            self.assertTrue(result["all_candidates_examined"])
            self.assertEqual(result["unexamined_candidate_filings"], 0)

    def test_failed_xml_keeps_source_partial_and_reports_safe_cause(self):
        mapping = {"instrument_id":"vt","cik":"1234567","series_id":"S000000001"}
        def handler(request):
            url = str(request.url)
            if "data.sec.gov" in url:
                return httpx.Response(200,json=payload(url))
            return httpx.Response(200,content=b"broken xml token")
        with TemporaryDirectory() as tmp:
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                with patch("finance_dashboard.sec_holdings_sync.parse_nport",
                           side_effect=HoldingsError("a private upstream body")):
                    result = import_fund(mapping, client=client,
                                         root=Path(tmp), max_filings=50)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["errors"], 1)
        self.assertEqual(result["first_error_reason"], "sec_holdings_xml_invalid")
        self.assertNotIn("private", json.dumps(result))

    def test_sec_check_validates_official_reference_indexes_without_xml_fetch(self):
        urls = []
        def handler(request):
            urls.append(str(request.url))
            series = ("S000022482" if "857489" in str(request.url)
                      else "S000002564")
            return httpx.Response(200, text=(
                '<html><a href="primary_doc.html">HTML</a>'
                '<a href="primary_doc.xml">XML</a>'
                '<a href="?series=' + series + '">' + series + '</a></html>'))
        with TemporaryDirectory() as tmp:
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                result = check_sec_sources(
                    config=Path(tmp)/"nonexistent.json",
                    user_agent="Research contact@example.org", client=client)
        self.assertEqual(result["status"],"ready")
        self.assertEqual(result["requests"],2)
        self.assertEqual(len(urls),2)
        self.assertTrue(all(url.endswith("-index.htm") for url in urls))
        self.assertTrue(all(x["xml_filename"] == "primary_doc.xml"
                            for x in result["funds"]))

    def test_html_primary_document_resolves_sec_index_xml_without_guessing(self):
        """Official SEC indexes commonly list HTML primary plus XML sibling."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            mapping = {"instrument_id":"vt","cik":"1234567","series_id":"S000000001"}
            acc = ["0001234567-26-000120","0001234567-26-000121",
                   "0001234567-26-000122"]
            submissions = {"cik":1234567,"filings":{
                "recent":{
                    "accessionNumber":acc,
                    "form":["NPORT-P"] * 3,
                    "filingDate":["2026-05-21"] * 3,
                    "acceptanceDateTime":["2026-05-21T18:30:00"] * 3,
                    "primaryDocument":["primary_doc.html"] * 3,
                }, "files":[]}}
            seen = []
            def handler(request):
                url = str(request.url)
                seen.append(url)
                if "data.sec.gov" in url:
                    return httpx.Response(200,json=submissions)
                if url.endswith("-index.htm"):
                    series = "S000000001" if "000120-index" in url else "S000000002"
                    return httpx.Response(200,text=(
                        '<html><a href="primary_doc.html">HTML</a>'
                        '<a href="primary_doc.xml">XML</a>'
                        '<a href="/cgi-bin/browse-edgar?series=' + series +
                        '">' + series + '</a></html>'))
                if url.endswith("/primary_doc.xml"):
                    self.assertIn("000120/primary_doc.xml", url)
                    return httpx.Response(200,content=XML)
                return httpx.Response(404)
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                first = import_fund(mapping,client=client,root=root,max_filings=1)
                self.assertEqual(first["stored_or_already_present"],1)
                self.assertEqual(first["attempted"],1)
                self.assertEqual(first["index_candidates_examined"],3)
                self.assertEqual(first["other_series_skipped"],2)
                self.assertEqual(first["status"],"complete")
                self.assertEqual(len(list_holdings(root,"vt")["records"]),1)
                downloaded = [x for x in seen if x.endswith("/primary_doc.xml")]
                self.assertEqual(len(downloaded),1)
                # Re-running the same source range reuses the validated record.
                second = import_fund(mapping,client=client,root=root,max_filings=1)
                self.assertEqual(second["already_cached_in_selection"],1)
                self.assertEqual(second["attempted"],0)
                self.assertEqual(len([x for x in seen
                    if x.endswith("/primary_doc.xml")]),1)

    def test_missing_submissions_primary_filename_uses_official_index(self):
        mapping = {"instrument_id":"vt","cik":"1234567","series_id":"S000000001"}
        source = {"cik":1234567,"filings":{"recent":{
            "accessionNumber":[ACC],"form":["NPORT-P"],
            "filingDate":["2026-05-21"],
            "acceptanceDateTime":["2026-05-21T18:30:00"],
            "primaryDocument":[""],
        }, "files":[]}}
        urls = []
        def handler(request):
            url = str(request.url)
            urls.append(url)
            if "data.sec.gov" in url:
                return httpx.Response(200,json=source)
            if url.endswith("-index.htm"):
                return httpx.Response(404)
            if url.endswith("-index.html"):
                return httpx.Response(200,text=(
                    '<html><a href="primary_doc.xml">XML</a>'
                    '<span>S000000001</span></html>'))
            if url.endswith("primary_doc.xml"):
                return httpx.Response(200,content=XML)
            return httpx.Response(404)
        with TemporaryDirectory() as tmp:
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                result = import_fund(mapping,client=client,root=Path(tmp),
                                     max_filings=1)
        self.assertEqual(result["status"],"complete")
        self.assertEqual(result["attempted"],1)
        self.assertTrue(any(url.endswith("-index.html") for url in urls))
        self.assertEqual(result["stored_or_already_present"],1)

    def test_index_with_ambiguous_xml_never_guesses_a_filing(self):
        from finance_dashboard.sec_holdings_sync import _xml_in_filing_index
        doc, reason = _xml_in_filing_index(
            '<html><a href="extra.xml">Extra</a>'
            '<a href="another.xml">Other</a>'
            '<a href="?id=S000000001">S000000001</a></html>',
            "S000000001","primary_doc.html")
        self.assertIsNone(doc)
        self.assertEqual(reason,"no_verified_primary_xml")
        doc, reason = _xml_in_filing_index(
            '<html><a href="primary_doc.xml">XML</a>'
            '<span>S000000002</span></html>',
            "S000000001","primary_doc.html")
        self.assertIsNone(doc)
        self.assertEqual(reason,"other_series")

    def test_sec_server_503_is_retried_boundedly_and_403_is_not(self):
        from finance_dashboard.sec_holdings_sync import _get_json
        counts = {"success":0,"blocked":0,"unavailable":0}

        def handler(request):
            route = request.url.path
            if route.endswith("/success.json"):
                counts["success"] += 1
                return httpx.Response(503 if counts["success"] < 3 else 200,
                                      json={"cik":"123"})
            if route.endswith("/blocked.json"):
                counts["blocked"] += 1
                return httpx.Response(403, json={"error":"not allowed"})
            counts["unavailable"] += 1
            return httpx.Response(503, json={"error":"temporarily unavailable"})

        with httpx.Client(transport=httpx.MockTransport(handler)) as client, \
             patch("finance_dashboard.sec_holdings_sync.time.sleep") as sleep:
            self.assertEqual(_get_json(
                client,"https://data.sec.gov/submissions/success.json")["cik"],
                "123")
            self.assertEqual(counts["success"],3)
            with self.assertRaises(httpx.HTTPStatusError):
                _get_json(client,"https://data.sec.gov/submissions/blocked.json")
            self.assertEqual(counts["blocked"],1)
            with self.assertRaises(httpx.HTTPStatusError):
                _get_json(client,"https://data.sec.gov/submissions/unavailable.json")
            self.assertEqual(counts["unavailable"],3)
            self.assertEqual(sleep.call_count,4)

    def test_sec_index_http_403_does_not_scan_or_download_every_candidate(self):
        with TemporaryDirectory() as tmp:
            mapping = {"instrument_id":"vt","cik":"1234567","series_id":"S000000001"}
            records = {"cik":1234567,"filings":{"recent":{
                "accessionNumber":[ACC] * 10,
                "form":["NPORT-P"] * 10,
                "filingDate":["2026-05-21"] * 10,
                "acceptanceDateTime":["2026-05-21T18:30:00"] * 10,
                "primaryDocument":["primary_doc.html"] * 10,
            }, "files":[]}}
            calls = []
            def handler(request):
                calls.append(str(request.url))
                if "data.sec.gov" in str(request.url):
                    return httpx.Response(200,json=records)
                return httpx.Response(403, text="Forbidden")
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                result = import_fund(mapping,client=client,root=Path(tmp),max_filings=12)
            self.assertEqual(result["status"],"blocked")
            self.assertEqual(result["halted_reason"],"sec_access_denied")
            self.assertEqual(result["http_status"],403)
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
