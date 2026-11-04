"""Offline corpus status is a compact declaration inventory, never fake readiness."""
from contextlib import redirect_stdout
from io import StringIO
import json
import unittest

from finance_dashboard.catalog import load_documents
from finance_dashboard.research_corpus import load_research_corpus
from scripts.phase2_corpus_status import build_inventory, format_inventory, main


class OfflineCorpusStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source, _ = load_documents()
        cls.report = build_inventory(load_research_corpus(), source["series"])

    def test_exact_approved_roles_and_no_empirical_readiness_claim(self):
        r = self.report
        self.assertEqual(r["analysis_count"], 35)
        self.assertEqual(r["method_source_count"], 49)
        self.assertEqual(r["scalar_roles"], 124)
        self.assertEqual(r["scalar_bound_roles"], 103)
        self.assertEqual(r["unbound_scalar_roles"], 21)
        self.assertEqual(r["structured_roles"], 44)
        self.assertFalse(r["empirical_readiness_evaluated"])
        self.assertEqual(r["report_kind"], "source_contract_inventory")
        self.assertEqual(r["errors"], [])
        self.assertNotIn("readiness_matrix", r)
        self.assertNotIn("fully_validated_analysis_count", r)

    def test_default_output_is_copyable_and_keeps_original_gaps_visible(self):
        output = format_inventory(self.report)
        self.assertLess(len(output.splitlines()), 40)
        self.assertIn("NOT EVALUATED", output)
        self.assertIn("F01: nominal_gdp", output)
        self.assertIn("L07: wiid_gini", output)
        self.assertNotIn('"decision": "blocked"', output)
        full = format_inventory(self.report, details=True)
        self.assertIn("C01: scalar", full)
        self.assertIn("P05: scalar", full)

    def test_machine_readable_mode_does_not_invent_data_evidence(self):
        stream = StringIO()
        with redirect_stdout(stream):
            exit_code = main(["--json"])
        parsed = json.loads(stream.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertFalse(parsed["empirical_readiness_evaluated"])
        self.assertNotIn("analyses", parsed)
        self.assertEqual(parsed["unbound_scalar_roles"], 21)


if __name__ == "__main__":
    unittest.main()
