"""Market-source contracts: venue, splits, dividends, FX, revisions and API data."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal as D
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import httpx
from fastapi.testclient import TestClient
from finance_dashboard.api import create_app
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from finance_dashboard.market import (
    EcbFxClient, MarketDataError, MarketHistory, PriceBar, YahooMarketClient,
    currency_to_eur, instruments, parse_ecb_fx_csv, parse_yahoo_chart, performance,
)
from finance_dashboard.database import Base, MarketPriceVersion, MarketActionVersion, FxRateVersion
from finance_dashboard.market_service import MarketIngestionService, current_market_prices, current_fx


def utc(y,m,d):
    return int(datetime(y,m,d,18,tzinfo=timezone.utc).timestamp())


def yahoo_fixture(symbol="VWCE.DE", currency="EUR", instrument_type="ETF"):
    return {"chart":{"error":None,"result":[{
        "meta":{"symbol":symbol,"currency":currency,"exchangeTimezoneName":"Europe/Berlin",
                "instrumentType":instrument_type,"exchangeName":"GER"},
        "timestamp":[utc(2025,1,2),utc(2025,1,3),utc(2025,1,6)],
        "indicators":{"quote":[{"close":[100.0,51.0,53.0],"volume":[100,200,300]}],
                      "adjclose":[{"adjclose":[48.0,50.0,53.0]}]},
        "events":{
            "splits":{"one":{"date":utc(2025,1,3),"numerator":2,"denominator":1}},
            "dividends":{"two":{"date":utc(2025,1,6),"amount":2.0}}
        }
    }]}}


class MarketAdapterTests(unittest.TestCase):
    def test_registry_eu_isin_and_currency_not_fund_base(self):
        registry=instruments()
        self.assertEqual(len(registry),25)
        self.assertEqual(registry["vwce.de"]["isin"],"IE00BK5BQT80")
        self.assertEqual(registry["vwrl.as"]["isin"],"IE00B3RBWM25")
        self.assertEqual(registry["vwce.de"]["trading_currency"],"EUR")
        self.assertEqual(registry["vwce.de"]["fund_base_currency"],"USD")
        self.assertNotEqual(registry["vwce.de"]["isin"],registry["vwrl.as"]["isin"])
        self.assertTrue(all(x["quote_scale"]=="1" for x in registry.values()))
        self.assertTrue(all(x["source_symbol"] for x in registry.values()))

    def test_exchange_venue_mismatch_rejected(self):
        instrument=instruments()["vwce.de"]
        payload=yahoo_fixture()
        payload["chart"]["result"][0]["meta"]["exchangeName"]="AMS"
        with self.assertRaisesRegex(MarketDataError,"exchange identity"):
            parse_yahoo_chart(payload,instrument)

    def test_yahoo_corporate_actions_date_alignment(self):
        inst=instruments()["vwce.de"]
        h=parse_yahoo_chart(yahoo_fixture(),inst)
        self.assertEqual(len(h.price_bars),3)
        self.assertEqual(h.dividends[date(2025,1,6)],D("2.0"))
        self.assertEqual(h.splits[date(2025,1,3)],D(2))
        self.assertEqual(h.price_bars[date(2025,1,2)].close,D("100.0"))
        self.assertEqual(h.price_bars[date(2025,1,2)].adjusted_close,D("48.0"))
        self.assertEqual(h.price_bars[date(2025,1,6)].volume,300)

    def test_reject_wrong_currency_or_symbol_and_missing_adjustment(self):
        inst=instruments()["vwce.de"]
        raw=yahoo_fixture(currency="USD")
        with self.assertRaisesRegex(MarketDataError,"currency"):
            parse_yahoo_chart(raw,inst)
        raw=yahoo_fixture(symbol="VT")
        with self.assertRaisesRegex(MarketDataError,"symbol"):
            parse_yahoo_chart(raw,inst)
        raw=yahoo_fixture()
        del raw["chart"]["result"][0]["indicators"]["adjclose"]
        with self.assertRaisesRegex(MarketDataError,"Malformed"):
            parse_yahoo_chart(raw,inst)

    def test_split_during_exchange_closure_is_preserved(self):
        item=instruments()["vwce.de"]
        data=yahoo_fixture()
        # A split event is recorded on an exchange closure between Jan 3
        # and Jan 6; it must not be reassigned to a fake trading session.
        split=data["chart"]["result"][0]["events"]["splits"]["one"]
        split["date"]=utc(2025,1,4)
        hist=parse_yahoo_chart(data,item)
        self.assertIn(date(2025,1,4),hist.splits)
        self.assertNotIn(date(2025,1,4),hist.price_bars)
        result=performance(hist)
        byday={r["date"]:r for r in result["observations"]}
        self.assertEqual(byday["2025-01-06"]["split_ratio"],"2")
        self.assertEqual(result["corporate_actions"][0]["ex_date"],"2025-01-04")

    def test_yahoo_mock_transport(self):
        def handler(request):
            self.assertEqual(request.url.params["events"],"div,splits")
            self.assertEqual(request.url.params["interval"],"1d")
            return httpx.Response(200,json=yahoo_fixture())
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            yahoo=YahooMarketClient(client)
            h=yahoo.fetch(instruments()["vwce.de"])
            self.assertEqual(len(h.price_bars),3)

    def test_ecb_fx_conversion_and_holiday_gap(self):
        csv="""KEY,TIME_PERIOD,OBS_VALUE
