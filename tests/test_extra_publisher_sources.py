"""Test original ECB/Eurostat/SEC ingestion and independent source identity."""
from datetime import date
from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile
from unittest.mock import MagicMock, patch
import json
import unittest

from finance_dashboard.bis import ProviderError
from finance_dashboard.catalog import load_documents, validate
from finance_dashboard.extra_publisher_sources import (
    fetch_ecb_dwa, fetch_eurostat_hpi, fetch_sec_nmfp,
    parse_eurostat_hpi, parse_nmfp_month, nmfp_archives, SEC_NMFP_INDEX)
from finance_dashboard.extra_publisher_evidence import independent_values
from finance_dashboard.provider_registry import get_provider
from finance_dashboard.research_corpus import load_research_corpus
from finance_dashboard.source_policy_registry import PolicyRegistry


def eurostat():
    dimensions={key:{"category":{"index":{val:0}}} for key,val in
                (("freq","Q"),("purchase","TOTAL"),("unit","I15_Q"),("geo","PT"))}
    dimensions["time"]={"category":{"index":{"2025-Q1":0,"2025-Q2":1}}}
    return {"class":"dataset","id":list(dimensions),"size":[1,1,1,1,2],
            "dimension":dimensions,"value":{"0":100,"1":110}}


def zipped_sec():
    tables={
    "SUBMISSION.tsv":"ACCESSION_NUMBER\tSUBMISSIONTYPE\tREPORTDATE\tFILING_DATE\tSERIESID\n"
       "old\tN-MFP3\t2026-10-31\t2026-11-01\tS000000001\n"
       "new\tN-MFP3/A\t2026-10-31\t2026-11-03\tS000000001\n"
       "feeder\tN-MFP3\t2026-10-31\t2026-11-02\tS000000002\n",
    "SERIESLEVELINFO.tsv":"ACCESSION_NUMBER\tFEEDERFUNDFLAG\tNETASSETSOFSERIES\tAVERAGEPORTFOLIOMATURITY\tAVERAGELIFEMATURITY\n"
       "old\tN\t100000000\t30\t60\n"
       "new\tN\t200000000\t28\t56\n"
       "feeder\tY\t900000000\t10\t20\n",
    "LIQUIDASSETSDETAILS.tsv":"ACCESSION_NUMBER\tTOTLIQUIDASSETSNEARPCTDATE\tPCTWEEKLYLIQUIDASSETS\n"
       "old\t2026-10-30\t0.70\nnew\t2026-10-30\t0.80\nfeeder\t2026-10-30\t0.99\n"}
    output=BytesIO()
    with ZipFile(output,"w") as archive:
        for name,rows in tables.items():archive.writestr(name,rows)
    return output.getvalue()


