"""Every limitation the acceptance engine can emit has owner-readable text."""
from pathlib import Path
import re
import unittest

from finance_dashboard.engine.limitations import (UnmappedLimitation, describe, load_register,
                                                  method_limitations)

SRC = Path(__file__).resolve().parents[1] / "src" / "finance_dashboard"
ACCEPTANCE_MODULES = ["research_acceptance.py", "holdings_acceptance.py", "chronology_acceptance.py",
                      "marxian_acceptance.py", "regional_valuation_acceptance.py",
                      "comparative_corpus.py", "research_readiness.py"]


class LimitationRegisterTests(unittest.TestCase):
    def test_every_code_literal_in_acceptance_modules_has_text(self):
        codes = {m for f in ACCEPTANCE_MODULES
                 for m in re.findall(r'"code":\s*"([a-z0-9_]+)"', (SRC / f).read_text())}
        self.assertGreaterEqual(len(codes), 28)
        self.assertEqual(sorted(codes - set(load_register()["phase2"])), [])

    def test_code_constants_in_acceptance_modules_have_text(self):
        codes = {m for f in ACCEPTANCE_MODULES
                 for m in re.findall(r'^[A-Z_]*CODE[A-Z_]*\s*=\s*"([a-z0-9_]+)"', (SRC / f).read_text(), re.M)}
        self.assertIn("announcement_dates_not_published_before_committee", codes)
        self.assertEqual(sorted(codes - set(load_register()["phase2"])), [])

    def test_constant_code_lists_have_text(self):
        from finance_dashboard.holdings_acceptance import CONDITIONAL_CODES
        self.assertEqual(sorted(set(CONDITIONAL_CODES) - set(load_register()["phase2"])), [])

    def test_detail_only_limitation_is_described(self):
        item = {"code": "role_descoped_by_phase1_revision", "role": "x", "detail": "no free source"}
        described = describe(item)
        self.assertEqual(described["detail"], "no free source")
        self.assertEqual(described["role"], "x")
        self.assertTrue(described["text"])

    def test_codes_whose_reason_varies_do_not_assert_one(self):
        # The corpus gives each descoped role and deferral its own reason (replaced by an
        # explicit ECB role, denominator already embedded, no free source ...); the
        # register text must defer to that detail instead of claiming one.
        texts = load_register()["phase2"]
        for code in ("role_descoped_by_phase1_revision", "deferred_research_extension",
                     "history_starts_with_archive_captures"):
            self.assertNotIn("because", texts[code])
            self.assertNotIn("no free source", texts[code])
            self.assertNotIn("no accepted inputs", texts[code])
            self.assertIn("given with it", texts[code])

    def test_unmapped_code_raises(self):
        with self.assertRaises(UnmappedLimitation):
            describe({"code": "not_a_code"})

    def test_method_limitations_replace_hand_typed_strings(self):
        for analysis_id in ("P06", "P07", "F03"):
            items = method_limitations(analysis_id)
            self.assertEqual(len(items), 3)
            self.assertTrue(all(item["code"] and item["text"] for item in items))
        self.assertEqual(method_limitations("XYZ"), [])


if __name__ == "__main__":
    unittest.main()
