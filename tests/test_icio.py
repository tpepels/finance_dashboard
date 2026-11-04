"""Original ICIO shape, source identity and tax-inclusive accounting."""
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from hashlib import sha256
from unittest.mock import patch

from finance_dashboard.icio import audit_matrix, diagnose_icio_package, readme_dimensions, store_icio_package, read_icio_evidence
from finance_dashboard import icio
from finance_dashboard.research_artifacts import research_artifact_evidence


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

    def test_opt_in_signed_residual_details_do_not_rewrite_prior_audit_schema(self):
        body = "V1,AAA_A01,BBB_A01,AAA_INVNT,OUT\nAAA_A01,1,2,5,7\nBBB_A01,3,4,-1,6\nTLS,-1,2,2,3\nVA,5,-2,0,0\nOUT,7,6,0,0\n"
        basic = audit_matrix(io.StringIO(body), ["AAA_A01", "BBB_A01"], ["AAA_INVNT"])
        detailed = audit_matrix(io.StringIO(body), ["AAA_A01", "BBB_A01"], ["AAA_INVNT"], include_residuals=True)
        self.assertNotIn("residual_diagnostics", basic)
        self.assertEqual({key: value for key, value in detailed.items() if key != "residual_diagnostics"}, basic)
        details = detailed["residual_diagnostics"]
        self.assertEqual(details["rows"], [{"code": "AAA_A01", "residual": "1", "gross_output": "7"}])
        self.assertEqual(details["columns"], [{"code": "AAA_A01", "residual": "1", "gross_output": "7"}])
        self.assertEqual(details["signed_row_residual_total"], "1")
        self.assertEqual(details["signed_column_residual_total"], "1")
        self.assertEqual(details["column_failure_counts_by_country"], {"AAA": 1})
        self.assertEqual(details["row_failure_counts_by_industry"], {"A01": 1})
        self.assertEqual(details["cause_status"], "unexplained_original_source_residuals")

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
            self.assertEqual(result["release_comparison"]["status"], "missing_original_release_comparison")
            self.assertFalse(result["release_comparison"]["original_source_hashes_verified"])

    def test_historical_original_uses_same_accounting_and_receipts_without_certifying_full_history(self):
        body = b"V1,AAA_A01,AAA_INVNT,OUT\nAAA_A01,1,2,4\nTLS,0,0,0\nVA,3,0,0\nOUT,4,0,0\n"
        descriptor = {"sha256": sha256(body).hexdigest(), "bytes": len(body)}
        dimensions = {"industry_codes": ["AAA_A01"], "final_demand_codes": ["AAA_INVNT"],
                      "unit": "current_USD_million", "country_count": 1, "industry_count": 1}
        readme = Path(__file__).parent / "fixtures" / "icio" / "ReadMe_ICIO_small.xlsx"
        with TemporaryDirectory() as temp, patch.dict(icio.HISTORY_MATRICES, {2021: descriptor}, clear=True), \
                patch.object(icio, "readme_dimensions", return_value=dimensions):
            root = Path(temp)
            matrix = root / "2021_SML.csv"
            matrix.write_bytes(body)
            audit = icio._historical_audit(str(matrix), str(readme), 2021, descriptor["sha256"])
            pin = (descriptor["sha256"], icio.README_SHA256, 2021, "regular-history-accounting-v1")
            pins = patch.object(icio, "PINNED_AUDITS", {pin: sha256(icio.canonical_bytes(audit)).hexdigest()}, create=True)
            pins.start()
            self.addCleanup(pins.stop)
            bundle = icio.store_icio_matrix(matrix, readme, 2021, root / "evidence")
            manifest = (bundle / "manifest.json").read_bytes()
            with patch.object(icio, "_historical_audit", side_effect=AssertionError("reader must not repeat full audit")):
                result = read_icio_evidence(root / "evidence")
            self.assertEqual(result["status"], "original_matrix_accounting_failed")
            self.assertEqual(result["historical_coverage"]["verified_years"], [2021])
            self.assertEqual(result["historical_coverage"]["missing_years"], list(range(1995, 2021)) + [2022])
            self.assertFalse(result["full_history_verified"])
            self.assertFalse(result["first_publication_verified"])
            self.assertEqual(result["historical_matrices"][0]["residual_diagnostics"]["rows"][0]["residual"], "-1")
            self.assertEqual(result["historical_matrices"][0]["matrix_sha256"], descriptor["sha256"])
            self.assertEqual(icio.store_icio_matrix(matrix, readme, 2021, root / "evidence"), bundle)
            self.assertEqual((bundle / "manifest.json").read_bytes(), manifest)
            self.assertEqual(len(list((bundle.parent / "retrievals").glob("*.json"))), 2)
            (bundle / "matrix.csv").write_bytes(body.replace(b",1,2,4", b",1,3,4"))
            with self.assertRaises(ValueError):
                read_icio_evidence(root / "evidence")

    def test_1995_replica_keeps_distinct_declared_release_and_canonical_source_route(self):
        body = b"V1,AAA_A01,AAA_INVNT,OUT\nAAA_A01,1,2,3\nTLS,0,0,0\nVA,2,0,0\nOUT,3,0,0\n"
        descriptor = {"sha256": sha256(body).hexdigest(), "bytes": len(body),
                      "source_url": "https://reproducibility.worldbank.org/catalog/601/download/1785/RR_THA_2026_689.zip",
                      "replica": "RR_THA_2026_689", "replica_declared_update": "October 2025",
                      "package_sha256": "f" * 64, "archive_member": "RR_THA_2026_689/1995_SML.csv"}
        dimensions = {"industry_codes": ["AAA_A01"], "final_demand_codes": ["AAA_INVNT"],
                      "unit": "current_USD_million", "country_count": 1, "industry_count": 1}
        readme = Path(__file__).parent / "fixtures" / "icio" / "ReadMe_ICIO_small.xlsx"
        with TemporaryDirectory() as temp, patch.dict(icio.HISTORY_MATRICES, {1995: descriptor}, clear=True), \
                patch.object(icio, "readme_dimensions", return_value=dimensions):
            root = Path(temp)
            matrix = root / "1995_SML.csv"
            matrix.write_bytes(body)
            audit = icio._historical_audit(str(matrix), str(readme), 1995, descriptor["sha256"])
            self.assertEqual(audit["replica"], "RR_THA_2026_689")
            self.assertEqual(audit["replica_declared_update"], "October 2025")
            self.assertEqual(audit["source_url"], descriptor["source_url"])
            self.assertEqual(audit["matrix_archive_member"], descriptor["archive_member"])
            self.assertEqual(audit["package_sha256"], descriptor["package_sha256"])
            self.assertFalse(audit["common_update_verified"])
            pin = (descriptor["sha256"], icio.README_SHA256, 1995, "regular-history-accounting-v1")
            with patch.object(icio, "PINNED_AUDITS", {pin: sha256(icio.canonical_bytes(audit)).hexdigest()}):
                bundle = icio.store_icio_matrix(matrix, readme, 1995, root / "evidence")
                result = read_icio_evidence(root / "evidence")
            self.assertTrue(result["accounting_passed"])
            self.assertEqual(result["historical_coverage"]["verified_years"], [1995])
            self.assertEqual(result["historical_coverage"]["missing_years"], list(range(1996, 2023)))
            self.assertFalse(result["historical_coverage"]["common_update_verified"])
            manifest = json.loads((bundle / "manifest.json").read_text())
            self.assertEqual(manifest["sources"]["matrix"], descriptor["source_url"])

    def test_unpinned_historical_original_is_rejected_before_archive(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            matrix = root / "2021_SML.csv"
            matrix.write_bytes(b"not the identified original")
            readme = Path(__file__).parent / "fixtures" / "icio" / "ReadMe_ICIO_small.xlsx"
            with self.assertRaisesRegex(ValueError, "icio_pinned_original_identity_mismatch"):
                icio.store_icio_matrix(matrix, readme, 2021, root / "evidence")
            self.assertFalse((root / "evidence").exists())

    @unittest.skipUnless(os.environ.get("TEST_ICIO_1995"), "Requires original 1995 OECD replica matrix")
    def test_full_original_1995_balances_without_certifying_history_or_common_update(self):
        original = Path(os.environ["TEST_ICIO_1995"])
        readme = Path(__file__).parent / "fixtures" / "icio" / "ReadMe_ICIO_small.xlsx"
        with TemporaryDirectory() as temp:
            root = Path(temp)
            icio.store_icio_matrix(original, readme, 1995, root)
            result = read_icio_evidence(root)
            self.assertTrue(result["accounting_passed"])
            self.assertEqual(result["maximum_row_residual"], "0.0230")
            self.assertEqual(result["maximum_column_residual"], "0.0157")
            self.assertEqual(result["historical_coverage"]["verified_years"], [1995])
            self.assertFalse(result["full_history_verified"])
            self.assertFalse(result["common_update_verified"])
            self.assertFalse(result["first_publication_verified"])
            self.assertEqual(result["replica_declared_update"], "October 2025")
            self.assertEqual(result["matrix_sha256"], icio.OCTOBER_2025_MATRICES[1995]["sha256"])

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
            partial = research_artifact_evidence(root)["icio"]
            self.assertEqual(partial, result)
            self.assertEqual(partial["year"], 2022)
            self.assertTrue(partial["original_source_hash_verified"])
            self.assertFalse(partial["full_history_verified"])
            self.assertFalse(partial["accounting_passed"])
            detailed = diagnose_icio_package(source, readme)
            details = detailed["residual_diagnostics"]
            self.assertEqual(len(details["rows"]), 123)
            self.assertEqual(len(details["columns"]), 26)
            self.assertEqual(details["rows"][0], {"code": "USA_L", "residual": "238.6058", "gross_output": "4501781.2474"})
            self.assertEqual(details["columns"][0], {"code": "CHN_L", "residual": "-82.0320", "gross_output": "1237186.6496"})
            self.assertEqual(details["column_failure_counts_by_country"], {"CHN": 26})
            self.assertEqual(details["signed_row_residual_total"], "670.1066")
            self.assertEqual(details["signed_column_residual_total"], "-93.3633")
            # Diagnostic acquisition must not rewrite any prior sealed audit.
            stored_audit = json.loads((bundle / "audit.json").read_bytes())
            self.assertNotIn("residual_diagnostics", stored_audit)
            self.assertEqual(stored_audit["maximum_row_residual"], detailed["maximum_row_residual"])
            self.assertEqual(store_icio_package(source, readme, root), bundle)
            (bundle / "audit.json").write_text('{"accounting_passed":true}')
            with self.assertRaises(ValueError): read_icio_evidence(root)
            invalid = research_artifact_evidence(root)["icio"]
            self.assertEqual(invalid["status"], "invalid_original_matrix_evidence")
            self.assertFalse(invalid["original_source_hash_verified"])
