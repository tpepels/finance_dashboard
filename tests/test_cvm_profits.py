"""Original consolidated accounts retain issuer/period/scale/revision boundaries."""
import csv
from datetime import date
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

import httpx

ROOT=Path(__file__).parent/"fixtures/profits"


def excerpt_package():
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w') as archive:
        archive.writestr('dfp_cia_aberta_DRE_con_2025.csv',(ROOT/'cvm_2025_consolidated_profit_excerpt.csv').read_bytes())
        archive.writestr('dfp_cia_aberta_2025.csv',(ROOT/'cvm_2025_filings_excerpt.csv').read_bytes())
    return output.getvalue()


class CvmProfitTests(unittest.TestCase):
    def test_original_factual_income_rows_keep_parent_income_scales_losses_and_duplicate_evidence(self):
        from finance_dashboard.cvm_profits import parse_cvm_consolidated_income
        result=parse_cvm_consolidated_income((ROOT/"cvm_2025_consolidated_profit_excerpt.csv").read_bytes(),
            (ROOT/"cvm_2025_filings_excerpt.csv").read_bytes())
        records={r["cnpj"]:r for r in result["records"]}
        self.assertEqual(records["00.000.000/0001-91"]["parent_attributable_income_native"],"13698124.0000000000")
        self.assertEqual(records["00.000.000/0001-91"]["parent_attributable_income_brl"],"13698124000.0000000000")
        self.assertEqual(records["00.000.000/0001-91"]["authority_received_date"],"2026-02-11")
        self.assertGreater(records["02.171.304/0001-47"]["duplicate_identical_source_rows"],0)
        self.assertEqual(records["42.276.907/0001-28"]["state"],"reported_profit_partition_mismatch")
        self.assertTrue(any(r["parent_attributable_income_native"].startswith("-") for r in records.values()))
        self.assertTrue(any(r["native_scale"]=="UNIDADE" and r["parent_attributable_income_brl"]==r["parent_attributable_income_native"] for r in records.values()))
        self.assertEqual({r["parent_income_account"] for r in records.values()},{"3.09.01","3.11.01","3.13.01"})
        self.assertTrue(any(not r["calendar_year_aligned"] for r in records.values()))
        self.assertTrue(any(r["filing_version"]==3 for r in records.values()))
        self.assertFalse(result["worldwide_population_verified"])
        self.assertFalse(result["ultimate_parent_deduplication_verified"])

    def test_missing_parent_value_is_not_replaced_with_total_income(self):
        from finance_dashboard.cvm_profits import parse_cvm_consolidated_income
        text=(ROOT/"cvm_2025_consolidated_profit_excerpt.csv").read_bytes().decode("latin1")
        rows=list(csv.DictReader(io.StringIO(text),delimiter=";"))
        rows=[r for r in rows if not (r["CNPJ_CIA"]=="00.000.000/0001-91" and r["CD_CONTA"]=="3.11.01")]
        stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=list(rows[0]),delimiter=";");writer.writeheader();writer.writerows(rows)
        result=parse_cvm_consolidated_income(stream.getvalue().encode("latin1"),(ROOT/"cvm_2025_filings_excerpt.csv").read_bytes())
        bank=next(r for r in result["records"] if r["cnpj"]=="00.000.000/0001-91")
        self.assertEqual(bank["state"],"missing_parent_income")
        self.assertIsNone(bank["parent_attributable_income_native"])

    def test_receipt_cutoff_excludes_later_filings_without_claiming_publication_vintages(self):
        from finance_dashboard.cvm_profits import parse_cvm_consolidated_income
        result=parse_cvm_consolidated_income((ROOT/'cvm_2025_consolidated_profit_excerpt.csv').read_bytes(),
            (ROOT/'cvm_2025_filings_excerpt.csv').read_bytes(),authority_receipt_cutoff=date(2020,1,1))
        self.assertEqual(result['records'],[])
        self.assertEqual(result['authority_receipt_cutoff'],'2020-01-01')
        self.assertIn('not a public-release vintage',result['selection'])
        earlier=parse_cvm_consolidated_income((ROOT/'cvm_2025_consolidated_profit_excerpt.csv').read_bytes(),
            (ROOT/'cvm_2025_filings_excerpt.csv').read_bytes(),authority_receipt_cutoff=date(2026,3,12))
        self.assertTrue(all(r['authority_received_date']<='2026-03-12' for r in earlier['records']))
        self.assertNotIn('00.864.214/0001-06',{r['cnpj'] for r in earlier['records']})
        missing=next(r for r in earlier['unavailable_historical_revisions'] if r['cnpj']=='00.864.214/0001-06')
        self.assertEqual(missing['filing_version'],1)
        self.assertIn('later revision not substituted',missing['reason'])

    def test_canonical_acquisition_preserves_original_and_appends_verified_receipts(self):
        from finance_dashboard.cvm_profits import collect_cvm_annual_source,read_cvm_sources
        from finance_dashboard.bis import ProviderError
        original=excerpt_package()
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,content=original,
                    headers={'last-modified':'Wed, 04 Nov 2026 00:00:00 GMT'},request=request))) as client:
                first=collect_cvm_annual_source(root=root,year=2025,client=client)
                folder=root/'corporate-profits/cvm/2025'/first['bundle_digest']
                manifest=(folder/'manifest.json').read_bytes()
                collect_cvm_annual_source(root=root,year=2025,client=client)
            self.assertEqual((folder/'original.zip').read_bytes(),original)
            self.assertEqual((folder/'manifest.json').read_bytes(),manifest)
            self.assertEqual(len(list((folder.parent/'retrievals').glob('*.json'))),2)
            result=read_cvm_sources(root)
            self.assertFalse(result['aggregate_produced'])
            record=result['records'][0]
            self.assertEqual(record['acquisition_method'],'publisher_http')
            self.assertEqual(record['selection_method'],'acquisition_receipt')
            self.assertGreater(len(record['records']),0)
            self.assertTrue(all(not r['first_publication_verified'] for r in record['records']))
            (folder/'original.zip').write_bytes(original+b'tampered')
            with self.assertRaises(ProviderError): read_cvm_sources(root)

    def test_error_html_and_redirects_cannot_be_archived_as_cvm_originals(self):
        from finance_dashboard.cvm_profits import collect_cvm_annual_source
        from finance_dashboard.bis import ProviderError
        for status in (200,302):
            with TemporaryDirectory() as tmp:
                with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(status,
                        content=b'<html>not an annual archive</html>',request=request))) as client:
                    with self.assertRaises(ProviderError):
                        collect_cvm_annual_source(root=Path(tmp),year=2025,client=client)
                self.assertEqual(list(Path(tmp).rglob('manifest.json')),[])

    @unittest.skipUnless(os.environ.get("TEST_CVM_PACKAGE"),"private original CVM archive supplied separately")
    def test_full_original_2025_archive_checks_all_consolidated_reporters(self):
        from finance_dashboard.cvm_profits import audit_cvm_annual_archive
        report=audit_cvm_annual_archive(Path(os.environ["TEST_CVM_PACKAGE"]).read_bytes(),year=2025)
        self.assertEqual(report["population"]["filing_issuers"],669)
        self.assertEqual(report["population"]["consolidated_income_issuers"],440)
        self.assertEqual(len(report["records"]),440)
        self.assertTrue(any(r["state"]=="reported_profit_partition_mismatch" for r in report["records"]))
        self.assertFalse(report["worldwide_population_verified"])


if __name__=="__main__": unittest.main()
