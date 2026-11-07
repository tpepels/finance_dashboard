"""Offline corpus status is a compact declaration inventory, never fake readiness."""
import corpus_counts
from contextlib import redirect_stdout
from io import StringIO
import json
import unittest

from finance_dashboard.catalog import load_documents
from finance_dashboard.research_corpus import load_research_corpus
from finance_dashboard.research_corpus_cli import build_inventory, format_inventory, main


class OfflineCorpusStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source, _ = load_documents()
        cls.report = build_inventory(load_research_corpus(), source["series"])

    def test_exact_approved_roles_and_no_empirical_readiness_claim(self):
        r = self.report
        self.assertEqual(r["analysis_count"], corpus_counts.ANALYSES)
        self.assertEqual(r["method_source_count"], 49)
        self.assertEqual(r["scalar_roles"], corpus_counts.SCALAR_ROLES)
        self.assertEqual(r["scalar_bound_roles"], corpus_counts.BOUND_SCALAR_ROLES)
        self.assertEqual(r["unbound_scalar_roles"], corpus_counts.UNBOUND_SCALAR_ROLES)
        self.assertEqual(r["structured_roles"], corpus_counts.STRUCTURED_ROLES)
        self.assertFalse(r["empirical_readiness_evaluated"])
        self.assertEqual(r["report_kind"], "source_contract_inventory")
        self.assertEqual(r["errors"], [])
        self.assertNotIn("readiness_matrix", r)
        self.assertNotIn("fully_validated_analysis_count", r)

    def test_default_output_is_copyable_and_keeps_original_gaps_visible(self):
        output = format_inventory(self.report)
        self.assertLess(len(output.splitlines()), 40)
        self.assertIn("NOT EVALUATED", output)
        self.assertIn("L01: oecd_matched_value_added", output)
        self.assertIn("V03: regional_trailing_pe", output)
        self.assertNotIn('"decision": "blocked"', output)
        full = format_inventory(self.report, details=True)
        self.assertIn("C01: scalar", full)
        self.assertIn("P05: scalar", full)

    def test_unverified_oecd_candidates_cover_fourteen_original_l01_l03_roles_without_binding(self):
        r = self.report
        self.assertEqual(r["unverified_source_candidate_roles"], 4)
        self.assertEqual({item["id"] for item in r["analyses_with_unverified_candidates"]},
                         {"L01"})
        for item in r["analyses_with_unverified_candidates"]:
            for role in item["roles"]:
                self.assertIn(role["role"], next(
                    a for a in r["analyses"] if a["id"] == item["id"]
                )["unbound_scalar_roles"])
                for candidate in role["candidate_sources"]:
                    self.assertEqual(candidate["status"], "unverified_candidate")
                    self.assertTrue(candidate["source_url"].startswith("https://"))
                    self.assertTrue(candidate["required_original_checks"])
        output = format_inventory(r, candidates=True)
        self.assertNotIn("L03/net_fixed_capital", output)
        self.assertIn("L01/oecd_matched_hours", output)
        self.assertIn("not mapped, fetched or scientifically verified", output)
        self.assertEqual(r["scalar_bound_roles"], corpus_counts.BOUND_SCALAR_ROLES)
        self.assertFalse(r["empirical_readiness_evaluated"])

    def test_machine_readable_mode_does_not_invent_data_evidence(self):
        stream = StringIO()
        with redirect_stdout(stream):
            exit_code = main(["--json"])
        parsed = json.loads(stream.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertFalse(parsed["empirical_readiness_evaluated"])
        self.assertNotIn("analyses", parsed)
        self.assertEqual(parsed["unbound_scalar_roles"], corpus_counts.UNBOUND_SCALAR_ROLES)


if __name__ == "__main__":
    unittest.main()
