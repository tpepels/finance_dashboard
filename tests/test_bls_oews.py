"""BLS OEWS primary population, publisher identity and archive validation."""
import unittest
from datetime import date
from decimal import Decimal
from io import BytesIO
from unittest.mock import MagicMock, patch
from zipfile import ZipFile

from finance_dashboard.bis import ProviderError
from finance_dashboard.bls_oews import (
    SOURCE_KEYS, fetch_bls_oews, parse_national_rows, parse_national_zip,
    published_archives,
)


def source_index():
    return """<h2>May 2025</h2><a href="/oes/special-requests/oesm25nat.zip">National</a>
    <h2>May 2024</h2><a href="/oes/special-requests/oesm24nat.zip">National</a>
    <h2>May 2023</h2><a href="/oes/special-requests/oesm23nat.zip">National</a>"""


def data_rows():
    return [
        ["May 2025 OEWS original release"],
        ["OCC_CODE", "OCC_TITLE", "TOT_EMP", "H_MEAN", "H_MEDIAN"],
        ["00-0000", "All Occupations", 155495730, 33.54, 24.51],
        ["11-0000", "Management Occupations", 11132700, 69.84, 60.83],
    ]


def zip_bytes(year):
    data = BytesIO()
    with ZipFile(data, "w") as archive:
        archive.writestr(f"national_M{year}_dl.xlsx", b"PK\x03\x04test-workbook")
    return data.getvalue()


class BLSOEWSOriginalTests(unittest.TestCase):
    def test_index_only_accepts_published_same_host_releases(self):
        self.assertEqual([year for year, _ in published_archives(source_index(),
            today=date(2026, 11, 14))], [2023, 2024, 2025])
        with self.assertRaisesRegex(ProviderError, "May 2025"):
            published_archives('<a href="https://example.org/oes/special-requests/oesm25nat.zip">fake</a>')
        self.assertEqual(len(published_archives(
            source_index() + '<a href="/oes/special-requests/oesm27nat.zip">future</a>',
            today=date(2026, 11, 14))), 3)

    def test_mean_and_median_refer_to_identical_national_occupation_population(self):
        self.assertEqual(parse_national_rows(data_rows(), 2025),
            {"H_MEAN": Decimal("33.54"), "H_MEDIAN": Decimal("24.51")})
        with self.assertRaisesRegex(ProviderError, "duplicated"):
            parse_national_rows(data_rows() + [data_rows()[2]], 2025)
        incorrect = data_rows()
        incorrect[2] = ["00-0000", "Management", 155495730, 33.54, 24.51]
        with self.assertRaisesRegex(ProviderError, "identity"):
            parse_national_rows(incorrect, 2025)
        malformed = data_rows()
        malformed[2] = ["00-0000", "All Occupations", 155495730, "#", 24.51]
        with self.assertRaisesRegex(ProviderError, "numeric"):
            parse_national_rows(malformed, 2025)

    def test_exact_archive_workbook_year_and_bounded_content(self):
        fake = MagicMock()
        fake.sheet_names = ["national"]
        fake.get_sheet_by_index.return_value.to_python.return_value = data_rows()
        with patch("python_calamine.CalamineWorkbook.from_filelike", return_value=fake):
            self.assertEqual(parse_national_zip(zip_bytes(2025), 2025)["H_MEDIAN"],
                             Decimal("24.51"))
            with self.assertRaisesRegex(ProviderError, "identity"):
                parse_national_zip(zip_bytes(2024), 2025)
            with self.assertRaisesRegex(ProviderError, "not an approved"):
                parse_national_zip(b"HTTP 403 blocked", 2025)

    def test_provider_uses_same_workbook_and_respects_historical_window(self):
        router = MagicMock()
        router._get_document.side_effect = [
            MagicMock(text=source_index()), MagicMock(content=zip_bytes(2024)),
            MagicMock(content=zip_bytes(2025))]
        fake = MagicMock()
        fake.sheet_names = ["national"]
        fake.get_sheet_by_index.return_value.to_python.return_value = data_rows()
        with patch("python_calamine.CalamineWorkbook.from_filelike", return_value=fake):
            got = fetch_bls_oews(router, "labour.us.oews_all_mean_hourly",
                date(2024, 1, 1), {}, SOURCE_KEYS["labour.us.oews_all_mean_hourly"])
        self.assertEqual(got.observations, {
            date(2024, 5, 1): Decimal("33.54"),
            date(2025, 5, 1): Decimal("33.54")})
        self.assertEqual(router._get_document.call_count, 3)
        with self.assertRaisesRegex(ProviderError, "Unregistered"):
            fetch_bls_oews(router, "labour.us.cps_weekly_p50_nominal", None, {},
                           "NATIONAL/ALL_OCCUPATIONS/H_MEAN")


if __name__ == "__main__":
    unittest.main()
