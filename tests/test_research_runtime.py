"""One fresh, read-only evaluation binds source roles and public evidence."""
from dataclasses import FrozenInstanceError
import importlib
import importlib.util
import json
from pathlib import Path
from datetime import datetime, timezone
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from finance_dashboard.catalog import load_documents
from finance_dashboard.database import Base, ObservationVersion
from finance_dashboard.providers import ProviderRouter
from finance_dashboard.research_corpus import load_research_corpus
from finance_dashboard.service import IngestionService
from finance_dashboard.source_capture import CapturedProvider


FIXTURES = Path(__file__).parent / "fixtures" / "phase2_native_inputs"


class ResearchRuntimeTests(unittest.TestCase):
    def runtime(self):
        self.assertIsNotNone(importlib.util.find_spec("finance_dashboard.research_runtime"),
                             "API and CLI need one canonical corpus evaluation")
        return importlib.import_module("finance_dashboard.research_runtime")

    def test_source_selection_includes_unplotted_roles_once(self):
        corpus = {"analyses": [{"comparison_contract": {
            "original_requirements": [{"series_ids": ["unplotted", "shared"]},
                                      {"series_ids": []}],
            "variants": [{"series_ids": ["shared", "plotted"]}],
        }, "context_series_ids": ["context", "shared"]}]}
        self.assertEqual(self.runtime().required_series_ids(corpus),
                         ["context", "plotted", "shared", "unplotted"])

    def test_original_unplotted_cpi_evidence_is_fresh_and_read_only(self):
        runtime = self.runtime()
        registry = load_documents()[0]["series"]
        document = load_research_corpus()
        document = {**document, "analyses": [a for a in document["analyses"] if a["id"] == "P04"]}
        sid = "prices.us.cpi_all_items_sa"
        fixture = json.loads((FIXTURES / "provenance.json").read_text())[sid]
        raw = (FIXTURES / fixture["file"]).read_bytes()
        with TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / "history.db"
            evidence = root / "evidence"
            engine = create_engine("sqlite:///" + str(db))
            Base.metadata.create_all(engine)
            try:
                with patch.dict("os.environ", {"FRED_API_KEY": "", "FRED_PUBLIC_CSV_FALLBACK": "1"}):
                    with httpx.Client(transport=httpx.MockTransport(
                            lambda request: httpx.Response(200, content=raw))) as client:
                        service = IngestionService(engine, CapturedProvider(ProviderRouter(client), evidence))
                        self.assertEqual(service.refresh(sid, full=True)["status"], "success")
                before_db = db.read_bytes()
                before_files = {p.relative_to(evidence): p.read_bytes()
                                for p in evidence.rglob("*") if p.is_file()}
                evaluation = runtime.evaluate_corpus(engine, registry, document,
                    evidence_root=evidence, vintage_root=root / "vintages")
                source = next(s for s in evaluation.source_proof["series"] if s["series_id"] == sid)
                self.assertTrue(source["source_values_match"])
                role = next(r for r in evaluation.public_report["analyses"][0]["requirements"]
                            if r["role"] == "inflation_index")
                gate = next(g for g in role["checks"] if g["id"] == "original_source_values")
                self.assertEqual(gate["state"], "passed")
                self.assertFalse(evaluation.public_report["analyses"][0]["acceptance"]["accepted"])
                self.assertTrue(evaluation.public_report["alfred_publication_vintages_checked"])
                self.assertNotIn("input_observations", json.dumps(evaluation.public_report))
                self.assertEqual(db.read_bytes(), before_db)
                self.assertEqual({p.relative_to(evidence): p.read_bytes()
                                  for p in evidence.rglob("*") if p.is_file()}, before_files)
                self.assertFalse((root / "vintages").exists())
                with self.assertRaises(FrozenInstanceError):
                    evaluation.public_report = {}
                # Corrupted original bytes must be rechecked on the next read.
                original = next(p for p in evidence.rglob("*") if p.is_file() and p.read_bytes() == raw)
                original.write_bytes(raw + b"\ncorrupted")
                changed = runtime.evaluate_corpus(engine, registry, document, evidence_root=evidence)
                changed_source = next(s for s in changed.source_proof["series"] if s["series_id"] == sid)
                self.assertFalse(changed_source["source_values_match"])
                changed_role = next(r for r in changed.public_report["analyses"][0]["requirements"]
                                    if r["role"] == "inflation_index")
                changed_gate = next(g for g in changed_role["checks"] if g["id"] == "original_source_values")
                self.assertEqual(changed_gate["state"], "incomplete")
            finally:
                engine.dispose()

    def test_concurrent_same_period_revision_cannot_mix_proof_and_coverage_snapshots(self):
        runtime = self.runtime()
        registry = load_documents()[0]["series"]
        document = load_research_corpus()
        document = {**document, "analyses": [a for a in document["analyses"] if a["id"] == "P04"]}
        sid = "prices.us.cpi_all_items_sa"
        fixture = json.loads((FIXTURES / "provenance.json").read_text())[sid]
        raw = (FIXTURES / fixture["file"]).read_bytes()
        with TemporaryDirectory() as temp:
            root = Path(temp)
            engine = create_engine("sqlite:///" + str(root / "history.db"))
            with engine.connect() as connection:
                connection.exec_driver_sql("PRAGMA journal_mode=WAL")
            Base.metadata.create_all(engine)
            try:
                with patch.dict("os.environ", {"FRED_API_KEY": "", "FRED_PUBLIC_CSV_FALLBACK": "1"}):
                    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=raw))) as client:
                        ingested = IngestionService(engine, CapturedProvider(ProviderRouter(client), root / "evidence")).refresh(sid, full=True)["versions_added"]
                reconcile = runtime.reconcile_session
                def append_revision(session, *args):
                    proof = reconcile(session, *args)
                    with Session(engine) as writer:
                        row = writer.scalars(select(ObservationVersion).where(
                            ObservationVersion.series_id == sid)).first()
                        writer.add(ObservationVersion(series_id=sid, period=row.period, value=row.value + 1,
                            first_seen_at=datetime.now(timezone.utc), ingestion_run_id=row.ingestion_run_id))
                        writer.commit()
                    return proof
                with patch.object(runtime, "reconcile_session", side_effect=append_revision):
                    snapshot = runtime.evaluate_corpus(engine, registry, document, evidence_root=root / "evidence")
                source = next(s for s in snapshot.public_report["analyses"][0]["linked_sources"] if s["series_id"] == sid)
                self.assertEqual(source["stored_versions"], ingested)
                fresh = runtime.evaluate_corpus(engine, registry, document, evidence_root=root / "evidence")
                item = next(s for s in fresh.source_proof["series"] if s["series_id"] == sid)
                self.assertFalse(item["source_values_match"])
            finally:
                engine.dispose()
