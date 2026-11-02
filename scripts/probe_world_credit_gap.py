"""Probe real official coverage of a GDP-weighted BIS-coverage gap composite."""
from datetime import date
import json
import httpx

with httpx.Client(timeout=22,follow_redirects=True) as client:
    url="https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CREDIT_GAP/1.0/Q..P.A.C"
    try:
        response=client.get(url,params={"startPeriod":"2025-Q1"},
            headers={"Accept":"application/vnd.sdmx.data+json;version=1.0.0"})
        payload=response.json()
        data=payload.get("data",{})
        series=data.get("dataSets",[{}])[0].get("series",{})
        dims=data.get("structure",{}).get("dimensions",{}).get("series",[])
        area=next((d for d in dims if d.get("id")=="BORROWERS_CTY"),{})
        print(json.dumps({"source":"bis_world_gap","status":response.status_code,
            "bytes":len(response.content),"series":len(series),
            "area_codes":[v.get("id") for v in area.get("values",[])],
            "series_keys":list(series)[:4],
            "dim_ids":[d.get("id") for d in dims]}),flush=True)
    except Exception as exc:
        print(json.dumps({"source":"bis_world_gap","error":type(exc).__name__}),flush=True)
    for path in ("country/all/indicator/NY.GDP.MKTP.CD?format=json&per_page=1000&date=2024:2025",
                 "country?format=json&per_page=400"):
        url="https://api.worldbank.org/v2/"+path
        try:
            r=client.get(url)
            data=r.json()
            print(json.dumps({"source":"worldbank","url_path":path.split("?")[0],
                "status":r.status_code,"meta":data[0] if isinstance(data,list) else None,
                "sample":data[1][:2] if isinstance(data,list) else None}),flush=True)
        except Exception as exc:
            print(json.dumps({"source":"worldbank","error":type(exc).__name__}),flush=True)
