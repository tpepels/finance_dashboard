"""Short real feed acceptance with explicit venue, split and dividend evidence."""
from finance_dashboard.market import instruments, YahooMarketClient, EcbFxClient
import json

market=YahooMarketClient()
try:
    for key in ("nvda","vwce.de","vwrl.as","vt","gld"):
        item=instruments()[key]
        try:
            hist=market.fetch(item)
            print(json.dumps({"id":key,"bars":len(hist.price_bars),"dividends":len(hist.dividends),"splits":{k.isoformat():str(v) for k,v in hist.splits.items()},"currency":hist.currency}),flush=True)
        except Exception as exc:
            print(json.dumps({"id":key,"error":type(exc).__name__,"message":str(exc)[:400]}),flush=True)
finally:
    market.close()
