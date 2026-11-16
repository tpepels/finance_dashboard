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
    "NMFP_SUBMISSION.tsv":"ACCESSION_NUMBER\tSUBMISSIONTYPE\tREPORTDATE\tFILING_DATE\tSERIESID\n"
       "old\tN-MFP3\t2026-10-31\t2026-11-01\tS000000001\n"
       "new\tN-MFP3/A\t2026-10-31\t2026-11-03\tS000000001\n"
       "feeder\tN-MFP3\t2026-10-31\t2026-11-02\tS000000002\n",
    "NMFP_SERIESLEVELINFO.tsv":"ACCESSION_NUMBER\tFEEDERFUNDFLAG\tNETASSETOFSERIES\tAVERAGEPORTFOLIOMATURITY\tAVERAGELIFEMATURITY\n"
       "old\tN\t100000000\t30\t60\n"
       "new\tN\t200000000\t28\t56\n"
       "feeder\tY\t900000000\t10\t20\n",
    "NMFP_LIQUIDASSETSDETAILS.tsv":"ACCESSION_NUMBER\tTOTLIQUIDASSETSNEARPCTDATE\tPCTWEEKLYLIQUIDASSETS\n"
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
        with ZipFile(BytesIO(raw)) as archive:
            self.assertEqual(
                sorted(archive.namelist()),
                sorted(["NMFP_SUBMISSION.tsv", "NMFP_SERIESLEVELINFO.tsv",
                        "NMFP_LIQUIDASSETSDETAILS.tsv"]))

    def test_sec_real_publisher_schema_rejects_invented_net_assets_column(self):
        # Diagnostic archive 20250710-20250807_nmfp.zip names the original
        # column NETASSETOFSERIES (without the plural S).
        valid = zipped_sec()
        self.assertEqual(
            parse_nmfp_month(valid, date(2026, 10, 1))["NET_ASSETS_MUSD"],
            Decimal("200"))
        invalid = BytesIO()
        with ZipFile(BytesIO(valid)) as source, ZipFile(invalid, "w") as dest:
            for name in source.namelist():
                contents = source.read(name)
                if name == "NMFP_SERIESLEVELINFO.tsv":
                    contents = contents.replace(
                        b"NETASSETOFSERIES", b"NETASSETSOFSERIES")
                dest.writestr(name, contents)
        with self.assertRaises(ProviderError):
            parse_nmfp_month(invalid.getvalue(), date(2026, 10, 1))
        from finance_dashboard.extra_publisher_evidence import _month_zip, EvidenceError
        with self.assertRaises(EvidenceError):
            _month_zip(invalid.getvalue(), date(2026, 10, 1))

    def test_managed_ingestion_archive_and_independent_reconciliation(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        import httpx
        from finance_dashboard.providers import ProviderRouter
        from finance_dashboard.source_capture import SourceAcquisition
        from finance_dashboard.service import IngestionService
        from finance_dashboard.database import make_engine, Base
        from finance_dashboard.source_reconciliation import reconcile

        dwa="DWA.Q.PT.S14._Z._Z.NWA.T10.PT.S.N"
        index_link="https://www.sec.gov/files/dera/data/form-n-mfp-data-sets/20261008-20261106_nmfp.zip"
        html=f'<a href="{index_link}">2026 October NMFP</a>'
        def transport(request):
            if request.url.host=="data-api.ecb.europa.eu":
                return httpx.Response(200,text="KEY,TIME_PERIOD,OBS_VALUE\n"+
                                      f"{dwa},2025-Q1,57.2\n{dwa},2025-Q2,57.4\n")
            if request.url.host=="ec.europa.eu":
                return httpx.Response(200,json=eurostat())
            if request.url.host=="www.sec.gov":
                if request.url.path.endswith("_nmfp.zip"):
                    return httpx.Response(200,content=zipped_sec())
                return httpx.Response(200,text=html)
            raise AssertionError("Unapproved publisher URL "+str(request.url))
        identifiers=["wealth.pt.ecb_dwa_top10",
                     "property.pt.eurostat_hpi_total",
                     "funding.us.sec_nmfp_net_assets_musd"]
        with TemporaryDirectory() as temp, patch.dict("os.environ",{
                "SEC_USER_AGENT":"OriginalSourceTests tester@example.org"}):
            root=Path(temp)
            db="sqlite:///"+str(root/"series.db")
            engine=make_engine(db)
            Base.metadata.create_all(engine)
            with httpx.Client(transport=httpx.MockTransport(transport)) as http:
                service=IngestionService(engine,SourceAcquisition(ProviderRouter(http),root))
                for sid in identifiers:
                    first=service.refresh(sid,full=True)
                    self.assertGreater(first["versions_added"],0,sid)
                    repeated=service.refresh(sid,full=True)
                    self.assertEqual(repeated["versions_added"],0,sid)
            report=reconcile(db,root,identifiers)
            self.assertTrue(report["passed"],report)
            self.assertEqual(report["matched_series"],3)
            # Verify original bytes are archived, and changing a publisher
            # response invalidates the proof rather than changing history.
            original=next((root/"responses"/identifiers[0]).glob("*/response-0.bin"))
            original.write_bytes(original.read_bytes().replace(b"57.2",b"55.2"))
            altered=reconcile(db,root,[identifiers[0]])
            self.assertFalse(altered["passed"])
            engine.dispose()

    def test_sec_independent_reader_orders_amendments_by_date_not_date_strings(self):
        from finance_dashboard.extra_publisher_evidence import _month_zip
        source = BytesIO(zipped_sec())
        patched = BytesIO()
        with ZipFile(source) as original, ZipFile(patched, "w") as updated:
            for name in original.namelist():
                raw = original.read(name)
                if name == "NMFP_SUBMISSION.tsv":
                    # ISO old filing sorts *after* US-formatted newer filing
                    # as strings. Both valid SEC dates must sort by date.
                    self.assertIn(b"2026-11-03", raw)
                    raw = raw.replace(b"2026-11-03", b"11/03/2026")
                updated.writestr(name, raw)
        raw = patched.getvalue()
        actual = parse_nmfp_month(raw, date(2026, 10, 1))
        independently_verified = _month_zip(raw, date(2026, 10, 1))
        self.assertEqual(actual, independently_verified)
        self.assertEqual(actual["NET_ASSETS_MUSD"], Decimal("200"))

    def test_sec_as_filed_liquidity_fraction_marginally_above_one(self):
        # Minimal literal rows of SEC original 20250710-20250807_nmfp.zip
        # (SHA-256 f14a3b3cd632221b9d4d5f0fbba0e0d39cf879c909743c9da928c10eb5e69573),
        # accession 0001145549-25-050323, series S000080765. A government
        # fund files weekly liquid assets marginally above total assets on
        # some days. Fifteen of the sixteen 2025-07..2026-10 publisher months
        # contain such rows, never above 1.0004.
        from finance_dashboard.extra_publisher_evidence import _month_zip, EvidenceError
        def original(liquidity_rows):
            tables={
            "NMFP_SUBMISSION.tsv":"ACCESSION_NUMBER\tSUBMISSIONTYPE\tREPORTDATE\tFILING_DATE\tSERIESID\n"
               "0001145549-25-050323\tN-MFP3\t31-JUL-2025\t04-AUG-2025\tS000080765\n",
            "NMFP_SERIESLEVELINFO.tsv":"ACCESSION_NUMBER\tFEEDERFUNDFLAG\tNETASSETOFSERIES\tAVERAGEPORTFOLIOMATURITY\tAVERAGELIFEMATURITY\n"
               "0001145549-25-050323\tN\t   1125762182.06\t4\t4\n",
            "NMFP_LIQUIDASSETSDETAILS.tsv":"ACCESSION_NUMBER\tTOTLIQUIDASSETSNEARPCTDATE\tPCTWEEKLYLIQUIDASSETS\n"
               +"".join(f"0001145549-25-050323\t{day}\t{value}\n" for day,value in liquidity_rows)}
            output=BytesIO()
            with ZipFile(output,"w") as archive:
                for name,rows in tables.items():archive.writestr(name,rows)
            return output.getvalue()
        month=date(2025,7,1)
        published=original([("03-JUL-2025"," 1.0002"),("25-JUL-2025"," 1.0001"),
                            ("31-JUL-2025","  .9998")])
        result=parse_nmfp_month(published,month)
        self.assertEqual(result["NET_ASSETS_MUSD"],Decimal("1125.76218206"))
        self.assertEqual(result["WEEKLY_LIQUIDITY_PCT"],Decimal("99.98"))
        self.assertEqual(result,_month_zip(published,month))
        # The as-filed value is stored unchanged, never clipped to 100.
        final_day=original([("31-JUL-2025"," 1.0002")])
        self.assertEqual(parse_nmfp_month(final_day,month)["WEEKLY_LIQUIDITY_PCT"],
                         Decimal("100.02"))
        self.assertEqual(_month_zip(final_day,month)["WEEKLY_LIQUIDITY_PCT"],
                         Decimal("100.02"))
        # Anything further from the fraction scale stays an ambiguous
        # convention and rejects the original; negatives stay invalid.
        for ambiguous in (" 1.0101"," 1.5","99.98"):
            raw=original([("31-JUL-2025",ambiguous)])
            with self.assertRaisesRegex(ProviderError,"fraction exceeds"):
                parse_nmfp_month(raw,month)
            with self.assertRaises(EvidenceError):
                _month_zip(raw,month)
        negative=original([("31-JUL-2025","-.0001")])
        with self.assertRaises(ProviderError):
            parse_nmfp_month(negative,month)
        with self.assertRaises(EvidenceError):
            _month_zip(negative,month)

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