class OriginalDataTests(unittest.TestCase):
    def test_catalogue_and_acceptance(self):
        series,_=load_documents()
        extra={p:[s for s in series["series"] if s["provider"]==p] for p in
               ("ECB_DWA","EUROSTAT_HPI","SEC_NMFP")}
        self.assertEqual([len(extra[p]) for p in extra],[8,15,4])
        self.assertEqual(validate(*load_documents()),[])
        for provider,items in extra.items():
            self.assertEqual(get_provider(provider).acquisition,"response")
            self.assertTrue(all(item["source_key"] for item in items))
        corpus=load_research_corpus()
        for q,provider in (("L07","ECB_DWA"),("C07","EUROSTAT_HPI"),("F07","SEC_NMFP")):
            analysis=next(a for a in corpus["analyses"] if a["id"]==q)
            ids={s["id"] for s in extra[provider]}
            relevant=[r for r in analysis["comparison_contract"]["original_requirements"]
                      if set(r["series_ids"])&ids]
            self.assertTrue(relevant)
            self.assertTrue(all(r["requirement_class"]=="supplemental" for r in relevant))
        policies=PolicyRegistry()
        for url in ("https://data-api.ecb.europa.eu/service/data/DWA/",
                    "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hpi_q",
                    SEC_NMFP_INDEX):
            self.assertIsNotNone(policies.for_url(url))

    def test_ecb_dwa_exact_scope_and_independent_evidence(self):
        key="DWA.Q.PT.S14._Z._Z.NWA.T10.PT.S.N"
        raw=("KEY,TIME_PERIOD,OBS_VALUE\n"+
             f"{key},2025-Q1,57.2\n{key},2025-Q2,57.4\n")
        url="https://data-api.ecb.europa.eu/service/data/DWA/"+key[4:]+"?format=csvdata"
        router=MagicMock()
        router._get_document.return_value=MagicMock(text=raw,request=MagicMock(url=url))
        result=fetch_ecb_dwa(router,"wealth.pt.ecb_dwa_top10",None,
                             {"geography":"PT","frequency":"Q"},key)
        self.assertEqual(result.observations[date(2025,4,1)],Decimal("57.4"))
        values,scope=independent_values("ECB_DWA",[(raw.encode(),"hash")],
             [{"url":url}],{"source_key":key,"unit":"percent"},None)
        self.assertEqual(values,result.observations)
        self.assertEqual(scope["source_native_unit"],"percent")
        with self.assertRaises(Exception):
            independent_values("ECB_DWA",[(raw.encode(),"hash")],
                 [{"url":url.replace("PT.S.N","PT.S.D")}],{"source_key":key},None)

    def test_eurostat_schema_and_original_source_link(self):
        payload=eurostat()
        values=parse_eurostat_hpi(payload,area="PT",purchase="TOTAL")
        self.assertEqual(values[date(2025,4,1)],Decimal(110))
        url=("https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hpi_q"
             "?freq=Q&geo=PT&purchase=TOTAL&unit=I15_Q")
        router=MagicMock()
        router._get_document.return_value=MagicMock(json=lambda:payload,
                                                    request=MagicMock(url=url))
        series=fetch_eurostat_hpi(router,"property.pt.eurostat_hpi_total",None,
                                  {"geography":"PT"},"prc_hpi_q/PT/TOTAL/I15_Q")
        self.assertEqual(series.observations,values)
        evidence,_=independent_values("EUROSTAT_HPI",
             [(json.dumps(payload).encode(),"hash")],[{"url":url}],
             {"source_key":"prc_hpi_q/PT/TOTAL/I15_Q"},None)
        self.assertEqual(evidence,values)
        with self.assertRaises(ProviderError):
            parse_eurostat_hpi(payload,area="DE",purchase="TOTAL")
        with self.assertRaises(Exception):
            independent_values("EUROSTAT_HPI",
              [(json.dumps(payload).encode(),"hash")],
              [{"url":url.replace("geo=PT","geo=DE")}],
              {"source_key":"prc_hpi_q/PT/TOTAL/I15_Q"},None)

    def test_sec_nmfp_amendments_feeder_exclusion_and_liquidity(self):
        raw=zipped_sec()
        result=parse_nmfp_month(raw,date(2026,10,1))
        self.assertEqual(result["NET_ASSETS_MUSD"],Decimal(200))
        self.assertEqual(result["WAM_DAYS"],Decimal(28))
        self.assertEqual(result["WAL_DAYS"],Decimal(56))
        self.assertEqual(result["WEEKLY_LIQUIDITY_PCT"],Decimal(80))
        link="https://www.sec.gov/files/dera/data/form-n-mfp-data-sets/20261008-20261106_nmfp.zip"
        html=f'<a href="{link}">2026 October NMFP</a>'
        self.assertEqual(nmfp_archives(html),[(date(2026,10,1),link)])
        original,_=independent_values("SEC_NMFP",
            [(html.encode(),"hash"),(raw,"hash")],
            [{"url":SEC_NMFP_INDEX},{"url":link}],
            {"source_key":"NET_ASSETS_MUSD","unit":"million_usd"},None)
        self.assertEqual(original[date(2026,10,1)],Decimal(200))
        with self.assertRaises(Exception):
            independent_values("SEC_NMFP",
                [(html.encode(),"hash"),(raw,"hash")],
                [{"url":SEC_NMFP_INDEX},{"url":link.replace("www.sec.gov","invalid.test")}],
                {"source_key":"NET_ASSETS_MUSD","unit":"million_usd"},None)
        with self.assertRaises(ProviderError):
            parse_nmfp_month(b"<html>Access denied</html>",date(2026,10,1))

    def test_sec_requires_operator_contact(self):
        with patch.dict("os.environ",{"SEC_USER_AGENT":""}):
            with self.assertRaisesRegex(ProviderError,"SEC_USER_AGENT"):
                fetch_sec_nmfp(MagicMock(),"funding.us.sec_nmfp_wam_days",None,{},"WAM_DAYS")

    def test_new_engine_inputs_are_supplemental(self):
        from finance_dashboard.engine.analyses import DEFINITIONS
        for q,prefix,count in (("L07","dwa:",8),("C07","eurostat:",15),("F07","sec_nmfp:",4)):
            self.assertEqual(sum(s.startswith(prefix) for s in
                                 DEFINITIONS[q].optional_inputs),count)


if __name__=="__main__":
    unittest.main()
