"""Plan phase D1b: BIS real broad effective exchange rates (trimmed responses of 2026-11-18)."""
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import unittest

from finance_dashboard.bis import ProviderError
from finance_dashboard.bis_eer import EER_SERIES, eer_key, parse_bis_eer
from finance_dashboard.captured_sources import _bis
from finance_dashboard.catalog import load_documents
from finance_dashboard.provider_registry import PROVIDER_REGISTRY
from finance_dashboard.source_reconciliation import EvidenceError

FIXTURES = Path(__file__).parent / "fixtures" / "bis_eer"


def payload(area, exact=False):
    text = (FIXTURES / f"eer_{area}.json").read_text()
    return json.loads(text, parse_float=Decimal) if exact else json.loads(text)


class BisEerTests(unittest.TestCase):
    def test_registration_and_agreement(self):
        catalog = {item["id"]: item for item in load_documents()[0]["series"]}
        self.assertEqual(PROVIDER_REGISTRY["BIS_EER"].handler, "fetch_bis_eer")
        for sid, area in EER_SERIES.items():
            self.assertEqual((catalog[sid]["provider"], catalog[sid]["source_key"]), ("BIS_EER", eer_key(area)))
            parsed, _prepared = parse_bis_eer(payload(area), area=area)
            reader = _bis(payload(area, exact=True), catalog[sid])
            self.assertEqual(reader[0] if isinstance(reader, tuple) else reader, parsed, sid)
            self.assertEqual((min(parsed), max(parsed)), (date(1994, 1, 1), date(2026, 9, 1)))

    def test_other_area_is_refused(self):
        catalog = {item["id"]: item for item in load_documents()[0]["series"]}
        with self.assertRaises(ProviderError):
            parse_bis_eer(payload("US"), area="XM")
        with self.assertRaises(EvidenceError):
            _bis(payload("US", exact=True), catalog["fx.ea.real_effective_rate.bis"])


if __name__ == "__main__":
    unittest.main()
