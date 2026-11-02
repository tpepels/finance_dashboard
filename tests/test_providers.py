"""Deterministic provider parsing/transport checks; network never required."""
from datetime import date
from decimal import Decimal
import unittest
from unittest.mock import patch
import httpx

from finance_dashboard.providers import (
    ProviderRouter, ProviderError, SourceUnavailable,
    parse_fred_csv, parse_fred_json, parse_ecb_csv, parse_world_bank, parse_imf_mapper, parse_shiller_sheet, parse_un_sdg, parse_pink_sheet_gold, parse_siblis_cape, parse_bis_credit_gap,
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

    def test_bis_gap_selects_actual_minus_trend_by_code(self):
        def series(values):
            return {"observations": {"0": [values]}}
        payload = {"meta": {"prepared": "2026-09-01T01:00:00Z"}, "data": {
          "structure": {"dimensions": {
            "series": [
              {"id":"FREQ","values":[{"id":"Q"}]},
              {"id":"BORROWERS_CTY","values":[{"id":"US"}]},
              {"id":"TC_BORROWERS","values":[{"id":"P"}]},
              {"id":"TC_LENDERS","values":[{"id":"A"}]},
              {"id":"CG_DTYPE","values":[{"id":"B"},{"id":"A"},{"id":"C"}]}
            ],
            "observation":[{"id":"TIME_PERIOD","values":[{"id":"2025-Q4"}]}]}},
          "dataSets":[{"series":{
            "0:0:0:0:0":series("130.5"),
            "0:0:0:0:1":series("132.0"),
            "0:0:0:0:2":series("1.5")
          }}]}}
        result, _ = parse_bis_credit_gap(payload,"US")
        self.assertEqual(result, {date(2025,10,1):Decimal("1.5")})
        with self.assertRaisesRegex(ProviderError, "frequency or geography"):
            parse_bis_credit_gap(payload,"JP")

    def test_global_cape_sparse_free_snapshots(self):
        raw = {"ticker":"ACWI","ratio":"cape","data":[
            {"trading_day (EOD)":"2025-09-30","value":30.75},
            {"trading_day (EOD)":"2025-12-31","value":31.25}]}
        result = parse_siblis_cape(raw, "ACWI", start=date(2025, 10, 1))
        self.assertEqual(result, {date(2025,12,31):Decimal("31.25")})
        with self.assertRaisesRegex(ProviderError, "identity mismatch"):
            parse_siblis_cape({**raw,"ticker":"WORLD"}, "ACWI")

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

    def test_world_bank_pink_sheet_gold(self):
        rows = [
          ["monthly prices in nominal US dollars"], ["metadata"], ["metadata"], [""],
          ["", "Gold", "Copper"], ["", "($/troy oz)", "($/mt)"],
          ["2025M01", 2641.5, 100.0], ["2025M02", None, 100.0],
          ["2025M03", 2900.25, 100.0]
        ]
        result = parse_pink_sheet_gold(rows)
        self.assertEqual(result[date(2025,1,1)], Decimal("2641.5"))
        self.assertEqual(result[date(2025,3,1)], Decimal("2900.25"))
        self.assertNotIn(date(2025,2,1), result)
        with self.assertRaisesRegex(ProviderError, "priced per troy ounce"):
            rows[5][1] = "($/kg)"
            parse_pink_sheet_gold(rows)

    def test_un_global_labour_share(self):
        raw = {"series": "SL_EMP_GTOTL", "geoAreaCode": 1, "dimensions": [
            {"value": "53.9", "timePeriodStart": "2004", "Age": "ALLAGE", "Reporting Type": "G"},
            {"value": "53.1", "timePeriodStart": "2005", "Age": "ALLAGE", "Reporting Type": "G"},
            {"value": "44", "timePeriodStart": "2005", "Age": "ALLAGE", "Reporting Type": "N"}
        ]}
        values = parse_un_sdg(raw, "SL_EMP_GTOTL", "1")
        self.assertEqual(values[date(2004, 1, 1)], Decimal("53.9"))
        self.assertEqual(values[date(2005, 1, 1)], Decimal("53.1"))
        self.assertEqual(len(values), 2)

    def test_shiller_month_dates_and_cape(self):
        class Sheet:
            ncols = 3
            nrows = 5
            data = [
                ("Title", "", ""), ("Date", "P", "CAPE"),
                (1871.01, 1.0, 12.25), (1871.11, 1.3, 13.4),
                (1871.12, 1.4, ""),
            ]
            def cell_value(self, row, col):
                return self.data[row][col]
        observations = parse_shiller_sheet(Sheet())
        self.assertEqual(observations[date(1871, 1, 1)], Decimal("12.25"))
        self.assertEqual(observations[date(1871, 11, 1)], Decimal("13.4"))
        self.assertNotIn(date(1871, 12, 1), observations)

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

    def test_un_transport(self):
        def handler(request):
            self.assertIn("SL_EMP_GTOTL/GeoArea/1/DataSlice", str(request.url))
            return httpx.Response(200, json={
                "series": "SL_EMP_GTOTL", "geoAreaCode": 1,
                "dimensions": [{"value": "53.9", "timePeriodStart": "2004",
                                "Age": "ALLAGE", "Reporting Type": "G"}],
            })
        router = self.router(handler)
        try:
            got = router.fetch("labour.world.income_share")
            self.assertEqual(got.observations[date(2004, 1, 1)], Decimal("53.9"))
        finally:
            router.close()

    def test_bis_credit_gap_transport(self):
        payload = {"data":{"structure":{"dimensions":{
            "series":[{"id":"FREQ","values":[{"id":"Q"}]},
                      {"id":"BORROWERS_CTY","values":[{"id":"US"}]},
                      {"id":"TC_BORROWERS","values":[{"id":"P"}]},
                      {"id":"TC_LENDERS","values":[{"id":"A"}]},
                      {"id":"CG_DTYPE","values":[{"id":"C"}]}],
            "observation":[{"id":"TIME_PERIOD","values":[{"id":"2025-Q1"}]}]}},
            "dataSets":[{"series":{"0:0:0:0:0":{"observations":{"0":["-2.75"]}}}}]}}
        def handler(request):
            self.assertIn("WS_CREDIT_GAP/1.0/Q.US", str(request.url))
            return httpx.Response(200, json=payload)
        router=self.router(handler)
        try:
            got=router.fetch("credit_gap.us.bis")
            self.assertEqual(got.observations[date(2025,1,1)],Decimal("-2.75"))
        finally:
            router.close()

    def test_siblis_transport(self):
        def handler(request):
            self.assertTrue(str(request.url).endswith("/ACWI/cape"))
            return httpx.Response(200, json={"ticker":"ACWI","ratio":"cape",
                "data":[{"trading_day (EOD)":"2025-12-31","value":31.25}]})
        router = self.router(handler)
        try:
            result = router.fetch("profit.global.corporate_share")
            self.assertEqual(result.observations[date(2025,12,31)], Decimal("31.25"))
        finally:
            router.close()

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
            self.assertEqual(len(router.supported_ids()), 23)
            with self.assertRaises(SourceUnavailable):
                router.fetch("valuation.global.cape")
            self.assertEqual(len(router.blocked()), 7)
        finally:
            router.close()


if __name__ == "__main__":
    unittest.main()
