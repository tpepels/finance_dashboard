"""Full structured-artifact capability and original-role coverage tests."""
import corpus_counts
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
from finance_dashboard.structured_workflow import structured_operating_plan


class StructuredCapabilitiesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = load_research_corpus()
        cls.catalog = load_documents()[0]["series"]

    def test_all_14_registered_artifacts_and_all_44_structured_roles(self):
        self.assertEqual(set(CAPABILITIES), ARTIFACT_IDS)
        self.assertEqual(len(CAPABILITIES), 15)
        matrix = original_artifact_matrix(self.document, {})
        self.assertEqual(matrix["structured_roles"], corpus_counts.STRUCTURED_ROLES)
        self.assertEqual(
            matrix["roles_with_registered_artifacts"] +
            matrix["roles_without_registered_artifacts"], corpus_counts.STRUCTURED_ROLES)
        self.assertEqual(matrix["roles_without_registered_artifacts"], corpus_counts.STRUCTURED_WITHOUT_ARTIFACTS)
        self.assertTrue(any(row["role_count"] for row in matrix[
            "artifact_workstreams"]))
        self.assertEqual({r["artifact_id"] for r in matrix[
            "artifact_workstreams"]}, ARTIFACT_IDS)
        self.assertFalse(matrix["research_certified"])
        self.assertTrue(all(not r["scientific_methods_certified"]
                            for r in matrix["artifact_workstreams"]))
        self.assertIn("stan", matrix["native_collectors_available"])
        self.assertIn("ucits_holdings", matrix["native_collectors_available"])
        self.assertIn("msci_concentration", matrix["native_collectors_available"])
        self.assertNotIn(
            "msci_concentration",
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
                         "original_collection_candidate")
        self.assertEqual(len(by_kind["msci_concentration"]["subsource_collectors"]), 1)
        self.assertEqual(by_kind["sec_holdings"]["collection_state"],
                         "original_holdings_archive_path_required")
        self.assertEqual(by_kind["ucits_holdings"]["collection_state"],
                         "original_holdings_archive_path_required")
        self.assertGreaterEqual(len(task_policy_hosts("ucits_holdings")), 4)
        self.assertEqual(task_policy_hosts("cvm"), ())
        self.assertEqual(p["publisher_requests_made"], 0)
        self.assertFalse(p["scientific_certification"])

    def test_restricted_use_metadata_does_not_block_ishares_acquisition_plan(self):
        matrix = original_artifact_matrix(self.document, {})
        with TemporaryDirectory() as temp:
            p = collection_plan(
                matrix, registry=PolicyRegistry(), holdings_dir=Path(temp))
            ucits = next(row for row in p["artifacts"]
                         if row["kind"] == "ucits_holdings")
            self.assertEqual(ucits["collection_state"], "original_collection_candidate")
            self.assertIn("ishares", ucits["authorized_subsources"])

    def test_registered_msci_original_endpoint_enables_bounded_collection(self):
        matrix = original_artifact_matrix(self.document, {})
        url = "https://www.msci.com/research/specific-acwi-factsheet.pdf"
        with TemporaryDirectory() as temp:
            p = collection_plan(
                matrix, registry=PolicyRegistry(),
                holdings_dir=Path(temp), msci_factsheet_urls=(url,))
            row = next(item for item in p["artifacts"]
                       if item["kind"] == "msci_concentration")
            self.assertEqual(row["collection_state"], "original_collection_candidate")
            self.assertEqual(row["policy_ids"], ["msci"])
            self.assertEqual(p["publisher_requests_made"], 0)
            work = structured_operating_plan(
                self.document, Path(temp), holdings=Path(temp),
                kinds={"msci_concentration"}, cvm_year=None,
                agent=None, policy=PolicyRegistry(), msci_factsheet_urls=(url,))
            from finance_dashboard.msci_concentration_originals import (
                msci_publisher_factsheet_identity,
            )
            expected_id = "msci_concentration:" + msci_publisher_factsheet_identity(url)
            self.assertEqual(
                [item["id"] for item in work["selected_actions"]], [expected_id])
            self.assertEqual(work["selected_actions"][0]["source_url"], url)
            self.assertFalse(work["scientific_analysis_certified"])

    def test_multi_pdf_originals_are_independent_bounded_tasks(self):
        from finance_dashboard.msci_concentration_originals import (
            msci_publisher_factsheet_identity,
        )
        urls = (
            "https://www.msci.com/documents/10199/255599/2025-acwi.pdf",
            "https://www.msci.com/documents/10199/255599/2026-acwi.pdf",
        )
        matrix = original_artifact_matrix(self.document, {})
        with TemporaryDirectory() as temp:
            work = structured_operating_plan(
                self.document, Path(temp), holdings=Path(temp),
                kinds={"msci_concentration"}, cvm_year=None,
                agent=None, policy=PolicyRegistry(), msci_factsheet_urls=urls)
        actions = work["selected_actions"]
        self.assertEqual(len(actions), 2)
        self.assertEqual([x["source_url"] for x in actions], list(urls))
        self.assertEqual([x["id"] for x in actions], [
            "msci_concentration:" + msci_publisher_factsheet_identity(url)
            for url in urls
        ])
        self.assertTrue(all(x["publisher_policy"] == "msci" for x in actions))
        self.assertEqual(len(set(x["id"] for x in actions)), 2)

    def test_msci_collector_rejects_wrong_source_action_before_network(self):
        from finance_dashboard.msci_concentration_originals import (
            msci_publisher_factsheet_identity,
        )
        url = "https://www.msci.com/documents/10199/255599/acwi.pdf"
        calls = []
        with httpx.Client(transport=httpx.MockTransport(
                lambda req: self.fail("Unexpected source request"))) as client:
            with patch(
                "finance_dashboard.msci_concentration_originals.collect_msci_concentration_factsheet"
            ) as collect:
                collect.return_value = Path("/evidence/abc")
                with self.assertRaisesRegex(ValueError, "source_identity_mismatch"):
                    collect_structured_original(
                        "msci_concentration", root=Path("/unused"), client=client,
                        subsource="pdf-wrong-id", msci_factsheet_url=url)
                self.assertEqual(collect.call_count, 0)
                result = collect_structured_original(
                    "msci_concentration", root=Path("/unused"), client=client,
                    subsource=msci_publisher_factsheet_identity(url),
                    msci_factsheet_url=url)
                self.assertEqual(result["archive"], "abc")
                self.assertEqual(result["state"], "retained_original")
                self.assertEqual(collect.call_count, 1)

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
            self.assertEqual(result["structured_roles"], corpus_counts.STRUCTURED_ROLES)
            self.assertEqual(result["roles_without_registered_artifacts"], corpus_counts.STRUCTURED_WITHOUT_ARTIFACTS)
            self.assertTrue(any(
                item["collection_state"] == "operator_original_required"
                for item in result["artifact_workstreams"]))
            self.assertFalse(result["scientific_analysis_certified"])
            self.assertFalse(result["first_publication_not_inferred"] is False)


if __name__ == "__main__":
    unittest.main()