EXR.D.USD.EUR.SP00.A,2025-01-02,1.2000
EXR.D.USD.EUR.SP00.A,2025-01-03,1.2500
"""
        rates=parse_ecb_fx_csv(csv,"USD")
        self.assertEqual(currency_to_eur(date(2025,1,5),"USD",rates),D("1.25"))
        self.assertIsNone(currency_to_eur(date(2024,12,31),"USD",rates))
        self.assertEqual(D(125)/currency_to_eur(date(2025,1,5),"USD",rates),D(100))
        with self.assertRaisesRegex(MarketDataError,"identity"):
            parse_ecb_fx_csv(csv,"GBP")

    def test_raw_vs_vendor_adjusted_vs_reinvested(self):
        h=parse_yahoo_chart(yahoo_fixture(),instruments()["vwce.de"])
        out=performance(h)
        byday={r["date"]:r for r in out["observations"]}
        # 2-for-1 split: 51*2/100 = 1.02 (2% return).
        self.assertEqual(D(byday["2025-01-03"]["cash_dividend_reinvested_index"]),D(102))
        # Dividend on day 3: (53+2)/51 times split-adjusted basis.
        self.assertEqual(D(byday["2025-01-06"]["cash_dividend_reinvested_index"]),
                         D(102)*D(55)/D(51))
        self.assertEqual(D(byday["2025-01-02"]["price_index"]),D(100))
        self.assertNotEqual(byday["2025-01-06"]["price_index"],
                            byday["2025-01-06"]["vendor_adjusted_index"])

    def test_usd_asset_to_eur_per_ecb(self):
        h=MarketHistory("VT","USD",{
          date(2025,1,2):PriceBar(date(2025,1,2),D(120),D(120),100),
          date(2025,1,3):PriceBar(date(2025,1,3),D(125),D(125),200),
        },{},{},"https://query1.finance.yahoo.com/v8/finance/chart/VT")
        p=performance(h,{date(2025,1,2):D("1.2"),date(2025,1,3):D("1.25")})
        self.assertEqual(D(p["observations"][0]["adjusted_close_eur"]),D(100))
        self.assertEqual(D(p["observations"][1]["eur_adjusted_index"]),D(100))
        self.assertNotEqual(p["observations"][1]["vendor_adjusted_index"],
                            p["observations"][1]["eur_adjusted_index"])


class FakeYahoo:
    def __init__(self):
        self.history=parse_yahoo_chart(yahoo_fixture(),instruments()["vwce.de"])
        self.fail=False
    def fetch(self,definition,start=None):
        if self.fail:
            raise MarketDataError("private-source.example/token=secret")
        return self.history


class FakeEcb:
    def fetch(self,currency,start=None):
        if currency not in ("USD","GBP","CHF"):
            raise ValueError("invalid currency")
        return {date(2025,1,2):D("1.2"),date(2025,1,3):D("1.25")}


class MarketPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine("sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread":False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.yahoo=FakeYahoo()
        self.service=MarketIngestionService(self.engine,self.yahoo,FakeEcb())

    def tearDown(self):
        self.engine.dispose()

    def test_market_revision_idempotence_and_failed_ingest(self):
        r=self.service.refresh_instrument("vwce.de")
        self.assertEqual(r["versions_added"],5)
        self.assertEqual(self.service.refresh_instrument("vwce.de")["versions_added"],0)
        h=self.yahoo.history
        bars=dict(h.price_bars)
        day=date(2025,1,3)
        bars[day]=PriceBar(day,D("51.5"),D("50.5"),200)
        self.yahoo.history=MarketHistory(h.symbol,h.currency,bars,h.dividends,h.splits,h.source_url)
        self.assertEqual(self.service.refresh_instrument("vwce.de")["versions_added"],1)
        with Session(self.engine) as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(MarketPriceVersion)),4)
            self.assertEqual(session.scalar(select(func.count()).select_from(MarketActionVersion)),2)
            self.assertEqual(current_market_prices(session,"vwce.de")[1].close,D("51.5"))
        self.yahoo.fail=True
        with self.assertRaises(MarketDataError):
            self.service.refresh_instrument("vwce.de")
        with Session(self.engine) as session:
            self.assertEqual(len(current_market_prices(session,"vwce.de")),3)
            self.assertEqual(session.scalar(select(func.count()).select_from(MarketPriceVersion)),4)

    def test_market_api_registry_query_and_status(self):
        self.service.refresh_instrument("vwce.de")
        with TestClient(create_app(self.engine)) as client:
            registry=client.get("/api/markets")
            self.assertEqual(registry.status_code,200)
            self.assertEqual(registry.json()["count"],25)
            self.assertEqual(client.get("/api/markets/vwce.de").json()["isin"],"IE00BK5BQT80")
            self.assertEqual(client.get("/api/markets/does-not-exist").status_code,404)
            query=client.post("/api/market/query",json={
                "instrument_ids":["vwce.de"],"start":"2025-01-03"})
            self.assertEqual(query.status_code,200)
            result=query.json()["series"][0]
            self.assertEqual(result["status"],"ready")
            self.assertEqual(result["isin"],"IE00BK5BQT80")
            self.assertEqual(len(result["observations"]),2)
            self.assertEqual(len(result["corporate_actions"]),2)
            self.assertEqual(client.post("/api/market/query",json={
                "instrument_ids":["unknown"]}).status_code,404)
            status=client.get("/api/market/status")
            self.assertEqual(status.status_code,200)
            row=next(x for x in status.json()["instruments"] if x["id"]=="vwce.de")
            self.assertEqual(row["status"],"success")

    def test_fx_version_history(self):
        self.assertEqual(self.service.refresh_fx("USD")["versions_added"],2)
        self.assertEqual(self.service.refresh_fx("USD")["versions_added"],0)
        with Session(self.engine) as session:
            self.assertEqual(current_fx(session,"USD")[date(2025,1,3)],D("1.25"))

    def test_eur_asset_and_asof_snapshot(self):
        self.service.refresh_instrument("vwce.de")
        data=self.service.read_performance("vwce.de",start=date(2025,1,3))
        self.assertEqual(data["status"],"ready")
        self.assertEqual(len(data["observations"]),2)
        self.assertEqual(data["instrument_id"],"vwce.de")
        self.assertEqual(data["distribution_policy"],"accumulating")
        self.assertEqual(D(data["observations"][0]["eur_adjusted_index"]),D(50)/D(48)*100)


if __name__=="__main__":
    unittest.main()
