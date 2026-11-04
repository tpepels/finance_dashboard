"""Actual retained publisher rows remain partial native issuer evidence."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import shutil
import unittest

from finance_dashboard.research_artifacts import research_artifact_evidence


FIXTURES = Path(__file__).parent / "fixtures/profits/taiwan-2026q3"
EDITION = "2026-11-04-59569897b7cc"


class TaiwanProfitTests(unittest.TestCase):
    def test_parent_income_is_not_replaced_with_total_income_or_comprehensive_income(self):
        from finance_dashboard.taiwan_profits import parse_taiwan_income
        original = (FIXTURES / "t187ap06_O_ci.csv").read_bytes()
        result = parse_taiwan_income(original, board="O")
        self.assertEqual(len(result["records"]), 60)
        missing = next(r for r in result["records"] if r["company_code"] == "2035")
        self.assertEqual(missing["reported_total_period_income_native"], "-180835.00")
        self.assertIsNone(missing["parent_attributable_income_native"])
        self.assertEqual(missing["native_fiscal_year"], "115")
        self.assertEqual(missing["reported_reference_year"], 2026)
        self.assertEqual(missing["native_quarter"], "3")
        self.assertEqual(missing["reported_table_date"], "2026-11-04")
        self.assertIsNone(missing["native_currency"])
        self.assertIsNone(missing["native_scale"])
        self.assertFalse(missing["annual_period_verified"])
        self.assertFalse(missing["consolidation_scope_verified"])
        self.assertFalse(missing["first_publication_verified"])
        loss = next(r for r in result["records"] if r["parent_attributable_income_native"] is not None
                    and r["parent_attributable_income_native"].startswith("-"))
        self.assertTrue(loss["parent_attributable_income_native"].startswith("-"))

    def test_retained_originals_have_compact_scientific_limits_and_no_read_mutations(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            destination = root / "profit-samples" / EDITION
            shutil.copytree(FIXTURES, destination)
            before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            result = research_artifact_evidence(root, kinds={"taiwan_profits"})["taiwan_profits"]
            self.assertTrue(result["original_source_hash_verified"])
            self.assertEqual(result["issuer_records"], 135)
            self.assertEqual(result["records_with_parent_income"], 123)
            self.assertEqual(result["negative_parent_income_records"], 14)
            self.assertEqual(result["reported_reference_years"], [2026])
            self.assertEqual(result["reported_native_quarters"], ["3"])
            self.assertEqual(result["source_count"], 2)
            self.assertFalse(result["native_currency_scale_verified"])
            self.assertFalse(result["annual_period_verified"])
            self.assertFalse(result["worldwide_population_verified"])
            self.assertFalse(result["aggregate_produced"])
            self.assertFalse(result["first_publication_verified"])
            self.assertEqual({p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}, before)
            for private in (temp, "issuer_name", "parent_attributable_income_native", "大統益"):
                self.assertNotIn(private, json.dumps(result, ensure_ascii=False))

    def test_tampered_source_manifest_or_hash_ledger_fails_closed(self):
        for name in ("t187ap06_L_ci.csv", "acquisition_manifest.json", "SHA256SUMS"):
            with self.subTest(name=name), TemporaryDirectory() as temp:
                root = Path(temp)
                destination = root / "profit-samples" / EDITION
                shutil.copytree(FIXTURES, destination)
                (destination / name).write_bytes(b"private tampering")
                result = research_artifact_evidence(root, kinds={"taiwan_profits"})["taiwan_profits"]
                self.assertEqual(result["status"], "invalid_original_taiwan_profit_evidence")
                self.assertFalse(result["original_source_hash_verified"])
                self.assertNotIn("private", json.dumps(result))

    def test_wrong_table_schema_repeated_issuer_or_invalid_decimal_is_rejected(self):
        from finance_dashboard.taiwan_profits import parse_taiwan_income
        original = (FIXTURES / "t187ap06_L_ci.csv").read_bytes()
        lines = original.decode("utf-8-sig").splitlines()
        cases = [original.replace("淨利（淨損）歸屬於母公司業主".encode(), "其他利益".encode()),
                 ("\n".join([*lines, lines[1]])).encode(),
                 original.replace(b'"1284559.00"', b'"NaN"')]
        for raw in cases:
            with self.assertRaises(ValueError):
                parse_taiwan_income(raw, board="L")
