"""Short real feed acceptance with explicit venue, split and dividend evidence."""
from finance_dashboard.market import instruments, YahooMarketClient, EcbFxClient
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import httpx

market=YahooMarketClient()
try:
    for key in ("nvda","vwce.de","vwrl.as","vt","gld"):
        item=instruments()[key]
        try:
            hist=market.fetch(item)
            print(json.dumps({"id":key,"bars":len(hist.price_bars),"dividends":len(hist.dividends),"splits":{k.isoformat():str(v) for k,v in hist.splits.items()},"currency":hist.currency}),flush=True)
        except Exception as exc:
            print(json.dumps({"id":key,"error":type(exc).__name__,"message":str(exc)[:400]}),flush=True)
            if key=="nvda":
                response=httpx.get("https://query1.finance.yahoo.com/v8/finance/chart/NVDA",
                    params={"interval":"1d","period1":0,"period2":9999999999,"events":"div,splits"},
                    timeout=15,headers={"User-Agent":"Mozilla/5.0"})
                if response.status_code==200:
                    item=response.json()["chart"]["result"][0]
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
