"""Complete market/ETF and FX static-data export, no secrets in JSON."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from decimal import Decimal
import sys

from .market import EcbFxClient, YahooMarketClient, instruments, performance, MarketDataError


def export_markets(
    *,
    registry: dict[str, dict] | None = None,
    market_factory=YahooMarketClient,
    fx_factory=EcbFxClient,
    max_workers: int = 3,
) -> tuple[dict, dict[str, dict], dict[str, dict]]:
    """Fetch every instrument and required ECB FX currency, or fail entirely.

    Returns (manifest, market-data dictionaries, FX dictionaries). Caller
    commits them only after BOTH macro and market coverage are complete.
    """
    registry = registry if registry is not None else instruments()
    if not registry:
        raise ValueError("Market registry is empty")
    if not 1 <= max_workers <= 8:
        raise ValueError("Invalid market worker count")
    fx_client=fx_factory()
    try:
        currencies=sorted({d["trading_currency"] for d in registry.values() if d["trading_currency"]!="EUR"} | {"USD","GBP","CHF"})
        fx={currency:fx_client.fetch(currency) for currency in currencies}
    finally:
        fx_client.close()
    for currency, rates in fx.items():
        if not rates or any(day > date.today() or value <= 0 or not value.is_finite()
                            for day,value in rates.items()):
            raise MarketDataError(f"Invalid ECB FX observations for {currency}")

    def load_market(item):
        client=market_factory()
        try:
            history=client.fetch(item)
        finally:
            client.close()
        if not history.price_bars or history.symbol != item["source_symbol"]:
            raise MarketDataError("Provider returned an incorrect instrument")
        result=performance(history,fx.get(item["trading_currency"]))
        if not result["observations"]:
            raise MarketDataError("No returned market prices")
        return {
            "schema_version":1,
            "id":item["id"],
            "name":item["name"],
            "isin":item["isin"],
            "ticker":item["ticker"],
            "source_symbol":item["source_symbol"],
            "exchange_mic":item["exchange_mic"],
            "trading_currency":item["trading_currency"],
            "fund_base_currency":item["fund_base_currency"],
            "kind":item["kind"],
            "asset_class":item["asset_class"],
            "distribution_policy":item["distribution_policy"],
            "benchmark":item["benchmark"],
            "reference_url":item["reference_url"],
            "source":"YAHOO_CHART",
            "data":result,
            "unit_note":"Raw prices use listing trading currency; ECB quote is foreign units per EUR; vendor adjusted and gross cash-dividend indices are distinct.",
        }
    payloads={}
    failures=[]
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures={pool.submit(load_market, item): sid for sid,item in registry.items()}
        for future in as_completed(futures):
            sid=futures[future]
            try:
                payloads[sid]=future.result()
                print(f"Verified market {sid}: {len(payloads[sid]['data']['observations'])} days",flush=True)
            except Exception:
                failures.append(sid)
                print(f"Market fetch failed: {sid} (details redacted)", file=sys.stderr,flush=True)
    if failures:
        raise RuntimeError("Market export incomplete: "+", ".join(sorted(failures)))
    manifest={
        "schema_version":1,
        "base_currency":"EUR",
        "instrument_count":len(registry),
        "fx_currencies":currencies,
        "instruments":[{
            "id":sid,"name":item["name"],"kind":item["kind"],
            "asset_class":item["asset_class"],"isin":item["isin"],
            "exchange_mic":item["exchange_mic"],
            "trading_currency":item["trading_currency"],
            "fund_base_currency":item["fund_base_currency"],
            "distribution_policy":item["distribution_policy"],
            "file":f"markets/{sid}.json",
            "count":len(payloads[sid]["data"]["observations"]),
            "first":payloads[sid]["data"]["observations"][0]["date"],
            "last":payloads[sid]["data"]["observations"][-1]["date"],
        } for sid,item in sorted(registry.items())],
        "source_note":"Unofficial Yahoo chart adjusted closes and explicit corporate actions; ETF price return differs from issuer NAV and index total-return benchmark; ECB official FX to EUR.",
    }
    fx_files={}
    for currency,rates in fx.items():
        fx_files[currency]={
            "schema_version":1,
            "currency":currency,"base_currency":"EUR",
            "quote_convention":f"1 EUR = X {currency}",
            "source_url":f"https://data.ecb.europa.eu/data/datasets/EXR/EXR.D.{currency}.EUR.SP00.A",
            "observations":[{"date":day.isoformat(),"foreign_per_eur":str(value)}
                            for day,value in sorted(rates.items())],
        }
    return manifest,payloads,fx_files
