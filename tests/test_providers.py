"""Deterministic provider parsing/transport checks; network never required."""
from datetime import date
from decimal import Decimal
import unittest
from unittest.mock import patch
import httpx

from finance_dashboard.providers import ProviderRouter
from finance_dashboard.bis import ProviderError
from finance_dashboard.provider_parsers import (
    SourceUnavailable, parse_fred_csv, parse_fred_json, parse_fred_table_html, parse_ecb_csv, parse_world_bank, parse_imf_mapper, parse_shiller_sheet, parse_un_sdg, parse_pink_sheet_gold, parse_siblis_cape, parse_bis_credit_gap, parse_corgano_gold,
)


class ParserTests(unittest.TestCase):
    def test_fred_csv_missing_and_precision(self):
        values = parse_fred_csv(
            "observation_date,DFII10\n2026-01-01,.\n2026-01-02,-0.125\n",
            "DFII10", "D",
        )
        self.assertEqual(values, {date(2026, 1, 2): Decimal("-0.125")})

    def test_fred_quarterly_iso_periods(self):
        html = """<div>Series ID NCBCEPNW</div><table>
            <tr><th>DATE</th><th>VALUE</th></tr>
            <tr><td>2026-01-01</td><td>214.8</td></tr>
            <tr><td>2026-04-01</td><td>242.3</td></tr></table>"""
        obs = parse_fred_table_html(html, "NCBCEPNW", "Q")
        self.assertEqual(obs[date(2026,4,1)], Decimal("242.3"))

    def test_fred_html_table_and_source_identity(self):
        html = """<html><body><div>Series ID DFII10</div>
            <table><tr><th>DATE</th><th>VALUE</th></tr>
            <tr><td>2026-01-01</td><td>.</td></tr>
            <tr><td>2026-01-02</td><td>2.375</td></tr></table></body></html>"""
        self.assertEqual(parse_fred_table_html(html, "DFII10", "D"),
                         {date(2026,1,2):Decimal("2.375")})
        with self.assertRaisesRegex(ProviderError,"identify"):
            parse_fred_table_html(html, "DFEDTARU", "D")

    def test_fred_html_extended_history(self):
        html = """<div>Series ID DFII10</div>
          <table><tr><th>DATE</th><th>VALUE</th></tr>
          <tr><td>2003-01-02</td><td>2.1</td></tr></table>
          <div id="extra-rows"> #2025-09-29| 1.80
          #2025-09-30| 1.80 #2025-10-01| . #2025-10-02| 1.77 </div>"""
        observed = parse_fred_table_html(html, "DFII10", "D")
        self.assertEqual(observed[date(2003,1,2)], Decimal("2.1"))
        self.assertEqual(observed[date(2025,10,2)], Decimal("1.77"))
        self.assertEqual(len(observed), 4)
        bad = html.replace("#2025-10-02| 1.77", "#wrong| 1.77")
        with self.assertRaisesRegex(ProviderError, "Invalid observation period"):
            parse_fred_table_html(bad,"DFII10","D")

    def test_fred_annual_iso_dates_and_year_labels_are_equivalent(self):
        observed = parse_fred_json({"observations": [
            {"date": "2022-01-01", "value": "0.64"},
            {"date": "2023", "value": "0.63"},
        ]}, "A")
        self.assertEqual(observed, {
            date(2022, 1, 1): Decimal("0.64"),
            date(2023, 1, 1): Decimal("0.63"),
        })
        with self.assertRaisesRegex(ProviderError, "Invalid observation period"):
            parse_fred_json({"observations": [
                {"date": "2023-07-01", "value": "0.63"}
            ]}, "A")

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
        with patch("finance_dashboard.provider_adapters.date") as fake_date:
            fake_date.today.return_value = date(2026, 11, 2)
            fake_date.side_effect = lambda *args: date(*args)
            raw = {"values": {"GGXWDG_NGDP": {"WEOWORLD": {
                "2024": 90.123, "2025": 91.234, "2026": 92.345, "2027": 93.45
            }}}}
            values = parse_imf_mapper(raw, "WEOWORLD", "GGXWDG_NGDP")
            self.assertEqual(values[date(2025, 1, 1)], Decimal("91.234"))
            self.assertNotIn(date(2026, 1, 1), values)

    def test_world_productivity_reporting_and_age(self):
        raw = {"series":"SL_EMP_PCAP","geoAreaCode":1,"dimensions":[
            {"value":"2.63","timePeriodStart":"2000","Age":"15+","Reporting Type":"G"},
            {"value":"9.1","timePeriodStart":"2001","Age":"ALLAGE","Reporting Type":"G"}]}
        values=parse_un_sdg(raw,"SL_EMP_PCAP","1")
        self.assertEqual(values,{date(2000,1,1):Decimal("2.63")})

    def test_gold_spot_mid_quote_provenance(self):
        from datetime import datetime, timezone
        payload={"data":{"metal":"gold","symbol":"XAU","price_usd":{"per_oz":3900.25,"per_gram":125.4,"per_kg":125400},
                         "as_of":datetime.now(timezone.utc).isoformat()},
                 "meta":{"unit":"USD / troy oz","source":"Swissquote bid/ask midpoint"}}
        expected={date.today():Decimal("3900.25")}
        self.assertEqual(parse_corgano_gold(payload),expected)
        payload["meta"]["source"]="COMEX futures"
        with self.assertRaisesRegex(ProviderError,"futures price"):
            parse_corgano_gold(payload)

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

    def test_shiller_refuses_severely_truncated_monthly_workbook(self):
        class SparseSheet:
            ncols = 2
            nrows = 4
            data = [
                ("Date","CAPE"),(1881.01,12.0),
                (1980.01,10.0),(2026.04,35.0),
            ]
            def cell_value(self,row,col):
                return self.data[row][col]
        with self.assertRaisesRegex(ProviderError,
                                    "incomplete monthly CAPE history"):
            parse_shiller_sheet(SparseSheet())

    def test_shiller_split_headers_and_total_return_cape_are_not_confused(self):
        rows = [
            ["Shiller source", "", "", ""],
            ["Date", "", "", ""],
            ["", "", "Cyclically Adjusted P/E", "Total Return CAPE"],
            ["", "", "CAPE", "TR CAPE"],
        ]
        for year in range(1881, 1894):
            for month in range(1, 13):
                rows.append([float(f"{year}.{month:02d}"), "", 12.5, 99.0])
        observations = parse_shiller_sheet(rows)
        self.assertEqual(len(observations), 13 * 12)
        self.assertEqual(observations[date(1881, 1, 1)], Decimal("12.5"))
        self.assertEqual(observations[date(1893, 12, 1)], Decimal("12.5"))

    def test_shiller_official_multiline_headers_ignore_fraction_tr_cape_and_excess(self):
        # Official Shiller workbook uses header rows 1..7 and two spacers.
        # Ordinary CAPE has both "Cyclically Adjusted" and "CAPE" text.
        headers = [
            ["Shiller monthly series", "", "", "", "", "", ""],
            ["", "", "", "", "", "", ""],
            ["Date", "", "Date", "", "", "", ""],
            ["", "", "Fraction", "", "Cyclically Adjusted", "Total Return", "Excess CAPE Yield"],
            ["", "", "", "", "P/E Ratio", "CAPE", ""],
            ["", "", "", "", "CAPE", "TR CAPE", ""],
            ["", "", "", "", "", "", ""],
            ["", "", "", "", "", "", ""],
        ]
        for year in range(1871, 1895):
            for month in range(1, 13):
                cape = 12.5 if year >= 1881 else "NA"
                headers.append([float(f"{year}.{month:02d}"), "", 0.34,
                                "", cape, 99.0, 3.0])
        series = parse_shiller_sheet(headers)
        self.assertEqual(min(series), date(1881, 1, 1))
        self.assertEqual(len(series), 14 * 12)
        self.assertEqual(series[date(1894, 12, 1)], Decimal("12.5"))
        self.assertNotIn(date(1871, 1, 1), series)

    def test_shiller_rejects_partial_recent_history_even_when_contiguous(self):
        rows = [["Date", "CAPE"]]
        for year in range(2024, 2027):
            for month in range(1, 13):
                rows.append([float(f"{year}.{month:02d}"), 39.0])
        with self.assertRaisesRegex(ProviderError, "incomplete monthly CAPE history"):
            parse_shiller_sheet(rows)

    def test_shiller_router_preserves_parser_error_code(self):
        """A valid Excel container with an incomplete history is not corruption."""
        from finance_dashboard.service import safe_source_failure_code
        def handler(request):
            if request.url.host == "shillerdata.com":
                return httpx.Response(200, text=(
                    '<a href="https://img1.wsimg.com/official/ie_data.xls">Download</a>'))
            return httpx.Response(200, content=bytes.fromhex(
                "D0CF11E0A1B11AE1") + b"\x00" * 40)
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            router = ProviderRouter(client=client)
            with patch("python_calamine.CalamineWorkbook.from_filelike") as load:
                load.return_value.get_sheet_by_name.return_value.to_python.return_value = [
                    ["Date", "CAPE"],
                    [1881.01, 12.0],
                    [1980.01, 20.0],
                    [2026.04, 35.0],
                ]
                with self.assertRaisesRegex(
                        ProviderError, "incomplete monthly CAPE history") as caught:
                    router.fetch("valuation.us.cape")
        self.assertEqual(safe_source_failure_code(caught.exception),
                         "shiller_incomplete")

    def test_shiller_router_rejects_html_masquerading_as_workbook(self):
        def handler(request):
            if request.url.host == "shillerdata.com":
                return httpx.Response(200, text=(
                    '<a href="https://img1.wsimg.com/official/ie_data.xls">Download</a>'))
            return httpx.Response(200, text="<html>download failed</html>")
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaisesRegex(
                    ProviderError, "not an Excel workbook"):
                ProviderRouter(client=client).fetch("valuation.us.cape")

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

    def test_corgano_spot_transport(self):
        from datetime import datetime,timezone
        def handler(request):
            self.assertIn("api/v1/latest", str(request.url))
            return httpx.Response(200, json={
                "data":{"metal":"gold","symbol":"XAU","price_usd":{"per_oz":3900.25,"per_gram":125.4,"per_kg":125400},
                        "as_of":datetime.now(timezone.utc).isoformat()},
                "meta":{"unit":"USD / troy oz","source":"Swissquote midpoint"}
            })
        router=self.router(handler)
        try:
            self.assertIn(date.today(),router.fetch("gold.usd.spot").observations)
        finally:
            router.close()

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
            result = router.fetch("valuation.global.cape")
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

    def test_pwt_germany_france_italy_are_real_fred_ratio_series(self):
        registered = {
            "labour.de.pwt_labour_share": ("LABSHPDEA156NRUG", "0.63735"),
            "labour.fr.pwt_labour_share": ("LABSHPFRA156NRUG", "0.63098"),
            "labour.it.pwt_labour_share": ("LABSHPITA156NRUG", "0.51165"),
        }
        requested = []
        def handler(request):
            sid = request.url.params["series_id"]
            requested.append(sid)
            self.assertEqual(request.url.params["api_key"], "a" * 32)
            official = {row[0]: row[1] for row in registered.values()}
            self.assertIn(sid, official)
            return httpx.Response(200, json={"observations":[
                {"date": "2022-01-01", "value":"0.64"},
                {"date": "2023-01-01", "value":official[sid]},
            ]})
        router = self.router(handler)
        try:
            with patch.dict("os.environ", {"FRED_API_KEY": "a"*32}):
                for source_id, (fred_id, value) in registered.items():
                    with self.subTest(source_id=source_id):
                        row=router.fetch(source_id)
                        self.assertEqual(row.series_id, source_id)
                        self.assertEqual(row.observations[date(2023,1,1)],Decimal(value))
                        self.assertEqual(row.request_url,
                            "https://fred.stlouisfed.org/series/" + fred_id)
            self.assertEqual(set(requested), {r[0] for r in registered.values()})
        finally:
            router.close()

    def test_fred_authenticated_overlap_filters_only_older_returned_periods(self):
        # Upstream returns full-history rows despite observation_start.
        # Incremental ingestion must keep the original date boundary.
        def handler(request):
            self.assertEqual(request.url.params["series_id"], "LABSHPDEA156NRUG")
            self.assertEqual(request.url.params["observation_start"], "2022-06-01")
            return httpx.Response(200, json={"observations": [
                {"date":"2010-01-01","value":"0.70"},
                {"date":"2022-01-01","value":"0.65"},
                {"date":"2023-01-01","value":"0.63"},
            ]})
        router = self.router(handler)
        try:
            with patch.dict("os.environ", {"FRED_API_KEY":"a"*32}):
                row = router.fetch("labour.de.pwt_labour_share",date(2022,6,1))
                self.assertEqual(row.observations,
                                 {date(2023,1,1):Decimal("0.63")})
        finally:
            router.close()

    def test_fred_authenticated_full_import_preserves_old_source_dates(self):
        def handler(request):
            self.assertNotIn("observation_start", request.url.params)
            return httpx.Response(200,json={"observations":[
                {"date":"1950-01-01","value":"0.70"},
                {"date":"2023-01-01","value":"0.63"}]})
        router = self.router(handler)
        try:
            with patch.dict("os.environ",{"FRED_API_KEY":"a"*32}):
                self.assertEqual(len(router.fetch(
                    "labour.de.pwt_labour_share").observations),2)
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

    def test_fred_without_credential_uses_public_official_table(self):
        def handler(request):
            self.assertTrue(str(request.url).endswith("/data/DFII10"))
            return httpx.Response(200,text="""<div>Series ID DFII10</div>
                <table><tr><th>DATE</th><th>VALUE</th></tr>
                <tr><td>2026-01-02</td><td>2.375</td></tr></table>""")
        router = self.router(handler)
        try:
            with patch.dict("os.environ", {"FRED_API_KEY": "", "FRED_PUBLIC_CSV_FALLBACK": ""}):
                self.assertEqual(router.fetch("bond.us.real_10y").observations,
                                 {date(2026,1,2):Decimal("2.375")})
        finally:
            router.close()

    def test_unresolved_never_fabricated(self):
        router = self.router(lambda request: self.fail("No network for unresolved"))
        try:
            # Full mapped registry (including newly added world macro aggregates), not a stale fixed size.
            catalog, _ = __import__("finance_dashboard.catalog", fromlist=["load_documents"]).load_documents()
            mapped = {row["id"] for row in catalog["series"] if row["status"] == "mapped"}
            self.assertEqual(set(router.supported_ids()), mapped)
            with self.assertRaises(SourceUnavailable):
                router.fetch("profit.global.corporate_share")
            self.assertEqual(len(router.blocked()), 0)
        finally:
            router.close()


if __name__ == "__main__":
    unittest.main()
