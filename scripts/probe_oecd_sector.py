"""One-off OECD public SDMX contract probe; non-secret, bounded network calls."""
import urllib.request
import xml.etree.ElementTree as ET
from urllib.error import HTTPError,URLError

base="https://sdmx.oecd.org/public/rest/"
for flow in ["DSD_NASEC1@DF_QSA_TRANSACTIONS_C","DSD_NASEC1@DF_QSA"]:
  url=f"{base}dataflow/OECD.SDD.NAD/{flow}/1.1?references=all"
  print("FLOW",flow,flush=True)
  try:
    req=urllib.request.Request(url,headers={"Accept":"application/vnd.sdmx.structure+xml;version=3.0","User-Agent":"CapitalMonitor/1.0 contact: repository"})
    with urllib.request.urlopen(req,timeout=18) as r:
      body=r.read(1800000)
      print("STRUCTURE",r.status,len(body),body[:120],flush=True)
    root=ET.fromstring(body)
    for struct in root.iter():
      if struct.tag.endswith("DataStructure"):
        for el in struct.iter():
          if el.tag.endswith("Dimension") or el.tag.endswith("TimeDimension"):
            print("DIM",el.attrib.get("id"),el.attrib.get("position"),flush=True)
  except Exception as exc:
    print("FLOW_ERROR",type(exc).__name__,str(exc)[:220],flush=True)
for dataset in ["DSD_NASEC1@DF_QSA_TRANSACTIONS_C","DSD_NASEC1@DF_QSA"]:
  for key in ["A..OECD..........","A.OECD..........."]:
    url=f"{base}v1/data/OECD.SDD.NAD,{dataset},1.1/{key}?startPeriod=2023&endPeriod=2023"
    req=urllib.request.Request(url,headers={"Accept":"csvfile","User-Agent":"CapitalMonitor/1.0"})
    try:
      with urllib.request.urlopen(req,timeout=12) as resp:
        print("DATA",dataset,key,resp.status,resp.read(1400)[:1400],flush=True)
    except Exception as exc:
      print("DATA_ERROR",dataset,key,type(exc).__name__,str(exc)[:190],flush=True)

# Eurostat fallback: official ESA2010 institutional sector annual series.
for geo in ["EA20","EU27_2020"]:
 for sector,na_item in [("S11","B2G"),("S12","B2G"),("S1","B1GQ"),("S11","B2G_B3G")]:
  from urllib.parse import urlencode
  url="https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/nasa_10_nf_tr?"+urlencode({"geo":geo,"sector":sector,"na_item":na_item,"unit":"CP_MEUR","sinceTimePeriod":"2020"})
  try:
    req=urllib.request.Request(url,headers={"User-Agent":"CapitalMonitor/1.0"})
    with urllib.request.urlopen(req,timeout=8) as response:
      b=response.read(1400)
      print("EUROSTAT",geo,sector,na_item,response.status,b[:600],flush=True)
  except Exception as exc:
    print("EUROSTAT_ERROR",geo,sector,na_item,type(exc).__name__,str(exc)[:140],flush=True)

# Inspect available ESA accounts / direct official corporate-profit indicator.
import json
for name, query in [
  ("nasa_10_nf_tr",{"geo":"EU27_2020","sector":"S11","unit":"CP_MEUR","sinceTimePeriod":"2024"}),
  ("nasa_10_ki",{"geo":"EU27_2020","sector":"S11","unit":"PC","sinceTimePeriod":"2023"}),
]:
 from urllib.parse import urlencode
 url="https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"+name+"?"+urlencode(query)
 try:
  req=urllib.request.Request(url,headers={"User-Agent":"CapitalMonitor/1.0"})
  with urllib.request.urlopen(req,timeout=10) as response:
   obj=json.loads(response.read(2000000))
  print("EU_META",name,"size",obj.get("size"),"dims",obj.get("id"),"value_count",len(obj.get("value",{})),flush=True)
  for dim,meta in obj.get("dimension",{}).items():
   if dim in ("na_item","direct","geo","sector","unit"): print("EU_DIM",name,dim,meta["category"].get("index"),str(meta["category"].get("label"))[:1600],flush=True)
  print("EU_VAL",name,list(obj.get("value",{}).items())[:20],flush=True)
 except Exception as exc:
  print("EU_META_ERROR",name,type(exc).__name__,str(exc)[:240],flush=True)
