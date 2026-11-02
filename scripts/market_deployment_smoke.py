"""Acceptance against actual Docker/PG worker and API, never mocked observations."""
from __future__ import annotations

from datetime import date
import json
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import URLError

API="http://127.0.0.1:8080"


def get(path):
    with urlopen(API+path,timeout=8) as response:
        return json.load(response)


def query(ids,start=None,end=None):
    payload={"instrument_ids":ids}
    if start: payload["start"]=start
    if end: payload["end"]=end
    request=Request(API+"/api/market/query",data=json.dumps(payload).encode(),
        headers={"Content-Type":"application/json"},method="POST")
    with urlopen(request,timeout=30) as response:
        return json.load(response)["series"]


def main():
    for n in range(20):
        try:
            if get("/api/health")["status"]=="ok":
                break
        except (URLError,KeyError):
            time.sleep(1)
    else:
        raise AssertionError("Docker app did not become healthy")
    registry=get("/api/markets")
    assert registry["count"]==24,registry["count"]
    info=get("/api/market/status")
    statuses={x["id"]:x for x in info["instruments"]}
    assert len(statuses)==24
    for sid,row in statuses.items():
        assert row["status"]=="success",(sid,row)
        assert row["received"]>1,(sid,row)
        assert row["last_success"],(sid,row)
    for fx in info["fx"]:
        assert fx["status"]=="success" and fx["received"]>100,(fx)
    eur_us=query(["vwce.de","vt"],start="2025-01-01")
    assert len(eur_us)==2
    for item in eur_us:
        assert item["status"]=="ready" and len(item["observations"])>100
        assert item["observations"][0]["adjusted_close_eur"] is not None
        assert item["observations"][0]["eur_adjusted_index"] is not None
        assert item["source_url"].startswith("https://")
        assert item["currency"] in ("EUR","USD")
    vwr=query(["vwrl.as"],start="2025-01-01")[0]
    assert vwr["dividend_events"]>0,"Distributing Vanguard share class missing dividends"
    assert any(x["type"]=="dividend" for x in vwr["corporate_actions"])
    nvda=query(["nvda"],start="2001-09-01",end="2001-10-01")[0]
    assert any(x["ex_date"]=="2001-09-12" and x["type"]=="split"
               for x in nvda["corporate_actions"]),"2001 exchange closure split lost"
    p=get("/api/market/gold-world-proxy?currency=EUR&window_months=36")
    assert p["status"]=="proxy_not_global_index",p
    assert len(p["observations"])>50,p
    assert all(-1<=x["correlation"]<=1 for x in p["observations"] if x["correlation"] is not None)
    print(json.dumps({"verified_instruments":len(statuses),
        "fx_currencies":len(info["fx"]),
        "eur_rows":[len(x["observations"]) for x in eur_us],
        "vanguard_dividends":vwr["dividend_events"],
        "nvda_split_2001":True,
        "gold_vt_rolling_correlation_months":len(p["observations"])}))
    print("MARKET_POSTGRES_LIVE_ACCEPTANCE=PASS")


if __name__=="__main__":
    try:
        main()
    except Exception as exc:
        print(f"MARKET_POSTGRES_LIVE_ACCEPTANCE=FAIL ({type(exc).__name__}: {str(exc)[:250]})",file=sys.stderr)
        raise
