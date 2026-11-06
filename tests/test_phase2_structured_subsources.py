"""Independent publisher policy routing for multi-source native artifacts."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from finance_dashboard.phase2_structured_acquisition import (
    collection_plan, collect_structured_original,
    original_artifact_matrix, ucits_original_routes,
)
from finance_dashboard.research_corpus import load_research_corpus
from finance_dashboard.source_policy_registry import PolicyRegistry
from finance_dashboard.structured_workflow import structured_operating_plan


class IndependentPublisherSubsourcesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = load_research_corpus()

    def test_both_publisher_subsources_can_be_planned_independently(self):
        matrix = original_artifact_matrix(self.document, {})
        with TemporaryDirectory() as tmp:
            result = collection_plan(
                matrix, registry=PolicyRegistry(),
                holdings_dir=Path(tmp))
            ucits = next(row for row in result["artifacts"]
                         if row["kind"] == "ucits_holdings")
            self.assertEqual(
                ucits["collection_state"],
                "original_collection_candidate")
            subs = {item["subsource"]: item
                    for item in ucits["subsource_collectors"]}
            self.assertEqual(set(subs), {"ishares", "vanguard"})
            self.assertEqual(
                subs["ishares"]["collection_state"],
                "original_collection_candidate")
            self.assertEqual(
                subs["vanguard"]["collection_state"],
                "original_collection_candidate")
            self.assertEqual(ucits["authorized_subsources"], ["ishares", "vanguard"])
            self.assertIn("ishares", ucits["policy_ids"])
            self.assertIn("vanguard-fund-docs", ucits["policy_ids"])
            self.assertFalse(result["scientific_certification"])

    def test_each_source_is_independent_journal_action(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            plan = structured_operating_plan(
                self.document, root,
                holdings=root / "holdings",
                kinds={"ucits_holdings"}, cvm_year=None,
                agent=None, policy=PolicyRegistry())
            ids = [action["id"] for action in plan["selected_actions"]]
            self.assertEqual(ids, ["ucits_holdings:ishares", "ucits_holdings:vanguard"])
            self.assertNotIn("ucits_holdings", ids)
            row = plan["artifact_workstreams"][0]
            self.assertEqual(row["artifact_id"], "ucits_holdings")
            self.assertEqual(len(row["subsource_collectors"]), 2)
            self.assertFalse(plan["scientific_analysis_certified"])

    def test_native_vanguard_collector_reuses_existing_source_store(self):
        with TemporaryDirectory() as temp:
            with httpx.Client(transport=httpx.MockTransport(
                    lambda r: self.fail("unregistered network"))) as client:
                with patch(
                    "finance_dashboard.vanguard_ucits_holdings.collect_vanguard_ucits_sources"
                ) as managed:
                    managed.return_value = {"status": "complete"}
                    result = collect_structured_original(
                        "ucits_holdings", root=Path(temp), client=client,
                        subsource="vanguard", holdings_dir=Path(temp))
                    self.assertEqual(result["kind"], "ucits_holdings")
                    self.assertEqual(result["subsource"], "vanguard")
                    self.assertEqual(result["state"], "retained_original")
                    self.assertEqual(managed.call_count, 1)
                with self.assertRaisesRegex(
                        ValueError, "subsource_must_be_explicit"):
                    collect_structured_original(
                        "ucits_holdings", root=Path(temp),
                        client=client, holdings_dir=Path(temp))


if __name__ == "__main__":
    unittest.main()
