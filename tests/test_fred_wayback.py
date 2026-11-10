"""FRED's own downloads as archived by the Internet Archive: pinned by CDX digest, read without filling."""
from datetime import date
from decimal import Decimal
import gzip
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from finance_dashboard import fred_wayback as fw
from finance_dashboard.bis import ProviderError
from finance_dashboard.msci_regional_factsheets import cdx_digest

CSV = b"observation_date,BAMLH0A0HYM2\n1996-12-31,3.13\n1997-01-01,\n1997-01-02,3.06\n"


def pinned(payload):
    return {"BAMLH0A0HYM2": {"timestamp": "20251104204105", "original": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2",
                             "cdx_digest": cdx_digest(payload)}}


class FredWaybackTests(unittest.TestCase):
    def test_store_and_read_the_pinned_capture(self):
        payload = gzip.compress(CSV)
        with TemporaryDirectory() as temp, mock.patch.dict(fw.CAPTURES, pinned(payload), clear=True):
            fw.store_capture(Path(temp), "BAMLH0A0HYM2", payload)
            values, proof = fw.read_fred_wayback(Path(temp), "BAMLH0A0HYM2")
        self.assertEqual(values, {date(1996, 12, 31): Decimal("3.13"), date(1997, 1, 2): Decimal("3.06")})
        self.assertEqual(proof["cdx_digest"], cdx_digest(payload))
        self.assertEqual(proof["capture_url"], "https://web.archive.org/web/20251104204105id_/https://fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2")

    def test_other_bytes_or_another_series_are_refused(self):
        payload = gzip.compress(CSV)
        with TemporaryDirectory() as temp, mock.patch.dict(fw.CAPTURES, pinned(payload), clear=True):
            with self.assertRaises(ProviderError):
                fw.store_capture(Path(temp), "BAMLH0A0HYM2", gzip.compress(CSV + b"1997-01-03,3.0\n"))
            other = gzip.compress(CSV.replace(b"BAMLH0A0HYM2", b"DGS10"))
            with mock.patch.dict(fw.CAPTURES, pinned(other)):
                with self.assertRaises(ProviderError):
                    fw.store_capture(Path(temp), "BAMLH0A0HYM2", other)

    def test_missing_archive_is_explicit(self):
        with TemporaryDirectory() as temp:
            with self.assertRaises(FileNotFoundError):
                fw.read_fred_wayback(Path(temp), "BAMLH0A0HYM2")


if __name__ == "__main__":
    unittest.main()


class ArchiveVerifiedDaysTests(unittest.TestCase):
    def test_days_rolled_out_of_fred_are_verified_by_the_identical_archived_value(self):
        from finance_dashboard.source_reconciliation import _archive_verified_periods
        payload = gzip.compress(CSV)
        definition = {"provider": "FRED", "source_key": "BAMLH0A0HYM2"}
        stored = {date(1996, 12, 31): Decimal("3.13"), date(1997, 1, 2): Decimal("3.07")}
        with TemporaryDirectory() as temp, mock.patch.dict(fw.CAPTURES, pinned(payload), clear=True):
            fw.store_capture(Path(temp), "BAMLH0A0HYM2", payload)
            verified = _archive_verified_periods(Path(temp), definition, sorted(stored), stored, "sqlite")
            self.assertEqual(verified, [date(1996, 12, 31)])                 # 1997-01-02 differs: stays unverified
            self.assertEqual(_archive_verified_periods(Path(temp), {"provider": "ECB", "source_key": "X"},
                                                       sorted(stored), stored, "sqlite"), [])
