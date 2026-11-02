"""Phase 4 market-risk contracts: no calendar filling or unverified exposures."""
import unittest
from finance_dashboard.portfolio_risk import compare_market_histories


def source(symbol, *, currency="USD", n=15, prices=None,
           missing=(), eur=True):
    if prices is None:
        prices = [100 + i * 2 for i in range(n)]
    # Calendar-month months 2024-01 to 2025-12, real trading dates
    bars = []
    for i, price in enumerate(prices):
        year = 2024 + i // 12
        month = i % 12 + 1
        if i in missing:
            continue
        bars.append({
            "date": f"{year:04d}-{month:02d}-26",
            "adjusted_close": str(price),
            "adjusted_close_eur": str(price / 2) if eur else None,
        })
    return {"symbol": symbol, "currency": currency, "status": "ready",
            "observations": bars}


def registry(*ids):
    return {sid: {"name": sid.upper(), "kind": "etf", "asset_class": "equity",
                  "domicile": "Ireland", "trading_currency": "USD",
                  "fund_base_currency": "USD", "benchmark": "UNVERIFIED"}
            for sid in ids}


class ComparisonTests(unittest.TestCase):
    def test_real_shared_month_price_normalization_and_eur_translation(self):
        histories = {
            "vt": source("VT", n=15, prices=[100+i for i in range(15)]),
            "gld": source("GLD", n=15, prices=[200+i*2 for i in range(15)]),
        }
        result = compare_market_histories(histories, registry("vt","gld"),
                                           currency="EUR")
        self.assertEqual(result["status"], "ready")
        self.assertEqual(len(result["aligned_months"]), 15)
        self.assertEqual(result["instruments"][0]["observations"][0]["index_100"], 100)
        self.assertAlmostEqual(result["instruments"][0]["observations"][-1]["index_100"], 114)
        self.assertEqual(result["instruments"][0]["observations"][0]["last_trade_date"], "2024-01-26")
        self.assertIsNotNone(result["instruments"][0]["annualized_volatility_pct"])
        self.assertEqual(result["instruments"][0]["geographic_holdings_status"], "not_verified")

    def test_drawdown_location_and_recovery_follows_recorded_months(self):
        prices = [100, 120, 90, 100, 125] + [130 + i for i in range(10)]
        histories = {"vt": source("VT",prices=prices),
                     "gld": source("GLD",n=15)}
        result = compare_market_histories(histories,registry("vt","gld"))
        dd = result["instruments"][0]["max_drawdown"]
        self.assertEqual(dd["max_drawdown_pct"], -25)
        self.assertEqual(dd["peak_month"], "2024-02")
        self.assertEqual(dd["trough_month"], "2024-03")
        self.assertEqual(dd["recovery_month"], "2024-05")
        self.assertEqual(result["instruments"][0]["observations"][2]["drawdown_pct"], -25)

    def test_gaps_are_never_bridged_by_chaining_returns(self):
        histories = {"vt": source("VT",n=15, missing=(5,)),
                     "gld": source("GLD",n=15)}
        result = compare_market_histories(histories,registry("vt","gld"))
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["aligned_months"][0], "2024-07")
        self.assertEqual(result["excluded_common_months"], 5)
        self.assertEqual(len(result["instruments"][0]["observations"]), 9)

    def test_no_insufficient_overlap_returns_or_invented_fx(self):
        histories = {"vt": source("VT",n=4, missing=(1,2)),
                     "gld": source("GLD",n=4)}
        result = compare_market_histories(histories,registry("vt","gld"))
        self.assertEqual(result["status"], "insufficient_overlap")
        self.assertEqual(result["instruments"], [])
        histories["vt"]["observations"] = []
        result = compare_market_histories(histories,registry("vt","gld"))
        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["missing_instruments"], ["vt"])

    def test_weighted_monthly_rebalancing_is_not_buy_and_hold(self):
        paths = {"vt": source("VT", n=15, prices=[100,110,100]+[110]*12),
                 "gld": source("GLD",n=15,prices=[100,100,110]+[110]*12)}
        result=compare_market_histories(paths,registry("vt","gld"),
                                        weights={"vt": 0.5, "gld": 0.5})
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["portfolio"]["observations"][0]["index_100"], 100)
        self.assertEqual(result["portfolio"]["weights_pct"], {"vt":50,"gld":50})
        self.assertEqual(result["portfolio"]["holdings_country_weights"],
                         "not_available_without_verified_holdings_history")
        # First month: +5% => 105. Next: half -9.09% and half +10% => 105.47727%.
        self.assertAlmostEqual(result["portfolio"]["observations"][1]["index_100"],105)
        self.assertAlmostEqual(result["portfolio"]["observations"][2]["index_100"],105.477273,places=5)

    def test_zero_series_or_unmatched_currency_does_not_fake_results(self):
        paths = {"vt": source("VT",currency="USD"),
                 "eu": source("EU",currency="EUR")}
        catalogue = registry("vt","eu")
        catalogue["eu"]["trading_currency"] = "EUR"
        with self.assertRaisesRegex(ValueError,"USD-quoted"):
            compare_market_histories(paths,catalogue,currency="USD")
        with self.assertRaisesRegex(ValueError,"sum|100 percent"):
            compare_market_histories(paths,catalogue,weights={"vt":0.6,"eu":0.3})
        with self.assertRaisesRegex(ValueError,"every selected"):
            compare_market_histories(paths,catalogue,weights={"vt":1.0})


if __name__ == "__main__":
    unittest.main()
