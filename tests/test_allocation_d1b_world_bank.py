"""Plan phase D1b: World Bank PPP conversion factors and official exchange rates (trimmed responses of 2026-11-18)."""
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import unittest

from finance_dashboard.catalog import load_documents
from finance_dashboard.provider_parsers import parse_world_bank

FIXTURES = Path(__file__).parent / "fixtures" / "world_bank_allocation"
AREAS = ("EMU", "JPN", "GBR", "CHN", "CHE")


class WorldBankPppTests(unittest.TestCase):
    def test_registration(self):
        keys = {item["source_key"]: item for item in load_documents()[0]["series"] if item["provider"] == "WORLD_BANK"}
        for area in AREAS:
            for indicator in ("PA.NUS.PPP", "PA.NUS.FCRF"):
                item = keys[f"{area}/{indicator}"]
                self.assertEqual((item["frequency"], item["unit"]), ("A", "currency_per_usd"))
        self.assertFalse(any(key.endswith("PA.NUS.PPPC.RF") for key in keys))   # withdrawn indicator

    def test_real_responses_parse(self):
        euro = parse_world_bank(json.loads((FIXTURES / "PA.NUS.FCRF_EMU.json").read_text()), "EMU", "PA.NUS.FCRF", None)
        self.assertEqual(euro[date(1999, 1, 1)], Decimal("0.938283072395283"))
        japan = parse_world_bank(json.loads((FIXTURES / "PA.NUS.PPP_JPN.json").read_text()), "JPN", "PA.NUS.PPP", None)
        self.assertEqual(japan[date(2025, 1, 1)], Decimal("97.08005"))
        self.assertEqual(min(japan), date(1990, 1, 1))


if __name__ == "__main__":
    unittest.main()
