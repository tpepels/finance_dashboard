"""Read-only publisher-reported WID codes stay separated from scientific acceptance."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import httpx

from finance_dashboard.wid import WidClient
from finance_dashboard.wid_quality import original_wid_quality

FIXTURES=Path(__file__).parent/"fixtures"/"wid_top1"


class WIDOriginalQualityTests(unittest.TestCase):
    def test_original_publisher_quality_codes_preserved_after_immutable_pair_receipt(self):
        data=(FIXTURES/"US_data.csv").read_bytes()
        metadata=(FIXTURES/"US_metadata.csv").read_bytes()
        def source(request):
            name=str(request.url.path)
            return httpx.Response(200,content=metadata if "metadata" in name else data)
        with TemporaryDirectory() as folder,httpx.Client(
                transport=httpx.MockTransport(source)) as client:
            root=Path(folder)
            WidClient(client,archive_dir=root).fetch("inequality.us.pretax_income.top10")
            status=original_wid_quality(root)
            self.assertEqual(status["schema_version"],1)
            us=status["areas"]["US"]
            self.assertEqual(us["state"],"archived_metadata")
            self.assertEqual(len(us["source_sha256"]),64)
            self.assertEqual(len(us["manifest_sha256"]),64)
            self.assertEqual(
                us["series"]["inequality.us.pretax_income.top1"],
                {"state":"reported","quality_code":"5",
                 "latest_original_period":"2024-01-01"})
            self.assertEqual(
                us["series"]["inequality.us.net_personal_wealth.top10"]["quality_code"],"0")
            self.assertEqual(us["series"]["piketty.us.real_pretax_average.all"]["state"],
                             "not_reported")
            self.assertEqual(status["areas"]["FR"]["state"],
                             "no_verified_quality_metadata")
            self.assertIn("without inferring",status["quality_interpretation"])

    def test_manifest_tampering_withholds_all_codes_instead_of_fake_grade(self):
        data=(FIXTURES/"US_data.csv").read_bytes()
        metadata=(FIXTURES/"US_metadata.csv").read_bytes()
        with TemporaryDirectory() as folder,httpx.Client(transport=httpx.MockTransport(
                lambda r:httpx.Response(200,content=metadata if "metadata" in
                                        r.url.path else data))) as client:
            root=Path(folder)
            WidClient(client,archive_dir=root).fetch("inequality.us.pretax_income.top10")
            manifest=next(root.glob("wid/US/*/manifest.json"))
            manifest.write_bytes(manifest.read_bytes()+b" ")
            result=original_wid_quality(root)
            self.assertEqual(result["areas"]["US"]["state"],
                             "no_verified_quality_metadata")
            self.assertEqual(result["areas"]["US"]["series"],{})


if __name__=="__main__":
    unittest.main()
