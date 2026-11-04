"""Offline exact BIS DSR SDMX and original country/sector adapter tests."""
from datetime import date
from decimal import Decimal
import unittest

import httpx
from finance_dashboard.bis import ProviderError
from finance_dashboard.bis_dsr import parse_bis_dsr, DSR_SERIES, BIS_DSR_ROOT
from finance_dashboard.providers import ProviderRouter


def fixture(country="US", sector="P"):
    return {
        "meta": {"prepared": "2026-09-14T09:00:00Z"},
        "data": {
            "structure": {"dimensions": {
                "series": [
                    {"id": "FREQ", "values": [{"id": "Q"}]},
                    {"id": "BORROWERS_CTY", "values": [{"id": country}]},
                    {"id": "DSR_BORROWERS", "values": [{"id": sector}]},
                ],
                "observation": [{
                    "id": "TIME_PERIOD",
                    "values": [{"id": "2025-Q4"}, {"id": "2026-Q1"},
                               {"id": "2026-Q2"}],
                }],
            }},
            "dataSets": [{"series": {"0:0:0": {
                "observations": {"0": ["14.25"], "1": ["14.50"],
                                 "2": [None]}
            }}}],
        },
    }


class BisDsrTests(unittest.TestCase):
    def test_full_registered_id_set_is_original(self):
        self.assertEqual(len(DSR_SERIES), 8)
        for country, sector in DSR_SERIES.values():
            self.assertIn(sector, "PHN")
            self.assertEqual(len(country), 2)

    def test_original_quarters_missing_values_and_prepared_metadata(self):
        values, prepared = parse_bis_dsr(fixture(), country="US", sector="P")
        self.assertEqual(values, {
            date(2025, 10, 1): Decimal("14.25"),
            date(2026, 1, 1): Decimal("14.50"),
        })
        self.assertEqual(prepared.year, 2026)
        values, _ = parse_bis_dsr(
            fixture(), country="US", sector="P", start=date(2026, 1, 1))
        self.assertEqual(values, {date(2026, 1, 1): Decimal("14.50")})

    def test_exact_source_identity(self):
        with self.assertRaisesRegex(ProviderError, "mismatch"):
            parse_bis_dsr(fixture("JP"), country="US", sector="P")
        with self.assertRaisesRegex(ProviderError, "mismatch"):
            parse_bis_dsr(fixture("US", "H"), country="US", sector="P")
        with self.assertRaisesRegex(ProviderError, "Unregistered"):
            parse_bis_dsr(fixture(), country="ES", sector="P")

    def test_duplicated_or_invalid_source_is_rejected(self):
        obj = fixture()
        obj["data"]["dataSets"][0]["series"]["1:0:0"] = obj["data"]["dataSets"][0]["series"]["0:0:0"]
        with self.assertRaises(ProviderError):
            parse_bis_dsr(obj, country="US", sector="P")
        obj = fixture()
        obj["data"]["dataSets"][0]["series"]["0:0:0"]["observations"]["1"] = ["Infinity"]
        with self.assertRaisesRegex(ProviderError, "nonfinite"):
            parse_bis_dsr(obj, country="US", sector="P")
        obj = fixture()
        obj["data"]["structure"]["dimensions"]["series"][2]["id"] = "BORROWERS"
        with self.assertRaisesRegex(ProviderError, "dimensions"):
            parse_bis_dsr(obj, country="US", sector="P")

    def test_request_exact_bis_key_and_quarter(self):
        def respond(request):
            self.assertTrue(str(request.url).startswith(BIS_DSR_ROOT))
            self.assertIn("/Q.US.P", str(request.url))
            self.assertEqual(request.url.params.get("startPeriod"), "2026-Q1")
            self.assertIn("sdmx", request.headers["Accept"])
            return httpx.Response(200, json=fixture())
        with httpx.Client(transport=httpx.MockTransport(respond)) as client:
            router = ProviderRouter(client=client)
            try:
                result = router.fetch("debt_service.us.private.bis",
                                      date(2026, 1, 1))
                self.assertEqual(result.observations,
                                 {date(2026, 1, 1): Decimal("14.50")})
                self.assertIsNotNone(result.prepared_at)
            finally:
                router.close()


if __name__ == "__main__":
    unittest.main()
