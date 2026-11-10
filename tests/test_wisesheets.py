"""Contract tests for secure Wisesheets SEC-listed earnings aggregation."""
from __future__ import annotations
from datetime import date
from decimal import Decimal as D
import unittest
from unittest.mock import patch
import httpx

from finance_dashboard.wisesheets import (
    WisesheetsError, WisesheetsClient, parse_companies, unique_issuers,
    parse_financials, parse_ecb_currency, parse_world_gdp,
    calculate_sec_earnings, collect_wisesheets,
)


class WiseTests(unittest.TestCase):
    def test_company_pagination_and_cik_dedup(self):
        rows, next_cursor = parse_companies({
            "data": [
                {"ticker": "GOOG", "cik": "0001652044", "hasFinancials": True, "status": "active"},
                {"ticker": "GOOGL", "cik": "0001652044", "hasFinancials": True, "status": "active"},
                {"ticker": "ASML", "cik": "0000937966", "hasFinancials": True, "status": "active"},
            ],
            "meta": {"nextCursor": "abc"},
        })
        self.assertEqual(next_cursor,"abc")
        unique = unique_issuers(rows)
        self.assertEqual(len(unique),2)
        self.assertEqual(unique["1652044"]["ticker"],"GOOG")
        with self.assertRaisesRegex(WisesheetsError,"cursor"):
            parse_companies({"data": [], "meta": {}})

    def test_financials_negative_values_and_fiscal_end(self):
        request = {"AAPL":"320193","MSFT":"789019"}
        sample = {
            "meta": {"layout":"long"},
            "data": [
                {"ticker":"AAPL", "cik":"0000320193", "metric":"net_income",
                 "fiscalPeriod":"FY", "fiscalYear":2024,"periodEnd":"2024-09-28",
                 "unit":"USD","value":"-700000000",
                 "source":{"accession":"0000320193-24-000001","filingDate":"2024-10-01","kind":"reported"}},
                {"ticker":"MSFT","cik":"0000789019","metric":"net_income",
                 "fiscalPeriod":"FY", "fiscalYear":2024,"periodEnd":"2024-06-30",
                 "unit":"USD","value":"90000000",
                 "source":{"accession":"0000789019-24-000001","filingDate":"2024-08-01","kind":"reported"}},
            ],
        }
        values=parse_financials(sample,request)
        self.assertEqual(values[("320193",2024)]["amount"],D("-700000000"))
        self.assertEqual(values[("789019",2024)]["amount"],D("90000000"))
        sample["data"][1]["metric"]="revenue"
        with self.assertRaisesRegex(WisesheetsError,"wrong financial metric"):
            parse_financials(sample,request)

    def test_missing_original_filing_is_excluded_not_fabricated(self):
        sample={"data":[{"ticker":"AAPL","cik":"0000320193",
            "metric":"net_income","fiscalPeriod":"FY","fiscalYear":2024,
            "periodEnd":"2024-09-28","unit":"USD","value":"500",
            "source":{"kind":"calculated","accession":None,"filingDate":None}}],
            "meta":{"layout":"long"}}
        rows=parse_financials(sample,{"AAPL":"320193"})
        self.assertFalse(rows[("320193",2024)]["source_is_verifiable"])
        aggregate=calculate_sec_earnings(
            {"320193":{"cik":"320193","ticker":"AAPL","has_financials":True}},
            rows,{}, {2024:D(1000)})
        self.assertEqual(aggregate["observations"][0]["untraceable_earnings_issuers"],1)
        self.assertEqual(D(aggregate["observations"][0]["sec_filer_net_income_usd"]),D(0))

    def test_sec_cik_alias_resolves_only_same_reporter(self):
        row={"ticker":"ALIAS","cik":"0000320193","metric":"net_income",
             "fiscalPeriod":"FY","fiscalYear":2024,"periodEnd":"2024-09-30",
             "unit":"USD","value":"100",
             "source":{"kind":"reported","accession":"111","filingDate":"2024-10-15"}}
        quality={}
        parsed=parse_financials({"meta":{"layout":"long"},"data":[row]},
                                {"AAPL":"320193"},quality=quality)
        self.assertEqual(parsed[("320193",2024)]["amount"],D(100))
        self.assertEqual(quality["ticker_alias_rows"],1)
        invalid_quality={}
        invalid_rows=parse_financials({"meta":{"layout":"long"},"data":[
            {**row,"cik":"0000000123"}]}, {"AAPL":"320193"},
            quality=invalid_quality)
        self.assertEqual(invalid_rows,{})
        self.assertEqual(invalid_quality["unmatched_issuer_rows"],1)

    def test_snapshot_series_separates_us_issuer_earnings_from_global_profit(self):
        from finance_dashboard.wisesheets import snapshot_series
        sample={"id":"profit.us_sec_filers.world_gdp_share",
                "observations":[
                    {"year":2023,"sec_filer_net_income_usd":"-10",
                     "sec_filer_income_as_pct_of_world_gdp":"-0.1",
                     "usd_conversion_coverage_pct_of_reporting_issuers":"80"},
                    {"year":2024,"sec_filer_net_income_usd":"120",
                     "sec_filer_income_as_pct_of_world_gdp":"1.2",
                     "usd_conversion_coverage_pct_of_reporting_issuers":"90"},
                ]}
        self.assertEqual(snapshot_series(sample,"SEC_US_FILER_NET_INCOME_USD",
                              start=date(2024,1,1)),{date(2024,1,1):D(120)})
        self.assertEqual(snapshot_series(sample,"SEC_US_FILER_WORLD_GDP_SHARE_PERCENT"),
                         {date(2023,1,1):D("-0.1"),date(2024,1,1):D("1.2")})
        with self.assertRaisesRegex(WisesheetsError,"Unrecognized"):
            snapshot_series(sample,"WORLD_LISTED_NET_INCOME")

    def test_future_and_inconsistent_fiscal_rows_are_counted_not_used(self):
        base={"ticker":"AAPL","cik":"0000320193","metric":"net_income",
              "fiscalPeriod":"FY","unit":"USD","value":"900",
              "source":{"kind":"reported","accession":"x","filingDate":"2026-10-31"}}
        payload={"meta":{"layout":"long"},"data":[
            {**base,"fiscalYear":2028,"periodEnd":"2028-12-31"},
            {**base,"fiscalYear":2025,"periodEnd":"2020-12-31"},
            {**base,"fiscalYear":2024,"periodEnd":"2024-09-30"},
        ]}
        quality={}
        vals=parse_financials(payload,{"AAPL":"320193"},quality=quality)
        self.assertEqual(len(vals),1)
        self.assertEqual(quality["future_fiscal_rows"],1)
        self.assertEqual(quality["inconsistent_fiscal_year_rows"],1)

    def test_ecb_cross_rate_and_partial_issuer_coverage(self):
        issuers={
            "1":{"cik":"1","ticker":"AAPL","has_financials":True},
            "2":{"cik":"2","ticker":"ASML","has_financials":True},
            "3":{"cik":"3","ticker":"OTHER","has_financials":True},
        }
        rows={
            ("1",2024):{"unit":"USD","amount":D("20"),"period_end":date(2024,12,31)},
            ("2",2024):{"unit":"EUR","amount":D("-3"),"period_end":date(2024,12,31)},
            ("3",2024):{"unit":"XYZ","amount":D("400"),"period_end":date(2024,12,31)},
        }
        fx={"USD": {date(2024,6,1)+__import__("datetime").timedelta(days=i):D("1.2")
                    for i in range(220)}}
        out=calculate_sec_earnings(issuers,rows,fx,{2024:D(100)})
        year=out["observations"][0]
        self.assertEqual(D(year["sec_filer_net_income_usd"]),D("16.4"))
        self.assertEqual(year["unconvertible_issuers_by_currency"],{"XYZ":1})
        self.assertEqual(year["reporting_issuers"],3)
        self.assertEqual(year["usd_converted_issuers"],2)
        self.assertEqual(out["status"],"partial_us_sec_reporter_coverage")

    def test_fx_source_identity_and_gdp(self):
        csv="KEY,TIME_PERIOD,OBS_VALUE\nEXR.D.USD.EUR.SP00.A,2024-06-03,1.07\n"
        self.assertEqual(parse_ecb_currency(csv,"USD"),{date(2024,6,3):D("1.07")})
        with self.assertRaisesRegex(WisesheetsError,"mismatch"):
            parse_ecb_currency(csv,"EUR")
        sample=[{"pages":1},[{"indicator":{"id":"NY.GDP.MKTP.CD"},
                   "countryiso3code":"WLD","date":"2024","value":100}]]
        self.assertEqual(parse_world_gdp(sample),{2024:D(100)})

    def test_bearer_key_is_sent_only_to_wisesheets(self):
        requests=[]
        def handler(req):
            requests.append(req)
            if req.url.host=="api.wisesheets.io":
                self.assertEqual(req.headers.get("authorization"),"Bearer TEST_SECRET")
                return httpx.Response(200,json={"plan":{
                    "planCode":"free","features":["fundamentals"],
                    "limits":{"historyYears":5,"requestsPerMinute":200,"monthlyRequests":5000}}})
            self.assertIsNone(req.headers.get("authorization"))
            return httpx.Response(200,text="KEY,TIME_PERIOD,OBS_VALUE\nEXR.D.USD.EUR.SP00.A,2024-06-03,1.20")
        with httpx.Client(transport=httpx.MockTransport(handler)) as raw:
            client=WisesheetsClient("TEST_SECRET",client=raw)
            self.assertEqual(client.plan()["code"],"free")
            self.assertEqual(client.fx_history("USD","2024-01-01")[date(2024,6,3)],D("1.20"))
            client.close()
        self.assertEqual(len(requests),2)

    def test_snapshot_reader_reports_staleness_without_live_api(self):
        from finance_dashboard.wisesheets import load_sec_profit_snapshot
        import tempfile, json
        from pathlib import Path
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/"data.json"
            self.assertIsNone(load_sec_profit_snapshot(dest))
            dest.write_text(json.dumps({
                "schema_version":1,"id":"profit.us_sec_filers.world_gdp_share",
                "status":"partial_us_sec_reporter_coverage",
                "currency":"USD",
                "source_snapshot_at_utc":"2024-01-01T00:00:00+00:00",
                "observations":[{"year":2024,"world_gdp_usd":"100",
                    "sec_filer_income_as_pct_of_world_gdp":"5"}],
            }))
            result=load_sec_profit_snapshot(dest)
            self.assertEqual(result["snapshot_status"],"stale")
            self.assertGreater(result["snapshot_age_days"],45)
            dest.write_text('{"id":"wrong"}')
            with self.assertRaisesRegex(WisesheetsError,"snapshot"):
                load_sec_profit_snapshot(dest)

    def test_snapshot_endpoint_uses_no_token_or_network(self):
        from fastapi.testclient import TestClient
        from sqlalchemy import create_engine
        from sqlalchemy.pool import StaticPool
        from finance_dashboard.api import create_app
        # This read-only endpoint test must not accidentally start the actual
        # refresh worker against an in-memory SQLite test database. Such a
        # worker would outlive the TestClient and close SQLite connections
        # from another thread on teardown.
        with patch.dict("os.environ", {"FINANCE_AUTO_REFRESH": "0"}):
            engine=create_engine("sqlite+pysqlite:///:memory:",
                connect_args={"check_same_thread": False}, poolclass=StaticPool)
            try:
                app=create_app(engine)
                with TestClient(app) as browser:
                    # The pre-engine SEC filer earnings view is retired; G03 shows listed earnings.
                    self.assertEqual(browser.get("/api/earnings/sec-filers").status_code, 404)
            finally:
                engine.dispose()

    def test_collect_keeps_world_label_out_of_numerator(self):
        class FakeClient:
            requests_made=2
            def plan(self):return {"code":"free","history_years":5,
                    "monthly_requests":5000,"requests_per_minute":200}
            def companies(self):return {"1":{"cik":"1","ticker":"AAPL","has_financials":True}}
            def earnings(self,issuers):return {
                ("1",2024):{"unit":"USD","amount":D(5),"period_end":date(2024,12,31)}}
            def fx_history(self,currency,start):
                return {date(2024,1,1):D("1.2")}
            def world_gdp(self):return {2024:D(100)}
        result=collect_wisesheets(FakeClient(),min_issuers=1)
        self.assertEqual(D(result["observations"][0]["sec_filer_income_as_pct_of_world_gdp"]),D(5))
        self.assertIn("NOT a global", result["description"])


if __name__=="__main__":
    unittest.main()
