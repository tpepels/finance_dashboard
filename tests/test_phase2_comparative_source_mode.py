"""Scoped original-source acquisition: safe targets and exact reconciliation decisions."""
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import sqlite3
import subprocess
import sys
import unittest

from finance_dashboard.catalog import load_documents
from finance_dashboard.comparative_workflow import (
    NATIVE_SOURCE_FAMILIES, checked_acquisition_target,
    scientific_gap_summary, select_source_ids, targeted_source_summary,
    verified_phase2_snapshot,
)


class TargetedPhase2SourcesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = load_documents()[0]["series"]

    def test_selects_canonical_new_provider_families_without_parallel_inventory(self):
        ids = select_source_ids(self.registry, new_sources=True)
        self.assertEqual(len(NATIVE_SOURCE_FAMILIES), 7)
        self.assertEqual(len(ids), 59)
        self.assertIn("activity.us.oecd_cli", ids)
        self.assertIn("bank.us.fdic_total_assets", ids)
        self.assertIn("credit.us.private_nonfinancial_stock_bis", ids)
        self.assertNotIn("credit_gap.us.bis_trend", ids)  # Existing BIS source family
        self.assertEqual(select_source_ids(self.registry, ids=[ids[1], ids[0]]), ids[:2])
        for invalid in (["unknown"], [ids[0], ids[0]]):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                select_source_ids(self.registry, ids=invalid)

    def test_import_source_mode_without_workbook_dependency(self):
        """Targeted source tools and CLI help must run without artifact readers."""
        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ)
        env["PYTHONPATH"] = str(root / "src")
        code = (
            'import sys; sys.modules["python_calamine"] = None; '
            'import finance_dashboard.comparative_workflow as module; '
            'assert "finance_dashboard.research_runtime" not in sys.modules; '
            'assert "finance_dashboard.research_artifacts" not in sys.modules; '
            'assert module.select_source_ids('
            '[{"id":"example", "status":"mapped", "provider":"OECD_CLI"}], '
            'ids=["example"]) == ["example"]'
        )
        result = subprocess.run(
            [sys.executable, "-c", code], cwd=root, env=env,
            capture_output=True, text=True, timeout=25, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        result = subprocess.run(
            [sys.executable, "-m", "finance_dashboard", "research", "compare", "--help"],
            cwd=root, env=env, capture_output=True, text=True,
            timeout=25, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--new-sources", result.stdout)
        self.assertIn("--vintage-dir", result.stdout)
        self.assertIn("--holdings-dir", result.stdout)

    def test_cli_requires_verified_backup_target_for_any_acquisition(self):
        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ)
        env["PYTHONPATH"] = str(root / "src")
        command = [sys.executable, "-m", "finance_dashboard", "research", "compare",
                   "--new-sources", "--acquire",
                   "--database-url", "sqlite:////nonexistent/research.sqlite3",
                   "--source-evidence-dir", "/nonexistent/evidence"]
        result = subprocess.run(command, cwd=root, env=env, capture_output=True,
                                text=True, timeout=25, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("--backup-dir", result.stderr)

    def test_existing_sqlite_database_and_source_archive_required_before_writes(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            evidence = root / "originals"
            evidence.mkdir()
            database = root / "isolated.sqlite3"
            url = "sqlite:///" + str(database)
            with self.assertRaisesRegex(ValueError, "existing_persistent_database_required"):
                checked_acquisition_target(url, evidence)
            database.write_text("not an actual database")
            with self.assertRaisesRegex(ValueError, "valid_existing_sqlite_database_required"):
                checked_acquisition_target(url, evidence)
            database.unlink()
            with sqlite3.connect(database) as conn:
                conn.execute("CREATE TABLE original_archive_test (x INTEGER)")
            with self.assertRaisesRegex(ValueError, "finance_history_schema_required"):
                checked_acquisition_target(url, evidence)
            with sqlite3.connect(database) as conn:
                conn.execute("CREATE TABLE series (id TEXT PRIMARY KEY)")
                conn.execute("CREATE TABLE ingestion_runs (id TEXT PRIMARY KEY)")
                conn.execute("CREATE TABLE observation_versions (id INTEGER PRIMARY KEY)")
            checked_acquisition_target(url, evidence)
            with self.assertRaisesRegex(ValueError, "existing_source_evidence_directory_required"):
                checked_acquisition_target(url, root / "wrong-originals")

    def test_verified_snapshots_retain_database_and_raw_originals_before_and_after(self):
        import json
        import tarfile
        from finance_dashboard.backup import verify_manifest
        with TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / "finance.sqlite3"
            evidence = root / "source-evidence"
            evidence.mkdir()
            original = evidence / "publisher-original.csv"
            original.write_bytes(b"2025-Q1,12.5\\n")
            with sqlite3.connect(db) as connection:
                connection.execute("CREATE TABLE series (id TEXT PRIMARY KEY)")
                connection.execute("CREATE TABLE ingestion_runs (id TEXT PRIMARY KEY)")
                connection.execute("CREATE TABLE observation_versions (id INTEGER PRIMARY KEY)")
                connection.execute("INSERT INTO series VALUES ('baseline')")
            url = "sqlite:///" + str(db)
            checkpoint = root / "protected-research-checkpoint"
            with self.assertRaisesRegex(ValueError, "backup_location_overlaps_source_archive"):
                verified_phase2_snapshot(url, evidence, evidence / "nested-backup", label="before")
            before = verified_phase2_snapshot(url, evidence, checkpoint, label="before")
            self.assertEqual(len(before["database_sha256"]), 64)
            self.assertEqual(len(before["evidence_archive_sha256"]), 64)
            with sqlite3.connect(db) as connection:
                connection.execute("INSERT INTO series VALUES ('acquired')")
            original.write_bytes(b"2025-Q1,13.0\\n")
            after = verified_phase2_snapshot(url, evidence, checkpoint, label="after")
            self.assertNotEqual(before["database_sha256"], after["database_sha256"])
            self.assertNotEqual(before["evidence_archive_sha256"], after["evidence_archive_sha256"])
            for label, receipt in (("before", before), ("after", after)):
                self.assertTrue(verify_manifest(Path(receipt["manifest"])))
                manifest = json.loads(Path(receipt["manifest"]).read_text())
                db_copy = Path(receipt["manifest"]).parent / manifest["database"]["file"]
                with sqlite3.connect(db_copy) as connection:
                    count = connection.execute("SELECT count(*) FROM series").fetchone()[0]
                self.assertEqual(count, 1 if label == "before" else 2)
                archive = Path(receipt["manifest"]).parent / manifest["evidence_archive"]["file"]
                with tarfile.open(archive) as bundle:
                    original_bytes = bundle.extractfile("source-evidence/publisher-original.csv").read()
                self.assertEqual(
                    original_bytes,
                    b"2025-Q1,12.5\\n" if label == "before" else b"2025-Q1,13.0\\n",
                )

    def test_scientific_gaps_are_derived_from_canonical_runtime_report(self):
        report = {
            "acceptance_summary": {"fully_accepted_analyses": 0},
            "role_resolution_summary": {"unbound_scalar_roles": 21},
            "analyses": [
                {"id": "F01", "requirements": [
                    {"role": "nominal_gdp", "input_type": "scalar_history", "checks": [
                        {"id": "source_binding", "state": "blocked", "code": "source_binding_missing"},
                        {"id": "publisher_dimensions", "state": "incomplete", "code": "publisher_dimensions_unverified"},
                    ]}
                ]},
                {"id": "M02", "requirements": [
                    {"role": "reference", "input_type": "scalar_history", "checks": [
                        {"id": "source_binding", "state": "passed", "code": "source_binding_present"},
                    ]}
                ]},
            ],
            "readiness_matrix": [
                {"id": "F01", "decision": "blocked",
                 "original": {"decision": "blocked", "missing_or_partial_roles": ["nominal_gdp"]},
                 "fallback": {"decision": "not_applicable"},
                 "reasons": [{"code": "exact_original_inputs_missing_or_partial"}]},
                {"id": "M02", "decision": "complete",
                 "original": {"decision": "complete", "missing_or_partial_roles": []},
                 "fallback": {"decision": "not_applicable"}, "reasons": []},
            ],
        }
        proof = {
            "series_count": 2, "matched_series": 1, "fully_reconciled_series": 1,
            "series": [
                {"series_id": "source-present", "source_covers_all_stored_periods": True},
                {"series_id": "source-missing", "source_covers_all_stored_periods": False,
                 "failure_code": "missing_evidence"},
            ],
        }
        result = scientific_gap_summary(report, source_proof=proof)
        self.assertTrue(result["empirical_readiness_evaluated"])
        self.assertEqual(result["fully_accepted_analyses"], 0)
        self.assertEqual(result["failed_or_unverified_gate_counts"],
                         {"publisher_dimensions": 1, "source_binding": 1})
        self.assertEqual(result["analysis_gaps"][0]["unverified_role_gates"][0]["role"], "nominal_gdp")
        self.assertEqual(result["analysis_gaps"][0]["unverified_roles"], ["nominal_gdp"])
        self.assertEqual(len(result["analysis_gaps"]), 1)
        self.assertEqual(result["required_input_source_reconciliation"]["unverified_source_ids"],
                         [{"id": "source-missing", "failure_code": "missing_evidence"}])

    def test_current_original_value_match_does_not_hide_extra_unreconciled_history(self):
        ids = ["activity.us.oecd_cli"]
        source = {"series_id": ids[0], "source_values_match": True,
                  "source_covers_all_stored_periods": False, "source_periods": 20,
                  "failure_code": None}
        proof = {"passed": True, "all_stored_histories_reconciled": False,
                 "matched_series": 1, "fully_reconciled_series": 0, "series": [source]}
        report = targeted_source_summary(ids, [], proof)
        self.assertFalse(report["passed"])
        self.assertFalse(report["scientific_analysis_certified"])
        self.assertEqual(report["sources"][0]["acquisition"], "not_requested")
        source["source_covers_all_stored_periods"] = True
        proof["fully_reconciled_series"] = 1
        proof["all_stored_histories_reconciled"] = True
        self.assertTrue(targeted_source_summary(ids, [], proof)["passed"])


if __name__ == "__main__":
    unittest.main()
