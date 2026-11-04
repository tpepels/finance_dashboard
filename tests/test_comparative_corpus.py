"""Actual DB joins and source-proof binding for bounded Phase 2 data panels."""
import copy
from datetime import date, datetime, timezone
from decimal import Decimal
import importlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from finance_dashboard.database import Base, IngestionRun, ObservationVersion, SeriesRow
from finance_dashboard.research_corpus import load_research_corpus


ROOT = Path(__file__).resolve().parents[1]
YIELDS = ["bond.us.nominal_10y", "bond.us.real_10y", "bond.us.breakeven_10y"]


class ComparativeCorpusTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.registry = json.loads((ROOT / "definitions/series.json").read_text())["series"]
        self.by_id = {row["id"]: row for row in self.registry}
        self.document = load_research_corpus()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.engine.dispose)

    def runtime(self):
        self.assertIsNotNone(importlib.util.find_spec("finance_dashboard.comparative_corpus"),
                             "Missing actual-observation comparative corpus runtime")
        return importlib.import_module("finance_dashboard.comparative_corpus")

    def insert(self, sid, values):
        with Session(self.engine) as session, session.begin():
            if session.get(SeriesRow, sid) is None:
                source = self.by_id[sid]
                session.add(SeriesRow(id=sid, provider=source["provider"], source_key=source["source_key"],
                                      updated_at=datetime.now(timezone.utc)))
                session.flush()
            run_id = str(uuid4())
            session.add(IngestionRun(id=run_id, series_id=sid, started_at=datetime.now(timezone.utc),
                                     status="success", observations_received=len(values), versions_added=len(values)))
            session.flush()
            session.add_all(ObservationVersion(series_id=sid, period=date.fromisoformat(period),
                value=Decimal(value), first_seen_at=datetime.now(timezone.utc), ingestion_run_id=run_id)
                for period, value in values.items())

    def yields(self):
        self.insert(YIELDS[0], {"2020-01-02": "4", "2020-01-03": "4.1", "2020-01-06": "4.2"})
        self.insert(YIELDS[1], {"2020-01-02": "1.5", "2020-01-06": "1.7"})
        self.insert(YIELDS[2], {"2020-01-02": "2.5", "2020-01-03": "2.5", "2020-01-06": "2.5"})

    def proof(self, ids):
        runtime = self.runtime()
        from finance_dashboard.service import current_observations
        with Session(self.engine) as session:
            return {"schema_version": 1, "series": [{"series_id": sid,
                "source_values_match": True, "source_covers_all_stored_periods": True, "source_sha256": "a" * 64,
                "source_manifest_sha256": "b" * 64,
                "source_contract_sha256": runtime.source_contract_digest(self.by_id[sid]),
                "stored_observations_sha256": runtime.observation_values_digest(
                    {row.period: row.value for row in current_observations(session, sid)})}
                for sid in ids]}

    def build(self, proof=None, registry=None):
        with Session(self.engine) as session:
            return self.runtime().build_comparative_corpus(session, registry or self.registry,
                self.document, source_proof=proof)

    def panel(self, report, analysis_id):
        return next(row for row in report["panels"] if row["analysis_id"] == analysis_id)

    def test_join_contains_actual_version_ids_and_never_fills_missing_market_dates(self):
        self.yields()
        report = self.build()
        panel = self.panel(report, "M02")
        self.assertEqual(panel["matched_periods"], ["2020-01-02", "2020-01-06"])
        self.assertEqual(panel["matched_period_count"], 2)
        self.assertEqual(panel["input_coverage"][YIELDS[0]]["excluded_from_match"], ["2020-01-03"])
        self.assertEqual(panel["rows"][1]["values"][YIELDS[0]], "4.2")
        self.assertTrue(all(value > 0 for row in panel["rows"] for value in row["observation_version_ids"].values()))
        self.assertFalse(panel["source_reconciled"])
        self.assertEqual(panel["state"], "matched_current_vintage_unreconciled")
        self.assertFalse(panel["full_analysis_accepted"])
        self.assertEqual(report["fully_validated_analysis_count"], 0)
        self.assertIsNone(panel["input_coverage"][YIELDS[0]]["missing_internal_periods"])

    def test_independent_source_proof_can_verify_only_the_bounded_current_snapshot(self):
        self.yields()
        report = self.build(self.proof(YIELDS))
        panel = self.panel(report, "M02")
        self.assertTrue(panel["source_reconciled"])
        self.assertEqual(panel["state"], "bounded_current_vintage_verified")
        self.assertFalse(panel["requested_coverage_complete"])
        self.assertFalse(panel["first_publication_verified"])
        self.assertEqual(panel["checks"][0]["id"], "yield_decomposition")
        self.assertTrue(panel["checks"][0]["passed"])
        self.assertEqual(panel["checks"][0]["tolerance"], "0.015")
        self.assertEqual(report["fully_validated_analysis_count"], 0)

    def test_declared_dimensions_do_not_prove_original_publisher_population_or_index_base(self):
        self.yields()
        panel = self.panel(self.build(self.proof(YIELDS)), "M02")
        scope = panel.get("source_metadata_scope")
        self.assertIsInstance(scope, dict)
        self.assertEqual(scope["checked_against"], "canonical_registry_declaration")
        self.assertFalse(scope["publisher_metadata_verified"])
        self.assertFalse(scope["population_verified"])
        self.assertFalse(scope["index_base_verified"])
        self.assertFalse(scope["same_publisher_release_verified"])

    def test_decimal_digest_is_canonical_without_losing_large_numeric_precision(self):
        runtime = self.runtime()
        self.assertEqual(runtime.observation_values_digest({date(2020, 1, 1): Decimal("1.0000000000")}),
                         runtime.observation_values_digest({"2020-01-01": "1"}))
        self.assertNotEqual(runtime.observation_values_digest({"2020-01-01": "12345678901234567890.1234567891"}),
                            runtime.observation_values_digest({"2020-01-01": "12345678901234567890.1234567892"}))

    def test_partial_digestless_and_stale_source_proofs_cannot_verify_the_panel(self):
        self.yields()
        original = self.proof(YIELDS)
        for mutation in ("partial", "digestless", "wrong_contract", "false_match", "source_dropped_periods"):
            proof = copy.deepcopy(original)
            if mutation == "partial": proof["series"].pop()
            elif mutation == "digestless": proof["series"][0].pop("stored_observations_sha256")
            elif mutation == "wrong_contract": proof["series"][0]["source_contract_sha256"] = "c" * 64
            elif mutation == "source_dropped_periods": proof["series"][0]["source_covers_all_stored_periods"] = False
            else: proof["series"][0]["source_values_match"] = False
            with self.subTest(proof=mutation):
                self.assertFalse(self.panel(self.build(proof), "M02")["source_reconciled"])
        self.insert(YIELDS[0], {"2020-01-02": "4.01"})
        stale = self.panel(self.build(original), "M02")
        self.assertFalse(stale["source_reconciled"])
        self.assertIn("source_proof_stale", stale["failure_codes"])

    def test_source_verified_bad_yield_identity_fails_and_rounding_is_explicit(self):
        self.yields()
        self.insert(YIELDS[2], {"2020-01-02": "2.51"})
        self.assertTrue(self.panel(self.build(self.proof(YIELDS)), "M02")["checks"][0]["passed"])
        self.insert(YIELDS[2], {"2020-01-02": "2.52"})
        panel = self.panel(self.build(self.proof(YIELDS)), "M02")
        self.assertFalse(panel["checks"][0]["passed"])
        self.assertEqual(panel["state"], "comparison_check_failed")
        self.assertIn("2020-01-02", panel["checks"][0]["failed_periods"])

    def test_metadata_mismatch_or_missing_required_input_fails_closed(self):
        self.yields()
        registry = copy.deepcopy(self.registry)
        next(row for row in registry if row["id"] == YIELDS[1])["frequency"] = "M"
        panel = self.panel(self.build(self.proof(YIELDS), registry), "M02")
        self.assertEqual(panel["state"], "metadata_mismatch")
        self.assertIn("native_frequency_mismatch", panel["failure_codes"])
        missing = self.panel(self.build(), "G06")
        self.assertEqual(missing["state"], "inputs_missing")
        self.assertEqual(missing["matched_period_count"], 0)

    def test_quarterly_gap_diagnostics_do_not_create_observations(self):
        ids = ["labour.us.nonfarm_productivity", "labour.us.nonfarm_hourly_comp", "prices.us.nonfarm_output_deflator"]
        for sid in ids:
            self.insert(sid, {"2020-01-01": "100", "2020-04-01": "101", "2020-10-01": "103"})
        panel = self.panel(self.build(self.proof(ids)), "L01")
        self.assertEqual(panel["matched_period_count"], 3)
        self.assertEqual(panel["input_coverage"][ids[0]]["missing_internal_periods"], ["2020-07-01"])
        self.assertFalse(panel["requested_coverage_complete"])
        self.assertNotIn("2020-07-01", panel["matched_periods"])

    def test_dfa_partition_and_tiva_identity_check_real_matched_values(self):
        dfa = ["wealth.us.top1_share", "wealth.us.next9_share", "wealth.us.middle40_share", "wealth.us.bottom50_share"]
        for sid, value in zip(dfa, ["32", "38", "28", "2"]): self.insert(sid, {"2020-01-01": value})
        self.assertTrue(self.panel(self.build(self.proof(dfa)), "L05")["checks"][0]["passed"])
        self.insert(dfa[-1], {"2020-01-01": "4"})
        self.assertEqual(self.panel(self.build(self.proof(dfa)), "L05")["state"], "comparison_check_failed")
        ids = []
        for country in ["us", "fr", "pt", "cn", "jp", "de", "in"]:
            for suffix, value in [("foreign_final_demand_va", "25"), ("value_added", "100"), ("foreign_final_demand_share", "25")]:
                sid = f"supply_chain.{country}.{suffix}"
                ids.append(sid)
                self.insert(sid, {"2020-01-01": value})
        self.assertTrue(self.panel(self.build(self.proof(ids)), "G06")["checks"][0]["passed"])
        self.insert("supply_chain.pt.value_added", {"2020-01-01": "0"})
        self.assertEqual(self.panel(self.build(self.proof(ids)), "G06")["state"], "comparison_check_failed")

    def test_four_one_decimal_published_shares_use_the_joint_rounding_bound(self):
        # Each independently rounded 0.1pp share has a 0.05pp error bound;
        # four published groups can differ from 100 by at most 0.2pp.
        ids = ["wealth.us.top1_share", "wealth.us.next9_share", "wealth.us.middle40_share", "wealth.us.bottom50_share"]
        for sid, value in zip(ids, ["32.1", "38.0", "28.0", "2.0"]):
            self.insert(sid, {"2020-01-01": value})
        panel = self.panel(self.build(self.proof(ids)), "L05")
        self.assertTrue(panel["checks"][0]["passed"])
        self.assertEqual(panel["checks"][0]["tolerance"], "0.2")
        self.insert(ids[-1], {"2020-01-01": "2.3"})
        self.assertFalse(self.panel(self.build(self.proof(ids)), "L05")["checks"][0]["passed"])

    def test_canonical_artifacts_detect_tampering_and_changed_observation_versions(self):
        self.yields()
        runtime = self.runtime()
        report = self.build(self.proof(YIELDS))
        self.assertEqual(runtime.validate_comparative_corpus(report, self.registry, self.document), [])
        receipt = runtime.store_comparative_corpus(report, Path(self.tmp.name))
        path = Path(receipt["report_path"])
        self.assertTrue(path.is_file())
        with Session(self.engine) as session:
            self.assertEqual(runtime.load_comparative_corpus(path, self.registry, self.document, session=session)["report_sha256"], report["report_sha256"])
        tampered = copy.deepcopy(report)
        self.panel(tampered, "M02")["rows"][0]["values"][YIELDS[0]] = "99"
        self.assertIn("report_hash_mismatch", runtime.validate_comparative_corpus(tampered, self.registry, self.document))
        # Even an unchanged value in a newer DB version invalidates the old row-version evidence.
        self.insert(YIELDS[0], {"2020-01-02": "4"})
        with Session(self.engine) as session:
            self.assertIn("stale_observation_versions", runtime.validate_comparative_corpus(report, self.registry, self.document, session=session))
        path.write_text(json.dumps(tampered))
        with self.assertRaises(ValueError): runtime.load_comparative_corpus(path, self.registry, self.document)

    def test_forged_panel_flags_cannot_become_api_acceptance(self):
        self.yields()
        runtime = self.runtime()
        report = self.build()
        panel = self.panel(report, "M02")
        panel.update(state="fully_validated_comparative_corpus", full_analysis_accepted=True,
                     first_publication_verified=True, source_reconciled=True)
        # Rehashing an edited claim does not make it the result of the source/row checks.
        panel["panel_sha256"] = runtime.payload_digest({k:v for k,v in panel.items() if k != "panel_sha256"})
        report["report_sha256"] = runtime.payload_digest({k:v for k,v in report.items() if k != "report_sha256"})
        self.assertTrue(runtime.validate_comparative_corpus(report, self.registry, self.document))
        from finance_dashboard.research_corpus import research_corpus_report
        output = research_corpus_report(self.document, series_registry=self.registry, comparative_evidence=report)
        self.assertEqual(output["fully_validated_analysis_count"], 0)
        self.assertEqual(output["bounded_current_vintage_panel_count"], 0)


if __name__ == "__main__": unittest.main()
