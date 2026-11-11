"""Analysis API, conditionals listing and command: bundles over a stored corpus."""
from datetime import datetime, timezone
import io
import json
import os
from contextlib import redirect_stdout
from unittest.mock import patch
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from fastapi.testclient import TestClient

from engine_fixtures import memory_engine, seed
from finance_dashboard.api import create_app
from finance_dashboard.engine.acceptance import AcceptanceCache, snapshot_from_report
from finance_dashboard.engine.analyses import P07
from finance_dashboard.engine import conditionals_cli
from test_engine_p07 import p07_fixture

AT = datetime(2026, 11, 8, tzinfo=timezone.utc)
CATALOGUE_LIMIT = {"code": "dimensions_as_declared_in_catalogue", "series_ids": ["fx.usd_per_eur.ecb"]}


def report(extra_limitation=None):
    p07_roles = [{"role": role, "series_ids": [sid], "state": "accepted", "accepted": True,
                  "limitations": [CATALOGUE_LIMIT] if role == "usd_per_eur" else []}
                 for role, sid in P07.inputs.items()]
    limitations = [CATALOGUE_LIMIT] + ([extra_limitation] if extra_limitation else [])
    return {"analyses": [
        {"id": "P07", "acceptance": {"state": "conditional", "requirements": p07_roles,
                                     "limitations": limitations, "blocking_roles": []}},
        {"id": "G03", "acceptance": {"state": "deferred", "requirements": [], "blocking_roles": [],
                                     "limitations": [{"code": "deferred_research_extension", "detail": "none"}]}},
        {"id": "V01", "acceptance": {"state": "accepted", "requirements": [], "blocking_roles": [],
                                     "limitations": []}},
    ]}


def cache_of(public_report):
    return AcceptanceCache(lambda: snapshot_from_report(public_report, AT), ttl_seconds=3600,
                           spawn=lambda work: work())


