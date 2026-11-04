"""Original ICIO shape, source identity and tax-inclusive accounting."""
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from finance_dashboard.icio import audit_matrix, readme_dimensions, store_icio_package, read_icio_evidence


class IcioTests(unittest.TestCase):
    def test_accounts_require_taxes_and_preserve_negative_inventory_and_value_added(self):
        body = "V1,AAA_A01,BBB_A01,AAA_INVNT,OUT\nAAA_A01,1,2,5,8\nBBB_A01,3,4,-1,6\nTLS,-1,2,2,3\nVA,5,-2,0,0\nOUT,8,6,0,0\n"
        report = audit_matrix(io.StringIO(body), ["AAA_A01", "BBB_A01"], ["AAA_INVNT"])
        self.assertTrue(report["accounting_passed"])
        self.assertEqual(report["negative_cells"], 3)
        self.assertEqual(report["identities"]["inputs_plus_taxes_plus_value_added"], "column_sum(Z)+TLS+VA=OUT")
        bad = body.replace("TLS,-1,2", "TLS,0,2")
        self.assertFalse(audit_matrix(io.StringIO(bad), ["AAA_A01", "BBB_A01"], ["AAA_INVNT"])["accounting_passed"])

    def test_partial_swapped_duplicate_or_nonfinite_matrix_cannot_pass(self):
        body = "V1,AAA_A01,AAA_INVNT,OUT\nAAA_A01,1,2,3\nTLS,0,0,0\nVA,2,0,0\nOUT,3,0,0\n"
        for broken in (body.replace("AAA_A01,1,2,3", "AAA_A01,1,2"),
                       body.replace("VA,2,0,0\n", ""),
                       body.replace("AAA_A01,1,2,3", "AAA_A01,NaN,2,3"),
                       body.replace("TLS,0,0,0", "VA,0,0,0")):
            with self.assertRaises(ValueError):
                audit_matrix(io.StringIO(broken), ["AAA_A01"], ["AAA_INVNT"])

    def test_original_readme_declares_actual_dimensions_units_and_native_codes(self):
        original = Path(__file__).parent / "fixtures" / "icio" / "ReadMe_ICIO_small.xlsx"
        result = readme_dimensions(original.read_bytes())
        self.assertEqual(len(result["industry_codes"]), 4050)
        self.assertEqual(len(result["final_demand_codes"]), 486)
        self.assertEqual(result["unit"], "current_USD_million")
        self.assertEqual(result["country_count"], 81)
        self.assertEqual(result["industry_count"], 50)
        self.assertEqual(result["industry_codes"][0], "AGO_A01")
        self.assertEqual(result["industry_codes"][-1], "ROW_T")

    def test_absent_original_matrix_is_not_an_empty_validated_matrix(self):
        with TemporaryDirectory() as temp:
            result = read_icio_evidence(Path(temp))
            self.assertEqual(result["status"], "missing_original_matrix")
            self.assertFalse(result["full_history_verified"])

    @unittest.skipUnless(os.environ.get("TEST_ICIO_PACKAGE"), "Requires original 55MB World Bank ICIO replication package")
    def test_full_original_2022_matrix_preserves_source_accounting_failures(self):
        source = Path(os.environ["TEST_ICIO_PACKAGE"])
        readme = Path(__file__).parent / "fixtures" / "icio" / "ReadMe_ICIO_small.xlsx"
        with TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = store_icio_package(source, readme, root)
            result = read_icio_evidence(root)
            self.assertEqual(result["status"], "original_matrix_accounting_failed")
            self.assertTrue(result["original_source_hash_verified"])
            self.assertEqual(result["industry_cells"], 16402500)
            self.assertEqual(result["final_demand_cells"], 1968300)
            self.assertFalse(result["accounting_passed"])
            self.assertEqual(len(result["row_accounting_failures"]), 123)
            self.assertEqual(len(result["column_accounting_failures"]), 26)
            self.assertEqual(result["maximum_row_residual"], "238.6058")
            self.assertEqual(result["maximum_column_residual"], "82.0320")
            self.assertEqual(result["output_vector_mismatches"], [])
            self.assertFalse(result["full_history_verified"])
            self.assertEqual(result["matrix_sha256"], "fbab8fd2727bda9fd8c6cfee8227816db82d33bef6aa4b90194ca5dcbc5ad14b")
            self.assertEqual(store_icio_package(source, readme, root), bundle)
            (bundle / "audit.json").write_text('{"accounting_passed":true}')
            with self.assertRaises(ValueError): read_icio_evidence(root)
