"""Original BIS WS_TC quarter, sector, unit and immutable-source evidence contracts.

Publisher-shaped fixtures; no network access or production database changes.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
import copy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from finance_dashboard.bis import ProviderError
from finance_dashboard.bis_credit import BIS_TC_ROOT, TC_SERIES, tc_key, parse_bis_total_credit
from finance_dashboard.captured_sources import _bis
from finance_dashboard.catalog import load_documents
from finance_dashboard.database import Base, make_engine
from finance_dashboard.providers import ProviderRouter
from finance_dashboard.service import IngestionService
from finance_dashboard.source_capture import CapturedProvider
from finance_dashboard.source_reconciliation import EvidenceError, reconcile


def original(sid="credit.us.private_nonfinancial_stock_bis",
             values=("100.25", "103.75", None)):
    country, borrower, unit_type, unit_measure, multiplier = TC_SERIES[sid]
    key = tc_key(country, borrower, unit_type)
    dimensions = ("FREQ", "BORROWERS_CTY", "TC_BORROWERS", "TC_LENDERS",
                  "VALUATION", "UNIT_TYPE", "TC_ADJUST")
    return {
        "meta": {"prepared": "2026-08-21T07:45:40Z"},
        "data": {
            "structure": {
                "dimensions": {
                    "series": [{"id": name, "values": [{"id": value}]}
                               for name, value in zip(dimensions, key.split("."), strict=True)],
                    "observation": [{"id": "TIME_PERIOD", "values": [
                        {"id": "2025-Q4"}, {"id": "2026-Q1"}, {"id": "2026-Q2"}]}]},
                "attributes": {"series": [
                    {"id": "UNIT_MEASURE", "values": [{"id": unit_measure}]},
                    {"id": "UNIT_MULT", "values": [{"id": multiplier}]}]}},
            "dataSets": [{"series": {"0:0:0:0:0:0:0": {
                "attributes": [0, 0], "observations": {
                    str(i): [value] for i, value in enumerate(values)}}}}]}}


class OriginalBisTotalCreditTests(unittest.TestCase):
    def test_all_twenty_source_contracts_are_distinct_and_native(self):
        self.assertEqual(len(TC_SERIES), 20)
        registry = {row["id"]: row for row in load_documents()[0]["series"]}
        keys = set()
        for sid, spec in TC_SERIES.items():
            self.assertIn(sid, registry)
            row = registry[sid]
            self.assertEqual(row["provider"], "BIS_TOTAL_CREDIT")
            self.assertEqual(row["frequency"], "Q")
            self.assertEqual(row["source_key"], "BIS,WS_TC,2.0/" + tc_key(*spec[:3]))
            self.assertEqual(row["unit"], "billion_local_currency" if spec[2] == "XDC" else "percent")
            self.assertEqual(spec[4], "9" if spec[2] == "XDC" else "0")
            self.assertNotIn(row["source_key"], keys)
            keys.add(row["source_key"])

    def test_country_sector_units_missingness_and_start_filter(self):
        for sid in ("credit.us.private_nonfinancial_stock_bis",
                    "credit.jp.private_nonfinancial_stock_bis",
                    "credit.us.private_nonfinancial_gdp_bis",
                    "credit.de.household_gdp_bis",
                    "credit.cn.corporate_gdp_bis"):
            with self.subTest(sid=sid):
                response = original(sid)
                observed, prepared = parse_bis_total_credit(response, sid)
                self.assertEqual(observed, {
                    date(2025, 10, 1): Decimal("100.25"),
                    date(2026, 1, 1): Decimal("103.75")})
                self.assertEqual(prepared.isoformat(), "2026-08-21T07:45:40+00:00")
                subset, _ = parse_bis_total_credit(response, sid, start=date(2026, 1, 1))
                self.assertEqual(subset, {date(2026, 1, 1): Decimal("103.75")})
        series = "credit.us.private_nonfinancial_stock_bis"
        response = original(series, values=("100.25", "NaN", "103.75"))
        observed, _ = parse_bis_total_credit(response, series)
        self.assertNotIn(date(2026, 1, 1), observed)
        self.assertEqual(observed[date(2026, 4, 1)], Decimal("103.75"))

    def test_unit_multiplier_country_sector_and_incomplete_metadata_fail_closed(self):
        sid = "credit.us.private_nonfinancial_stock_bis"
        for mutation in ("country", "borrower", "unit", "multiplier", "index", "structure", "observation"):
            response = original(sid)
            node = response["data"]["dataSets"][0]["series"]["0:0:0:0:0:0:0"]
            dims = response["data"]["structure"]
            if mutation == "country":
                dims["dimensions"]["series"][1]["values"][0]["id"] = "JP"
            elif mutation == "borrower":
                dims["dimensions"]["series"][2]["values"][0]["id"] = "H"
            elif mutation == "unit":
                dims["attributes"]["series"][0]["values"][0]["id"] = "EUR"
            elif mutation == "multiplier":
                dims["attributes"]["series"][1]["values"][0]["id"] = "0"
            elif mutation == "index":
                node["attributes"] = [99, 0]
            elif mutation == "structure":
                dims["dimensions"]["series"][2]["id"] = "WRONG_BORROWER"
            elif mutation == "observation":
                node["observations"]["0"] = []
            with self.subTest(mutation=mutation), self.assertRaises(ProviderError):
                parse_bis_total_credit(response, sid)
        for value in ("-2", "Infinity", "bad"):
            with self.subTest(value=value), self.assertRaises(ProviderError):
                parse_bis_total_credit(original(sid, (value, "103.75", None)), sid)

    def test_unfinished_quarter_cannot_be_published_as_a_historical_stock(self):
        sid = "credit.us.private_nonfinancial_stock_bis"
        response = original(sid)
        dims = response["data"]["structure"]["dimensions"]["observation"][0]["values"]
        dims[1]["id"] = "2026-Q4"
        definition = next(r for r in load_documents()[0]["series"] if r["id"] == sid)
        with patch("finance_dashboard.bis_credit.date") as clock:
            clock.today.return_value = date(2026, 11, 4)
            clock.side_effect = date
            with self.assertRaisesRegex(ProviderError, "quarter has not ended"):
                parse_bis_total_credit(response, sid)
        with patch("finance_dashboard.captured_sources.date") as clock:
            clock.today.return_value = date(2026, 11, 4)
            clock.side_effect = date
            with self.assertRaises(EvidenceError):
                _bis(response, definition)

    def test_future_empty_placeholder_is_not_an_observation(self):
        sid = "credit.us.private_nonfinancial_stock_bis"
        response = original(sid)
        response["data"]["structure"]["dimensions"]["observation"][0]["values"][2]["id"] = "2026-Q4"
        with patch("finance_dashboard.bis_credit.date") as clock:
            clock.today.return_value = date(2026, 11, 4)
            clock.side_effect = date
            values, _ = parse_bis_total_credit(response, sid)
        self.assertEqual(values, {date(2025, 10, 1): Decimal("100.25"),
                                  date(2026, 1, 1): Decimal("103.75")})
        definition = next(r for r in load_documents()[0]["series"] if r["id"] == sid)
        with patch("finance_dashboard.captured_sources.date") as clock:
            clock.today.return_value = date(2026, 11, 4)
            clock.side_effect = date
            independent, _ = _bis(response, definition)
        self.assertEqual(independent, values)

    def test_provider_routing_and_complete_capture_reconcile_without_changing_production(self):
        sid = "credit.us.private_nonfinancial_stock_bis"
        payload = original(sid)
        def reply(request):
            self.assertTrue(str(request.url).startswith(BIS_TC_ROOT))
            self.assertIn("/Q.US.P.A.M.XDC.A", str(request.url))
            return httpx.Response(200, json=payload)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            url = "sqlite:///" + str(root / "isolated.sqlite")
            evidence = root / "source-evidence"
            engine = make_engine(url)
            Base.metadata.create_all(engine)
            try:
                with httpx.Client(transport=httpx.MockTransport(reply)) as client:
                    router = ProviderRouter(client=client)
                    wrapped = CapturedProvider(router, evidence)
                    service = IngestionService(engine, wrapped)
                    first = service.refresh(sid, full=True)
                    self.assertEqual(first["versions_added"], 2)
                    second = service.refresh(sid, full=True)
                    self.assertEqual(second["versions_added"], 0)
                proof = reconcile(url, evidence, [sid])
                self.assertTrue(proof["passed"], proof)
                self.assertEqual(proof["series"][0]["source_periods"], 2)
                self.assertTrue(list(evidence.glob("responses/*/*/manifest.json")))
            finally:
                engine.dispose()


if __name__ == "__main__":
    unittest.main()
