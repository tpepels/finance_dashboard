"""Native original workbook inputs enter the existing capture/ingestion path."""
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import httpx

from finance_dashboard.catalog import load_documents
from finance_dashboard.database import Base, make_engine
from finance_dashboard.providers import ProviderRouter, parse_shiller_sheet, ProviderError
from finance_dashboard.source_capture import CapturedProvider
from finance_dashboard.source_reconciliation import reconcile
from test_captured_source_families import xlsx_from_factual_cells

FIXTURE = Path(__file__).parent / "fixtures/native_source_families"
SHILLER = ["valuation.us.shiller_price", "valuation.us.shiller_earnings",
           "valuation.us.shiller_dividend", "prices.us.shiller_cpi",
           "returns.us.shiller_real_total_return"]
COMMODITIES = ["prices.commodity.natural_gas_us_usd", "prices.commodity.maize_usd"]


class MissingOriginalInputsTests(unittest.TestCase):
    def test_ordinary_full_workbook_refresh_preserves_old_revisions_and_full_source_proof(self):
        from finance_dashboard.service import IngestionService
        source = json.loads((FIXTURE / "shiller_inputs_cells.json").read_text())
        rows = source["rows"]
        def response(request):
            if request.url.host == "shillerdata.com":
                return httpx.Response(200, text=f'<a href="{source["source_url"]}">ie_data.xls</a>')
            return httpx.Response(200, content=xlsx_from_factual_cells(rows, "Data"))
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            url = "sqlite:///" + str(root / "history.sqlite3")
            engine = make_engine(url)
            Base.metadata.create_all(engine)
            try:
                with httpx.Client(transport=httpx.MockTransport(response)) as client:
                    service = IngestionService(engine, CapturedProvider(ProviderRouter(client), root))
                    service.refresh(SHILLER[0])
                    # The already-downloaded workbook revises a point far outside overlap.
                    rows[7][1] = 4.45
                    update = service.refresh(SHILLER[0])
                    self.assertEqual(update["versions_added"], 1)
                self.assertTrue(reconcile(url, root, [SHILLER[0]])["passed"])
                manifests = [json.loads(path.read_text()) for path in root.glob("responses/*/*/manifest.json")]
                self.assertTrue(all(record["requested_from"] is None for record in manifests))
            finally:
                engine.dispose()

    def test_authored_workbook_inputs_preserve_population_price_basis_and_missing_months(self):
        from finance_dashboard.service import IngestionService
        shiller = json.loads((FIXTURE / "shiller_inputs_cells.json").read_text())
        pink = json.loads((FIXTURE / "pink_gas_maize_cells.json").read_text())
        books = {"img1.wsimg.com": xlsx_from_factual_cells(shiller["rows"], "Data"),
                 "thedocs.worldbank.org": xlsx_from_factual_cells(pink["rows"], "Monthly Prices")}
        def response(request):
            if request.url.host == "shillerdata.com":
                return httpx.Response(200, text=f'<a href="{shiller["source_url"]}">ie_data.xls</a>')
            return httpx.Response(200, content=books[request.url.host])
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            url = "sqlite:///" + str(root / "inputs.sqlite3")
            engine = make_engine(url)
            Base.metadata.create_all(engine)
            try:
                with httpx.Client(transport=httpx.MockTransport(response)) as client:
                    provider = CapturedProvider(ProviderRouter(client), root)
                    service = IngestionService(engine, provider)
                    for sid in SHILLER + COMMODITIES:
                        first = service.refresh(sid, full=True)
                        self.assertGreater(first["versions_added"], 100)
                        self.assertEqual(service.refresh(sid, full=True)["versions_added"], 0)
                    points = {sid: provider.fetch(sid).observations for sid in SHILLER + COMMODITIES}
                first = date(1871, 1, 1)
                self.assertEqual(points[SHILLER[0]][first], Decimal("4.44"))
                self.assertEqual(points[SHILLER[1]][first], Decimal("0.4"))
                self.assertEqual(points[SHILLER[2]][first], Decimal("0.26"))
                self.assertEqual(points[SHILLER[3]][first], Decimal("12.46406116"))
                self.assertEqual(points[SHILLER[4]][first], Decimal("119.61170928657417"))
                self.assertNotIn(date(2026, 10, 1), points[SHILLER[1]])
                self.assertEqual(points[COMMODITIES[0]][date(1960, 1, 1)], Decimal("0.14"))
                self.assertEqual(points[COMMODITIES[1]][date(1960, 1, 1)], Decimal("45.0"))
                proof = reconcile(url, root, SHILLER + COMMODITIES)
                self.assertTrue(proof["passed"], proof)
                by_id = {row["series_id"]: row for row in proof["series"]}
                self.assertEqual(by_id[SHILLER[4]]["source_price_basis"], "real_cpi_deflated")
                self.assertTrue(by_id[SHILLER[4]]["source_author_constructed"])
                self.assertIn("estimated", " ".join(by_id[SHILLER[3]]["source_workbook_notes"]).lower())
                self.assertIn("consumer-price basket", by_id[SHILLER[3]]["source_population"])
                self.assertTrue(by_id[SHILLER[1]]["source_author_constructed"])
                self.assertEqual(by_id[COMMODITIES[0]]["source_native_unit"], "usd_per_mmbtu")
                self.assertEqual(by_id[COMMODITIES[1]]["source_native_unit"], "usd_per_metric_ton")
            finally:
                engine.dispose()

    def test_shiller_selector_refuses_real_price_in_place_of_original_price_and_unknown_column(self):
        rows = json.loads((FIXTURE / "shiller_inputs_cells.json").read_text())["rows"]
        with self.assertRaises(ProviderError):
            parse_shiller_sheet(rows, variable="unknown")
        # Changing the original price header cannot silently select real/TR price.
        changed = [list(row) for row in rows]
        changed[6][1] = "Real Price"
        with self.assertRaises(ProviderError):
            parse_shiller_sheet(changed, variable="P")

    def test_independent_commodity_selector_rejects_currency_or_scale_drift(self):
        from finance_dashboard.captured_sources import _pink_sheet
        from finance_dashboard.providers import PINK_SHEET_URL
        from finance_dashboard.source_reconciliation import EvidenceError
        registry = {row["id"]: row for row in load_documents()[0]["series"]}
        for label, sid, unit in [("Natural gas, US", COMMODITIES[0], "mmbtu"),
                                 ("Maize", COMMODITIES[1], "mt")]:
            for wrong in (f"(C$/{unit})", f"(100 $/{unit})", f"($/100 {unit})"):
                with self.subTest(label=label, unit=wrong), self.assertRaises(EvidenceError):
                    original = xlsx_from_factual_cells([["Date", label], ["", wrong], ["2024M01", 2]], "Monthly Prices")
                    _pink_sheet(original, registry[sid], PINK_SHEET_URL)

    def test_canonical_roles_bind_exact_workbook_and_weo_sources(self):
        from finance_dashboard.research_corpus import load_research_corpus, validate_research_corpus
        document = load_research_corpus()
        registry = load_documents()[0]["series"]
        self.assertEqual(validate_research_corpus(document, registry), [])
        analyses = {row["id"]: row for row in document["analyses"]}
        for ident, roles in {"V01": ["original_equity_price", "original_earnings", "original_cpi", "original_dividend"],
                             "C06": ["weo_real_gdp_growth", "gas_price", "food_price"],
                             "V05": ["matched_equity_total_return", "inflation_deflator"]}.items():
            requirements = {row["role"]: row for row in analyses[ident]["comparison_contract"]["original_requirements"]}
            for role in roles:
                self.assertTrue(requirements[role]["series_ids"], (ident, role))
        self.assertEqual(len(next(row for row in analyses["C06"]["comparison_contract"]["original_requirements"]
                                 if row["role"] == "weo_real_gdp_growth")["series_ids"]), 3)
