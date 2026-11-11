"""Repeated reads share work only while the assessed inputs are unchanged."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Barrier, Event
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from engine_fixtures import seed
from finance_dashboard.api import create_app
from finance_dashboard.database import Base, ObservationVersion, make_engine
from finance_dashboard.engine.acceptance import AcceptanceCache, snapshot_from_report
from finance_dashboard.engine.analyses import P07
from finance_dashboard.engine.evidence_guard import EvidenceState
from finance_dashboard.engine.cache import BundleCache, SQLiteRevision
from finance_dashboard.engine.export import export_text
from finance_dashboard.comparative_corpus import observation_versions_digest
from finance_dashboard.service import current_observations
from test_engine_api import AT, report
from test_engine_p07 import p07_fixture


class BundleCacheApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.evidence = self.root / 'evidence'
        self.evidence.mkdir()
        self.owner = self.root / 'owner.json'
        self.owner.write_text('{}')
        self.holdings = self.root / 'portfolio-holdings.json'
        self.env = patch.dict(os.environ, {
            'FINANCE_AUTO_REFRESH': '0', 'FINANCE_AUTO_BACKUP': '0',
            'FINANCE_INCLUDE_MARKETS': '0', 'FINANCE_OWNER_INPUTS': str(self.owner),
            'FINANCE_PORTFOLIO_HOLDINGS': str(self.holdings),
            'FINANCE_SOURCE_EVIDENCE_DIR': str(self.evidence),
            'FINANCE_HOLDINGS_DIR': str(self.root / 'holdings'),
        })
        self.env.start()
        self.engine = make_engine('sqlite:///' + str(self.root / 'test.sqlite'))
        Base.metadata.create_all(self.engine)
        seed(self.engine, p07_fixture())
        self.app = create_app(self.engine)
        self.bind_snapshot()
        self.ctx = TestClient(self.app)
        self.client = self.ctx.__enter__()

    def bind_snapshot(self):
        with Session(self.engine) as session:
            versions = {sid: observation_versions_digest(current_observations(session, sid))
                        for sid in P07.inputs.values()}
        snapshot = replace(snapshot_from_report(report(), AT), source_versions=versions,
                           evidence_state=EvidenceState.capture([self.evidence, self.owner, self.holdings]))
        self.app.state.acceptance = AcceptanceCache(lambda: snapshot, 3600, spawn=lambda work: work())

    def tearDown(self):
        self.ctx.__exit__(None, None, None)
        self.engine.dispose()
        self.env.stop()
        self.temp.cleanup()

    def result(self, **params):
        result = self.client.get('/api/analysis/P07', params=params)
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def test_repeat_and_export_reuse_one_assessed_computation(self):
        first = self.result(today='2026-11-06')
        second = self.result(today='2026-11-06')
        exported = self.client.get('/api/analysis/P07/export', params={'today': '2026-11-06'})
        self.assertEqual(second, first)
        self.assertEqual(exported.text, export_text(first))

    def test_concurrent_identical_requests_share_the_computation(self):
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: self.result(), range(6)))
        self.assertEqual(len({row['computed_at'] for row in results}), 1)

    def test_date_and_configured_figures_do_not_collide(self):
        first = self.result(today='2026-11-06')
        other_day = self.result(today='2025-11-06')
        self.assertNotEqual(first['values'], other_day['values'])
        caps = self.client.get('/api/analysis/P07/views/capabilities').json()
        spec = caps['figures'][0]['defaults']
        configured = self.result(view=json.dumps(spec))
        self.assertIn('figure', configured)
        self.assertNotIn('figure', self.result())
        self.assertEqual(self.result(view=json.dumps(spec, sort_keys=True)), configured)

    def test_new_unverified_version_cannot_reuse_a_cached_result_or_export(self):
        self.result()
        with Session(self.engine) as session, session.begin():
            last = current_observations(session, P07.inputs['equity_netr_usd'])[-1]
            session.add(ObservationVersion(series_id=last.series_id, period=last.period, value=last.value,
                first_seen_at=datetime(2026, 11, 11, tzinfo=timezone.utc), ingestion_run_id=last.ingestion_run_id))
        for suffix in ('', '/views/capabilities', '/export'):
            response = self.client.get('/api/analysis/P07' + suffix)
            self.assertEqual(response.status_code, 503)
            self.assertIn('Retry-After', response.headers)

    def test_in_place_value_edit_is_withheld_and_reassessment_recomputes(self):
        first = self.result()
        with Session(self.engine) as session, session.begin():
            last = current_observations(session, P07.inputs['equity_netr_usd'])[-3]
            last.value *= 2
        self.assertEqual(self.client.get('/api/analysis/P07').status_code, 503)
        self.bind_snapshot()
        reassessed = self.result()
        self.assertNotEqual(first['values'], reassessed['values'])

    def test_evidence_and_owner_file_changes_cannot_reuse_results(self):
        for target in (self.evidence / 'original.csv', self.owner, self.holdings):
            self.bind_snapshot()
            self.result()
            target.write_text('changed')
            self.assertEqual(self.client.get('/api/analysis/P07').status_code, 503)

    def test_a_new_assessment_never_reuses_previous_phase2_metadata(self):
        first = self.result()
        self.bind_snapshot()
        second = self.result()
        self.assertNotEqual(first['computed_at'], second['computed_at'])


class BundleCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / 'test.sqlite'
        self.engine = make_engine('sqlite:///' + str(self.path))
        with sqlite3.connect(self.path) as connection:
            connection.execute('CREATE TABLE revision (value INTEGER)')
            connection.execute('INSERT INTO revision VALUES (1)')
        self.snapshot = SimpleNamespace(evidence_state=EvidenceState.capture([]))
        self.cache = BundleCache(self.engine, max_entries=2)

    def tearDown(self):
        self.cache.close()
        self.engine.dispose()
        self.temp.cleanup()

    def load(self):
        with sqlite3.connect(self.path) as connection:
            return {'values': [connection.execute('SELECT value FROM revision').fetchone()[0]]}

    def write(self, value):
        with sqlite3.connect(self.path) as connection:
            connection.execute('UPDATE revision SET value = ?', (value,))

    def test_hits_and_returns_are_independent_mutable_bundles(self):
        first = self.cache.get('same', self.snapshot, self.load)
        first['values'].append('client edit')
        second = self.cache.get('same', self.snapshot, self.load)
        self.assertEqual(second, {'values': [1]})
        second['values'].clear()
        self.assertEqual(self.cache.get('same', self.snapshot, self.load), {'values': [1]})

    def test_least_recently_used_entries_are_bounded(self):
        calls = []
        def load(key):
            calls.append(key)
            return self.load()
        for key in ('a', 'b', 'a', 'c', 'b'):
            self.cache.get(key, self.snapshot, lambda: load(key))
        self.assertEqual(calls, ['a', 'b', 'c', 'b'])

    def test_external_commit_invalidates_the_completed_bundle(self):
        self.assertEqual(self.cache.get('same', self.snapshot, self.load)['values'], [1])
        self.write(2)
        self.assertEqual(self.cache.get('same', self.snapshot, self.load)['values'], [2])

    def test_database_replacement_invalidates_the_completed_bundle(self):
        self.cache.get('same', self.snapshot, self.load)
        replacement = self.root / 'replacement.sqlite'
        with sqlite3.connect(replacement) as connection:
            connection.execute('CREATE TABLE revision (value INTEGER)')
            connection.execute('INSERT INTO revision VALUES (2)')
        replacement.replace(self.path)
        self.assertEqual(self.cache.get('same', self.snapshot, self.load)['values'], [2])

    def test_commit_during_computation_rechecks_and_cannot_populate_old_revision(self):
        calls = []
        def load():
            result = self.load()
            calls.append(result['values'][0])
            if len(calls) == 1:
                self.write(2)
            return result
        self.assertEqual(self.cache.get('same', self.snapshot, load)['values'], [2])
        self.assertEqual(self.cache.get('same', self.snapshot, load)['values'], [2])
        self.assertEqual(calls, [1, 2, 2])

    def test_overlapping_requests_share_work_but_not_mutable_results(self):
        entered, release = Event(), Event()
        started = Barrier(6)
        calls = []
        def load():
            calls.append(1)
            entered.set()
            self.assertTrue(release.wait(5))
            return self.load()
        def request():
            started.wait(5)
            return self.cache.get('same', self.snapshot, load)
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(request) for _ in range(6)]
            self.assertTrue(entered.wait(5))
            release.set()
            results = [future.result(5) for future in futures]
        self.assertEqual(len(calls), 1)
        results[0]['values'].append('edit')
        self.assertTrue(all(result == {'values': [1]} for result in results[1:]))

    def test_failed_computation_is_not_reused(self):
        with self.assertRaisesRegex(ValueError, 'failed input'):
            self.cache.get('same', self.snapshot,
                           lambda: (_ for _ in ()).throw(ValueError('failed input')))
        self.assertEqual(self.cache.get('same', self.snapshot, self.load), {'values': [1]})

    def test_unavailable_revision_or_assessment_uses_normal_loader(self):
        for snapshot in (self.snapshot, SimpleNamespace(evidence_state=None)):
            with patch.object(self.cache._revision, 'capture', return_value=None):
                self.assertEqual(self.cache.get('same', snapshot, self.load), self.load())
                self.write(2)
                self.assertEqual(self.cache.get('same', snapshot, self.load), {'values': [2]})

    def test_in_memory_sqlite_never_reuses_results(self):
        engine = make_engine('sqlite://')
        try:
            self.assertIsNone(SQLiteRevision(engine).capture())
        finally:
            engine.dispose()


if __name__ == '__main__':
    unittest.main()
