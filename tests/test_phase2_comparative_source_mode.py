"""Scoped original-source acquisition: safe targets and exact reconciliation decisions."""
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import sqlite3
import subprocess
import sys
import unittest

from finance_dashboard.catalog import load_documents
from scripts.phase2_comparative_corpus import (
    NATIVE_SOURCE_FAMILIES, checked_acquisition_target,
    select_source_ids, targeted_source_summary,
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
            'import scripts.phase2_comparative_corpus as module; '
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
            [sys.executable, "scripts/phase2_comparative_corpus.py", "--help"],
            cwd=root, env=env, capture_output=True, text=True,
            timeout=25, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--new-sources", result.stdout)

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
            checked_acquisition_target(url, evidence)
            with self.assertRaisesRegex(ValueError, "existing_source_evidence_directory_required"):
                checked_acquisition_target(url, root / "wrong-originals")

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
