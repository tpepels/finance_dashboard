"""Full structured-artifact capability and original-role coverage tests."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from finance_dashboard.catalog import load_documents
from finance_dashboard.phase2_structured_acquisition import (
    CAPABILITIES, collection_plan, collect_structured_original,
    original_artifact_matrix, task_policy_hosts,
)
from finance_dashboard.research_corpus import load_research_corpus
from finance_dashboard.research_readiness import ARTIFACT_IDS
from finance_dashboard.source_policy_registry import PolicyRegistry
from scripts.phase2_structured_batch import structured_operating_plan


class StructuredCapabilitiesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = load_research_corpus()
        cls.catalog = load_documents()[0]["series"]

    def test_all_13_registered_artifacts_and_all_44_structured_roles(self):
        self.assertEqual(set(CAPABILITIES), ARTIFACT_IDS)
        self.assertEqual(len(CAPABILITIES), 13)
        matrix = original_artifact_matrix(self.document, {})
        self.assertEqual(matrix["structured_roles"], 44)
        self.assertEqual(
            matrix["roles_with_registered_artifacts"] +
            matrix["roles_without_registered_artifacts"], 44)
        self.assertEqual(matrix["roles_without_registered_artifacts"], 28)
        self.assertTrue(any(row["role_count"] for row in matrix[
            "artifact_workstreams"]))
        self.assertEqual({r["artifact_id"] for r in matrix[
            "artifact_workstreams"]}, ARTIFACT_IDS)
        self.assertFalse(matrix["research_certified"])
        self.assertTrue(all(not r["scientific_methods_certified"]
                            for r in matrix["artifact_workstreams"]))
        self.assertIn("stan", matrix["native_collectors_available"])
        self.assertIn("ucits_holdings", matrix["native_collectors_available"])
        self.assertIn("msci_concentration",
                      matrix["direct_originals_requiring_explicit_registration"])

    def test_live_policy_preclassification_and_explicit_archive_root(self):
        matrix = original_artifact_matrix(self.document, {})
        p = collection_plan(matrix, registry=PolicyRegistry(),
                            cvm_year=2025)
        by_kind = {item["kind"]: item for item in p["artifacts"]}
        self.assertEqual(by_kind["cvm"]["collection_state"],
                         "original_collection_candidate")
        self.assertIn("oecd-sdmx", by_kind["stan"]["policy_ids"])
        self.assertEqual(by_kind["msci_concentration"]["collection_state"],
                         "operator_original_required")
        self.assertEqual(by_kind["sec_holdings"]["collection_state"],
                         "original_holdings_archive_path_required")
        self.assertEqual(by_kind["ucits_holdings"]["collection_state"],
                         "original_holdings_archive_path_required")
        self.assertGreaterEqual(len(task_policy_hosts("ucits_holdings")), 4)
        self.assertEqual(task_policy_hosts("cvm"), ())
        self.assertEqual(p["publisher_requests_made"], 0)
        self.assertFalse(p["scientific_certification"])

    def test_existing_native_cvm_collector_reused_not_reimplemented(self):
        hits = []
        def handler(request):
            hits.append(request)
            return httpx.Response(200, content=b"synthetic")
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            with patch("finance_dashboard.cvm_profits.collect_cvm_annual_source") as collect:
                collect.return_value = {"bundle_digest": "a" * 64}
                result = collect_structured_original(
                    "cvm", root=Path("/tmp/nonexistent-artifact-original"),
                    client=client, cvm_year=2025)
                self.assertEqual(result["state"], "retained_original")
                self.assertEqual(result["archive"], "a" * 64)
                self.assertEqual(collect.call_count, 1)
                self.assertEqual(collect.call_args.kwargs["client"], client)
        self.assertEqual(hits, [])

    def test_partial_originals_never_satisfy_all_roles(self):
        with TemporaryDirectory() as tmp:
            result = structured_operating_plan(
                self.document, Path(tmp), holdings=None,
                kinds=set(CAPABILITIES), cvm_year=2025,
                agent=None, policy=PolicyRegistry())
            self.assertEqual(result["structured_roles"], 44)
            self.assertEqual(result["roles_without_registered_artifacts"], 28)
            self.assertTrue(any(
                item["collection_state"] == "operator_original_required"
                for item in result["artifact_workstreams"]))
            self.assertFalse(result["scientific_analysis_certified"])
            self.assertFalse(result["first_publication_not_inferred"] is False)


if __name__ == "__main__":
    unittest.main()
