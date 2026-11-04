"""Artifact availability is verified separately from macro-series bindings."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import json

from finance_dashboard.research_artifacts import research_artifact_evidence
from finance_dashboard.cvm_profits import store_cvm_source
from finance_dashboard.ucits_holdings import parse_holdings_csv, store_ucits_source
from finance_dashboard.sec_holdings import parse_nport, store_source_bundle
from test_cvm_profits import excerpt_package


class ResearchArtifactTests(unittest.TestCase):
    def test_scoped_evaluation_does_not_read_unrelated_original_archives(self):
        with TemporaryDirectory() as temp, patch("finance_dashboard.research_artifacts.read_icio_evidence",
                side_effect=AssertionError("unrelated large matrix must not be read")):
            result = research_artifact_evidence(Path(temp), kinds={"cvm"})
            self.assertEqual(set(result), {"cvm"})
            self.assertFalse(result["cvm"]["original_source_hash_verified"])

    def test_missing_matrix_is_explicit_and_loader_does_not_create_files(self):
        with TemporaryDirectory() as temp:
            root = Path(temp) / "missing"
            result = research_artifact_evidence(root)
            self.assertEqual(result["icio"]["status"], "missing_original_matrix")
            self.assertFalse(result["icio"]["full_history_verified"])
            self.assertEqual(result["tiva"]["status"], "missing_original_tiva_pair")
            self.assertEqual(result["cvm"]["status"], "missing_original_cvm_evidence")
            self.assertEqual(result["sec_holdings"]["status"], "not_checked_original_positions")
            self.assertEqual(result["ucits_holdings"]["status"], "not_checked_original_positions")
            self.assertFalse(root.exists())

    def test_explicit_missing_holdings_differs_from_not_checked_and_never_uses_environment(self):
        with TemporaryDirectory() as temp:
            root = Path(temp) / "absent"
            with patch("finance_dashboard.research_artifacts.read_position_source", side_effect=AssertionError("unexpected read")):
                result = research_artifact_evidence(root, holdings_root=root / "holdings")
            self.assertEqual(result["sec_holdings"]["status"], "missing_original_positions")
            self.assertEqual(result["ucits_holdings"]["status"], "missing_original_ucits_positions")
            self.assertFalse(result["sec_holdings"]["original_source_hash_verified"])
            self.assertFalse(root.exists())

    def test_verified_cvm_and_ucits_sources_are_compact_and_independently_fail_closed(self):
        fixtures = Path(__file__).parent / "fixtures/holdings"
        original = (fixtures / "swda-2026-11-03-excerpt.csv").read_bytes()
        with TemporaryDirectory() as temp:
            root = Path(temp)
            cvm = store_cvm_source(excerpt_package(), year=2025, root=root)
            facts = parse_holdings_csv(original)
            ucits = store_ucits_source(original, facts=facts, root=root / "holdings")
            before = sorted((str(p.relative_to(root)), p.read_bytes()) for p in root.rglob("*") if p.is_file())
            result = research_artifact_evidence(root, holdings_root=root / "holdings")
            self.assertTrue(result["cvm"]["original_source_hash_verified"])
            self.assertEqual(result["cvm"]["verified_years"], [2025])
            self.assertGreater(result["cvm"]["issuer_records"], 0)
            self.assertIn("evidence_retrieved_at_utc", result["cvm"]["sources"][0])
            self.assertGreater(len(result["cvm"]["sources"][0]["reported_fiscal_periods"]), 0)
            self.assertFalse(result["cvm"]["authority_receipt_is_first_publication"])
            self.assertFalse(result["cvm"]["worldwide_population_verified"])
            self.assertFalse(result["cvm"]["aggregate_produced"])
            self.assertTrue(result["ucits_holdings"]["original_source_hash_verified"])
            self.assertEqual(result["ucits_holdings"]["position_coverage"]["positions"], len(facts["positions"]))
            self.assertGreater(result["ucits_holdings"]["position_coverage"]["positions_with_reported_currency"], 0)
            self.assertEqual(result["ucits_holdings"]["cash_positions"], 1)
            self.assertEqual(result["ucits_holdings"]["unclassified_fx_positions"], 1)
            self.assertFalse(result["ucits_holdings"]["original_index_constituents_verified"])
            source = result["ucits_holdings"]["sources"][0]
            self.assertIn("immutable_manifest_retrieved_at_utc", source)
            self.assertEqual(len(source["source_manifest_sha256"]), 64)
            self.assertFalse(source["nav_accounting_identity_checked"])
            self.assertIsNone(source["nav_accounting_identity_passed"])
            rendered = json.dumps(result)
            for private in (temp, "source_row", "issuer_name", "parent_attributable_income_native", "source_xml"):
                self.assertNotIn(private, rendered)
            after = sorted((str(p.relative_to(root)), p.read_bytes()) for p in root.rglob("*") if p.is_file())
            self.assertEqual(after, before)
            (ucits / "original.csv").write_bytes(b"damaged")
            failed = research_artifact_evidence(root, holdings_root=root / "holdings")
            self.assertEqual(failed["ucits_holdings"]["status"], "invalid_original_ucits_evidence")
            self.assertTrue(failed["cvm"]["original_source_hash_verified"])
            (cvm / "original.zip").write_bytes(b"damaged")
            failed = research_artifact_evidence(root, holdings_root=root / "holdings")
            self.assertEqual(failed["cvm"]["status"], "invalid_original_cvm_evidence")
            self.assertFalse(failed["cvm"]["original_source_hash_verified"])

    def test_sec_positions_report_only_verified_metadata_and_direct_identity_coverage(self):
        fixtures = Path(__file__).parent / "fixtures/holdings"
        original = (fixtures / "vt-2026-07-31-excerpt.xml").read_bytes()
        accession = "0000857489-26-000275"
        url = "https://www.sec.gov/Archives/edgar/data/857489/000085748926000275/primary_doc.xml"
        metadata = {"cik": 857489, "filings": {"recent": {"accessionNumber": [accession],
            "form": ["NPORT-P"], "filingDate": ["2026-09-28"], "acceptanceDateTime": ["2026-09-28T19:00:00"]}}}
        aggregate = parse_nport(original, instrument_id="vt", accession=accession, filing_url=url,
                                sec_metadata=metadata, expected_series_id="S000022482")
        with TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = store_source_bundle(original, sec_metadata=metadata, aggregate=aggregate, root=root / "holdings")
            result = research_artifact_evidence(root, holdings_root=root / "holdings")["sec_holdings"]
            self.assertTrue(result["original_source_hash_verified"])
            self.assertEqual(result["sources"][0]["holdings_date"], "2026-07-31")
            self.assertEqual(result["position_coverage"]["positions"], 2)
            self.assertEqual(result["position_coverage"]["positions_with_reported_issuer_lei"], 1)
            self.assertEqual(result["position_coverage"]["derivative_positions"], 1)
            self.assertTrue(result["sources"][0]["fund_accounting_identity_passed"])
            self.assertIn("acquisition_observed_at_utc", result["sources"][0])
            self.assertEqual(result["sources"][0]["publication_evidence"]["sec_acceptance_timestamp_unverified_timezone"],
                             "2026-09-28T19:00:00")
            self.assertFalse(result["sources"][0]["publication_evidence"]["first_public_dissemination_verified"])
            self.assertFalse(result["original_index_constituents_verified"])
            self.assertFalse(result["first_publication_verified"])
            self.assertFalse(result["ultimate_parent_mapping_verified"])
            for private in (temp, "Surgery Partners", "549300LC82HG33S19I03", "derivative_contracts", "source_xml"):
                self.assertNotIn(private, json.dumps(result))
            (bundle / "original.xml").write_bytes(b"private broken data")
            failed = research_artifact_evidence(root, holdings_root=root / "holdings")
            self.assertEqual(failed["sec_holdings"]["status"], "invalid_original_sec_evidence")
            self.assertEqual(failed["ucits_holdings"]["status"], "missing_original_ucits_positions")

    def test_malformed_or_empty_matrix_archive_fails_closed_without_private_exception(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            parent = root / "icio" / "regular-2025-2022"
            parent.mkdir(parents=True)
            result = research_artifact_evidence(root)
            self.assertEqual(result["icio"]["status"], "invalid_original_matrix_evidence")
            self.assertFalse(result["icio"]["original_source_hash_verified"])
            self.assertFalse(result["icio"]["full_history_verified"])
            self.assertNotIn(temp, str(result))
            (parent / "retrievals").mkdir()
            (parent / "retrievals" / "secret.json").write_text("not an original receipt with private tokens")
            self.assertEqual(research_artifact_evidence(root), result)
            self.assertNotIn("secret", str(result))
