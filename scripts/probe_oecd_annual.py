"""Temporary live availability probe, intentionally bounded and never publishes datasets."""
from urllib.request import urlopen,Request
from urllib.error import HTTPError
from urllib.parse import quote
import json
urls=[
"https://sdmx.oecd.org/public/rest/data/OECD.SDD.NAD,DSD_NASEC10@DF_TABLE14,1.1/A.AUS.S11...._Z....V..?startPeriod=2022&endPeriod=2023&format=csvfile",
"https://sdmx.oecd.org/public/rest/data/OECD.SDD.NAD,DSD_NASEC10@DF_TABLE14_EXP,1.1/A.AUS.S11...._Z....V..?startPeriod=2022&endPeriod=2023&format=csvfile",
"https://sdmx.oecd.org/public/rest/dataflow/OECD.SDD.NAD/DSD_NASEC10@DF_TABLE14/1.1?references=all",
"https://api.db.nomics.world/v22/series/OECD/DSD_NASEC10%40DF_TABLE14_EXP/A.AUS.S1.S1.D.B2G._Z._Z.XDC.S.V.N.T0800?observations=1",
"https://api.db.nomics.world/v22/series/OECD/DSD_NASEC10%40DF_TABLE14_EXP/A.AUS.S11.S11.D.B2A3G._Z._Z.XDC.S.V.N.T0800?observations=1",
"https://api.db.nomics.world/v22/series/OECD/DSD_NASEC10%40DF_TABLE14_REV/A.AUS.S11.S11.D.B2A3G._Z._Z.XDC.S.V.N.T0800?observations=1",
"https://api.db.nomics.world/v22/series/OECD/DSD_NASEC10%40DF_TABLE14_EXP?limit=1",
]
for u in urls:
 try:
  req=Request(u,headers={"User-Agent":"Mozilla/5.0 (compatible; EconomicDataMonitor/1.0)","Accept":"*/*"})
  with urlopen(req,timeout=9) as r:
   data=r.read(1400)
   print(json.dumps({"url":u,"status":r.status,"type":r.headers.get("content-type"),"body":data.decode("utf-8","replace")[:900]}),flush=True)
 except Exception as e:
  print(json.dumps({"url":u,"error":type(e).__name__,"detail":str(e)[:120]}),flush=True)
