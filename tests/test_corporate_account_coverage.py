"""Native account-field coverage and the canonical raw-evidence boundary."""
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from finance_dashboard.corporate_account_coverage import (
    SOURCE_IDS, UN_INVESTIGATION_FILES, _required_coverage, _retained_inputs,
    inventory_eurostat_account_rows, inventory_oecd_account_rows,
    read_corporate_account_coverage, read_un_corporate_source_investigation,
)
from finance_dashboard.source_reconciliation import EvidenceError


FIXTURE = Path(__file__).parent / "fixtures" / "corporate_accounts"


class CorporateAccountCoverageTests(unittest.TestCase):
    def test_exact_native_oecd_fields_keep_sector_and_industry_scopes(self):
        inventory = inventory_oecd_account_rows((FIXTURE / "oecd_native_dimension_excerpt.csv").read_bytes())
        self.assertEqual(len(inventory), 13)
        identities = {(item["sector"], item["accounting_entry"], item["transaction"]): item for item in inventory}
        self.assertIn(("S11", "D", "B1G"), identities)
        self.assertIn(("S12", "D", "B1G"), identities)
        self.assertEqual(identities[("S1", "D", "B1G")]["account_scope"], "whole_economy")
        self.assertEqual(identities[("S11", "D", "B1G")]["account_scope"], "institutional_sector")
        self.assertEqual(identities[("S11", "D", "B1G")]["unit_multiplier"], 6)
        coverage = _required_coverage(inventory)
        for sector in ("S11", "S12"):
            self.assertEqual(coverage["gross_operating_surplus"][sector]["country_year_pairs"], 1)
            self.assertEqual(coverage["gross_value_added"][sector]["country_year_pairs"], 1)
            for variable in ("compensation_of_employees", "net_operating_surplus", "consumption_of_fixed_capital",
                             "other_taxes_less_subsidies_on_production", "net_fixed_capital_stock"):
                self.assertEqual(coverage[variable][sector]["country_year_pairs"], 0)
                self.assertEqual(coverage[variable][sector]["status"], "not_present_in_retained_queried_originals")
                self.assertFalse(coverage[variable][sector]["global_source_availability_assessed"])
        self.assertEqual(coverage["matched_industry_gross_value_added"]["country_year_pairs"], 0)
        whole_economy_only = [identities[("S1", "D", "B1G")]]
        self.assertEqual(_required_coverage(whole_economy_only)["gross_value_added"]["S11"]["country_year_pairs"], 0)

    def test_native_eurostat_variable_periods_and_ratio_do_not_become_level_gva(self):
        inventory = [item for index in range(3) for item in inventory_eurostat_account_rows(
            (FIXTURE / f"flows-{index}.json").read_bytes(), dataset="nasa_10_nf_tr")]
        self.assertEqual([(item["sector"], item["transaction"], item["coverage"]["country_year_pairs"])
                          for item in inventory], [("S11", "B2A3G", 27), ("S12", "B2A3G", 27), ("S1", "B1GQ", 24)])
        for item in inventory:
            self.assertEqual(item["coverage"]["geographies_ever_reported"], 1)
            self.assertEqual(list(item["coverage"]["country_periods"]), ["EU27_2020"])
        ratio = inventory_eurostat_account_rows((FIXTURE / "ratio-0.json").read_bytes(), dataset="nasa_10_ki")[0]
        self.assertEqual(ratio["account_scope"], "published_sector_ratio")
        self.assertEqual(ratio["unit_measure"], "PC")
        self.assertEqual(ratio["coverage"]["country_year_pairs"], 27)
        self.assertEqual(_required_coverage(inventory + [ratio])["gross_value_added"]["S11"]["country_year_pairs"], 0)

    def test_existing_boundary_checks_every_raw_dependency_before_inventory(self):
        definition = {"id": SOURCE_IDS[0], "provider": "OECD_CORPORATE_GDPWEIGHTED", "source_key": "native-query"}
        with patch("finance_dashboard.corporate_account_coverage.constructed_source",
                   side_effect=EvidenceError("source_hash_mismatch")) as boundary, patch(
                "finance_dashboard.corporate_account_coverage._selected_manifest", side_effect=AssertionError("unchecked source used")):
            with self.assertRaisesRegex(EvidenceError, "source_hash_mismatch"):
                _retained_inputs(Path("unused"), definition)
            self.assertEqual(boundary.call_count, 1)
        sources = [{"file": f"response-{index}.bin", "url": f"https://example.test/{index}",
                    "sha256": str(index) * 64, "bytes": 1} for index in range(3)]
        selected = (datetime.now(timezone.utc), "a" * 64, Path("bundle/manifest.json"), {"sources": sources}, "acquisition_receipt")
        with patch("finance_dashboard.corporate_account_coverage.constructed_source",
                   return_value=({}, {"source_manifest_sha256": "a" * 64})), patch(
                "finance_dashboard.corporate_account_coverage._selected_manifest", return_value=selected), patch(
                "finance_dashboard.corporate_account_coverage._original_file", side_effect=[(b"0", "0"), (b"1", "1"), (b"2", "2")]) as original:
            raw, proof = _retained_inputs(Path("unused"), definition)
        self.assertEqual(raw, [b"0", b"1", b"2"])
        self.assertEqual(original.call_count, 3)
        self.assertTrue(all(call.kwargs == {"binary": True} for call in original.call_args_list))
        self.assertTrue(proof["original_source_hash_verified"])

    def test_changed_receipt_cannot_mix_validated_source_and_new_inputs(self):
        definition = {"id": SOURCE_IDS[0], "provider": "OECD_CORPORATE_GDPWEIGHTED", "source_key": "native-query"}
        selected = (datetime.now(timezone.utc), "b" * 64, Path("bundle/manifest.json"), {"sources": []}, "acquisition_receipt")
        with patch("finance_dashboard.corporate_account_coverage.constructed_source",
                   return_value=({}, {"source_manifest_sha256": "a" * 64})), patch(
                "finance_dashboard.corporate_account_coverage._selected_manifest", return_value=selected):
            with self.assertRaisesRegex(Exception, "selection changed"):
                _retained_inputs(Path("unused"), definition)

    def test_un_investigation_is_pinned_to_native_page_receipts_and_error_bodies(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertFalse(read_un_corporate_source_investigation(root)["original_source_hash_verified"])
            parent = root / "multinationals" / "2026-11-04"
            for name in UN_INVESTIGATION_FILES:
                target = parent / name; target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(FIXTURE / "un-investigation" / name, target)
            result = read_un_corporate_source_investigation(root)
            self.assertTrue(result["original_source_hash_verified"])
            self.assertEqual(result["correct_s11_operating_surplus_item"], "10")
            self.assertIn("non-produced", result["prior_reference_actual_label"])
            self.assertEqual([record["http_status"] for record in result["export_acquisitions"]], [404, 404])
            self.assertFalse(result["country_period_coverage_measured"])
            receipt = parent / "un-sector/download-errors.json"
            changed = json.loads(receipt.read_text()); changed[0]["http_status"] = 200
            receipt.write_text(json.dumps(changed))
            self.assertEqual(read_un_corporate_source_investigation(root)["status"], "invalid_original_un_source_investigation")

    def test_missing_originals_never_turn_into_measured_zero_global_availability(self):
        with TemporaryDirectory() as directory:
            result = read_corporate_account_coverage(Path(directory))
        self.assertEqual(result["status"], "missing_original_corporate_account_coverage")
        self.assertEqual(result["source_count"], 0)
        missing = result["required_variable_coverage"]["compensation_of_employees"]
        self.assertIsNone(missing["country_year_pairs"])
        self.assertEqual(missing["status"], "no_validated_retained_originals")
        self.assertFalse(missing["global_source_availability_assessed"])

    def test_reader_keeps_country_counts_source_specific_and_reports_query_absences(self):
        def retained(_root, definition):
            sid = definition["id"]
            if sid == SOURCE_IDS[0]:
                raw = [(FIXTURE / "oecd_native_dimension_excerpt.csv").read_bytes(), b"validated weight", b"validated local GDP"]
            elif sid == SOURCE_IDS[1]:
                raw = [(FIXTURE / f"flows-{i}.json").read_bytes() for i in range(3)]
            else:
                raw = [(FIXTURE / "ratio-0.json").read_bytes()]
            return raw, {"series_id": sid, "original_source_hash_verified": True,
                         "sources": [{"file": f"response-{i}.bin"} for i in range(len(raw))]}
        with TemporaryDirectory() as directory, patch(
                "finance_dashboard.corporate_account_coverage._retained_inputs", side_effect=retained):
            report = read_corporate_account_coverage(Path(directory))
        self.assertEqual(report["source_count"], 7)
        self.assertEqual(report["native_field_combinations"], 17)
        self.assertTrue(report["original_source_hash_verified"])
        surplus = report["required_variable_coverage"]["gross_operating_surplus"]
        self.assertIsNone(surplus["country_year_pairs"])
        self.assertEqual(surplus["source_coverage"][SOURCE_IDS[0]]["S11"]["country_year_pairs"], 1)
        self.assertEqual(surplus["source_coverage"][SOURCE_IDS[1]]["S11"]["country_year_pairs"], 27)
        for variable in ("compensation_of_employees", "net_operating_surplus", "consumption_of_fixed_capital",
                         "other_taxes_less_subsidies_on_production", "net_fixed_capital_stock",
                         "matched_industry_gross_value_added"):
            item = report["required_variable_coverage"][variable]
            self.assertEqual(item["country_year_pairs"], 0)
            self.assertEqual(item["validated_retained_sources_checked"], 3)
            self.assertFalse(item["global_source_availability_assessed"])
