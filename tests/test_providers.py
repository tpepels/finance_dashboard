"""Deterministic provider parsing/transport checks; network never required."""
from datetime import date
from decimal import Decimal
import unittest
from unittest.mock import patch
import httpx

from finance_dashboard.providers import (
    ProviderRouter, ProviderError, SourceUnavailable,
    parse_fred_csv, parse_fred_json, parse_ecb_csv, parse_world_bank, parse_imf_mapper,
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

    def test_imf_mapper_historical_only(self):
        from unittest.mock import patch
        # Treat year 2025 as historical and 2026 as current-year estimate/forecast.
        with patch("finance_dashboard.providers.date") as fake_date:
            fake_date.today.return_value = date(2026, 11, 2)
            fake_date.side_effect = lambda *args: date(*args)
            raw = {"values": {"GGXWDG_NGDP": {"WEOWORLD": {
                "2024": 90.123, "2025": 91.234, "2026": 92.345, "2027": 93.45
            }}}}
            values = parse_imf_mapper(raw, "WEOWORLD", "GGXWDG_NGDP")
            self.assertEqual(values[date(2025, 1, 1)], Decimal("91.234"))
            self.assertNotIn(date(2026, 1, 1), values)

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

    def test_imf_transport(self):
        def handler(request):
            self.assertTrue(str(request.url).endswith("/GGXWDG_NGDP"))
            return httpx.Response(200, json={
                "values": {"GGXWDG_NGDP": {"WEOWORLD": {"2020": 97.1}}}
            })
        router = self.router(handler)
        try:
            got = router.fetch("fiscal.world.public_debt")
            self.assertEqual(got.observations[date(2020, 1, 1)], Decimal("97.1"))
        finally:
            router.close()

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
            with patch.dict("os.environ", {"FRED_PUBLIC_CSV_FALLBACK": "1", "FRED_API_KEY": ""}):
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

    def test_fred_without_credential_reports_blocker(self):
        router = self.router(lambda request: self.fail("no FRED fetch without configuration"))
        try:
            with patch.dict("os.environ", {"FRED_API_KEY": "", "FRED_PUBLIC_CSV_FALLBACK": ""}):
                with self.assertRaisesRegex(SourceUnavailable, "FRED_API_KEY required"):
                    router.fetch("bond.us.real_10y")
        finally:
            router.close()

    def test_unresolved_never_fabricated(self):
        router = self.router(lambda request: self.fail("No network for unresolved"))
        try:
            self.assertEqual(len(router.supported_ids()), 16)
            with self.assertRaises(SourceUnavailable):
                router.fetch("valuation.global.cape")
            self.assertEqual(len(router.blocked()), 10)
        finally:
            router.close()


if __name__ == "__main__":
    unittest.main()
