"""Saved Phase 2 runtime reports are summarized without re-certification."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from finance_dashboard.phase2_report_summary import (
    format_saved_run, load_saved_run, summarize_saved_run,
)
from finance_dashboard.research_corpus_cli import main


def example():
    return {
        "phase": "phase2",
        "operation": "selected_original_source_reconciliation",
        "selection_count": 3,
        "passed": False,
        "verified_research_backups": {
            "before": {"manifest": "/data/backups/before/receipt.json"},
            "after": {"manifest": "/data/backups/after/receipt.json"},
        },
        "sources": [
            {"id": "activity.us.oecd_cli", "acquisition": "success",
             "source_values_match": True, "full_history_reconciled": True},
            {"id": "credit.us.private_nonfinancial_stock_bis",
             "acquisition": "failed", "acquisition_failure": "provider_http_403",
             "failure_code": "missing_evidence", "source_values_match": False,
             "full_history_reconciled": False},
            {"id": "bank.us.fdic_total_equity",
             "acquisition": "success", "source_values_match": True,
             "full_history_reconciled": False},
        ],
        "scientific_gaps": {
            "empirical_readiness_evaluated": True,
            "acceptance_summary": {"fully_accepted_analyses": 0},
            "failed_or_unverified_gate_counts": {
                "publisher_dimensions": 14, "temporal_evidence": 21,
            },
            "analysis_gaps": [
                {"id": "L02", "decision": "blocked",
                 "unverified_roles": ["net_operating_surplus"],
                 "blocking_reasons": ["source_binding_missing"]},
            ],
        },
    }


class SavedPhase2ReportTests(unittest.TestCase):
    def test_saved_summary_retains_acquisition_failures_and_scientific_uncertainty(self):
        report = summarize_saved_run(example())
        self.assertFalse(report["independently_reverified"])
        self.assertFalse(report["run_marked_passed"])
        self.assertEqual(report["acquisition_states"], {"failed": 1, "success": 2})
        self.assertEqual(report["source_values_matching"], 2)
        self.assertEqual(report["full_source_histories_reconciled"], 1)
        self.assertEqual(report["fully_accepted_analyses"], 0)
        self.assertEqual(len(report["failed_or_incomplete_sources"]), 2)
        self.assertEqual(report["gate_failure_counts"]["temporal_evidence"], 21)
        self.assertTrue(report["before_after_backup_receipts_recorded"])
        text = format_saved_run(report)
        self.assertIn("INCOMPLETE", text)
        self.assertIn("provider_http_403", text)
        self.assertIn("temporal_evidence: 21", text)
        self.assertNotIn("/data/backups/", text)

    def test_absent_empirical_gates_never_become_completely_accepted(self):
        report = example()
        del report["scientific_gaps"]
        parsed = summarize_saved_run(report)
        self.assertIsNone(parsed["fully_accepted_analyses"])
        self.assertFalse(parsed["empirical_scientific_gates_evaluated"])
        self.assertIn("NOT EVALUATED", format_saved_run(parsed))

    def test_malformed_or_partial_reports_fail_closed(self):
        for bad in ({}, {"phase": "phase2"},
                    {**example(), "selection_count": 4},
                    {**example(), "sources": [example()["sources"][0]] * 3},
                    {**example(), "scientific_gaps": {"acceptance_summary": {}}}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                summarize_saved_run(bad)

    def test_stdin_text_reader_enforces_size_and_incomplete_status(self):
        from finance_dashboard.phase2_report_summary import load_saved_text
        result = load_saved_text(json.dumps(example()))
        self.assertEqual(result["selected_series"], 3)
        self.assertFalse(result["run_marked_passed"])
        with self.assertRaisesRegex(ValueError, "missing_or_oversized"):
            load_saved_text(" " * 12_000_001)

    def test_cli_reads_completed_run_without_accessing_database(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "native-report.json"
            path.write_text(json.dumps(example()), encoding="utf-8")
            stream = StringIO()
            with redirect_stdout(stream):
                code = main(["--run-report", str(path), "--json"])
            self.assertEqual(code, 1)  # Incomplete reconciliation is not success.
            summary = json.loads(stream.getvalue())
            self.assertEqual(summary["report_kind"], "summary_of_saved_phase2_run")
            self.assertNotIn("analysis_gaps", summary)
            stream = StringIO()
            with redirect_stdout(stream):
                code = main(["--run-report", str(path), "--details"])
            self.assertEqual(code, 1)
            self.assertIn("L02: blocked", stream.getvalue())
            self.assertFalse((Path(temp) / "finance.sqlite3").exists())


if __name__ == "__main__":
    unittest.main()
