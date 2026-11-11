"""Owner holdings stay distinct from model allocations and survive safe API edits."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from engine_fixtures import memory_engine
from finance_dashboard.api import create_app
from finance_dashboard.engine.acceptance import AcceptanceCache, AcceptanceSnapshot


class PortfolioHoldingsApiTests(unittest.TestCase):
    def test_owner_holdings_revision_errors_and_model_independence(self):
        with TemporaryDirectory() as temp, patch.dict(os.environ, {
            'FINANCE_AUTO_REFRESH': '0', 'FINANCE_PORTFOLIO_HOLDINGS': str(Path(temp)/'holdings.json'),
            'FINANCE_OWNER_INPUTS': str(Path(temp)/'model.json')}):
            engine = memory_engine()
            try:
                app = create_app(engine)
                # This test owns a single-connection in-memory SQLite fixture.
                # Test the store/API, without a background research audit that
                # could still use that connection while teardown disposes it.
                app.state.acceptance = AcceptanceCache(
                    lambda: AcceptanceSnapshot(datetime.now(timezone.utc), {}),
                    ttl_seconds=3600, spawn=lambda work: work())
                with TestClient(app) as client:
                    before = client.get('/api/owner-inputs').json()
                    initial = client.get('/api/portfolio-holdings')
                    self.assertEqual(initial.status_code, 200)
                    self.assertEqual(initial.json()['revision'], 0)
                    body = {'revision': 0, 'combine_accounts': True, 'positions': [
                        {'id': 'one', 'account': 'Sample account', 'name': 'Sample equity',
                         'isin': 'US0378331005', 'quantity': 2, 'price_eur': 30, 'value_eur': 60,
                         'asset_class': 'equity', 'identity_source': 'owner'}]}
                    saved = client.put('/api/portfolio-holdings', json=body)
                    self.assertEqual(saved.status_code, 200, saved.text)
                    self.assertEqual(saved.json()['summary']['total_value_eur'], 60)
                    self.assertEqual(client.get('/api/owner-inputs').json(), before)
                    self.assertTrue(before['is_example'])
                    self.assertEqual(client.put('/api/portfolio-holdings', json=body).status_code, 409)
                    invalid = {**body, 'revision': 1, 'positions': [{**body['positions'][0], 'value_eur': -1}]}
                    self.assertEqual(client.put('/api/portfolio-holdings', json=invalid).status_code, 422)
                    self.assertEqual(client.get('/api/portfolio-holdings').json()['revision'], 1)
                    Path(temp, 'holdings.json').write_text('{broken')
                    self.assertEqual(client.get('/api/portfolio-holdings').status_code, 503)
                    self.assertEqual(client.put('/api/portfolio-holdings', json={**body, 'revision': 1}).status_code, 503)
                    self.assertEqual(Path(temp, 'holdings.json').read_text(), '{broken')
            finally:
                engine.dispose()

