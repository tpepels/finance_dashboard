"""Only Wayback raw captures of the official ACWI factsheet are accepted."""
import unittest

from finance_dashboard.msci_concentration_originals import MsciOriginalError, _url_identity


class WaybackFactsheetUrlTests(unittest.TestCase):
    def test_raw_capture_of_official_factsheet_is_accepted(self):
        url = "https://web.archive.org/web/20240131120000id_/https://www.msci.com/documents/10199/255599/msci-acwi-net.pdf"
        self.assertRegex(_url_identity(url), r"^[0-9a-f]{16}$")
        old = "https://web.archive.org/web/20141222190859id_/http://www.msci.com:80/resources/factsheets/index_fact_sheet/msci-acwi-net.pdf"
        self.assertRegex(_url_identity(old), r"^[0-9a-f]{16}$")

    def test_other_wayback_targets_or_rewritten_captures_are_rejected(self):
        for url in (
            "https://web.archive.org/web/20240131120000/https://www.msci.com/documents/10199/255599/msci-acwi-net.pdf",
            "https://web.archive.org/web/20240131120000id_/https://www.msci.com/documents/10199/255599/msci-world.pdf",
            "https://web.archive.org/web/20240131120000id_/https://evil.example/msci-acwi-net.pdf",
            "https://web.archive.org/web/20240131120000id_/https://www.msci.com/documents/10199/255599/msci-acwi-net.pdf?x=1",
        ):
            with self.subTest(url=url), self.assertRaises(MsciOriginalError):
                _url_identity(url)


if __name__ == "__main__":
    unittest.main()
