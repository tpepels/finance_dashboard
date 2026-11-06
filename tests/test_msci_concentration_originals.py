"""Native MSCI totals are dated evidence, including source revisions and rounding."""
from datetime import date
from decimal import Decimal
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil

from finance_dashboard import msci_concentration_originals as originals


FACTSHEET = """MSCI ACWI Index (USD)
The MSCI ACWI captures large and mid cap representation.
OCT 30, 2026    Index Factsheet
INDEX CHARACTERISTICS                   TOP 10 CONSTITUENTS
                                        Country Float Adj Mkt Index Sector
                                        Cap Wt. (%)
 Number of Constituents 2,413            APPLE                       US 5,061.70 5.02 Info Tech
                                        NVIDIA                      US 4,704.67 4.66 Info Tech
 Index 100,900,111.81                    MICROSOFT CORP              US 3,683.13 3.65 Info Tech
                                        AMAZON.COM                  US 2,326.92 2.31 Cons Discr
                                        TAIWAN SEMICONDUCTOR MFG     TW 1,791.11 1.78 Info Tech
                                        ALPHABET A                  US 1,641.96 1.63 Comm Srvcs
                                        BROADCOM                    US 1,473.78 1.46 Info Tech
                                        META PLATFORMS A            US 1,350.55 1.34 Comm Srvcs
                                        ALPHABET C                  US 1,300.59 1.29 Comm Srvcs
                                        TESLA                       US 1,143.84 1.13 Cons Discr
                                        Total                          24,478.26 24.26
FACTORS - KEY EXPOSURES THAT DRIVE RISK AND RETURN
"""


