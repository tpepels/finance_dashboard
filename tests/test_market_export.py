"""Full market export acceptance with source-independent, reproducible fixtures."""
from datetime import date
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch
import tempfile
import json
import unittest

from finance_dashboard.market import MarketHistory, PriceBar, instruments
from finance_dashboard.market_export import export_markets
from finance_dashboard.static_export import export_static


class FakeYahoo:
    fails = None
    def fetch(self, item):
        if item["id"] == self.fails:
            raise RuntimeError("API key / private URL should never be logged")
        d0,d1=date(2025,1,2),date(2025,1,3)
        c=item["trading_currency"]
        return MarketHistory(item["source_symbol"],c,{
            d0:PriceBar(d0,D(100),D(98),1000),
            d1:PriceBar(d1,D(102),D(100),1100),
        },({d1:D(1)} if item["distribution_policy"]=="distributing" else {}),
           {},f"https://invalid.example/{item['id']}")
    def close(self): pass


class FakeEcb:
    def fetch(self, currency):
        return {date(2025,1,2):D("1.20"),date(2025,1,3):D("1.25")}
    def close(self): pass


class FakeMacro:
    def fetch(self,sid,start=None):
        from finance_dashboard.bis import FetchedSeries
        return FetchedSeries(sid,"https://invalid.example",None,{date(2025,1,1):D(2)})
    def close(self): pass


class MarketExportTests(unittest.TestCase):
    def test_all_25_and_three_currency_feeds(self):
        self.assertEqual(len(instruments()),25)
        manifest,prices,fx=export_markets(market_factory=FakeYahoo,fx_factory=FakeEcb,max_workers=3)
        self.assertEqual(manifest["instrument_count"],25)
        self.assertEqual(set(instruments()),set(prices) - {"proxy.gold_vt_36m_usd", "proxy.gold_vt_36m_eur"})
        self.assertEqual(len(prices),27)
        self.assertEqual(set(fx),{"USD","GBP","CHF"})
        self.assertEqual(prices["vwce.de"]["trading_currency"],"EUR")
        self.assertEqual(prices["vwce.de"]["isin"],"IE00BK5BQT80")
        self.assertEqual(prices["vwrl.as"]["distribution_policy"],"distributing")
        self.assertEqual(prices["vt"]["data"]["observations"][0]["close_eur"],str(D(100)/D("1.20")))
        self.assertEqual(prices["vt"]["data"]["observations"][0]["eur_adjusted_index"],"100")
        self.assertEqual(prices["vwce.de"]["data"]["observations"][0]["eur_adjusted_index"],"100")
        self.assertEqual(fx["USD"]["quote_convention"],"1 EUR = X USD")

    def test_single_failure_blocks_entire_market_export(self):
        FakeYahoo.fails="nvda"
        try:
            with self.assertRaisesRegex(RuntimeError,"Market export incomplete: nvda"):
                export_markets(market_factory=FakeYahoo,fx_factory=FakeEcb,max_workers=2)
        finally:
            FakeYahoo.fails=None

    def test_macro_and_markets_saved_in_single_complete_output(self):
        manifest,prices,fx=export_markets(market_factory=FakeYahoo,fx_factory=FakeEcb)
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/"data"
            with patch("finance_dashboard.static_export.export_markets",
                       return_value=(manifest,prices,fx)):
                result=export_static(dest,series_ids=["bond.us.real_10y"],
                    provider_factory=FakeMacro,include_markets=True)
            self.assertEqual(result["series_count"],1)
            self.assertEqual(result["market"]["instrument_count"],25)
            self.assertEqual(len(list((dest/"markets").glob("*.json"))),28)
            self.assertEqual(len(list((dest/"fx").glob("*.json"))),3)
            self.assertTrue((dest/"series"/"bond.us.real_10y.json").exists())
            index=json.loads((dest/"index.json").read_text())
            self.assertEqual(index["market"]["base_currency"],"EUR")
            self.assertTrue(all("api_key" not in p.read_text()
                               for p in dest.rglob("*.json")))


if __name__=="__main__":
    unittest.main()
