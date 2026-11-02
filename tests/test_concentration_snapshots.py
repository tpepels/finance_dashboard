"""Source-document-backed concentration: all snapshots, provenance and gaps."""
from datetime import date
from decimal import Decimal
import copy
import json
import unittest

from finance_dashboard.concentration_snapshots import (
    ConcentrationSourceError, load_msci_concentration_snapshots,
    parse_msci_concentration_snapshots,
)
from finance_dashboard.catalog import DEFAULT_ROOT


class ConcentrationSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads((DEFAULT_ROOT / "data/msci_acwi_published_snapshots.json").read_text())

    def test_all_eight_source_cited_observations_are_exact_and_sparse(self):
        expected = {
            date(2019, 12, 1): Decimal("11.94"),
            date(2020, 10, 1): Decimal("15.93"),
            date(2021, 8, 1): Decimal("16.06"),
            date(2023, 10, 1): Decimal("18.45"),
            date(2024, 7, 1): Decimal("21.23"),
            date(2025, 5, 1): Decimal("21.88"),
            date(2025, 10, 1): Decimal("25.55"),
            date(2026, 9, 1): Decimal("25.40"),
        }
        self.assertEqual(load_msci_concentration_snapshots(), expected)
        self.assertNotIn(date(2022, 1, 1), expected)
        self.assertNotIn(date(2025, 9, 1), expected)

    def test_start_filter_and_no_historical_filling(self):
        result = load_msci_concentration_snapshots(start=date(2025, 1, 1))
        self.assertEqual(len(result), 3)
        with self.assertRaisesRegex(ConcentrationSourceError,"requested period"):
            load_msci_concentration_snapshots(start=date(2027, 1, 1))

    def test_forged_wrong_index_duplicate_and_invented_future_are_rejected(self):
        for mutate in [
            lambda s: s.update(index_code="999999"),
            lambda s: s["snapshot_rows"].append(copy.deepcopy(s["snapshot_rows"][0])),
            lambda s: s["snapshot_rows"][0].update(as_of="2030-12-31"),
            lambda s: s["snapshot_rows"][2].update(source_url="http://some.example/x"),
            lambda s: s["snapshot_rows"][3].update(top10_percent="NaN"),
            lambda s: s["snapshot_rows"][4].update(source_type="unsourced_yahoo_holdings"),
            lambda s: s["snapshot_rows"][6].update(source_note=""),
        ]:
            data=copy.deepcopy(self.source)
            mutate(data)
            with self.assertRaises(ConcentrationSourceError):
                parse_msci_concentration_snapshots(data)


if __name__=="__main__":
    unittest.main()
