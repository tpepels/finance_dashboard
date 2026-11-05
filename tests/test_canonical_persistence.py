"""Academic return inputs retain original identity through canonical ingestion."""
from datetime import date
from decimal import Decimal
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from finance_dashboard.catalog import load_documents, validate
from finance_dashboard.database import Base, make_engine, IngestionRun, ObservationVersion
from finance_dashboard.providers import ProviderRouter
from finance_dashboard.provider_parsers import SourceUnavailable
from finance_dashboard.research_returns import FRENCH_SERIES, SWINKELS_SERIES
from finance_dashboard.service import IngestionService, current_observations
from test_research_returns import FIXTURES, ODS, french_zip


def source_response(request, developed_body=None):
    if request.url.path.endswith('Developed_3_Factors_CSV.zip'):
        body = french_zip(body=developed_body)
    elif request.url.path.endswith('Emerging_5_Factors_CSV.zip'):
        body = french_zip('emerging')
    elif request.url.path.endswith('512630'):
        body = (FIXTURES / ODS).read_bytes()
    elif request.url.path.endswith('512631'):
        body = (FIXTURES / 'swinkels_readme.pdf').read_bytes()
    elif request.url.host == 'api.figshare.com':
        body = (FIXTURES / 'swinkels_original_figshare_v6_metadata.json').read_bytes()
    elif request.url.host == 'dataverse.nl':
        body = (FIXTURES / 'swinkels_publisher_metadata.json').read_bytes()
    else:
        raise AssertionError('Unexpected original source request')
    return httpx.Response(200, content=body, request=request)


class CanonicalReturnPersistenceTests(unittest.TestCase):
    def test_canonical_returns_bind_original_keys_native_units_and_scopes(self):
        # A missing declaration or relabelled benchmark cannot hide behind adapter support.
        series, charts = load_documents()
        self.assertEqual(validate(series, charts), [])
        by_id = {item['id']: item for item in series['series']}
        for sid, (dataset, variable) in FRENCH_SERIES.items():
            self.assertIn(sid, by_id)
            item = by_id[sid]
            self.assertEqual((item['provider'], item['source_key'], item['unit'], item['frequency']),
                             ('FRENCH_RETURNS', dataset+'/'+variable, 'percent', 'M'))
            self.assertEqual(item['currency'], 'USD')
            self.assertNotEqual(item['geography'], 'WORLD')
        for sid, (sheet, column) in SWINKELS_SERIES.items():
            self.assertIn(sid, by_id)
            item = by_id[sid]
            self.assertEqual((item['provider'], item['source_key'], item['unit'], item['frequency']),
                             ('SWINKELS_RETURNS', f'{sheet}/column:{column}/cached_decimal_return', 'ratio', 'M'))
            self.assertEqual(item['dataset_version'], '10.25397/eur.8152748.v6')
            self.assertEqual(item['published_through'], '2022-12-01')
            self.assertNotEqual(item['geography'], 'WORLD')

    def test_real_sixteen_source_histories_survive_storage_reopen_and_idempotent_refresh(self):
        # Lost early periods, Decimal scaling and artificial SQLite revisions fail.
        with TemporaryDirectory() as tmp, httpx.Client(transport=httpx.MockTransport(source_response)) as http:
            root = Path(tmp)
            url = 'sqlite+pysqlite:///' + str(root / 'returns.sqlite3')
            with patch.dict(os.environ, {'FINANCE_SOURCE_EVIDENCE_DIR': str(root/'evidence')}):
                engine = make_engine(url)
                Base.metadata.create_all(engine)
                router = ProviderRouter(client=http)
                service = IngestionService(engine, router)
                added = 0
                for sid in list(FRENCH_SERIES) + list(SWINKELS_SERIES):
                    report = service.refresh(sid)
                    added += report['versions_added']
                    self.assertEqual(report['status'], 'success')
                    self.assertEqual(service.refresh(sid)['versions_added'], 0)
                # Original ODS7435 + factual French excerpt(18+20)*3.
                self.assertEqual(added, 7549)
                with Session(engine) as session:
                    self.assertEqual(session.scalar(select(func.count()).select_from(ObservationVersion)), 7549)
                    runs = session.scalars(select(IngestionRun)).all()
                    self.assertTrue(all(run.requested_from is None for run in runs))
                    self.assertIsNone(next(run for run in runs if run.series_id.startswith('returns.')).response_prepared_at)
                engine.dispose()
                reopened = make_engine(url)
                with Session(reopened) as session:
                    equity = current_observations(session, 'returns.french.developed.market_total_usd')
                    self.assertEqual((equity[0].period, equity[0].value), (date(1990,7,1), Decimal('1.4500000000')))
                    bonds = current_observations(session, 'returns.swinkels.de.sovereign_10y_modelled_local')
                    self.assertEqual((bonds[0].period, bonds[0].value), (date(1972,10,1), Decimal('-0.0180878031')))
                    self.assertEqual(len(bonds), 603)
                manifests = list((root/'evidence/research-returns').glob('**/manifest.json'))
                self.assertEqual(len(manifests), 3)
                self.assertTrue(all(json.loads(p.read_text())['original_first_publication_at'] is None for p in manifests))
                reopened.dispose()

    def test_default_snapshot_refresh_records_old_equity_correction_and_preserves_versions(self):
        # Applying the ordinary two-year monthly overlap loses a 1990 correction.
        original = (FIXTURES/'developed_excerpts.csv').read_text()
        latest = {'body': original}
        with TemporaryDirectory() as tmp, httpx.Client(transport=httpx.MockTransport(
                lambda request: source_response(request, latest['body']))) as http:
            with patch.dict(os.environ, {'FINANCE_SOURCE_EVIDENCE_DIR': str(Path(tmp)/'evidence')}):
                engine = make_engine('sqlite+pysqlite:///'+str(Path(tmp)/'returns.sqlite3'))
                Base.metadata.create_all(engine)
                sid = 'returns.french.developed.market_total_usd'
                first = IngestionService(engine, ProviderRouter(client=http)).refresh(sid)
                self.assertEqual(first['versions_added'], 18)
                latest['body'] = original.replace('0.77    ,0.53', '0.78    ,0.53', 1)
                revised = IngestionService(engine, ProviderRouter(client=http)).refresh(sid)
                self.assertEqual(revised['versions_added'], 1)
                with Session(engine) as session:
                    values = current_observations(session, sid)
                    self.assertEqual(values[0].value, Decimal('1.4600000000'))
                    self.assertEqual(session.scalar(select(func.count()).select_from(ObservationVersion)), 19)
                    self.assertEqual({x.value for x in session.scalars(select(ObservationVersion).where(
                        ObservationVersion.period==date(1990,7,1)))}, {Decimal('1.4500000000'),Decimal('1.4600000000')})
                engine.dispose()

    def test_identity_drift_is_rejected_before_original_source_request(self):
        # A changed convention must not inherit an old source label.
        with httpx.Client(transport=httpx.MockTransport(lambda request: self.fail('Identity drift reached network'))) as http:
            router = ProviderRouter(client=http)
            for sid in ('returns.french.developed.market_total_usd', 'returns.swinkels.jp.sovereign_10y_modelled_local'):
                self.assertIn(sid, router.definitions)
                router.definitions[sid] = {**router.definitions[sid], 'source_key': 'wrong-source-concept'}
                with self.assertRaises(SourceUnavailable):
                    router.fetch(sid)