class MsciOriginalTests(unittest.TestCase):
    def test_original_pdf_download_uses_registered_client_and_immutable_archive(self):
        import httpx
        from tempfile import TemporaryDirectory
        from pathlib import Path
        pdf = (Path(__file__).parent /
               "fixtures/holdings/msci-acwi-2020-10-30-original.pdf").read_bytes()
        url = "https://www.msci.com/research/published-acwi-2020.pdf"
        requested = []
        def handler(req):
            requested.append(str(req.url))
            return httpx.Response(200, content=pdf,
                                  headers={"content-length": str(len(pdf))})
        with TemporaryDirectory() as temp:
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                root = Path(temp)
                first = originals.collect_msci_concentration_factsheet(
                    root=root, client=client, source_url=url)
                second = originals.collect_msci_concentration_factsheet(
                    root=root, client=client, source_url=url)
                self.assertEqual(first, second)
                values, evidence = originals.read_msci_concentration_originals(root)
                self.assertEqual(len(values), 1)
                self.assertTrue(evidence["source_sha256"])
                self.assertEqual(requested, [url, url])
                self.assertEqual(len(list((root / "msci-concentration").rglob("original.pdf"))), 1)

    def test_original_pdf_fails_closed_without_writing_on_bad_response(self):
        import httpx
        from tempfile import TemporaryDirectory
        from pathlib import Path
        url = "https://www.msci.com/research/acwi.pdf"
        attempts = []
        for response in (
            httpx.Response(200, content=b"<html>not a PDF</html>"),
            httpx.Response(200, content=b"%PDF-", headers={
                "content-length": str(originals.MAXIMUM_PDF_BYTES + 1)}),
            httpx.Response(302, headers={"location": "https://other.invalid/file.pdf"}),
        ):
            with self.subTest(response=response.status_code), TemporaryDirectory() as tmp:
                root = Path(tmp)
                with httpx.Client(transport=httpx.MockTransport(
                        lambda req: response)) as client:
                    with self.assertRaises(Exception):
                        originals.collect_msci_concentration_factsheet(
                            root=root, client=client, source_url=url)
                self.assertFalse((root / "msci-concentration").exists())
        with httpx.Client(transport=httpx.MockTransport(
                lambda req: attempts.append(req) or httpx.Response(200))) as client:
            with self.assertRaises(originals.MsciOriginalError):
                originals.collect_msci_concentration_factsheet(
                    root=Path("/unused"), client=client,
                    source_url="https://www.msci.com/document.pdf?token=private")
        self.assertFalse(attempts)

    def test_default_current_publisher_factsheet_and_explicit_sources(self):
        current = originals.msci_publisher_factsheet_sources()
        self.assertEqual(current, ((
            originals.msci_publisher_factsheet_identity(
                originals.CURRENT_ACWI_FACTSHEET_URL),
            originals.CURRENT_ACWI_FACTSHEET_URL),))
        self.assertIn("msci-acwi-net.pdf", current[0][1])
        historical = "https://www.msci.com/documents/10199/255599/2020-acwi.pdf"
        selected = originals.msci_publisher_factsheet_sources(
            (historical, originals.CURRENT_ACWI_FACTSHEET_URL))
        self.assertEqual(len(selected), 2)
        self.assertNotEqual(selected[0][0], selected[1][0])
        self.assertEqual(selected[0][1], historical)

    def test_source_selection_is_bounded_and_fails_before_network(self):
        valid = originals.CURRENT_ACWI_FACTSHEET_URL
        invalid = (
            (), (valid, valid),
            tuple(f"https://www.msci.com/documents/{i}/acwi.pdf"
                  for i in range(originals.MAX_FACTSHEET_SOURCES + 1)),
            ("https://not-msci.com/documents/acwi.pdf",),
            ("http://www.msci.com/documents/acwi.pdf",),
            ("https://www.msci.com/documents/acwi.pdf?api_key=secret",),
            ("https://www.msci.com/documents/acwi.pdf#page=1",),
            ("https://other:pass@www.msci.com/documents/acwi.pdf",),
        )
        for selection in invalid:
            with self.subTest(selection=selection):
                with self.assertRaises(originals.MsciOriginalError):
                    originals.msci_publisher_factsheet_sources(selection)

    def test_native_printed_total_is_retained_when_rounded_constituent_sum_differs(self):
        facts=originals.parse_msci_factsheet_text(FACTSHEET)
        self.assertEqual(facts["as_of"],"2026-10-30")
        self.assertEqual(facts["top10_percent"],"24.26")
        self.assertEqual(facts["sum_rounded_constituent_weights_pct"],"24.27")
        self.assertEqual(facts["constituent_sum_minus_published_total_pct"],"0.01")
        self.assertEqual(len(facts["constituents"]),10)
        self.assertEqual([p["name"] for p in facts["constituents"] if p["name"].startswith("ALPHABET")],
                         ["ALPHABET A","ALPHABET C"])

    def test_current_pdf_cannot_reconcile_a_historical_claim(self):
        with self.assertRaisesRegex(originals.MsciOriginalError,"date"):
            originals.parse_msci_factsheet_text(FACTSHEET,expected_asof="2025-05-30")

    def test_pdf_page_break_can_immediately_follow_a_footer(self):
        text=FACTSHEET.replace("OCT 30, 2026", "Previous page footer\fOCT 30, 2026")
        self.assertEqual(originals.parse_msci_factsheet_text(text)["as_of"],"2026-10-30")

    def test_wrong_index_missing_rows_and_material_total_difference_fail_closed(self):
        for text in (FACTSHEET.replace("MSCI ACWI Index (USD)","MSCI World Index (USD)"),
                     FACTSHEET.replace("                                        TESLA                       US 1,143.84 1.13 Cons Discr\n", ""),
                     FACTSHEET.replace("24,478.26 24.26","24,478.26 23.26")):
            with self.assertRaises(originals.MsciOriginalError):
                originals.parse_msci_factsheet_text(text)

    def test_source_month_preserves_exact_day_and_does_not_interpolate(self):
        result=originals.monthly_msci_values([
            {"as_of":"2020-10-30","top10_percent":"15.93"},
            {"as_of":"2023-10-31","top10_percent":"18.45"}])
        self.assertEqual(result,{date(2020,10,1):Decimal("15.93"),date(2023,10,1):Decimal("18.45")})
        with self.assertRaisesRegex(originals.MsciOriginalError,"conflicting"):
            originals.monthly_msci_values([
                {"as_of":"2020-10-30","top10_percent":"15.93"},
                {"as_of":"2020-10-30","top10_percent":"15.94"}])

    def test_constituent_count_requires_original_number_of_constituents_label(self):
        text=FACTSHEET.replace("Number of Constituents 2,413", "Number of 2,413".ljust(27))
        text=text.replace("                                        NVIDIA", " Constituents                           NVIDIA",1)
        self.assertEqual(originals.parse_msci_constituent_count_text(text),2413)
        self.assertIsNone(originals.parse_msci_constituent_count_text(text.replace("Number of 2,413","Unrelated 2,413")))

    def test_original_archive_requires_receipt_even_when_immutable_manifest_is_valid(self):
        original=(Path(__file__).parent/"fixtures/holdings/msci-acwi-2020-10-30-original.pdf").read_bytes()
        url="https://foro.masdividendos.com/uploads/short-url/fPVgQB8q4qpfx5mQlN0hs0VVkrR.pdf"
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            folder=originals.store_msci_concentration_original(original,source_url=url,root=root)
            values,evidence=originals.read_msci_concentration_originals(root)
            self.assertEqual(values,{date(2020,10,1):Decimal("15.93")})
            self.assertEqual(evidence["constituent_count_values"],{"2020-10-01":"2995"})
            self.assertEqual(evidence["original_document_proofs"][0]["selection_method"],"acquisition_receipt")
            shutil.rmtree(folder.parent/"retrievals")
            with self.assertRaisesRegex(originals.MsciOriginalError,"receipt"):
                originals.read_msci_concentration_originals(root)


if __name__=="__main__": unittest.main()
