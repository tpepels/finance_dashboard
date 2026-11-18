"""Plan phase D1b: Federal Reserve GZ spread and excess bond premium (excerpt of the 2026-11-18 CSV)."""
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import unittest

from finance_dashboard.bis import ProviderError
from finance_dashboard.captured_sources import _fed_ebp
from finance_dashboard.catalog import load_documents
from finance_dashboard.fed_ebp import FED_EBP_SERIES, FED_EBP_URL, parse_fed_ebp
from finance_dashboard.provider_registry import PROVIDER_REGISTRY
from finance_dashboard.source_reconciliation import EvidenceError

FIXTURES = Path(__file__).parent / "fixtures" / "fed_ebp"
TEXT = (FIXTURES / "ebp_excerpt.csv").read_text()


class FedEbpTests(unittest.TestCase):
    def test_registration_and_values(self):
        catalog = {item["id"]: item for item in load_documents()[0]["series"]}
        self.assertEqual(PROVIDER_REGISTRY["FED_EBP"].handler, "fetch_fed_ebp")
        for sid, column in FED_EBP_SERIES.items():
            self.assertEqual((catalog[sid]["provider"], catalog[sid]["source_key"]), ("FED_EBP", column))
            parsed = parse_fed_ebp(TEXT, sid)
            values, _ = _fed_ebp(TEXT, catalog[sid], FED_EBP_URL)
            self.assertEqual(values, parsed)
        # Publisher row: "1973-01-01,1.1307714053429057,-0.04765868268656903,0.1827584903883351"
        self.assertEqual(parse_fed_ebp(TEXT, "credit.us.excess_bond_premium")[date(1973, 1, 1)], Decimal("-0.04765868268656903"))
        self.assertEqual(parse_fed_ebp(TEXT, "credit.us.gz_spread")[date(2026, 10, 1)], Decimal("1.0045612268832755"))
        self.assertNotIn("credit.us.recession_probability", catalog)

    def test_columns_order_and_identity(self):
        with self.assertRaises(ProviderError):
            parse_fed_ebp(TEXT.replace("gz_spread,ebp", "ebp,gz_spread", 1), "credit.us.excess_bond_premium")
        lines = TEXT.splitlines()
        with self.assertRaises(ProviderError):
            parse_fed_ebp("\n".join([lines[0], lines[2], lines[1]]), "credit.us.excess_bond_premium")
        definition = {"source_key": "est_prob", "unit": "percentage_points", "frequency": "M"}
        with self.assertRaises(EvidenceError):
            _fed_ebp(TEXT, definition, FED_EBP_URL)
        self.assertEqual(json.loads((FIXTURES / "provenance.json").read_text())["rows"], 646)


if __name__ == "__main__":
    unittest.main()
