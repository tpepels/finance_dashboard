"""Verify actual Wisesheets AAPL/ASML/MSFT annual earnings and ECB conversion.

Uses the GitHub Actions WISESHEETS_API_KEY secret; prints no earnings,
account metadata, credentials or authenticated URLs.
"""
from __future__ import annotations
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
