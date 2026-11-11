"""Acceptance must never authorize revisions or evidence different from its proof."""
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest

from sqlalchemy.orm import Session
from finance_dashboard.database import ObservationVersion
from finance_dashboard.service import current_observations
from finance_dashboard.comparative_corpus import observation_versions_digest
from finance_dashboard.engine.acceptance import AcceptanceCache, snapshot_from_report
from finance_dashboard.engine.evidence_guard import EvidenceState, AcceptedInputsChanged
import test_engine_api as api_fixture
from test_engine_api import report, AT
from finance_dashboard.engine.analyses import P07


class EvidenceGuardTests(unittest.TestCase):
    setUp = api_fixture.EngineApiTests.setUp
    tearDown = api_fixture.EngineApiTests.tearDown

    def test_evidence_changing_during_assessment_is_retried_as_loading(self):
        def loader(): raise AcceptedInputsChanged('sources changed')
        self.app.state.acceptance = AcceptanceCache(loader, 3600, spawn=lambda work: work())
        result = self.client.get('/api/analysis/P07')
        self.assertEqual(result.status_code, 503)
        self.assertIn('Retry-After', result.headers)

    def bind_snapshot(self, evidence=None):
        with Session(self.engine) as session:
            versions = {sid: observation_versions_digest(current_observations(session, sid)) for sid in P07.inputs.values()}
        snapshot = replace(snapshot_from_report(report(), AT), source_versions=versions, evidence_state=evidence)
        cache = AcceptanceCache(lambda: snapshot, 3600, spawn=lambda work: work())
        cache.get()
        self.app.state.acceptance = cache
        return cache

    def test_a_new_unverified_version_is_withheld_even_when_value_is_unchanged(self):
        self.bind_snapshot()
        self.assertEqual(self.client.get('/api/analysis/P07').status_code, 200)
        with Session(self.engine) as session, session.begin():
            last = current_observations(session, P07.inputs['equity_netr_usd'])[-1]
            session.add(ObservationVersion(series_id=last.series_id, period=last.period, value=last.value,
                first_seen_at=datetime(2026, 11, 11, tzinfo=timezone.utc), ingestion_run_id=last.ingestion_run_id))
        response = self.client.get('/api/analysis/P07')
        self.assertEqual(response.status_code, 503)
        self.assertIn('Retry-After', response.headers)
        self.assertEqual(self.client.get('/api/analysis/P07/export').status_code, 503)

    def test_original_tampering_or_disappearance_with_unchanged_db_is_withheld(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp); original = root/'original.csv'; original.write_text('a,b\n1,2\n')
            before = original.stat()
            self.bind_snapshot(EvidenceState.capture([root]))
            self.assertEqual(self.client.get('/api/analysis/P07').status_code, 200)
            original.write_text('a,b\n1,3\n')
            os.utime(original, ns=(before.st_atime_ns, before.st_mtime_ns))
            self.assertEqual(self.client.get('/api/analysis/P07').status_code, 503)
            self.bind_snapshot(EvidenceState.capture([root]))
            original.unlink()
            self.assertEqual(self.client.get('/api/analysis/P07').status_code, 503)


if __name__ == '__main__': unittest.main()