class EngineApiTests(unittest.TestCase):
    def test_research_status_retries_only_while_assessment_is_loading(self):
        self.app.state.acceptance = AcceptanceCache(lambda: snapshot_from_report(report(), AT),
                                                   ttl_seconds=3600, spawn=lambda work: None)
        response = self.client.get('/api/research-status')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers['Retry-After'], '30')
        self.assertNotIn('counts', response.json())

    def test_research_status_preserves_original_deferred_state_and_limitation_text(self):
        response = self.client.get('/api/research-status')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        rows = {r['analysis_id']: r for r in body['questions']}
        self.assertEqual(rows['G03']['state'], 'deferred')
        self.assertTrue(rows['G03']['phase2']['limitations'][0]['text'])
        self.assertEqual(body['counts']['conditional'], 1)
        self.assertEqual(body['evaluated_at'], AT.isoformat())

    def test_saved_view_crud_preserves_independence_and_rejects_stale_writes(self):
        with TemporaryDirectory() as tmp, patch.dict(os.environ, {'FINANCE_SAVED_VIEWS': str(Path(tmp)/'saved-views.json')}):
            cap = self.client.get('/api/analysis/P07/views/capabilities').json()
            spec = cap['figures'][0]['defaults']
            first = self.client.post('/api/saved-views', json={'name': 'First', 'analysis_id': 'P07', 'spec': spec})
            self.assertEqual(first.status_code, 201, first.text)
            a = first.json()
            second = self.client.post('/api/saved-views', json={'name': 'Second', 'analysis_id': 'P07', 'spec': spec}).json()
            update = {'name': 'Renamed', 'spec': spec, 'revision': a['revision']}
            self.assertEqual(self.client.put('/api/saved-views/'+a['id'], json=update).status_code, 200)
            self.assertEqual(self.client.put('/api/saved-views/'+a['id'], json=update).status_code, 409)
            rows = {r['id']: r for r in self.client.get('/api/saved-views').json()['items']}
            self.assertEqual(rows[second['id']]['name'], 'Second')
            self.assertEqual(rows[a['id']]['name'], 'Renamed')
            invalid = self.client.post('/api/saved-views', json={'name':'Bad','analysis_id':'P07','spec':{**spec,'roles':['unknown']}})
            self.assertEqual(invalid.status_code, 422)
            self.assertEqual(self.client.delete('/api/saved-views/'+a['id'], params={'revision': 1}).status_code, 409)
            self.assertEqual(self.client.delete('/api/saved-views/'+a['id'], params={'revision': 2}).status_code, 204)
            Path(tmp,'saved-views.json').write_text('corrupted')
            self.assertEqual(self.client.get('/api/saved-views').status_code, 503)

    def test_configured_figure_and_export_share_the_same_server_values(self):
        response = self.client.get('/api/analysis/P07/views/capabilities')
        self.assertEqual(response.status_code, 200)
        figure = next(f for f in response.json()['figures'] if any(r['id']=='equity_netr_usd' for r in f['roles']))
        spec = {**figure['defaults'], 'start': '2024-01-01', 'transform': 'index_100', 'events': []}
        params = {'today': '2026-11-06', 'view': json.dumps(spec)}
        body = self.client.get('/api/analysis/P07', params=params)
        self.assertEqual(body.status_code, 200, body.text)
        text = self.client.get('/api/analysis/P07/export', params=params).text
        exported = json.loads(text.split('--- data (JSON) ---\n')[1])
        self.assertEqual(exported['figure'], body.json()['figure'])
        self.assertEqual(body.json()['view']['transform'], 'index_100')
        rejected = self.client.get('/api/analysis/P07', params={'view': json.dumps({**spec, 'geographies': ['MARS']})})
        self.assertEqual(rejected.status_code, 422)
        self.assertEqual(self.client.get('/api/analysis/UNKNOWN/views/capabilities').status_code, 404)

    def setUp(self):
        self.engine = memory_engine()
        seed(self.engine, p07_fixture())
        self.env = patch.dict(os.environ, {"FINANCE_AUTO_REFRESH": "0", "FINANCE_INCLUDE_MARKETS": "0",
                                           "FINANCE_AUTO_BACKUP": "0"})
        self.env.start()
        self.app = create_app(self.engine)
        self.app.state.acceptance = cache_of(report())
        self.ctx = TestClient(self.app)
        self.client = self.ctx.__enter__()

    def tearDown(self):
        self.ctx.__exit__(None, None, None)
        self.env.stop()
        self.engine.dispose()

    def test_bundle_carries_phase2_limitations_and_values(self):
        response = self.client.get("/api/analysis/P07", params={"today": "2026-11-06"})
        self.assertEqual(response.status_code, 200)
        bundle = response.json()
        self.assertEqual(bundle["phase2"]["state"], "conditional")
        self.assertTrue(bundle["phase2"]["limitations"][0]["text"])
        self.assertGreater(len(bundle["values"]["rows"]), 12)
        self.assertEqual(bundle["view"], {"today": "2026-11-06"})
        self.assertTrue(bundle["question"])
        self.assertTrue(bundle["citations"])
        fx = next(item for item in bundle["inputs"] if item["role"] == "usd_per_eur")
        self.assertEqual(fx["publisher"], "ECB")
        self.assertTrue(fx["limitations"][0]["text"])

    def test_unknown_analysis_is_404_and_deferred_has_no_values(self):
        self.assertEqual(self.client.get("/api/analysis/XYZ").status_code, 404)
        deferred = self.client.get("/api/analysis/G03").json()
        self.assertEqual(deferred["phase2"]["state"], "deferred")
        self.assertIsNone(deferred["values"])

    def test_listing_marks_which_analyses_the_engine_computes(self):
        rows = {row["analysis_id"]: row for row in self.client.get("/api/analysis").json()}
        self.assertTrue(rows["P07"]["has_engine"])
        self.assertTrue(all(row["has_engine"] for row in rows.values()), [r for r in rows if not rows[r]["has_engine"]])
        self.assertEqual(rows["G03"]["state"], "deferred")
        self.assertTrue(rows["P07"]["question"])
        self.assertTrue(rows["P07"]["decision_informed"])
        self.assertTrue(rows["M02"]["sources"])                 # method source labels, for search
        self.assertIn("US", rows["M02"]["geographies"])

    def test_unavailable_acceptance_is_503(self):
        def failing():
            raise OSError("evidence missing")
        self.app.state.acceptance = AcceptanceCache(failing, ttl_seconds=3600, spawn=lambda work: work())
        response = self.client.get("/api/analysis/P07")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Phase 2 acceptance evaluation unavailable")

    def test_evaluation_in_progress_is_503_with_retry_after(self):
        self.app.state.acceptance = AcceptanceCache(lambda: None, ttl_seconds=3600, spawn=lambda work: None)
        response = self.client.get("/api/analysis/P07")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Phase 2 acceptance evaluation in progress")
        self.assertEqual(response.headers["retry-after"], "30")

    def test_export_is_a_text_attachment_with_every_limitation(self):
        response = self.client.get("/api/analysis/P07/export", params={"today": "2026-11-06"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/plain"))
        self.assertIn('filename="P07-2026-', response.headers["content-disposition"])
        self.assertIn("--- data (JSON) ---", response.text)
        bundle = self.client.get("/api/analysis/P07", params={"today": "2026-11-06"}).json()
        for item in bundle["phase2"]["limitations"] + bundle["method_limitations"]:
            self.assertIn(item["text"], response.text)

    def test_export_names_code_series_role_and_detail_of_every_limitation(self):
        self.app.state.acceptance = cache_of(report({"code": "role_descoped_by_phase1_revision",
                                                     "role": "fx_quotes", "detail": "Replaced by an ECB role."}))
        text = self.client.get("/api/analysis/P07/export", params={"today": "2026-11-06"}).text
        bundle = self.client.get("/api/analysis/P07", params={"today": "2026-11-06"}).json()
        for item in bundle["limitations"]:
            self.assertIn(item["code"], text)
            for series_id in item["series_ids"]:
                self.assertIn(series_id, text)
        self.assertIn("fx_quotes", text)
        self.assertIn("Replaced by an ECB role.", text)
        self.assertIn('"limitations"', text.split("--- data (JSON) ---")[1])

    def test_conditionals_listing(self):
        rows = self.client.get("/api/conditionals").json()
        self.assertEqual([row["analysis_id"] for row in rows], ["P07"])
        self.assertTrue(rows[0]["limitations"][0]["text"])


class WarmUpTests(unittest.TestCase):
    def test_in_memory_database_is_never_evaluated_in_the_background(self):
        # A shared in-memory connection cannot serve a concurrent multi-minute evaluation.
        engine = memory_engine()
        with patch.dict(os.environ, {"FINANCE_AUTO_REFRESH": "1", "FINANCE_INCLUDE_MARKETS": "0",
                                     "FINANCE_AUTO_BACKUP": "0"}):
            app = create_app(engine)
        self.assertFalse(app.state.acceptance.loading)
        engine.dispose()


class ConditionalsCommandTests(unittest.TestCase):
    def run_command(self, public_report):
        out = io.StringIO()
        with redirect_stdout(out):
            code = conditionals_cli.main([], snapshot_loader=lambda args: snapshot_from_report(public_report, AT))
        return code, out.getvalue()

    def test_lists_conditional_analyses(self):
        code, output = self.run_command(report())
        self.assertEqual(code, 0)
        self.assertEqual([row["analysis_id"] for row in json.loads(output)], ["P07"])

    def test_unmapped_code_fails_and_names_it(self):
        code, output = self.run_command(report({"code": "not_a_code"}))
        self.assertEqual(code, 1)
        self.assertIn("not_a_code", output)


if __name__ == "__main__":
    unittest.main()
