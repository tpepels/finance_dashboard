"""Bounded source discovery: never commits data, symbols or token secrets."""
import httpx
from finance_dashboard.source_policy import managed_client, managed_get
import json

for symbol in ["VWCE.DE","VWRL.AS","IS3N.DE","SXR8.DE","VT","SPY","AAPL","GLD","ASML.AS"]:
    try:
        url=f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        with managed_client(timeout=9) as client:
            r=client.get(url,params={"range":"1mo","interval":"1d","events":"div,splits"},
                         headers={"User-Agent":"Mozilla/5.0 (compatible; MarketDataValidation/1.0)"})
        status={"symbol":symbol,"status":r.status_code,"bytes":len(r.content)}
        if r.status_code==200:
            chart=r.json()["chart"]
            q=chart.get("result") or []
            if q:
                m=q[0].get("meta",{})
                status.update({"currency":m.get("currency"),"exchange":m.get("exchangeName"),"type":m.get("instrumentType"),"count":len(q[0].get("timestamp") or []),"adjusted":bool(q[0].get("indicators",{}).get("adjclose")),"events":sorted((q[0].get("events") or {}).keys())})
        print(json.dumps(status),flush=True)
    except Exception as exc:
        print(json.dumps({"symbol":symbol,"error":type(exc).__name__}),flush=True)
for currency in ("USD","GBP","CHF"):
    url=f"https://data-api.ecb.europa.eu/service/data/EXR/D.{currency}.EUR.SP00.A"
    try:
        r=managed_get(url,params={"format":"csvdata","lastNObservations":"5"},timeout=9)
        print(json.dumps({"fx":currency,"status":r.status_code,"bytes":len(r.content),"csv_header":r.text.splitlines()[0][:180] if r.status_code==200 else ""}),flush=True)
    except Exception as exc:
        print(json.dumps({"fx":currency,"error":type(exc).__name__}),flush=True)
