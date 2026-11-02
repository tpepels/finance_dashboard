"""Bounded source feasibility for remaining global indicators.

Discovery only. This script does not ingest data into the catalog or reproduce
licensed vendor datasets in CI logs.
"""
from __future__ import annotations
import httpx
import json
from urllib.parse import urlparse

URLS = {
  "siblis_indices": "https://siblisresearch.supabase.co/functions/v1/free-data-api/v1/indices",
  "siblis_world_cape": "https://siblisresearch.supabase.co/functions/v1/free-data-api/v1/WORLD/cape",
  "siblis_acwi_cape": "https://siblisresearch.supabase.co/functions/v1/free-data-api/v1/ACWI/cape",
  "siblis_global_cape": "https://siblisresearch.supabase.co/functions/v1/free-data-api/v1/GLOBAL/cape",
  "bis_gap_dataflow": "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CREDIT_GAP/1.0",
  "bis_gaps_dataflow": "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CREDIT_GAPS/1.0",
  "bis_gap_jp": "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CREDIT_GAP/1.0/Q.JP",
  "bis_gap_ea": "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CREDIT_GAP/1.0/Q.XM",
  "bis_gap_us": "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CREDIT_GAP/1.0/Q.US",
  "bis_topic": "https://data.bis.org/topics/CREDIT_GAPS/data",
}
with httpx.Client(timeout=9, follow_redirects=False) as client:
    for name,url in URLS.items():
        try:
            r=client.get(url,headers={"Accept":"application/vnd.sdmx.data+json;version=1.0.0"} if name in ("bis_gap_us","bis_gap_jp","bis_gap_ea") else {})
            report={"source":name,"status":r.status_code,"type":r.headers.get("content-type"),"bytes":len(r.content)}
            if name=="siblis_indices" and r.status_code==200:
                j=r.json()
                report["tickers"]=[x.get("ticker") for x in j.get("indices",[])][:100]
            if name.startswith("siblis_") and name!="siblis_indices" and r.status_code==200:
                j=r.json()
                report["ticker"]=j.get("ticker")
                report["ratio"]=j.get("ratio")
                report["count"]=len(j.get("data",[]))
                report["dates"]=[x.get("trading_day (EOD)") for x in j.get("data",[])[:2]]
            if name in ("bis_gap_us","bis_gap_jp","bis_gap_ea") and r.status_code==200:
                j=r.json(); data=j.get("data",{}); structures=data.get("structures",data.get("structure",[]))
                report["data_keys"]=list(data)
                report["structure_type"]=type(structures).__name__
                if isinstance(structures,dict): structures=[structures]
                if structures:
                    dims=structures[0].get("dimensions",{})
                    report["series_dimensions"]=[(v.get("id"),len(v.get("values",[])), [(z.get("id"),z.get("name")) for z in v.get("values",[])[:8]]) for v in dims.get("series",[])]
                    report["obs_dimensions"]=[(v.get("id"), len(v.get("values",[]))) for v in dims.get("observation",[])]
                report["series_keys"]=[list(ds.get("series",{}))[:6] for ds in data.get("dataSets",[])]
                report["sample_values"]={k:list(v.get("observations",{}).items())[:1] for ds in data.get("dataSets",[]) for k,v in list(ds.get("series",{}).items())[:3]}
            if name.startswith("bis_") and r.status_code in (200,400,404):
                report["preview"]=r.text[:220].replace("\n"," ")
            print(json.dumps(report),flush=True)
        except Exception as e:
            print(json.dumps({"source":name,"error":type(e).__name__}),flush=True)
