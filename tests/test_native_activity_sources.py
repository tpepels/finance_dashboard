"""Actual source observations retain units through append-only native panels."""
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from finance_dashboard.catalog import load_documents
from finance_dashboard.comparative_corpus import build_comparative_corpus
from finance_dashboard.database import Base
from finance_dashboard.providers import ProviderRouter
from finance_dashboard.research_corpus import load_research_corpus
from finance_dashboard.service import IngestionService, current_observations
from finance_dashboard.source_capture import SourceAcquisition
from finance_dashboard.source_reconciliation import reconcile_session


FIXTURES = Path(__file__).parent / "fixtures" / "phase2_native_inputs"


class NativeActivitySourceTests(unittest.TestCase):
    def test_actual_pandemic_activity_and_policy_sources_keep_native_units_and_periods(self):
        # Original current-vintage pandemic dates are a regression for confusing
        # payroll levels with unique persons, target settings with market rates,
        # or a CPI index with an inflation percentage. No forecast is evaluated.
        provenance = json.loads((FIXTURES / "provenance.json").read_text())
        by_key = {row["source_key"]: row for row in load_documents()[0]["series"]
                  if row["id"] in provenance}
        def response(request):
            key = request.url.params.get("id")
            if request.url.host == "api.worldbank.org":
                parts = request.url.path.split("/")
                key = parts[3] + "/" + parts[5]
            source = provenance[by_key[key]["id"]]
            body = (FIXTURES / source["file"]).read_bytes()
            self.assertEqual(sha256(body).hexdigest(), source["fixture_sha256"])
            return httpx.Response(200, content=body)

        corpus = load_research_corpus()
        corpus = {**corpus, "analyses": [row for row in corpus["analyses"]
                                       if row["id"] in {"C01", "C05", "M01"}]}
        registry = load_documents()[0]["series"]
        with TemporaryDirectory() as temp:
            root = Path(temp)
            engine = create_engine("sqlite:///" + str(root / "native.sqlite3"))
            Base.metadata.create_all(engine)
            try:
                with patch.dict("os.environ", {"FRED_API_KEY": "", "FRED_PUBLIC_CSV_FALLBACK": "1"}):
                    with httpx.Client(transport=httpx.MockTransport(response)) as client:
                        service = IngestionService(engine, SourceAcquisition(ProviderRouter(client), root))
                        for sid in provenance:
                            self.assertEqual(service.refresh(sid, full=True)["status"], "success")
                with Session(engine) as session:
                    proof = reconcile_session(session, root, list(provenance))
                    self.assertTrue(proof["passed"], proof)
                    self.assertEqual(proof["matched_series"], 9)
                    values = {sid: {row.period: row.value for row in current_observations(session, sid)}
                              for sid in provenance}
                    self.assertEqual(values["activity.us.nonfarm_payrolls"][date(2020, 4, 1)], Decimal("130426"))
                    self.assertEqual(values["activity.us.industrial_production"][date(2020, 4, 1)], Decimal("84.5619"))
                    self.assertEqual(values["activity.us.unemployment_rate"][date(2020, 4, 1)], Decimal("14.8"))
                    self.assertEqual(values["prices.us.cpi_all_items_sa"][date(2020, 4, 1)], Decimal("256.032"))
                    self.assertEqual(values["policy_rate.us.fed_lower"][date(2020, 3, 16)], Decimal("0.00"))
                    self.assertEqual(values["policy_rate.us.fed_upper"][date(2020, 3, 16)], Decimal("0.25"))
                    self.assertEqual(values["policy_rate.us.fed_effective"][date(2020, 3, 16)], Decimal("0.25"))
                    self.assertEqual(len(values["gdp.nominal_usd.world"]), 66)
                    panel_report = build_comparative_corpus(session, registry, corpus, source_proof=proof)
                    self.assertEqual(panel_report["bounded_current_vintage_panel_count"], 3)
                    self.assertEqual(sorted(p["matched_period_count"] for p in panel_report["panels"] if "derived_from_role" not in p), [4, 4, 6])
                    self.assertEqual(panel_report["fully_validated_analysis_count"], 0)
                    self.assertTrue(all(not p["first_publication_verified"] for p in panel_report["panels"]))
            finally:
                engine.dispose()
