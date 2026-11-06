"""Offline Phase 2 multi-source execution, scientific backlog, and run diagnostics."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

import httpx

from finance_dashboard.catalog import load_documents
from finance_dashboard.comparative_corpus import source_contract_digest
from finance_dashboard.phase2_workflow import (
    publisher_stop_reason, run_source_acquisition_batch, source_acquisition_plan,
)
from finance_dashboard.research_corpus import (
    analysis_series_ids, load_research_corpus, research_corpus_report,
)
from finance_dashboard.research_runtime import CorpusEvaluation
from finance_dashboard.source_policy_types import PolicyDeferred, PolicyViolation
from scripts.phase2_operating_batch import (
    build_phase2_operating_report, emit_operating_report, main,
)


def action(identifier):
    return {"id": identifier, "state": "acquisition_candidate"}


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = load_research_corpus()
        cls.registry = load_documents()[0]["series"]
        cls.report = research_corpus_report(
            cls.document, series_registry=cls.registry)
        cls.proof = {"series": []}

    def test_complete_35_analysis_and_original_role_source_graph(self):
        result = source_acquisition_plan(
            self.document, self.registry, self.report, self.proof, limit=12)
        self.assertEqual(result["analysis_count"], 35)
        self.assertEqual(set(a["id"] for a in result["analyses"]),
                         {a["id"] for a in self.document["analyses"]})
        expected = {sid for a in self.document["analyses"]
                    for sid in analysis_series_ids(a)}
        self.assertEqual(result["sources_referenced"], len(expected))
        self.assertGreater(result["source_acquisition_candidates"], 12)
        self.assertLessEqual(len(result["selected_actions"]), 12)
        self.assertFalse(result["scientific_analysis_certified"])
        self.assertFalse(result["first_publication_verified"])
        self.assertFalse(result["source_originals_modified"])
        self.assertEqual(result["publisher_requests_made"], 0)
        # No source_id enters the acquisition plan more than once, even when
        # ten research questions reference the same underlying publisher data.
        self.assertEqual(len({x["id"] for x in result["selected_actions"]}),
                         len(result["selected_actions"]))
        self.assertTrue(all(
            x["state"] == "acquisition_candidate"
            for x in result["selected_actions"]))
        self.assertTrue(all(
            x["affected_analysis_count"] == len(x["affected_analyses"])
            for x in result["selected_actions"]))

    def test_pruning_complete_original_preserves_stable_reusable_cursor(self):
        original = source_acquisition_plan(
            self.document, self.registry, self.report, self.proof, limit=3)
        first = original["selected_actions"][0]["id"]
        source = next(item for item in self.registry if item["id"] == first)
        proof = {"series": [{
            "series_id": first, "source_values_match": True,
            "source_covers_all_stored_periods": True, "stored_periods": 23,
            "source_sha256": "a" * 64,
            "source_manifest_sha256": "b" * 64,
            "stored_observations_sha256": "c" * 64,
            "source_contract_sha256": source_contract_digest(source),
        }]}
        report = {
            **self.report, "analyses": [{
                **analysis,
                "linked_sources": [{
                    **row, "stored_periods": 23,
                } if row["series_id"] == first else row
                    for row in analysis["linked_sources"]],
            } for analysis in self.report["analyses"]],
        }
        revised = source_acquisition_plan(
            self.document, self.registry, report, proof, limit=3)
        self.assertNotIn(first, {x["id"] for x in revised["selected_actions"]})
        self.assertEqual(revised["sources_with_verified_original_history"], 1)
        after = source_acquisition_plan(
            self.document, self.registry, report, proof,
            limit=3, after_id=first)
        self.assertEqual(after["selected_actions"], revised["selected_actions"])
        with self.assertRaisesRegex(ValueError, "invalid_phase2_acquisition_cursor"):
            source_acquisition_plan(
                self.document, self.registry, report, proof,
                limit=2, after_id="unregistered.invalid.source")
        with self.assertRaisesRegex(ValueError, "invalid_phase2_source_attempt_limit"):
            source_acquisition_plan(
                self.document, self.registry, report, proof, limit=0)

    def test_numeric_only_proof_cannot_skip_required_scientific_original(self):
        first = source_acquisition_plan(
            self.document, self.registry, self.report, self.proof, limit=1
        )["selected_actions"][0]["id"]
        numeric_only = {"series": [{
            "series_id": first,
            "source_values_match": True,
            "source_covers_all_stored_periods": True,
            "stored_periods": 23,
        }]}
        report = {
            **self.report, "analyses": [{
                **analysis, "linked_sources": [{
                    **row, "stored_periods": 23
                } if row["series_id"] == first else row
                    for row in analysis["linked_sources"]],
            } for analysis in self.report["analyses"]],
        }
        planned = source_acquisition_plan(
            self.document, self.registry, report, numeric_only, limit=2)
        self.assertEqual(planned["sources_with_verified_original_history"], 0)
        self.assertIn(first, {x["id"] for x in planned["selected_actions"]})

    def test_runtime_and_contract_membership_mismatch_fails_before_network(self):
        wrong = {**self.report, "analyses": self.report["analyses"][:-1]}
        with self.assertRaisesRegex(ValueError, "research_runtime"):
            source_acquisition_plan(
                self.document, self.registry, wrong, self.proof)
        wrong = {**self.report, "analyses": [
            {**a, "linked_sources": []} if a["id"] == "C01" else a
            for a in self.report["analyses"]]}
        with self.assertRaisesRegex(ValueError, "binding_projection"):
            source_acquisition_plan(
                self.document, self.registry, wrong, self.proof)

    def test_policy_failures_are_classified_and_stop_entire_batch(self):
        for exc, expected in (
            (PolicyDeferred("oecd-sdmx", "cooldown", 99999999999),
             "source_policy_deferred"),
            (PolicyViolation("oecd-sdmx", "acknowledgement_missing"),
             "source_policy_denied"),
            (ValueError("Provider HTTP 503 (sdmx.oecd.org)"),
             "provider_http_503"),
            (httpx.HTTPStatusError("upstream",
                 request=httpx.Request("GET", "https://example.com"),
                 response=httpx.Response(429)),
             "provider_http_429"),
        ):
            with self.subTest(expected=expected):
                seen = []
                def run(sid, *, full):
                    seen.append((sid, full))
                    raise exc
                result = run_source_acquisition_batch(
                    [action("one"), action("two"), action("three")], run)
                self.assertEqual(seen, [("one", True)])
                self.assertEqual(result["attempted"], 1)
                self.assertEqual(result["failed"], 1)
                self.assertEqual(result["deferred"], 2)
                self.assertEqual(result["stop_category"], expected)
                self.assertEqual(result["results"][1]["status"],
                                 "deferred_publisher_stop")
                self.assertNotIn("https://", json.dumps(result))
                self.assertFalse(result["scientific_analysis_certified"])

    def test_404_and_generic_validation_error_do_not_stop_independent_sources(self):
        seen = []
        def run(sid, *, full):
            seen.append(sid)
            if sid == "one":
                raise ValueError("Provider HTTP 404 (upstream)")
            if sid == "two":
                raise RuntimeError("credential=must-not-leak")
            return {"series_id": sid, "status": "success",
                    "versions_added": 9, "received": 100}
        result = run_source_acquisition_batch([
            action("one"), action("two"), action("three")], run)
        self.assertEqual(seen, ["one", "two", "three"])
        self.assertEqual(result["failed"], 2)
        self.assertEqual(result["succeeded"], 1)
        self.assertIsNone(result["stop_category"])
        self.assertNotIn("must-not-leak", json.dumps(result))

    def test_budget_defers_without_network_and_rejects_unsafe_tasks(self):
        run = Mock(return_value={"status": "success", "versions_added": 0})
        result = run_source_acquisition_batch(
            [action("a"), action("b"), action("c")],
            run, max_attempts=1)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(result["deferred"], 2)
        self.assertEqual([x["status"] for x in result["results"]],
                         ["success", "deferred_budget", "deferred_budget"])
        with self.assertRaises(ValueError):
            run_source_acquisition_batch([action("a"), action("a")], run)
        with self.assertRaises(ValueError):
            run_source_acquisition_batch([
                {"id": "a", "state": "verified_original_history"}], run)
        with self.assertRaises(ValueError):
            run_source_acquisition_batch([action("a")], run, max_attempts=121)

    def test_all_35_empirical_gates_and_stan_missing_originals_in_one_report(self):
        evaluation = CorpusEvaluation(
            public_report=self.report, comparative={},
            source_proof=self.proof)
        with TemporaryDirectory() as tmp:
            report = build_phase2_operating_report(
                evaluation, self.document, self.registry,
                evidence_root=Path(tmp), max_attempts=12)
            self.assertEqual(report["analyses"], 35)
            self.assertEqual(len(report["analysis_gaps"]), 35)
            self.assertEqual(report["stan"]["verified_original_countries"], 0)
            self.assertEqual(report["stan"]["pending_exact_selection_countries"], 38)
            self.assertEqual(report["stan"]["publisher_metadata"], "metadata_not_acquired")
            self.assertEqual(report["stan"]["same_scope_identity_countries"], 0)
            self.assertEqual(report["stan"]["publisher_requests_made"], 0)
            self.assertFalse(report["scientific_certification"])
            self.assertFalse(report["source_originals_modified"])
            compact = emit_operating_report(report)
            self.assertNotIn("analysis_gaps", compact)
            self.assertIn("gate_failures", compact)
            self.assertLess(len(json.dumps(compact)), 18_000)
            detailed = emit_operating_report(report, details=True)
            self.assertEqual(len(detailed["analysis_gaps"]), 35)
            self.assertTrue(all(
                row["first_publication_verified"] is False
                for row in detailed["analysis_gaps"]))

    def test_operating_cli_rejects_unsafe_arguments_before_database_access(self):
        for argv in (
            ["--database-url", "sqlite:////not-present", "--acquire"],
            ["--database-url", "sqlite:////not-present", "--max-attempts", "0"],
            ["--database-url", "sqlite:////not-present", "--backup-dir", "/tmp"],
        ):
            with self.subTest(argv=argv), self.assertRaises(SystemExit) as err:
                with redirect_stdout(StringIO()):
                    main(argv)
            self.assertEqual(err.exception.code, 2)
        for argv in (
            ["--database-url", "sqlite:////absent", "--revisit-from", "/tmp/old"],
            ["--database-url", "sqlite:////absent", "--sweep",
             "--revisit-mode", "both"],
            ["--database-url", "sqlite:////absent", "--sweep",
             "--acquire", "--resume", "--run-dir", "/tmp/new",
             "--backup-dir", "/tmp/backups",
             "--revisit-from", "/tmp/old"],
            ["--database-url", "sqlite:////absent", "--sweep",
             "--acquire", "--run-dir", "/tmp/old",
             "--backup-dir", "/tmp/backups",
             "--revisit-from", "/tmp/old"],
        ):
            with self.subTest(argv=argv), self.assertRaises(SystemExit) as err:
                with redirect_stdout(StringIO()):
                    main(argv)
            self.assertEqual(err.exception.code, 2)
        with TemporaryDirectory() as t:
            stream = StringIO()
            with redirect_stdout(stream):
                code = main([
                    "--database-url", "sqlite:///" + str(Path(t) / "absent.db"),
                    "--evidence-dir", t])
            self.assertEqual(code, 1)
            result = json.loads(stream.getvalue())
            self.assertEqual(result["phase"], "phase2")
            self.assertFalse(result["scientific_certification"])
            self.assertNotIn("https://", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
