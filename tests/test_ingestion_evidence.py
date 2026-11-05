"""Routine ingestion and immutable original-source evidence form one contract."""
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from finance_dashboard.database import Base, IngestionRun, ObservationVersion
from finance_dashboard.providers import ProviderRouter
from finance_dashboard.source_capture import SourceAcquisition
from finance_dashboard.service import IngestionService
from finance_dashboard.source_evidence_audit import (
    SourceEvidenceIntegrityError, verify_ingestion_receipt,
)


class IngestionEvidenceTests(unittest.TestCase):
    def test_full_then_partial_refresh_records_exact_archived_receipts(self):
        payload = b'{"observations":[{"date":"2024-01-02","value":"3.95"}]}'
        with TemporaryDirectory() as temp, patch.dict("os.environ", {
                "FRED_API_KEY": "private-secret-key"}):
            root = Path(temp)
            engine = create_engine("sqlite+pysqlite:///:memory:")
            Base.metadata.create_all(engine)
            calls = []
            def respond(request):
                calls.append(request)
                return httpx.Response(200, content=payload)
            try:
                with httpx.Client(transport=httpx.MockTransport(respond)) as client:
                    gateway = SourceAcquisition(ProviderRouter(client), root / "evidence")
                    service = IngestionService(engine, gateway)
                    first = service.refresh("bond.us.nominal_10y",
                                            today=date(2025, 1, 1))
                    second = service.refresh("bond.us.nominal_10y",
                                             today=date(2025, 1, 1))
                    self.assertEqual(first["versions_added"], 1)
                    self.assertEqual(second["versions_added"], 0)
                with Session(engine) as session:
                    runs = session.scalars(select(IngestionRun).order_by(
                        IngestionRun.started_at, IngestionRun.id)).all()
                    self.assertEqual(len(runs), 2)
                    scopes = {r.evidence_scope for r in runs}
                    self.assertEqual(scopes, {"full_source_snapshot",
                                              "requested_period_subset"})
                    for run in runs:
                        self.assertEqual(run.evidence_kind, "response")
                        self.assertRegex(run.evidence_bundle_digest, r"^[a-f0-9]{64}$")
                        folder = (root / "evidence" / "responses" / run.series_id /
                                  run.evidence_bundle_digest)
                        self.assertEqual((folder / "response-0.bin").read_bytes(), payload)
                        self.assertEqual(
                            json.loads((folder / "manifest.json").read_text())["scope"],
                            run.evidence_scope)
                        self.assertTrue((folder.parent / "retrievals" /
                                         run.evidence_receipt_name).is_file())
                        verified = verify_ingestion_receipt(
                            root / "evidence", series_id=run.series_id,
                            scope=run.evidence_scope,
                            bundle_digest=run.evidence_bundle_digest,
                            receipt_name=run.evidence_receipt_name)
                        self.assertEqual(
                            verified["status"], "verified_immutable_original_response")
                        self.assertFalse(verified["first_publication_verified"])
                    self.assertEqual(session.query(ObservationVersion).count(), 1)
                self.assertEqual(len(calls), 2)
                self.assertEqual(sha256(payload).hexdigest(),
                                 sha256((root / "evidence" / "responses" /
                                         "bond.us.nominal_10y" /
                                         runs[0].evidence_bundle_digest /
                                         "response-0.bin").read_bytes()).hexdigest())
                for path in (root / "evidence").rglob("*.json"):
                    self.assertNotIn("private-secret-key", path.read_text())
            finally:
                engine.dispose()

    def test_audit_detects_modified_original_without_recovering_over_it(self):
        raw = b'{"observations":[{"date":"2024-01-02","value":"3.95"}]}'
        with TemporaryDirectory() as temp, patch.dict("os.environ", {
                "FRED_API_KEY": "secret"}):
            root = Path(temp)
            with httpx.Client(transport=httpx.MockTransport(
                    lambda req: httpx.Response(200, content=raw))) as client:
                gateway = SourceAcquisition(ProviderRouter(client), root)
                gateway.fetch("bond.us.nominal_10y")
            evidence = gateway.last_evidence
            bundle = root / "responses" / "bond.us.nominal_10y" / evidence["bundle_digest"]
            original = bundle / "response-0.bin"
            original.write_bytes(b"corrupted")
            with self.assertRaises(SourceEvidenceIntegrityError) as raised:
                verify_ingestion_receipt(
                    root, series_id="bond.us.nominal_10y",
                    scope=evidence["scope"], bundle_digest=evidence["bundle_digest"],
                    receipt_name=evidence["receipt_name"])
            self.assertEqual(raised.exception.code, "source_original_hash_mismatch")
            self.assertEqual(original.read_bytes(), b"corrupted")

    def test_failed_parse_keeps_earlier_history_and_is_not_certified(self):
        calls = []
        def respond(request):
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(200, json={
                    "observations": [{"date": "2024-01-02", "value": "3.95"}]})
            return httpx.Response(200, content=b"not-json")
        with TemporaryDirectory() as temp, patch.dict("os.environ", {
                "FRED_API_KEY": "secret"}):
            engine = create_engine("sqlite+pysqlite:///:memory:")
            Base.metadata.create_all(engine)
            try:
                with httpx.Client(transport=httpx.MockTransport(respond)) as client:
                    service = IngestionService(
                        engine, SourceAcquisition(ProviderRouter(client),
                                                  Path(temp) / "evidence"))
                    service.refresh("bond.us.nominal_10y", today=date(2025, 1, 1))
                    with self.assertRaises((ValueError, httpx.DecodingError)):
                        service.refresh("bond.us.nominal_10y",
                                        today=date(2025, 1, 1))
                with Session(engine) as session:
                    history = session.scalars(select(IngestionRun)).all()
                    self.assertEqual([r.status for r in history].count("success"), 1)
                    self.assertEqual([r.status for r in history].count("failed"), 1)
                    failed = next(r for r in history if r.status == "failed")
                    self.assertIsNone(failed.evidence_bundle_digest)
                    values = session.scalars(select(ObservationVersion)).all()
                    self.assertEqual(len(values), 1)
                    self.assertEqual(values[0].value, Decimal("3.9500000000"))
                rejected = list((Path(temp) / "evidence" / "rejected-responses").rglob(
                    "manifest.json"))
                self.assertEqual(len(rejected), 1)
            finally:
                engine.dispose()


if __name__ == "__main__":
    unittest.main()
