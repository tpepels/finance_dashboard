"""Verify all mapped sources have persisted real observation versions."""
import json
import sys
from urllib.request import urlopen, Request
from urllib.error import URLError
from time import sleep

API="http://127.0.0.1:8080"


def get(path):
    with urlopen(API+path,timeout=12) as response:
        return json.load(response)


def query(ids):
    request=Request(API+"/api/query",data=json.dumps({"series_ids":ids}).encode(),
                    headers={"Content-Type":"application/json"},method="POST")
    with urlopen(request,timeout=40) as response:
        return json.load(response)


for attempt in range(15):
    try:
        if get("/api/health")["status"]=="ok":
            break
    except URLError:
        sleep(1)
else:
    raise RuntimeError("API did not become healthy")

catalog=get("/api/series")["items"]
mapped={row["id"] for row in catalog if row["status"]=="mapped"}
statuses={row["series_id"]:row for row in get("/api/data-status")["items"]}
if len(mapped)!=32 or len(catalog)!=34:
    raise AssertionError(f"Expected 32 mapped from 34, got {len(mapped)}/{len(catalog)}")
failures={sid:statuses.get(sid,{}).get("status") for sid in sorted(mapped)
          if statuses.get(sid,{}).get("status")!="success"
          or statuses.get(sid,{}).get("received",0)<1}
if failures:
    raise AssertionError(f"Mapped source ingestion incomplete: {failures}")
for sid in ("valuation.us.tobins_q","labour.world.productivity_compensation",
            "credit.world.private_gdp_gap","credit.world.private_gdp_gap_coverage",
            "gold.world.equity_correlation","equity.world.msci_acwi_netr_usd"):
    dataset=query([sid])["series"][0]
    if dataset["status"]!="ready" or not dataset["observations"]:
        raise AssertionError(f"Original newly mapped source not available through API: {sid}")
    print(json.dumps({"verified_exact_source":sid,
                      "count":len(dataset["observations"]),
                      "latest":dataset["observations"][-1]["date"]}),flush=True)
for sid in ("profit.global.corporate_share","concentration.global.top10"):
    if statuses[sid]["status"]!="source_unresolved":
        raise AssertionError(f"Unresolved source incorrectly presented as ready: {sid}")
print(f"PHASE2_ALL_MACRO_POSTGRES=PASS mapped={len(mapped)} unresolved=2",flush=True)
