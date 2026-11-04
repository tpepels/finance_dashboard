"""Targeted original-workbook and source-boundary checks for MNE evidence."""
import csv
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import zipfile

import unittest

from finance_dashboard.bis import ProviderError
from finance_dashboard.multinational_sources import (
    SOURCE_FILES, _register_summary, audit_amne_sources, audit_meip_sources,
    parse_meip_indicators, read_amne_evidence, read_meip_evidence,
    store_multinational_source,
)


FIXTURE = Path(__file__).parent / "fixtures" / "multinationals"


def amne_payloads():
    return {name: (FIXTURE / name).read_bytes() for name in SOURCE_FILES["amne"]}


class MultinationalOriginalTests(unittest.TestCase):
    def test_original_meip_fy2024_workbook_excludes_subtotal_and_retains_missing(self):
        result = parse_meip_indicators((FIXTURE / "OECD_UNSD_MEIP_MNE-Indicators_2024.xlsx").read_bytes())
        assert len(result["records"]) == 500
        assert len({r["hq_country"] for r in result["records"]}) == 34
        assert [r["reason"] for r in result["excluded_non_entity_rows"]] == ["blank_row", "unnamed_revenue_subtotal"]
        first = result["records"][0]
        assert first["parent_mne"] == "3M Co"
        assert first["net_profit_usd"] == "4188000000.0"
        assert first["unit_multiplier"] == 0 and first["source_fiscal_label"] == "FY2024"
        assert first["fiscal_end"] is None and not first["consolidation_scope_verified"]
        assert sum(r["rd_usd"] is None for r in result["records"]) == 292
        assert all(r["net_profit_usd"] is not None for r in result["records"])
        assert any(float(r["net_profit_usd"]) < 0 for r in result["records"])
        assert not first["parent_attributable_income_verified"]


    def test_meip_register_retains_ambiguous_heads_and_missing_jurisdiction(self):
        rows = json.loads((FIXTURE / "register_rows_excerpt.json").read_text())
        rows[-1][2] = ""
        result = _register_summary(rows, {"3M Co", "BP PLC", "Absent company"})
        assert result["parents_with_multiple_head_rows"] == ["BP PLC"]
        assert result["missing_jurisdiction_rows"] == 1
        assert result["financial_parents_not_in_register"] == ["Absent company"]
        assert result["hierarchy_counts"]["Unknown"] == 1
        assert not result["ultimate_parent_deduplication_verified"]


    def test_meip_summary_never_claims_world_profit_or_earlier_financial_history(self):
        indicators = (FIXTURE / "OECD_UNSD_MEIP_MNE-Indicators_2024.xlsx").read_bytes()
        register = json.loads((FIXTURE / "register_rows_excerpt.json").read_text())
        original_workbook = __import__("finance_dashboard.multinational_sources", fromlist=["_workbook"])._workbook
        def select(raw, required):
            return {"Group Register": register} if raw == b"register-excerpt" else original_workbook(raw, required)
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as target:
            for name in ("MEIP_GlobalRegister_2023.xlsx", "MEIP_DigitalRegister_2023.xlsx"):
                target.writestr(name, b"fixture archive directory check")
        payloads = {"OECD_UNSD_MEIP_MNE-Indicators_2024.xlsx": indicators,
                    "OECD_UNSD_MEIP_Global-Register_2024.xlsx": b"register-excerpt",
                    "MEIP_31Dec2023.zip": archive.getvalue(), "MEIP_Methodology.pdf": b"%PDF-1.4"}
        with patch("finance_dashboard.multinational_sources._workbook", side_effect=select):
            report = audit_meip_sources(payloads)
        assert report["parent_records"] == 500
        assert report["variable_coverage"]["net_profit_usd"]["reported_parents"] == 500
        assert report["variable_coverage"]["rd_usd"]["missing_parents"] == 292
        assert not report["previous_release_financial_indicators_present"]
        assert not report["worldwide_population_verified"]
        assert not report["aggregate_produced"] and not report["first_publication_verified"]


    def test_amne_native_metadata_flags_and_undeclared_zero_year(self):
        report = audit_amne_sources(amne_payloads())
        assert report["underlying_icio_release"] == "January 2026"
        assert report["year_2023_projection_disclosed"]
        assert report["unit_multiplier"] == 6
        assert report["location_count"] == 81 and report["individual_economy_count"] == 80
        assert report["industry_count"] == 41
        assert report["years"] == [2000]
        assert report["bilateral_output"]["excluded_undeclared_years"][2024] == {
            "rows": 1, "nonzero_cells": 0, "missing_cells": 0}
        assert report["xvem"]["flags_by_variable"]["flag_go"] == {"e": 4}
        assert not report["xvem"]["complete_reported_grid"]
        assert not report["net_profit_reported"] and not report["firm_identifiers_reported"]
        assert any(r["revision"] == "Domestic MNE split" for r in report["source_revision_log"])
        assert not report["aggregate_produced"]


    def test_amne_rejects_duplicate_key_and_retains_source_missing_value(self):
        payloads = amne_payloads()
        payloads["aamne-xvem.csv"] += payloads["aamne-xvem.csv"].splitlines(keepends=True)[1]
        with self.assertRaisesRegex(ProviderError, "repeated observation"):
            audit_amne_sources(payloads)
        payloads = amne_payloads()
        table = list(csv.reader(io.StringIO(payloads["aamne-xvem.csv"].decode())))
        table[1][6] = "NA"
        output = io.StringIO(); csv.writer(output).writerows(table)
        payloads["aamne-xvem.csv"] = output.getvalue().encode()
        assert audit_amne_sources(payloads)["xvem"]["missing_values_by_variable"]["GVA"] == 1


    def test_multinational_original_bundle_is_rebuilt_and_tamper_detected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            assert read_amne_evidence(root)["status"] == "missing_original_amne_evidence"
            assert read_meip_evidence(root)["source_count"] == 0
            folder = store_multinational_source("amne", amne_payloads(), root=root)
            manifest = (folder / "manifest.json").read_bytes()
            result = read_amne_evidence(root)
            assert result["original_source_hash_verified"] and result["source_count"] == 4
            assert result["selection_method"] == "acquisition_receipt"
            assert result["acquisition_method"] == "imported_original_bytes"
            assert not result["first_publication_verified"]
            store_multinational_source("amne", amne_payloads(), root=root)
            assert (folder / "manifest.json").read_bytes() == manifest
            assert len(list((folder.parent / "retrievals").glob("*.json"))) == 2
            original = folder / "aamne-xvem.csv"
            original.write_bytes(original.read_bytes() + b"\n")
            with self.assertRaisesRegex(ProviderError, "evidence inconsistent"):
                read_amne_evidence(root)
