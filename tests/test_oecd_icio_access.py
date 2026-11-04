"""Publisher challenges are retained as access evidence, never valid matrices."""
from pathlib import Path
from tempfile import TemporaryDirectory
import io
import unittest
import zipfile

import httpx

from finance_dashboard import oecd_icio_access as access
from finance_dashboard.icio import read_icio_evidence


class OecdIcioAccessTests(unittest.TestCase):
    def test_exact_download_errors_reach_canonical_evidence_without_verifying_years(self):
        def handler(request):
            return httpx.Response(403, content=b"<title>Just a moment...</title>",
                headers={"content-type": "text/html", "cf-mitigated": "challenge",
                         "server": "cloudflare", "set-cookie": "not retained"})
        with TemporaryDirectory() as temp, httpx.Client(transport=httpx.MockTransport(handler)) as client:
            root = Path(temp)
            folder = access.capture_publisher_access(root, client=client)
            report = read_icio_evidence(root)["publisher_acquisition"]
            self.assertEqual(report["status"], "publisher_downloads_blocked")
            self.assertEqual(report["blocked_archive_count"], 5)
            self.assertEqual(report["publisher_verified_years"], [])
            self.assertEqual(report["attempted_archive_years"], [1995, 2022])
            self.assertTrue(report["response_bytes_verified"])
            self.assertFalse(report["publisher_archive_acquired"])
            self.assertFalse(read_icio_evidence(root)["original_source_hash_verified"])
            self.assertEqual({row["classification"] for row in report["responses"]},
                             {"http_403_cloudflare_challenge"})
            self.assertTrue(all("set-cookie" not in row["headers"] for row in report["responses"]))
            self.assertEqual((folder / "1995-2000_SML.zip.response").read_bytes(),
                             b"<title>Just a moment...</title>")
            self.assertEqual(len(list((folder.parent / "retrievals").glob("*.json"))), 1)
            access.capture_publisher_access(root, client=client)
            self.assertEqual(len(list((folder.parent / "retrievals").glob("*.json"))), 2)
            (folder / "1995-2000_SML.zip.response").write_bytes(b"modified")
            with self.assertRaises(ValueError):
                access.read_publisher_access(root)

    def test_successful_html_is_not_classified_as_downloaded_zip(self):
        with TemporaryDirectory() as temp, httpx.Client(transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=b"<html>Not a ZIP</html>"))) as client:
            access.capture_publisher_access(Path(temp), client=client)
            report = access.read_publisher_access(Path(temp))
            self.assertFalse(report["publisher_archive_acquired"])
            self.assertEqual(report["publisher_verified_years"], [])
            self.assertTrue(all(row["classification"] == "unexpected_publisher_payload"
                                for row in report["responses"]))

    def test_retained_zip_is_pending_accounting_and_cannot_certify_any_year(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("2022_SML.csv", "not a validated matrix")
        def handler(request):
            return (httpx.Response(200, content=payload.getvalue()) if request.url.path.endswith(".zip")
                    else httpx.Response(403, content=b"denied"))
        with TemporaryDirectory() as temp, httpx.Client(transport=httpx.MockTransport(handler)) as client:
            access.capture_publisher_access(Path(temp), client=client)
            report = read_icio_evidence(Path(temp))
            self.assertTrue(report["publisher_acquisition"]["publisher_archive_acquired"])
            self.assertEqual(report["publisher_acquisition"]["retained_archive_count"], 5)
            self.assertEqual(report["publisher_acquisition"]["publisher_verified_years"], [])
            self.assertEqual(report["historical_coverage"]["verified_years"], [])
            self.assertFalse(report["original_source_hash_verified"])

    def test_missing_attempts_are_not_evidence_of_publisher_unavailability(self):
        with TemporaryDirectory() as temp:
            report = access.read_publisher_access(Path(temp))
            self.assertEqual(report["status"], "publisher_downloads_not_attempted")
            self.assertFalse(report["response_bytes_verified"])

    def test_direct_readme_can_verify_dimensions_without_certifying_denied_matrices(self):
        original = Path(__file__).parent / "fixtures" / "icio" / "ReadMe_ICIO_small.xlsx"
        def handler(request):
            if request.url.path.endswith("ReadMe_ICIO_small.xlsx"):
                return httpx.Response(200, content=original.read_bytes())
            return httpx.Response(403, content=b"download denied")
        with TemporaryDirectory() as temp, httpx.Client(transport=httpx.MockTransport(handler)) as client:
            access.capture_publisher_access(Path(temp), client=client)
            report = access.read_publisher_access(Path(temp))
            definition = report["publisher_definition"]
            self.assertTrue(definition["publisher_readme_identity_verified"])
            self.assertEqual(definition["unit"], "current_USD_million")
            self.assertEqual(definition["industry_nodes"], 4050)
            self.assertEqual(definition["final_demand_columns"], 486)
            self.assertTrue(definition["rest_of_world_included"])
            self.assertFalse(definition["china_mexico_split_nodes_included"])
            self.assertFalse(definition["revision_date_provided_by_readme"])
            self.assertEqual(report["publisher_verified_years"], [])
