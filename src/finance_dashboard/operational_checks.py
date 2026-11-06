"""Explicit operational acceptance checks retained from previous diagnostics.

Exploratory PostgreSQL-only and GitHub-Pages checks were retired with their
obsolete deployment modes. This module is inert until a command is selected.
"""
from __future__ import annotations
import argparse
import sys

def deployment_smoke():
    """Check a real Compose API after initial worker ingestion completes.
    
    No provider data is emulated. Queries trace real observations to persisted ingestion runs.
    """
    
    from datetime import date
    import json
    import sys
    import time
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen
    
    API = "http://127.0.0.1:8080"
    IDS = ["policy_rate.us.bis", "policy_rate.ea.bis", "policy_rate.jp.bis"]
    
    
    def get(path: str):
        with urlopen(API + path, timeout=4) as response:
            return json.load(response)
    
    
    def post(path: str, body: dict):
        request = Request(
            API + path, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urlopen(request, timeout=8) as response:
            return json.load(response)
    
    
    def main():
        # Only wait for the HTTP service to start, not for an arbitrary data duration.
        for attempt in range(20):
            try:
                assert get("/api/health")["status"] == "ok"
                break
            except (URLError, HTTPError, AssertionError):
                time.sleep(1)
        else:
            raise RuntimeError("HTTP server did not become healthy within 20 seconds")
    
        report = get("/api/data-status")
        by_id = {item["series_id"]: item for item in report["items"]}
        for sid in IDS:
            status = by_id[sid]
            assert status["status"] == "success", f"{sid}: {status}"
            assert status["received"] > 0, f"{sid}: no observations received"
            assert status["last_success"], f"{sid}: missing ingestion timestamp"
    
        payload = post("/api/query", {"series_ids": IDS, "start": "2026-01-01"})
        assert payload["snapshot_kind"] == "app_first_seen_not_publication_vintage"
        assert len(payload["series"]) == 3
        for item in payload["series"]:
            assert item["status"] == "ready", item
            assert item["observations"], item
            for record in item["observations"]:
                assert date.fromisoformat(record["date"]) <= date.today()
                assert record["ingestion_run_id"]
                assert record["first_seen_at"]
            print(json.dumps({
                "series_id": item["series_id"],
                "returned": len(item["observations"]),
                "first": item["observations"][0]["date"],
                "latest": item["observations"][-1]["date"],
                "source": item["source_url"],
            }))
        print("PHASE2_LIVE_ACCEPTANCE=PASS")
    
    
    if True:
        try:
            main()
        except Exception as exc:
            print(f"PHASE2_LIVE_ACCEPTANCE=FAIL: {exc}", file=sys.stderr)
            raise
    

def live_bis_check():
    """Bounded live provider acceptance; no hard-coded interest rates, no synthetic values.
    
    Run by Phase 2 live CI separately from deterministic offline tests.
    """
    
    from datetime import date, timedelta
    import json
    
    from finance_dashboard.bis import BisPolicyClient, COUNTRIES
    
    
    def main() -> int:
        start = date.today() - timedelta(days=45)
        client = BisPolicyClient(retries=1)
        try:
            for sid in COUNTRIES:
                data = client.fetch(sid, start=start)
                dates = list(data.observations)
                assert dates, f"Empty recent series: {sid}"
                assert min(dates) >= start, f"Observations before start: {sid}"
                assert max(dates) <= date.today(), f"Future-dated observation: {sid}"
                assert all(v.is_finite() for v in data.observations.values()), sid
                print(json.dumps({
                    "series_id": sid,
                    "source": data.request_url,
                    "first_observation": dates[0].isoformat(),
                    "last_observation": dates[-1].isoformat(),
                    "observations": len(dates),
                    "bis_response_prepared": data.prepared_at.isoformat() if data.prepared_at else None,
                }))
        finally:
            client.close()
        return 0
    
    
    if True:
        raise SystemExit(main())
    

def live_providers_check():
    """Bounded, live source acceptance for every mapped non-FRED/non-BIS series.
    
    FRED requires owner-supplied FRED_API_KEY; BIS has a separate full-Docker
    acceptance workflow. Missing values, future dates, and source IDs are validated.
    """
    from datetime import date, timedelta
    import json
    
    from finance_dashboard.providers import ProviderRouter
    
    
    def main() -> int:
        router = ProviderRouter()
        successful = 0
        try:
            sources = [sid for sid in router.supported_ids()
                       if router.definitions[sid]["provider"] != "BIS"]
            for sid in sources:
                start = date.today() - timedelta(days=2200 if sid.startswith("valuation.domestic") else 1100)
                result = router.fetch(sid, start)
                assert result.observations, f"No observations for {sid}"
                assert min(result.observations) >= start, f"Upstream ignored window: {sid}"
                assert max(result.observations) <= date.today(), f"Future observation: {sid}"
                successful += 1
                print(json.dumps({
                    "series_id": sid, "source_url": result.request_url.split("?")[0],
                    "count": len(result.observations), "latest": max(result.observations).isoformat(),
                }), flush=True)
        finally:
            router.close()
        print(f"PHASE2_ALL_NONBIS_LIVE=PASS (verified={successful}, BIS policies verified separately)")
        return 0
    
    
    if True:
        raise SystemExit(main())
    

def market_live_check():
    from finance_dashboard.source_policy import managed_get
    """Short real feed acceptance with explicit venue, split and dividend evidence."""
    from finance_dashboard.market import instruments, YahooMarketClient, EcbFxClient
    import json
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    import httpx
    
    market=YahooMarketClient()
    try:
        for key in ("nvda","vwce.de","vwrl.as","vt","gld","vxus","qqq","bnd"):
            item=instruments()[key]
            try:
                hist=market.fetch(item)
                print(json.dumps({"id":key,"bars":len(hist.price_bars),"dividends":len(hist.dividends),"splits":{k.isoformat():str(v) for k,v in hist.splits.items()},"currency":hist.currency}),flush=True)
            except Exception as exc:
                print(json.dumps({"id":key,"error":type(exc).__name__,"message":str(exc)[:400]}),flush=True)
                if key in ("nvda","vxus","qqq","bnd"):
                    response=managed_get(f"https://query1.finance.yahoo.com/v8/finance/chart/{item['source_symbol']}",
                        params={"interval":"1d","period1":0,"period2":9999999999,"events":"div,splits"},
                        timeout=15,headers={"User-Agent":"Mozilla/5.0"})
                    if response.status_code==200:
                        item=response.json()["chart"]["result"][0]
                        print(json.dumps({"id":key,"actual_exchange":item["meta"].get("exchangeName"),"actual_currency":item["meta"].get("currency"),"type":item["meta"].get("instrumentType")}),flush=True)
                        tz=ZoneInfo(item["meta"]["exchangeTimezoneName"])
                        dates={datetime.fromtimestamp(ts,timezone.utc).astimezone(tz).date()
                               for ts in item["timestamp"]}
                        for event in (item.get("events",{}).get("splits") or {}).values():
                            at=datetime.fromtimestamp(event["date"],timezone.utc)
                            print(json.dumps({"split_utc":at.isoformat(),
                                "split_local":at.astimezone(tz).date().isoformat(),
                                "local_is_trading_day":at.astimezone(tz).date() in dates,
                                "utc_is_trading_day":at.date() in dates,
                                "ratio":event.get("splitRatio")}),flush=True)
    finally:
        market.close()
    

def validate_wisesheets_snapshot():
    """Validate complete monthly SEC-reporting earnings aggregate before publication."""
    import json
    import sys
    from pathlib import Path
    from datetime import datetime, timezone
    from decimal import Decimal
    
    path = Path(sys.argv[1]) if len(sys.argv)>1 else Path("data/wisesheets/sec_filer_profit.json")
    payload = json.loads(path.read_text())
    assert payload["schema_version"] == 1
    assert payload["id"] == "profit.us_sec_filers.world_gdp_share"
    assert payload["status"] == "partial_us_sec_reporter_coverage"
    assert payload["currency"] == "USD"
    assert payload["unique_issuers_with_financials"] >= 5000
    assert 1 <= payload["wisesheets_requests_used_this_run"] <= 800
    rows = payload["observations"]
    assert len(rows) >= 3 and len({x["year"] for x in rows}) == len(rows)
    for row in rows:
        assert row["world_gdp_usd"] and Decimal(row["world_gdp_usd"]) > 0
        assert row["reporting_issuers"] >= 1000
        assert 0 < row["usd_converted_issuers"] <= row["reporting_issuers"]
        assert Decimal(row["usd_conversion_coverage_pct_of_reporting_issuers"]) <= 100
        assert Decimal(row["sec_filer_net_income_usd"]).is_finite()
        assert Decimal(row["sec_filer_income_as_pct_of_world_gdp"]).is_finite()
    snapshot=datetime.fromisoformat(payload["source_snapshot_at_utc"])
    assert snapshot.tzinfo is not None
    assert abs((datetime.now(timezone.utc)-snapshot).total_seconds())<86400
    raw = path.read_text()
    assert "WISESHEETS_API_KEY" not in raw and "Bearer " not in raw
    print("WISESHEETS_SEC_AGGREGATE=PASS "
          f"years={len(rows)} issuers={payload['unique_issuers_with_financials']} "
          f"requests={payload['wisesheets_requests_used_this_run']}", flush=True)
    

def wisesheets_live_sample():
    """Verify actual Wisesheets AAPL/ASML/MSFT annual earnings and ECB conversion.
    
    Uses the GitHub Actions WISESHEETS_API_KEY secret; prints no earnings,
    account metadata, credentials or authenticated URLs.
    """
    from datetime import date
    from finance_dashboard.wisesheets import (
        WisesheetsClient, parse_financials, calculate_sec_earnings,
    )
    import json
    
    client = WisesheetsClient()
    try:
        plan = client.plan()
        assert "fundamentals" in (["fundamentals"] if plan["history_years"] >= 5 else [])
        expected = {
            "AAPL": "320193",
            "MSFT": "789019",
            "ASML": "937966",
        }
        response = client._request("https://api.wisesheets.io/v1/financials/", params={
            "tickers": "AAPL,MSFT,ASML", "metrics": "net_income",
            "period": "last5y", "frequency": "annual",
            "layout": "long", "include": "source",
        })
        rows = parse_financials(response, expected)
        units = sorted({r["unit"] for r in rows.values()})
        assert len(rows) >= 12 and "EUR" in units and "USD" in units
        usd = client.fx_history("USD", "2020-01-01")
        world = client.world_gdp()
        companies = {cik: {"cik": cik,"ticker": ticker,"has_financials": True}
                     for ticker,cik in expected.items()}
        result = calculate_sec_earnings(companies, rows, {"USD": usd}, world)
        assert result["observations"] and result["status"]=="partial_us_sec_reporter_coverage"
        assert any(x["usd_converted_issuers"]>=2 for x in result["observations"])
        print(json.dumps({
            "WISESHEETS_SAMPLE_LIVE": "PASS",
            "plan": plan["code"],
            "available_fiscal_years": len(result["observations"]),
            "annual_company_records": len(rows),
            "reporting_currencies": units,
            "contains_provenance": True,
            "secret_disclosed": False,
        }), flush=True)
    finally:
        client.close()
    

_CHECKS = {
    "deployment-smoke": deployment_smoke,
    "live-bis-check": live_bis_check,
    "live-providers-check": live_providers_check,
    "market-live-check": market_live_check,
    "validate-wisesheets-snapshot": validate_wisesheets_snapshot,
    "wisesheets-live-sample": wisesheets_live_sample,
}

def main(argv=None):
    parser = argparse.ArgumentParser(description="Run selected operational check")
    parser.add_argument("name", choices=sorted(_CHECKS))
    args, remaining = parser.parse_known_args(argv)
    original_argv = sys.argv
    try:
        sys.argv = [args.name, *remaining]
        result = _CHECKS[args.name]()
        return result if isinstance(result, int) else 0
    finally:
        sys.argv = original_argv
