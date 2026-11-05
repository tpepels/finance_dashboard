"""Bounded live verification of the Wisesheets key and historical fundamentals.

No API tokens, company earnings or individual account information are logged.
Personal plan/quota flags and structural field names are sufficient to design
an authenticated ingestion adapter.
"""
from __future__ import annotations
import json
import os
import sys
import httpx
from finance_dashboard.source_policy import managed_client, managed_get

KEY = os.environ.get("WISESHEETS_API_KEY")
if not KEY:
    print("WISESHEETS_PROBE=FAIL missing Actions secret", flush=True)
    raise SystemExit(2)

ROOT = "https://api.wisesheets.io/v1"
HEADERS = {"Authorization": "Bearer " + KEY, "Accept": "application/json"}
requests = [
    ("me", "/me/", {}),
    ("metrics", "/metrics/", {}),
    ("us_company", "/companies/AAPL", {}),
    ("foreign_company", "/companies/ASML", {}),
    ("history", "/financials/", {
        "tickers": "AAPL,MSFT,ASML", "metrics": "net_income",
        "period": "last5y", "frequency": "annual", "layout": "long", "include": "source",
    }),
    ("universe", "/companies/", {"limit": 2}),
]
with managed_client(timeout=15, follow_redirects=False, headers=HEADERS) as client:
    for label, path, params in requests:
        try:
            r = client.get(ROOT + path, params=params)
            status = {"request": label, "status": r.status_code}
            if r.status_code == 200:
                payload = r.json()
                status["root_keys"] = sorted(payload) if isinstance(payload, dict) else None
                if isinstance(payload, dict):
                    data = payload.get("data")
                    status["data_type"] = type(data).__name__
                    if isinstance(data, list):
                        status["count"] = len(data)
                        status["row_fields"] = sorted(data[0]) if data and isinstance(data[0], dict) else []
                        status["first_row_format"] = {
                            k: (type(v).__name__ if not isinstance(v, dict) else sorted(v))
                            for k, v in (data[0] if data and isinstance(data[0], dict) else {}).items()
                        }
                        if label == "history":
                            status["identities"] = sorted(set(str(x.get("ticker")) for x in data))
                            status["periods"] = sorted(set(str(x.get("period")) for x in data))
                            status["units_by_ticker"] = {str(t): sorted(set(str(x.get("unit")) for x in data if str(x.get("ticker"))==t)) for t in status["identities"]}
                            status["fiscal_period_examples"] = sorted(set(str(x.get("fiscalPeriod")) for x in data))
                            status["period_end_examples"] = sorted(set(str(x.get("periodEnd")) for x in data))
                            status["filing_kinds"] = sorted(set(str((x.get("source") or {}).get("kind")) for x in data))
                    elif isinstance(data, dict):
                        status["data_fields"] = sorted(data)
                        if label in ("us_company", "foreign_company"):
                            status["ticker"] = data.get("ticker")
                            status["exchange"] = data.get("exchange")
                    meta = payload.get("meta")
                    status["meta_fields"] = sorted(meta) if isinstance(meta, dict) else []
                    if label == "me":
                        status["account_plan_fields"] = sorted(k for k in payload if k not in ("key", "token", "apiKey"))
                        plan = payload.get("plan") or {}
                        status["plan_code"] = plan.get("planCode")
                        status["plan_features"] = sorted(plan.get("features", [])) if isinstance(plan.get("features"), list) else list(plan.get("features", {}))
                        status["plan_limits"] = {str(k):v for k,v in (plan.get("limits") or {}).items() if isinstance(v,(int,float,str,bool))} if isinstance(plan.get("limits"),dict) else {}
                        for obj in (payload, data, meta):
                            if isinstance(obj, dict):
                                for k in ("plan", "tier", "features", "limits"):
                                    if k in obj:
                                        v = obj[k]
                                        status[k] = (sorted(v) if isinstance(v, dict) else v)
                if label == "metrics" and isinstance(data, list):
                    status["net_income_available"] = any(
                        "net_income" in str(item).lower() for item in data
                    )
            print(json.dumps(status, sort_keys=True, default=str), flush=True)
        except Exception as exc:
            print(json.dumps({"request": label, "error_type": type(exc).__name__}), flush=True)
        # Do not throw raw HTTP errors: those could include sensitive request headers.
