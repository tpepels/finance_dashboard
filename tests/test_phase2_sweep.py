"""Crash-safe Phase 2 sweep and publisher-neutral scheduling regression tests."""
import corpus_counts
from contextlib import redirect_stdout
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

import httpx

from finance_dashboard.catalog import load_documents
from finance_dashboard.phase2_role_workplan import (
    compact_role_workplan, phase2_role_workplan,
)
from finance_dashboard.phase2_sweep_journal import (
    Phase2SweepJournal, sweep_context,
)
from finance_dashboard.phase2_workflow import (
    run_source_acquisition_batch, source_acquisition_plan,
)
from finance_dashboard.source_policy_types import PolicyViolation, PolicyDeferred
from finance_dashboard.research_corpus import load_research_corpus, research_corpus_report
from finance_dashboard.research_operating import main


POLICY = "0" * 64
CONTRACT = "1" * 64


def context(ids=("a", "b", "c")):
    return sweep_context(list(ids), POLICY, CONTRACT)


def actions():
    return [{"id": sid, "publisher_policy": "fred-v1",
             "state": "acquisition_candidate"} for sid in ("a", "b", "c")]


class SweepJournalTests(unittest.TestCase):
    def test_resumable_complete_backlog_never_refetches_completed_sources(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp) / "run-1"
            calls = []
            def refresh(sid, *, full):
                self.assertTrue(full)
                calls.append(sid)
                return {"status": "success", "series_id": sid,
                        "received": 12, "versions_added": 4}
            with Phase2SweepJournal(folder, context=context(), create=True) as journal:
                first = run_source_acquisition_batch(
                    actions(), refresh, max_attempts=2,
                    stop_scope="publisher", journal=journal)
                self.assertEqual(first["attempted"], 2)
                self.assertEqual(first["deferred"], 1)
                self.assertEqual(journal.summary()["attempt_statuses"]["success"], 2)
            with Phase2SweepJournal(folder, context=context(), create=False) as journal:
                second = run_source_acquisition_batch(
                    actions(), refresh, max_attempts=3,
                    stop_scope="publisher", journal=journal)
                self.assertEqual(second["attempted"], 1)
                self.assertEqual(second["results"][0]["status"], "deferred_prior_attempt")
                self.assertEqual(second["results"][1]["status"], "deferred_prior_attempt")
                self.assertEqual(second["results"][2]["status"], "success")
                self.assertEqual(journal.summary()["tracked_attempts"], 3)
            self.assertEqual(calls, ["a", "b", "c"])
            with Phase2SweepJournal(folder, context=context(), create=False) as journal:
                third = run_source_acquisition_batch(
                    actions(), refresh, max_attempts=3,
                    stop_scope="publisher", journal=journal)
                self.assertEqual(third["attempted"], 0)
            self.assertEqual(calls, ["a", "b", "c"])

    def test_unknown_inflight_request_is_never_silently_repeated(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            with Phase2SweepJournal(root, context=context(), create=True) as journal:
                journal.mark_started("a")
            invoked = Mock()
            with Phase2SweepJournal(root, context=context(), create=False) as journal:
                report = run_source_acquisition_batch(
                    actions()[:1], invoked, max_attempts=1,
                    stop_scope="publisher", journal=journal)
                self.assertEqual(report["attempted"], 0)
                self.assertEqual(report["results"][0]["previous_status"],
                                 "started_without_result")
                self.assertEqual(journal.summary()["inflight_requires_review"], ["a"])
            invoked.assert_not_called()

    def test_failed_attempts_are_not_retired_from_evidence_but_not_retried(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            calls = []
            def refresh(sid, *, full):
                calls.append(sid)
                if sid == "a":
                    raise ValueError("Provider HTTP 404 (api.stlouisfed.org)")
                return {"status": "success", "received": 1, "versions_added": 0}
            with Phase2SweepJournal(root, context=context(), create=True) as journal:
                first = run_source_acquisition_batch(
                    actions()[:2], refresh, stop_scope="publisher",
                    journal=journal)
                self.assertEqual(first["failed"], 1)
            with Phase2SweepJournal(root, context=context(), create=False) as journal:
                second = run_source_acquisition_batch(
                    actions(), refresh, stop_scope="publisher", journal=journal)
                self.assertEqual(second["attempted"], 1)
                self.assertEqual(second["results"][0]["previous_reason"],
                                 "provider_http_404")
                self.assertEqual(journal.summary()["attempt_statuses"]["failed"], 1)
            self.assertEqual(calls, ["a", "b", "c"])

    def test_policy_and_contract_changes_block_resume_before_network(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            with Phase2SweepJournal(root, context=context(), create=True):
                pass
            for changed in (
                sweep_context(["a", "b", "c"], "2" * 64, CONTRACT),
                sweep_context(["a", "b", "c"], POLICY, "2" * 64),
                context(("a", "b", "new")),
            ):
                with self.subTest(changed=changed), self.assertRaisesRegex(
                        ValueError, "sweep_context_changed"):
                    with Phase2SweepJournal(root, context=changed, create=False):
                        pass
            with self.assertRaises(FileExistsError):
                with Phase2SweepJournal(root, context=context(), create=True):
                    pass

    def test_integrity_rechecks_original_start_hash_before_resume(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            with Phase2SweepJournal(root, context=context(), create=True) as journal:
                journal.mark_started("a")
                journal.mark_result("a", status="success", received=23, versions_added=2)
            starts = list((root / "events").glob("*.start.json"))
            self.assertEqual(len(starts), 1)
            entry = json.loads(starts[0].read_text())
            entry["at_utc"] = "2000-01-01T00:00:00+00:00"
            starts[0].write_text(
                json.dumps(entry, sort_keys=True, separators=(",", ":")))
            with self.assertRaisesRegex(ValueError, "sweep_result_integrity_invalid"):
                with Phase2SweepJournal(root, context=context(), create=False):
                    pass

    def test_same_run_requires_exclusive_writer_lock(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            with Phase2SweepJournal(root, context=context(), create=True):
                with self.assertRaisesRegex(ValueError, "sweep_journal_already_running"):
                    with Phase2SweepJournal(root, context=context(), create=False):
                        pass

    def test_malformed_or_orphaned_event_fails_closed(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            with Phase2SweepJournal(root, context=context(), create=True):
                pass
            bad = root / "events" / ("f" * 64 + ".result.json")
            bad.write_text("{}")
            with self.assertRaises(ValueError):
                with Phase2SweepJournal(root, context=context(), create=False):
                    pass


class PublisherScopedExecutionTests(unittest.TestCase):
    def test_genuine_fred_throttle_skips_fred_but_can_continue_other_publisher(self):
        fred_url = "https://api.stlouisfed.org/fred/series/observations"
        tasks = [
            {"id": "fred-1", "state": "acquisition_candidate",
             "publisher_policy": "fred-v1"},
            {"id": "fred-2", "state": "acquisition_candidate",
             "publisher_policy": "fred-v1"},
            {"id": "oecd-1", "state": "acquisition_candidate",
             "publisher_policy": "oecd-sdmx"},
        ]
        calls = []
        def request(sid, *, full):
            calls.append(sid)
            if sid == "fred-1":
                raise httpx.HTTPStatusError(
                    "throttle", request=httpx.Request("GET", fred_url),
                    response=httpx.Response(429))
            return {"status": "success", "received": 3, "versions_added": 3}
        result = run_source_acquisition_batch(
            tasks, request, stop_scope="publisher", max_attempts=3)
        self.assertEqual(calls, ["fred-1", "oecd-1"])
        self.assertEqual(result["attempted"], 2)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["succeeded"], 1)
        self.assertEqual(result["deferred"], 1)
        self.assertEqual(result["publisher_stop_categories"],
                         {"fred-v1": "provider_http_429"})
        self.assertIsNone(result["global_stop_category"])


    def test_verified_dynamic_oecd_policy_denial_does_not_block_independent_publishers(self):
        """A catalog documentation URL may differ from the actual API origin.

        The managed policy exception identifies the restricted API exactly.
        No acknowledgement is injected and no subsequent OAuth/API request to
        the denied OECD origin can occur.
        """
        tasks = [
            {"id": "oecd-dynamic", "state": "acquisition_candidate",
             "publisher_policy": "oecd-documents", "provider": "OECD_CORPORATE_GDPWEIGHTED"},
            {"id": "oecd-same-adapter", "state": "acquisition_candidate",
             "publisher_policy": "oecd-documents", "provider": "OECD_CORPORATE_GDPWEIGHTED"},
            {"id": "oecd-direct", "state": "acquisition_candidate",
             "publisher_policy": "oecd-sdmx", "provider": "OECD_CLI"},
            {"id": "fred-independent", "state": "acquisition_candidate",
             "publisher_policy": "fred-v1", "provider": "FRED"},
        ]
        called = []
        def refresh(sid, *, full):
            called.append(sid)
            if sid.startswith("oecd"):
                raise PolicyViolation("oecd-sdmx", "direct_network_origin_not_confirmed")
            return {"series_id": sid, "status": "success",
                    "received": 23, "versions_added": 2}
        result = run_source_acquisition_batch(
            tasks, refresh, stop_scope="publisher", max_attempts=4)
        self.assertEqual(called, ["oecd-dynamic", "fred-independent"])
        self.assertEqual(result["attempted"], 2)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["succeeded"], 1)
        self.assertEqual(result["deferred"], 2)
        self.assertIsNone(result["global_stop_category"])
        self.assertEqual(result["publisher_stop_categories"],
                         {"oecd-sdmx": "source_policy_denied"})
        self.assertEqual(result["publisher_adapter_mismatches"], [{
            "series_id": "oecd-dynamic",
            "declared_policy": "oecd-documents",
            "verified_upstream_policy": "oecd-sdmx",
            "stop_reason": "source_policy_denied",
        }])
        self.assertEqual([item["status"] for item in result["results"]], [
            "failed", "deferred_publisher_stop",
            "deferred_publisher_stop", "success"])

    def test_resumed_old_journal_does_not_guess_publisher_from_prior_failure(self):
        """A stored fixed failure reason is not a reliable upstream policy ID."""
        with TemporaryDirectory() as tmp:
            directory = Path(tmp) / "sweep"
            tasks = [
                {"id": "a", "state": "acquisition_candidate",
                 "provider": "OECD_CORPORATE_GDPWEIGHTED",
                 "publisher_policy": "oecd-documents"},
                {"id": "b", "state": "acquisition_candidate",
                 "provider": "SHILLER", "publisher_policy": "research-papers"},
            ]
            with Phase2SweepJournal(
                    directory, context=context(("a", "b")), create=True) as journal:
                journal.mark_started("a")
                journal.mark_result(
                    "a", status="failed", reason="source_policy_denied")
            calls = []
            def refresh(sid, *, full):
                calls.append(sid)
                return {"status": "success", "received": 1, "versions_added": 0}
            with Phase2SweepJournal(
                    directory, context=context(("a", "b")), create=False) as journal:
                result = run_source_acquisition_batch(
                    tasks, refresh, stop_scope="publisher",
                    journal=journal, max_attempts=2)
            self.assertEqual(calls, ["b"])
            self.assertEqual(result["attempted"], 1)
            self.assertEqual(result["results"][0]["status"], "deferred_prior_attempt")
            self.assertIsNone(result["global_stop_category"])

    def test_unknown_policy_violation_origin_remains_global_stop(self):
        tasks = [
            {"id": "a", "state": "acquisition_candidate",
             "publisher_policy": "fred-v1"},
            {"id": "b", "state": "acquisition_candidate",
             "publisher_policy": "bis"},
        ]
        def refresh(sid, *, full):
            raise PolicyViolation("registry", "unclassified_publisher")
        report = run_source_acquisition_batch(
            tasks, refresh, stop_scope="publisher")
        self.assertEqual(report["attempted"], 1)
        self.assertEqual(report["global_stop_category"], "source_policy_denied")
        self.assertEqual(report["publisher_stop_categories"], {})

    def test_unknown_origin_or_wrong_catalog_policy_forces_global_stop(self):
        tasks = [
            {"id": "a", "state": "acquisition_candidate",
             "publisher_policy": "oecd-sdmx"},
            {"id": "b", "state": "acquisition_candidate",
             "publisher_policy": "fred-v1"},
        ]
        calls = []
        def fetch(sid, *, full):
            calls.append(sid)
            raise ValueError("Provider HTTP 503 (unregistered.example)")
        result = run_source_acquisition_batch(
            tasks, fetch, stop_scope="publisher")
        self.assertEqual(calls, ["a"])
        self.assertEqual(result["deferred"], 1)
        self.assertEqual(result["global_stop_category"], "provider_http_503")


class ScientificWorkplanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = load_research_corpus()
        cls.registry = load_documents()[0]["series"]
        cls.report = research_corpus_report(
            cls.document, series_registry=cls.registry)

    def test_all_structured_and_unbound_scalar_roles_are_reported_not_dropped(self):
        self.assertEqual(phase2_role_workplan(self.report)["unbound_scalar_roles_with_publisher_candidates"], 0)
        # The candidate workstreams are exercised on L01's original OECD leads.
        report = research_corpus_report(corpus_counts.with_unbound_l01_candidates(self.document),
                                        series_registry=self.registry)
        work = phase2_role_workplan(report)
        expected = report["role_resolution_summary"]
        self.assertEqual(work["total_original_roles"], expected["role_count"])
        self.assertEqual(work["structured_roles"], expected["structured_roles"])
        self.assertEqual(work["unbound_scalar_roles"],
                         expected["unbound_scalar_roles"])
        self.assertEqual(work["total_original_roles"], corpus_counts.ROLES)
        self.assertEqual(work["structured_roles"], corpus_counts.STRUCTURED_ROLES)
        self.assertEqual(work["unbound_scalar_roles"], corpus_counts.UNBOUND_WITH_L01_LEADS)
        self.assertGreater(work["unbound_scalar_roles_with_publisher_candidates"], 0)
        self.assertEqual(
            work["unbound_scalar_roles_with_publisher_candidates"] +
            work["unbound_scalar_roles_without_publisher_candidates"], corpus_counts.UNBOUND_WITH_L01_LEADS)
        self.assertTrue(any(
            x["dataset"] == "OECD_STAN_2025"
            for x in work["publisher_original_candidate_groups"]))
        self.assertTrue(all(x["candidate_is_not_verified_source"]
                            for x in work["publisher_original_candidate_groups"]))
        self.assertFalse(work["scientific_certification"])
        self.assertFalse(work["structured_artifact_acquisition_automated"])
        compact = compact_role_workplan(work)
        self.assertEqual(compact["structured_roles"], corpus_counts.STRUCTURED_ROLES)
        self.assertTrue(compact["artifact_workstreams"])
        self.assertTrue(compact["publisher_original_candidate_groups"])
        self.assertEqual(
            compact["unbound_scalar_roles_with_publisher_candidates"],
            work["unbound_scalar_roles_with_publisher_candidates"])
        self.assertLess(len(json.dumps(compact)), 8_000)

    def test_all_families_same_runtime_contract_no_new_acceptance_shortcuts(self):
        planned = source_acquisition_plan(
            self.document, self.registry, self.report,
            {"series": []}, limit=400)
        self.assertEqual(len(planned["selected_actions"]),
                         planned["source_acquisition_candidates"])
        self.assertGreaterEqual(len(planned["selected_actions"]), 144)
        # No local source evidence supplied by this unit test; never bake the
        # user's live original-history counts into the static contract.
        # Private best-effort collection no longer treats licence metadata as
        # a reason to exclude a mapped acquisition candidate.
        self.assertEqual(len(planned["blocked_source_actions"]), 0)
        self.assertTrue(all(not row["historical_completeness_confirmed"]
                            for row in planned["selected_actions"]))
        self.assertFalse(planned["scientific_analysis_certified"])

    def test_operating_cli_explicit_sweep_requires_recovery_and_journal(self):
        for argv in (
            ["--database-url", "sqlite:////absent", "--sweep", "--acquire"],
            ["--database-url", "sqlite:////absent", "--sweep",
             "--acquire", "--backup-dir", "/data/backups"],
            ["--database-url", "sqlite:////absent", "--sweep", "--resume"],
            ["--database-url", "sqlite:////absent", "--max-attempts", "200"],
        ):
            with self.subTest(argv=argv), self.assertRaises(SystemExit) as err:
                with redirect_stdout(StringIO()):
                    main(argv)
            self.assertEqual(err.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
