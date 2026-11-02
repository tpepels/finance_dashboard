"""Venue-aware market histories, corporate actions and ECB FX.

Yahoo chart is an unofficial, no-key market-data feed. Source-adjusted closes
are not conflated with raw market closes or independent issuer NAVs.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from io import StringIO
import json
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx

from .catalog import DEFAULT_ROOT

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart"
ECB_FX = "https://data-api.ecb.europa.eu/service/data/EXR"
CURRENCIES = ("EUR", "USD", "GBP", "CHF")
MIC_CODES = {"XETR", "XAMS", "ARCX", "XNAS", "XNYS"}
EXCHANGE_ALIAS = {"XETR": ("GER",), "XAMS": ("AMS",), "ARCX": ("PCX",), "XNAS": ("NMS", "NGM"), "XNYS": ("NYQ",)}
D = Decimal


class MarketDataError(ValueError):
    pass


@dataclass(frozen=True)
class PriceBar:
    day: date
    close: Decimal
    adjusted_close: Decimal
    volume: int | None


@dataclass(frozen=True)
class MarketHistory:
    symbol: str
    currency: str
    price_bars: dict[date, PriceBar]
    dividends: dict[date, Decimal]
    splits: dict[date, Decimal]
    source_url: str


def instruments(root: Path = DEFAULT_ROOT) -> dict[str, dict]:
    doc = json.loads((Path(root) / "definitions" / "instruments.json").read_text(encoding="utf-8"))
    if doc.get("schema_version") != 1 or not isinstance(doc.get("instruments"), list):
        raise MarketDataError("Invalid instruments catalog schema")
    lookup = {}
    known_symbols = set()
    for item in doc["instruments"]:
        ident = item.get("id")
        symbol = item.get("source_symbol")
        if not isinstance(ident, str) or not ident or ident in lookup:
            raise MarketDataError("Missing or duplicated market instrument id")
        if not isinstance(symbol, str) or symbol in known_symbols or "/" in symbol or ".." in symbol:
            raise MarketDataError(f"Invalid or duplicated source symbol: {ident}")
        for key in ("name", "ticker", "reference_url", "notes", "domicile"):
            if not isinstance(item.get(key), str) or not item[key]:
                raise MarketDataError(f"{ident}: missing {key}")
        if item.get("source") != "YAHOO_CHART":
            raise MarketDataError(f"{ident}: unsupported market price provider")
        if item.get("kind") not in ("etf", "stock"):
            raise MarketDataError(f"{ident}: invalid kind")
        if item.get("trading_currency") not in CURRENCIES or item.get("fund_base_currency") not in CURRENCIES:
            raise MarketDataError(f"{ident}: unknown currency")
        if item.get("exchange_mic") not in MIC_CODES:
            raise MarketDataError(f"{ident}: invalid exchange venue")
        if item.get("quote_scale") != "1":
            raise MarketDataError(f"{ident}: unsupported quote unit (pence vs pounds must be explicit)")
        if item.get("distribution_policy") not in ("accumulating","distributing","none","corporate_dividends"):
            raise MarketDataError(f"{ident}: unknown dividend policy")
        if item.get("isin") is not None:
            import re
            if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", item["isin"]):
                raise MarketDataError(f"{ident}: invalid ISIN syntax")
        if item.get("isin_verified") and not item.get("isin"):
            raise MarketDataError(f"{ident}: verified ISIN missing")
        if not item["reference_url"].startswith("https://"):
            raise MarketDataError(f"{ident}: unsafe reference URL")
        known_symbols.add(symbol)
        lookup[ident] = item
    return lookup


def decimal_value(raw, *, positive: bool = False) -> Decimal:
    try:
        v = Decimal(str(raw))
    except (ValueError, TypeError, InvalidOperation) as exc:
        raise MarketDataError("Missing or invalid market value") from exc
    if not v.is_finite() or (positive and v <= 0):
        raise MarketDataError("Non-finite or nonpositive market value")
    return v


def _market_date(timestamp: int, zone: ZoneInfo) -> date:
    return datetime.fromtimestamp(int(timestamp), timezone.utc).astimezone(zone).date()


def parse_yahoo_chart(payload: dict, instrument: dict, *, start: date | None = None) -> MarketHistory:
    try:
        chart = payload["chart"]
        if chart.get("error") is not None:
            raise MarketDataError("Upstream market chart rejected instrument")
        results = chart["result"]
        if len(results) != 1:
            raise MarketDataError("Ambiguous or missing market chart")
        block = results[0]
        meta = block["meta"]
        ticker = meta["symbol"]
        currency = meta["currency"]
        zone = ZoneInfo(meta["exchangeTimezoneName"])
        quote_values = block["indicators"]["quote"][0]
        adj_values = block["indicators"]["adjclose"][0]["adjclose"]
        stamps = block["timestamp"]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise MarketDataError("Malformed market chart response") from exc
    if ticker != instrument["source_symbol"] or currency != instrument["trading_currency"]:
        raise MarketDataError("Market symbol or trading currency does not match registry")
    if meta.get("exchangeName") not in EXCHANGE_ALIAS[instrument["exchange_mic"]]:
        raise MarketDataError("Market exchange identity mismatch")
    expected_type = "ETF" if instrument["kind"] == "etf" else "EQUITY"
    if meta.get("instrumentType") != expected_type:
        raise MarketDataError("Market instrument category mismatch")
    n = len(stamps)
    if n != len(quote_values["close"]) or n != len(adj_values):
        raise MarketDataError("Market close/adjusted-close timestamps not aligned")
    volumes = quote_values.get("volume") or [None] * n
    if len(volumes) != n:
        raise MarketDataError("Market volume timestamps not aligned")
    bars = {}
    for index, stamp in enumerate(stamps):
        close, adj = quote_values["close"][index], adj_values[index]
        if close is None and adj is None:
            continue  # Provider's missing trading session, never forward-fill.
        if close is None or adj is None:
            raise MarketDataError("Source lacks adjusted close for a trading bar")
        day = _market_date(stamp, zone)
        if day > date.today() or (start and day < start):
            continue
        if day in bars:
            raise MarketDataError("Duplicate trading day in market chart")
        volume = volumes[index]
        if volume is not None and (not isinstance(volume, int) or volume < 0):
            raise MarketDataError("Invalid daily trading volume")
        bars[day] = PriceBar(day, decimal_value(close, positive=True),
                             decimal_value(adj, positive=True), volume)
    if not bars:
        raise MarketDataError("No valid market bars")
    events = block.get("events") or {}
    dividends, splits = {}, {}
    for event in (events.get("dividends") or {}).values():
        day = _market_date(event["date"], zone)
        # Keep the original ex-date, including exceptional exchange closure
        # dates; the cash event is applied at the next actual trading session.
        if day < min(bars) or (start and day < start) or day > max(bars):
            continue
        if day in dividends:
            raise MarketDataError("Multiple dividend events per day require explicit support")
        value = decimal_value(event["amount"])
        if value < 0:
            raise MarketDataError("Negative dividend")
        dividends[day] = value
    for event in (events.get("splits") or {}).values():
        day = _market_date(event["date"], zone)
        # Some historical splits occurred on exchange-closure dates
        # (NVDA, 2001-09-12, following 9/11). Retain the actual event date.
        if day < min(bars) or (start and day < start) or day > max(bars):
            continue
        if day in splits:
            raise MarketDataError("Multiple split events per day require explicit support")
        numerator = decimal_value(event["numerator"], positive=True)
        denominator = decimal_value(event["denominator"], positive=True)
        splits[day] = numerator / denominator
    return MarketHistory(
        instrument["source_symbol"], currency, dict(sorted(bars.items())),
        dividends, splits, f"{YAHOO_CHART}/{quote(instrument['source_symbol'], safe='')}",
    )


class YahooMarketClient:
    def __init__(self, client: httpx.Client | None = None):
        self._owns = client is None
        self.client = client or httpx.Client(timeout=30, headers={"User-Agent":"Mozilla/5.0"})

    def close(self):
        if self._owns:
            self.client.close()

    def fetch(self, instrument: dict, start: date | None = None) -> MarketHistory:
        sym = instrument["source_symbol"]
        params = {"interval":"1d", "events":"div,splits",
                  "period1":int(datetime.combine(start or date(1970,1,1),
                                              datetime.min.time(),timezone.utc).timestamp()),
                  "period2":int((datetime.now(timezone.utc)+timedelta(days=2)).timestamp())}
        url=f"{YAHOO_CHART}/{quote(sym, safe='')}"
        response=self.client.get(url,params=params)
        if response.status_code != 200:
            raise MarketDataError(f"Market feed rejected {sym}, HTTP {response.status_code}")
        return parse_yahoo_chart(response.json(),instrument,start=start)


def parse_ecb_fx_csv(raw: str, currency: str) -> dict[date, Decimal]:
    if currency not in ("USD","GBP","CHF"):
        raise MarketDataError("ECB FX supports USD, GBP, CHF per one EUR")
    reader=csv.DictReader(StringIO(raw.lstrip("\ufeff")))
    if not reader.fieldnames or not {"KEY","TIME_PERIOD","OBS_VALUE"}.issubset(reader.fieldnames):
        raise MarketDataError("ECB FX CSV columns missing")
    expected=f"EXR.D.{currency}.EUR.SP00.A"
    out={}
    for row in reader:
        if row["KEY"] != expected:
            raise MarketDataError("ECB FX series identity mismatch")
        day=date.fromisoformat(row["TIME_PERIOD"])
        if row["OBS_VALUE"] in ("","."):
            continue
        if day in out:
            raise MarketDataError("Duplicate FX date")
        out[day]=decimal_value(row["OBS_VALUE"],positive=True)
    if not out:
        raise MarketDataError("No ECB FX observations")
    return dict(sorted(out.items()))


class EcbFxClient:
    def __init__(self, client: httpx.Client | None = None):
        self._owns = client is None
        self.client=client or httpx.Client(timeout=30)

    def close(self):
        if self._owns:
            self.client.close()

    def fetch(self,currency: str,start: date | None = None) -> dict[date, Decimal]:
        if currency not in ("USD","GBP","CHF"):
            raise MarketDataError("Unsupported ECB FX currency")
        params={"format":"csvdata"}
        if start:
            params["startPeriod"]=start.isoformat()
        response=self.client.get(f"{ECB_FX}/D.{currency}.EUR.SP00.A",params=params)
        if response.status_code != 200:
            raise MarketDataError(f"ECB FX HTTP {response.status_code} for {currency}")
        return parse_ecb_fx_csv(response.text,currency)


def currency_to_eur(day: date, currency: str, fx: dict[date, Decimal],
                    *, tolerance_days: int = 5) -> Decimal | None:
    """ECB foreign-currency units / 1 EUR, so divide prices by this quote.

    Missing pre-euro observations produce None; no forward-filled earlier data.
    """
    if currency == "EUR":
        return D("1")
    for shift in range(tolerance_days+1):
        quote=fx.get(day-timedelta(days=shift))
        if quote is not None:
            return quote
    return None


def performance(history: MarketHistory, fx: dict[date, Decimal] | None = None) -> dict:
    """Return daily price, provider-adjusted and raw-cash-reinvestment indices.

    Splits are accounted for on ex-date, with cash dividends reinvested at
    the ex-date close, gross of taxes. Yahoo adjusted close is a separate
    vendor definition and may differ; no synthetic market calendar fill.
    """
    bars=list(history.price_bars.values())
    if not bars:
        raise MarketDataError("No prices")
    first=bars[0]
    price_base=first.close
    vendor_base=first.adjusted_close
    previous=None
    cash_index=D("100")
    eur_base=None
    out=[]
    for bar in bars:
        # Apply every corporate action on (last_market_day, this_market_day],
        # even when the provider recorded the event on an exchange closure.
        interval_start = previous.day if previous else bar.day-timedelta(days=1)
        period_dividends = sum(
            (value for action_day,value in history.dividends.items()
             if interval_start < action_day <= bar.day), D(0))
        period_splits = D(1)
        for action_day,ratio in history.splits.items():
            if interval_start < action_day <= bar.day:
                period_splits *= ratio
        if previous:
            numerator=(bar.close+period_dividends)*period_splits
            cash_index=cash_index*numerator/previous.close
        fx_rate=currency_to_eur(bar.day,history.currency,fx or {})
        eur_adj=bar.adjusted_close/fx_rate if fx_rate is not None else None
        if eur_adj is not None and eur_base is None:
            eur_base=eur_adj
        out.append({
            "date":bar.day.isoformat(),
            "close":str(bar.close),
            "adjusted_close":str(bar.adjusted_close),
            "volume":bar.volume,
            "dividend":str(period_dividends) if period_dividends != 0 else None,
            "split_ratio":str(period_splits) if period_splits != 1 else None,
            "price_index":str(price_base and bar.close/price_base*D(100)),
            "vendor_adjusted_index":str(bar.adjusted_close/vendor_base*D(100)),
            "cash_dividend_reinvested_index":str(cash_index),
            "fx_foreign_per_eur":str(fx_rate) if fx_rate is not None else None,
            "close_eur":str(bar.close/fx_rate) if fx_rate is not None else None,
            "adjusted_close_eur":str(eur_adj) if eur_adj is not None else None,
            "eur_adjusted_index":str(eur_adj/eur_base*D(100)) if eur_adj is not None else None,
        })
        previous=bar
    return {
        "symbol":history.symbol,
        "currency":history.currency,
        "base_currency":"EUR",
        "observations":out,
        "dividend_events":len(history.dividends),
        "split_events":len(history.splits),
        "corporate_actions": sorted([
            {"ex_date":day.isoformat(),"type":"dividend","value":str(value)}
            for day,value in history.dividends.items()
        ] + [
            {"ex_date":day.isoformat(),"type":"split","value":str(value)}
            for day,value in history.splits.items()
        ], key=lambda record:(record["ex_date"],record["type"])),
        "return_method":"vendor_adjusted_index uses Yahoo adjusted closes; cash_dividend_reinvested_index reinvests source cash dividends at the next trading close on/after ex-date, including on scheduled market closures, gross of tax; EUR index uses ECB foreign units per EUR, prior reference within 5 calendar days; no EUR values when FX unavailable",
    }
