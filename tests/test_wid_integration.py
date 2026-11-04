"""Original inequality observations keep source identity through storage and API."""
from datetime import date
from decimal import Decimal
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from finance_dashboard.api import create_app
from finance_dashboard.catalog import load_documents, validate
from finance_dashboard.database import Base, make_engine
from finance_dashboard.providers import ProviderRouter, SourceUnavailable
from finance_dashboard.service import IngestionService, current_observations
from test_wid import fixtures


class WidIntegrationTests(unittest.TestCase):
    def test_country_world_source_definitions_keep_distinct_native_keys(self):
        series, charts = load_documents()
        self.assertEqual(validate(series, charts), [])
        by_id = {item["id"]: item for item in series["series"]}
        self.assertIn("inequality.world.pretax_income.top10", by_id)
        world = by_id["inequality.world.pretax_income.top10"]
        self.assertEqual(world["source_key"], "WO/sptincj992/p90p100")
        self.assertEqual(world["frequency"], "A")
        self.assertEqual(world["unit"], "ratio")
        self.assertEqual(by_id["inequality.us.pretax_income.top10"]["source_key"],
                         "US/sptinc992j/p90p100")

    def test_original_share_revisions_evidence_and_corpus_survive_reopen(self):
        data, metadata = fixtures()
        current = {"data": data}
        requests = []
        def respond(request):
            requests.append(request.url.path)
            payload = metadata if "metadata" in request.url.path else current["data"]
            return httpx.Response(200, text=payload, headers={"Content-Type": "text/csv"})
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            url = "sqlite+pysqlite:///" + str(root / "finance.sqlite3")
            env = {"FINANCE_SOURCE_EVIDENCE_DIR": str(root / "evidence"),
                   "FINANCE_AUTO_REFRESH": "0", "FINANCE_DASHBOARD_UI_DIR": "",
                   "FINANCE_VINTAGE_DIR": str(root / "vintages")}
            with patch.dict(os.environ, env), httpx.Client(transport=httpx.MockTransport(respond)) as http:
                engine = make_engine(url)
                Base.metadata.create_all(engine)
                router = ProviderRouter(client=http)
                service = IngestionService(engine, router)
                first = service.refresh("inequality.us.pretax_income.top10", full=True)
                self.assertEqual(first["versions_added"], 2)
                service.refresh("inequality.us.net_personal_wealth.bottom50", full=True)
                self.assertEqual(len(requests), 2)
                engine.dispose()
                current["data"] = data.replace(";2000;0.40;", ";2000;0.41;")
                reopened = make_engine(url)
                updated = IngestionService(reopened, ProviderRouter(client=http))
                # Bulk source revisions can change years outside the ordinary
                # five-year annual overlap; default refresh must reconcile them.
                report = updated.refresh("inequality.us.pretax_income.top10")
                self.assertEqual(report["versions_added"], 1)
                with TestClient(create_app(reopened)) as api:
                    corpus = api.get("/api/research-corpus/L07").json()
                    self.assertEqual(corpus["existing_references_with_observations"], 2)
                    self.assertFalse(corpus["comparative_corpus_validated"])
                    source = next(x for x in corpus["linked_existing_series"]
                                  if x["series_id"] == "inequality.us.pretax_income.top10")
                    self.assertEqual(source["stored_periods"], 2)
                    self.assertEqual(source["stored_versions"], 3)
                    self.assertEqual(source["source_contract"]["source_key"], "US/sptinc992j/p90p100")
                    coverage = api.get("/api/source-coverage").json()
                    wealth = next(x for x in coverage["items"]
                                  if x["id"] == "inequality.us.net_personal_wealth.bottom50")
                    self.assertEqual(wealth["stored_periods"], 1)
                from sqlalchemy.orm import Session
                with Session(reopened) as session:
                    observed = {row.period: row.value for row in current_observations(
                        session, "inequality.us.pretax_income.top10")}
                    self.assertEqual(observed, {date(2000, 1, 1): Decimal("0.41"),
                                                date(2024, 1, 1): Decimal("0.46")})
                manifests = list((root / "evidence").glob("wid/US/*/manifest.json"))
                self.assertEqual(len(manifests), 2)
                self.assertTrue(all(json.loads(p.read_text())["original_first_publication_at"] is None
                                    for p in manifests))
                reopened.dispose()

    def test_registry_identity_drift_is_rejected_before_request(self):
        with httpx.Client(transport=httpx.MockTransport(
                lambda request: self.fail("Invalid mapping must not reach WID"))) as http:
            router = ProviderRouter(client=http)
            original = router.definitions.get("inequality.us.pretax_income.top10")
            self.assertIsNotNone(original)
            router.definitions["inequality.us.pretax_income.top10"] = {
                **original, "source_key": "US/disposable_income/p90p100"}
            with self.assertRaises(SourceUnavailable):
                router.fetch("inequality.us.pretax_income.top10")
