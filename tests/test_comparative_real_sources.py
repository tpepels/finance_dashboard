"""Real original return histories through ingestion, panels and full recovery."""
import json
from pathlib import Path
import shutil
import tarfile
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from finance_dashboard.backup import backup_local, verify_manifest
from finance_dashboard.catalog import load_documents
from finance_dashboard.comparative_corpus import build_comparative_corpus, store_comparative_corpus, load_comparative_corpus
from finance_dashboard.database import Base, ObservationVersion
from finance_dashboard.providers import ProviderRouter
from finance_dashboard.research_corpus import load_research_corpus
from finance_dashboard.research_returns import FRENCH_SERIES, SWINKELS_SERIES
from finance_dashboard.service import IngestionService
from finance_dashboard.source_reconciliation import reconcile_session
from test_canonical_persistence import source_response


class RealComparativeRecoveryTests(unittest.TestCase):
    def test_original_native_histories_panels_and_evidence_survive_backup_restore(self):
        # The complete CC-BY workbook and factual French excerpts are original
        # historical inputs. Full French outputs stay in private acquisition storage.
        registry = load_documents()[0]["series"]
        corpus = load_research_corpus()
        corpus = {**corpus, "analyses": [item for item in corpus["analyses"] if item["id"] == "P02"]}
        ids = sorted(set(FRENCH_SERIES) | set(SWINKELS_SERIES))
        with TemporaryDirectory() as temp:
            root = Path(temp)
            evidence = root / "source-evidence"
            db = root / "original.sqlite3"
            engine = create_engine("sqlite:///" + str(db))
            Base.metadata.create_all(engine)
            with patch.dict("os.environ", {"FINANCE_SOURCE_EVIDENCE_DIR": str(evidence)}):
                with httpx.Client(transport=httpx.MockTransport(source_response)) as http:
                    service = IngestionService(engine, ProviderRouter(http))
                    for sid in ids:
                        self.assertEqual(service.refresh(sid)["status"], "success")
            with Session(engine) as session:
                self.assertEqual(session.scalar(select(func.count()).select_from(ObservationVersion)), 7549)
                proof = reconcile_session(session, evidence, ids)
                self.assertTrue(proof["passed"], proof)
                self.assertEqual(proof["matched_series"], 16)
                report = build_comparative_corpus(session, registry, corpus, source_proof=proof)
                self.assertEqual(report["bounded_current_vintage_panel_count"], 3)
                self.assertEqual(report["fully_validated_analysis_count"], 0)
                self.assertTrue(all(not panel["full_analysis_accepted"] for panel in report["panels"]))
                receipt = store_comparative_corpus(report, evidence)
            engine.dispose()
            backup = backup_local(root / "backups", source_db=db, evidence_roots={"source-evidence": evidence})
            manifest = next((root / "backups").glob("finance-*Z.json"))
            self.assertTrue(verify_manifest(manifest)["verified"])
            restored = root / "restored"
            restored.mkdir()
            restored_db = restored / "finance.sqlite3"
            shutil.copyfile(root / "backups" / backup["database"]["file"], restored_db)
            with tarfile.open(root / "backups" / backup["evidence_archive"]["file"], "r:gz") as archive:
                archive.extractall(restored, filter="data")
            restored_engine = create_engine("sqlite:///" + str(restored_db))
            try:
                with Session(restored_engine) as session:
                    self.assertEqual(session.scalar(select(func.count()).select_from(ObservationVersion)), 7549)
                    original_report = Path(receipt["report_path"])
                    restored_report = restored / "source-evidence" / original_report.relative_to(evidence)
                    recovered = load_comparative_corpus(restored_report, registry, corpus, session=session)
                    self.assertEqual(recovered["report_sha256"], report["report_sha256"])
                    restored_proof = reconcile_session(session, restored / "source-evidence", ids)
                    self.assertTrue(restored_proof["passed"])
                    current = build_comparative_corpus(session, registry, corpus, source_proof=restored_proof)
                    self.assertEqual([p["panel_sha256"] for p in current["panels"]], [p["panel_sha256"] for p in report["panels"]])
            finally:
                restored_engine.dispose()
