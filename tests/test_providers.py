"""Deterministic provider parsing/transport checks; network never required."""
from datetime import date
from decimal import Decimal
import unittest
import httpx

from finance_dashboard.providers import (
    ProviderRouter, ProviderError, SourceUnavailable,
    parse_fred_csv, parse_fred_json, parse_ecb_csv, parse_world_bank,
)


class ParserTests(unittest.TestCase):
    def test_fred_csv_missing_and_precision(self):
        values = parse_fred_csv(
            "observation_date,DFII10\n2026-01-01,.\n2026-01-02,-0.125\n",
            "DFII10", "D",
        )
        self.assertEqual(values, {date(2026, 1, 2): Decimal("-0.125")})

    def test_fred_json_missing(self):
        values = parse_fred_json({"observations": [
            {"date": "2026-01-01", "value": "."},
            {"date": "2026-01-02", "value": "3.50"},
        ]}, "D")
        self.assertEqual(values[date(2026, 1, 2)], Decimal("3.50"))

    def test_ecb_exact_series(self):
        data = ("KEY,TIME_PERIOD,OBS_VALUE\n"
                "FM.D.U2.EUR.4F.KR.DFR.LEV,2026-01-01,2.0\n"
                "FM.D.U2.EUR.4F.KR.DFR.LEV,2026-01-02,\n")
        result = parse_ecb_csv(data, "FM.D.U2.EUR.4F.KR.DFR.LEV", "D")
        self.assertEqual(result, {date(2026, 1, 1): Decimal("2.0")})
        with self.assertRaisesRegex(ProviderError, "different series"):
            parse_ecb_csv(data, "FM.D.NOTHING", "D")

    def test_world_bank_annual_dates_and_missing_values(self):
        data = [
            {"page": 1, "pages": 1},
            [{"countryiso3code": "USA", "indicator": {"id": "NY.GDP.MKTP.KD.ZG"},
              "date": "2025", "value": 2.4},
             {"countryiso3code": "USA", "indicator": {"id": "NY.GDP.MKTP.KD.ZG"},
              "date": "2024", "value": None}],
        ]
        result = parse_world_bank(data, "USA", "NY.GDP.MKTP.KD.ZG")
        self.assertEqual(result, {date(2025, 1, 1): Decimal("2.4")})

    def test_world_bank_bad_geo_fails(self):
        data = [{"page": 1, "pages": 1}, [
            {"countryiso3code": "FRA", "indicator": {"id": "NY.GDP.MKTP.KD.ZG"},
             "date": "2025", "value": 2.4},
        ]]
        with self.assertRaisesRegex(ProviderError, "geography"):
            parse_world_bank(data, "USA", "NY.GDP.MKTP.KD.ZG")

    def test_world_bank_truncation_fails(self):
        with self.assertRaisesRegex(ProviderError, "truncated"):
            parse_world_bank([{"page": 1, "pages": 2}, []], "USA", "X")

    def test_nonfinite_rejected(self):
        with self.assertRaisesRegex(ProviderError, "infinite"):
            parse_fred_csv("DATE,DFII10\n2026-01-01,Infinity\n", "DFII10", "D")


class RouterTests(unittest.TestCase):
    def router(self, handler):
        return ProviderRouter(httpx.Client(transport=httpx.MockTransport(handler)))

    def test_world_bank_transport(self):
        def handler(request):
            self.assertIn("NY.GDP.MKTP.KD.ZG", str(request.url))
            return httpx.Response(200, json=[
                {"page": 1, "pages": 1},
                [{"countryiso3code": "USA", "indicator": {"id": "NY.GDP.MKTP.KD.ZG"},
                  "date": "2025", "value": 2.6}]
            ])
        router = self.router(handler)
        try:
            result = router.fetch("gdp.real_growth.us")
            self.assertEqual(result.observations[date(2025, 1, 1)], Decimal("2.6"))
        finally:
            router.close()

    def test_fred_public_csv(self):
        def handler(request):
            self.assertEqual(request.url.params["id"], "DFII10")
            return httpx.Response(
                200, text="observation_date,DFII10\n2026-01-01,1.5\n",
            )
        router = self.router(handler)
        try:
            self.assertEqual(
                router.fetch("bond.us.real_10y").observations,
                {date(2026, 1, 1): Decimal("1.5")},
            )
        finally:
            router.close()

    def test_ecb_transport(self):
        def handler(request):
            self.assertIn("FM/D.U2.EUR.4F.KR.DFR.LEV", str(request.url))
            return httpx.Response(200, text=(
                "KEY,TIME_PERIOD,OBS_VALUE\n"
                "FM.D.U2.EUR.4F.KR.DFR.LEV,2026-01-01,2.0\n"
            ))
        router = self.router(handler)
        try:
            self.assertEqual(
                router.fetch("policy_rate.ea.ecb_dfr").observations,
                {date(2026, 1, 1): Decimal("2.0")},
            )
        finally:
            router.close()

    def test_unresolved_never_fabricated(self):
        router = self.router(lambda request: self.fail("No network for unresolved"))
        try:
            self.assertEqual(len(router.supported_ids()), 15)
            with self.assertRaises(SourceUnavailable):
                router.fetch("valuation.global.cape")
            self.assertEqual(len(router.blocked()), 11)
        finally:
            router.close()


if __name__ == "__main__":
    unittest.main()
