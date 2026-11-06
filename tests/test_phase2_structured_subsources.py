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

    def test_mixed_issuer_and_msci_sources_have_distinct_journal_tasks(self):
        from finance_dashboard.msci_concentration_originals import (
            msci_publisher_factsheet_identity,
            CURRENT_ACWI_FACTSHEET_URL,
        )
        with TemporaryDirectory() as temp:
            base = Path(temp)
            plan = structured_operating_plan(
                self.document, base, holdings=base / "holdings",
                kinds={"msci_concentration", "ucits_holdings"},
                cvm_year=None, agent=None, policy=PolicyRegistry())
        tasks = plan["selected_actions"]
        self.assertEqual(len(tasks), 3)
        self.assertEqual(
            [row["id"] for row in tasks],
            ["msci_concentration:" + msci_publisher_factsheet_identity(
                CURRENT_ACWI_FACTSHEET_URL),
             "ucits_holdings:ishares", "ucits_holdings:vanguard"])
        self.assertEqual([row["publisher_policy"] for row in tasks],
                         ["msci", "ishares", "vanguard-fund-docs"])
        self.assertFalse(plan["scientific_analysis_certified"])

    def test_two_msci_pdfs_respect_shared_rate_and_resume_without_replay(self):
        """A deferred second URL has no journal start and may resume safely."""
        from finance_dashboard.msci_concentration_originals import (
            msci_publisher_factsheet_identity,
        )
        from finance_dashboard.phase2_sweep_journal import (
            Phase2SweepJournal, sweep_context,
        )
        from finance_dashboard.phase2_workflow import run_source_acquisition_batch
        from finance_dashboard.source_policy import managed_client
        from finance_dashboard.source_policy_ledger import SourcePolicyGate

        class Clock:
            def __init__(self):
                self.now = 1000000.0
            def __call__(self):
                return self.now
            def advance(self, seconds):
                self.now += seconds

        urls = (
            "https://www.msci.com/documents/10199/2020/a.pdf",
            "https://www.msci.com/documents/10199/2020/b.pdf",
        )
        fixture = (
            Path(__file__).parent / "fixtures/holdings" /
            "msci-acwi-2020-10-30-original.pdf"
        ).read_bytes()
        requested = []
        def reply(request):
            requested.append(str(request.url))
            return httpx.Response(200, content=fixture)
        with TemporaryDirectory() as temp:
            root = Path(temp)
            evidence = root / "evidence"
            plan = structured_operating_plan(
                self.document, evidence, holdings=None,
                kinds={"msci_concentration"}, cvm_year=None,
                agent=None, policy=PolicyRegistry(),
                msci_factsheet_urls=urls)
            actions = plan["selected_actions"]
            self.assertEqual(len(actions), 2)
            self.assertEqual(
                {a["id"] for a in actions},
                {"msci_concentration:" + msci_publisher_factsheet_identity(url)
                 for url in urls})
            source_by_id = {action["id"]: action["source_url"]
                            for action in actions}
            selected_ids = sorted(source_by_id)
            context = sweep_context(selected_ids, "0" * 64, "1" * 64)
            clock = Clock()
            gate = SourcePolicyGate(
                registry=PolicyRegistry(), state_path=root / "rate-ledger.sqlite",
                clock=clock, max_wait_seconds=0)
            journal_path = root / "journal"
            for turn in range(2):
                with managed_client(
                        policy_gate=gate,
                        transport=httpx.MockTransport(reply)) as client:
                    def refresh(action_id, *, full):
                        self.assertTrue(full)
                        name = action_id.partition(":")[2]
                        result = collect_structured_original(
                            "msci_concentration", root=evidence, client=client,
                            subsource=name,
                            msci_factsheet_url=source_by_id[action_id])
                        return {"status": "success", "received": 1,
                                "versions_added": int(
                                    result["state"] == "retained_original")}

                    with Phase2SweepJournal(
                            journal_path, context=context,
                            create=turn == 0) as journal:
                        outcome = run_source_acquisition_batch(
                            actions, refresh, max_attempts=2,
                            stop_scope="publisher", journal=journal,
                            policy_preflight=lambda row:
                                gate.availability(row["publisher_policy"]))
                        self.assertEqual(outcome["attempted"], 1)
                        self.assertEqual(journal.summary()["tracked_attempts"],
                                         turn + 1)
                        self.assertEqual(
                            [row["status"] for row in outcome["results"]],
                            ["success", "deferred_policy_preflight"] if turn == 0
                            else ["deferred_prior_attempt", "success"])
                if turn == 0:
                    self.assertEqual(len(requested), 1)
                    clock.advance(3601)
            self.assertEqual(requested, list(urls))
            self.assertEqual(gate.report()["requests_recorded"], 1)
            from finance_dashboard.msci_concentration_originals import (
                read_msci_concentration_originals,
            )
            values, proof = read_msci_concentration_originals(evidence)
            self.assertEqual(len(values), 1)
            self.assertEqual(len(proof["original_document_proofs"]), 2)
            self.assertEqual(len(list(evidence.rglob("original.pdf"))), 2)

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
