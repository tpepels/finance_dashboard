"""Original release changes are localized without balancing either source."""
from decimal import Decimal
from pathlib import Path
import os
from hashlib import sha256
from unittest.mock import patch
from tempfile import TemporaryDirectory
import unittest

from finance_dashboard import icio_release_diagnostics as diagnostics


class IcioReleaseDiagnosticsTests(unittest.TestCase):
    def test_one_revised_cell_retains_failed_current_release_and_exact_delta_identity(self):
        older = "V1,AAA_A01,BBB_A01,AAA_INVNT,OUT\nAAA_A01,1,2,5,8\nBBB_A01,3,4,-1,6\nTLS,-1,2,2,3\nVA,5,-2,0,0\nOUT,8,6,0,0\n"
        newer = older.replace("AAA_A01,1,2,5,8", "AAA_A01,1,3,5,8")
        with TemporaryDirectory() as temp:
            root = Path(temp)
            left, right = root / "older.csv", root / "newer.csv"
            left.write_text(older)
            right.write_text(newer)
            result = diagnostics.compare_matrix_files(left, right, ["AAA_A01", "BBB_A01"], ["AAA_INVNT"])
            self.assertEqual(left.read_text(), older)
            self.assertEqual(right.read_text(), newer)
        self.assertTrue(result["older_accounting"]["accounting_passed"])
        self.assertFalse(result["newer_accounting"]["accounting_passed"])
        self.assertEqual(result["numerically_changed_cells"], {"intermediate_use": 1, "final_demand": 0,
            "industry_output": 0, "taxes": 0, "value_added": 0, "output_margin": 0})
        row = result["failed_row_changes"][0]
        self.assertEqual(row["code"], "AAA_A01")
        self.assertEqual(row["older_residual"], "0")
        self.assertEqual(row["newer_residual"], "1")
        self.assertEqual(row["changes"], {"intermediate_use": "1", "final_demand": "0", "published_output": "0"})
        col = result["failed_column_changes"][0]
        self.assertEqual(col["code"], "BBB_A01")
        self.assertEqual(col["changes"], {"intermediate_input": "1", "taxes": "0", "value_added": "0", "published_output": "0"})
        self.assertEqual(Decimal(col["newer_residual"]) - Decimal(col["older_residual"]), Decimal(col["residual_change"]))
        self.assertFalse(result["cause_verified"])

    def test_serialization_only_change_is_not_a_numeric_revision_and_wrong_original_is_rejected(self):
        body = "V1,AAA_A01,AAA_INVNT,OUT\nAAA_A01,1,2,3\nTLS,0,0,0\nVA,2,0,0\nOUT,3,0,0\n"
        with TemporaryDirectory() as temp:
            root = Path(temp)
            left, right = root / "older.csv", root / "newer.csv"
            left.write_text(body)
            right.write_text(body.replace("AAA_A01,1,2,3", "AAA_A01,1.0000,2,3"))
            result = diagnostics.compare_matrix_files(left, right, ["AAA_A01"], ["AAA_INVNT"])
            self.assertEqual(sum(result["numerically_changed_cells"].values()), 0)
            self.assertEqual(result["failed_row_changes"], [])
            with self.assertRaisesRegex(ValueError, "icio_release_comparison_original_identity_mismatch"):
                diagnostics.diagnose_2022_release_change(left, right, root / "readme.xlsx")

    def test_canonical_comparison_reuses_verified_current_source_and_rejects_changed_original(self):
        older = b"V1,AAA_A01,AAA_INVNT,OUT\nAAA_A01,1,2,3\nTLS,0,0,0\nVA,2,0,0\nOUT,3,0,0\n"
        newer = older.replace(b"AAA_A01,1,2,3", b"AAA_A01,1,3,3")
        old_descriptor = {"sha256": sha256(older).hexdigest(), "bytes": len(older)}
        new_descriptor = {"sha256": sha256(newer).hexdigest(), "bytes": len(newer)}
        dimensions = {"industry_codes": ["AAA_A01"], "final_demand_codes": ["AAA_INVNT"], "unit": "current_USD_million"}
        readme = Path(__file__).parent / "fixtures" / "icio" / "ReadMe_ICIO_small.xlsx"
        with TemporaryDirectory() as temp, patch.dict(diagnostics.OCTOBER_2025_MATRICES, {2022: old_descriptor}, clear=True), \
                patch.dict(diagnostics.HISTORY_MATRICES, {2022: new_descriptor}, clear=True), \
                patch.object(diagnostics, "readme_dimensions", return_value=dimensions):
            root = Path(temp)
            left, right = root / "older.csv", root / "newer.csv"
            left.write_bytes(older)
            right.write_bytes(newer)
            audit = diagnostics.diagnose_2022_release_change(left, right, readme)
            with patch.object(diagnostics, "PINNED_COMPARISON_SHA256", sha256(diagnostics.canonical_bytes(audit)).hexdigest()):
                bundle = diagnostics.store_2022_release_comparison(left, right, readme, root / "evidence")
                sealed = (bundle / "manifest.json").read_bytes()
                with patch.object(diagnostics, "compare_matrix_files", side_effect=AssertionError("reader must not recompute accounting")):
                    result = diagnostics.read_2022_release_comparison(root / "evidence", verified_newer_sha256=new_descriptor["sha256"])
                    missing = diagnostics.read_2022_release_comparison(root / "evidence", verified_newer_sha256=None)
                self.assertTrue(result["original_source_hashes_verified"])
                self.assertTrue(result["older_accounting"]["accounting_passed"])
                self.assertFalse(result["newer_accounting"]["accounting_passed"])
                self.assertEqual(result["newer_accounting"]["row_accounting_failures"], 1)
                self.assertFalse(missing["original_source_hashes_verified"])
                self.assertEqual((bundle / "manifest.json").read_bytes(), sealed)
                (bundle / "older.csv").write_bytes(newer)
                with self.assertRaisesRegex(ValueError, "icio_archive_hash_mismatch"):
                    diagnostics.read_2022_release_comparison(root / "evidence", verified_newer_sha256=new_descriptor["sha256"])

    @unittest.skipUnless(os.environ.get("TEST_ICIO_OCTOBER_2022") and os.environ.get("TEST_ICIO_CURRENT_2022"),
                         "Requires both exact original 2022 ICIO releases")
    def test_exact_originals_localize_release_difference_without_replacing_failed_source(self):
        readme = Path(__file__).parent / "fixtures" / "icio" / "ReadMe_ICIO_small.xlsx"
        result = diagnostics.diagnose_2022_release_change(Path(os.environ["TEST_ICIO_OCTOBER_2022"]),
            Path(os.environ["TEST_ICIO_CURRENT_2022"]), readme)
        self.assertEqual(sha256(diagnostics.canonical_bytes(result)).hexdigest(), diagnostics.PINNED_COMPARISON_SHA256)
        self.assertTrue(result["original_source_hashes_verified"])
        self.assertTrue(result["older_accounting"]["accounting_passed"])
        self.assertFalse(result["newer_accounting"]["accounting_passed"])
        self.assertEqual(len(result["failed_row_changes"]), 123)
        self.assertEqual(len(result["failed_column_changes"]), 26)
        self.assertEqual(result["numerically_changed_cells"]["intermediate_use"], 9552688)
        usa = result["failed_row_changes"][0]
        self.assertEqual((usa["code"], usa["older_residual"], usa["newer_residual"]),
                         ("USA_L", "-0.0048", "238.6058"))
        self.assertEqual(usa["changes"], {"intermediate_use": "-596.7961", "final_demand": "835.4067", "published_output": "0.0000"})
        china = result["failed_column_changes"][0]
        self.assertEqual((china["code"], china["older_residual"], china["newer_residual"]),
                         ("CHN_L", "-0.0075", "-82.0320"))
        self.assertEqual(china["changes"], {"intermediate_input": "1379.6798", "taxes": "-1379.6785", "value_added": "0.000", "published_output": "82.0258"})
        self.assertFalse(result["cause_verified"])
