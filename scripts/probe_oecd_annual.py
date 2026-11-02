"""Temporary live availability probe, intentionally bounded; no dataset publication."""
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

# Check exact annual numerator/GDP series identity, OECD group and country coverage.
checks=[
("AUS_NFC","A.AUS.S11.S1.D.B2G._Z._Z.XDC.S.V.N.T0800"),
("AUS_FC","A.AUS.S12.S1.D.B2G._Z._Z.XDC.S.V.N.T0800"),
("AUS_GDP","A.AUS.S1.S1.D.B1GQ._Z._Z.XDC.S.V.N.T0800"),
("AUS_GVA","A.AUS.S1.S1.D.B1G._Z._Z.XDC.S.V.N.T0800"),
("AUS_GDP_C","A.AUS.S1.S1.C.B1GQ._Z._Z.XDC.S.V.N.T0800"),
("OECD_NFC","A.OECD.S11.S1.D.B2G._Z._Z.XDC.S.V.N.T0800"),
("OECD_GDP","A.OECD.S1.S1.D.B1GQ._Z._Z.XDC.S.V.N.T0800"),
]
for tag,key in checks:
 url=f"https://sdmx.oecd.org/public/rest/data/OECD.SDD.NAD,DSD_NASEC10@DF_TABLE14,1.1/{key}?startPeriod=2022&endPeriod=2023&format=csvfile"
 try:
  req=Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"*/*"})
  with urlopen(req,timeout=9) as rs:
   body=rs.read(1200).decode("utf-8","replace")
   rows=body.splitlines()
   print("CHECK",tag,rs.status,len(rows),rows[1:3],flush=True)
 except Exception as e: print("CHECK_ERROR",tag,type(e).__name__,str(e)[:150],flush=True)

# Verify same-source OECD GDP identity using S1 GVA + product taxes, while checking
# a single 3-year sample for complete country/sector transaction coverage.
from io import StringIO
import csv
countries="AUS AUT BEL CAN CHL COL CRI CZE DNK EST FIN FRA DEU GRC HUN ISL IRL ISR ITA JPN KOR LVA LTU LUX MEX NLD NZL NOR POL PRT SVK SVN ESP SWE CHE TUR GBR USA".split()
key="A."+"+".join(countries)+".S11+S12+S1.S1.C+D.B2G+B1G+D21X31._Z._Z.XDC.S.V.N.T0800"
url="https://sdmx.oecd.org/public/rest/data/OECD.SDD.NAD,DSD_NASEC10@DF_TABLE14,1.1/"+key+"?startPeriod=2021&endPeriod=2023&format=csvfile"
try:
 req=Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"*/*"})
 with urlopen(req,timeout=25) as resp:
  content=resp.read(6000000).decode("utf-8","replace")
 rows=list(csv.DictReader(StringIO(content)))
 from collections import Counter
 print("BULK",resp.status,"bytes",len(content),"rows",len(rows),"countries",len(set(x["REF_AREA"] for x in rows)),flush=True)
 print("BULK_TUPLES",Counter((x["SECTOR"],x["ACCOUNTING_ENTRY"],x["TRANSACTION"]) for x in rows).most_common(24),flush=True)
 print("BULK_AUS",[(x["SECTOR"],x["ACCOUNTING_ENTRY"],x["TRANSACTION"],x["TIME_PERIOD"],x["OBS_VALUE"]) for x in rows if x["REF_AREA"]=="AUS" and x["TIME_PERIOD"]=="2023"][:40],flush=True)
 print("BULK_COUNTRIES",sorted(set(x["REF_AREA"] for x in rows)),flush=True)
except Exception as e:
 print("BULK_ERROR",type(e).__name__,str(e)[:260],flush=True)
