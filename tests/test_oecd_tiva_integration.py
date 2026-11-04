"""TiVA source identities reach immutable observations and the research API."""
from decimal import Decimal
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from finance_dashboard.api import create_app
from finance_dashboard.catalog import load_documents, validate
from finance_dashboard.database import Base, make_engine
from finance_dashboard.providers import ProviderRouter, SourceUnavailable
from finance_dashboard.service import IngestionService, current_observations
from test_oecd_tiva import fixture, LEVEL_FLOW, SHARE_FLOW


class TivaIntegrationTests(unittest.TestCase):
    def test_exact_published_share_and_monetary_inputs_persist_with_separate_units(self):
        requested = []
        level = fixture()
        share = fixture(SHARE_FLOW)
        bodies = {LEVEL_FLOW: level + "\n".join(level.replace(",2022,", ",2000,").splitlines()[1:]) + "\n",
                  SHARE_FLOW: share + "\n".join(share.replace(",2022,", ",2000,").splitlines()[1:]) + "\n"}
        def respond(request):
            requested.append(request)
            return httpx.Response(200, text=bodies[
                SHARE_FLOW if "MAINSH" in request.url.path else LEVEL_FLOW])
        with TemporaryDirectory() as tmp, httpx.Client(transport=httpx.MockTransport(respond)) as http:
            root = Path(tmp)
            with patch.dict(os.environ, {"FINANCE_SOURCE_EVIDENCE_DIR": str(root / "evidence"),
                    "FINANCE_AUTO_REFRESH": "0", "FINANCE_DASHBOARD_UI_DIR": "",
                    "FINANCE_VINTAGE_DIR": str(root / "vintages")}):
                series, charts = load_documents()
                self.assertEqual(validate(series, charts), [])
                engine = make_engine("sqlite+pysqlite:///" + str(root / "finance.sqlite3"))
                Base.metadata.create_all(engine)
                service = IngestionService(engine, ProviderRouter(client=http))
                for identifier in ("supply_chain.pt.foreign_final_demand_va",
                                   "supply_chain.pt.value_added",
                                   "supply_chain.pt.foreign_final_demand_share"):
                    self.assertEqual(service.refresh(identifier, full=True)["versions_added"], 2)
                self.assertEqual(len(requested), 2)
                bodies[SHARE_FLOW] = bodies[SHARE_FLOW].replace(",2000,32.632,", ",2000,31.5,")
                revised = IngestionService(engine, ProviderRouter(client=http))
                self.assertEqual(revised.refresh(
                    "supply_chain.pt.foreign_final_demand_share")["versions_added"], 1)
                with TestClient(create_app(engine)) as api:
                    result = api.get("/api/research-corpus/G06").json()
                    self.assertEqual(result["existing_references_with_observations"], 3)
                    self.assertFalse(result["comparative_corpus_validated"])
                    sources = {s["series_id"]: s["source_contract"] for s in result["linked_existing_series"]}
                    self.assertEqual(sources["supply_chain.pt.foreign_final_demand_va"]["unit"], "million_usd")
                    self.assertEqual(sources["supply_chain.pt.foreign_final_demand_share"]["unit"], "percent")
                    self.assertEqual(sources["supply_chain.pt.foreign_final_demand_share"]["source_key"],
                        "OECD.STI.PIE,DSD_TIVA_MAINSH@DF_MAINSH,1.1/FFD_DVA.PRT._T.W.PT_VA.A")
                with Session(engine) as session:
                    values = {row.period.year: row.value for row in current_observations(
                        session, "supply_chain.pt.foreign_final_demand_share")}
                    self.assertEqual(values, {2000: Decimal("31.5"), 2022: Decimal("32.632")})
                self.assertEqual(len(list((root / "evidence").glob("oecd-tiva/*/manifest.json"))), 2)
                engine.dispose()

    def test_wrong_native_unit_mapping_never_reaches_publisher(self):
        with httpx.Client(transport=httpx.MockTransport(
                lambda request: self.fail("Wrong TiVA mapping must not reach the network"))) as http:
            router = ProviderRouter(client=http)
            identifier = "supply_chain.pt.foreign_final_demand_share"
            original = router.definitions.get(identifier)
            self.assertIsNotNone(original)
            router.definitions[identifier] = {**original,
                "source_key": "OECD.STI.PIE,DSD_TIVA_MAINSH@DF_MAINSH,1.1/FFD_DVA.PRT._T.W.PT_EXGR.A"}
            with self.assertRaises(SourceUnavailable):
                router.fetch(identifier)
