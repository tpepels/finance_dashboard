"""On-demand, publisher-governed source investigations.

No diagnostic performs requests at module import time. These operations are
explicitly selected through the single application CLI.
"""
from __future__ import annotations
import argparse

def phase2_gap_discovery():
    """Bounded source feasibility for remaining global indicators.
    
    Discovery only. This script does not ingest data into the catalog or reproduce
    licensed vendor datasets in CI logs.
    """
    import httpx
    from finance_dashboard.source_policy import managed_client, managed_get
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
    with managed_client(timeout=9, follow_redirects=False) as client:
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
    

def probe_bea_msci():
    """Bounded direct evidence for BEA Q1 and MSCI ACWI net total return."""
    from datetime import date
    import json
    import httpx
    from finance_dashboard.source_policy import managed_client, managed_get
    from html.parser import HTMLParser
    
    class Tables(HTMLParser):
        def __init__(self):
            super().__init__()
            self.tables=[];self.table=None;self.row=None;self.cell=None
        def handle_starttag(self,tag,attrs):
            if tag=="table": self.table=[]
            elif tag=="tr" and self.table is not None:self.row=[]
            elif tag in ("td","th") and self.row is not None:self.cell=[]
        def handle_data(self,data):
            if self.cell is not None:self.cell.append(data)
        def handle_endtag(self,tag):
            if tag in ("td","th") and self.cell is not None:
                self.row.append("".join(self.cell).strip());self.cell=None
            elif tag=="tr" and self.row is not None:
                self.table.append(self.row);self.row=None
            elif tag=="table" and self.table is not None:
                self.tables.append(self.table);self.table=None
    
    with managed_client(timeout=12,follow_redirects=True) as client:
        url="https://apps.bea.gov/scb/issues/2026/05-may/0526-domestic-returns.htm"
        try:
            response=client.get(url)
            parser=Tables();parser.feed(response.text)
            print(json.dumps({"source":"bea","status":response.status_code,"tables":len(parser.tables),
                "candidates":[{"table_number":i,"rows":len(t),"head":t[:2],"tail":t[-2:]}
                              for i,t in enumerate(parser.tables) if any(len(row)>=4 and row[0]=="1960" for row in t)][:3]}),flush=True)
        except Exception as exc:print(json.dumps({"source":"bea","error":type(exc).__name__}),flush=True)
        url="https://app2.msci.com/products/service/index/indexmaster/getLevelDataForGraph"
        for code in ("891800","892400"):
            try:
                r=client.get(url,params={"index_codes":code,"currency_symbol":"USD","index_variant":"NETR",
                    "data_frequency":"DAILY","start_date":"20260101","end_date":"20260401"},
                    headers={"User-Agent":"Mozilla/5.0","Referer":"https://www.msci.com/","Accept":"application/json"})
                obj=r.json() if r.status_code==200 else {}
                rows=(obj.get("indexes") or {}).get("INDEX_LEVELS") or []
                print(json.dumps({"source":"msci","index":code,"status":r.status_code,
                    "root_keys":list(obj),"currency":obj.get("ISO_currency_symbol"),"variant":obj.get("index_variant_type"),"source_index":obj.get("msci_index_code"),"count":len(rows),
                    "first":rows[:1],"last":rows[-1:]}),flush=True)
            except Exception as exc:print(json.dumps({"source":"msci","index":code,"error":type(exc).__name__}),flush=True)
    

def probe_fred_public():
    """Bounded probe of FRED's public observations tables, no API key."""
    import json
    import re
    import httpx
    from finance_dashboard.source_policy import managed_client, managed_get
    for sid in ("DFEDTARU","DFII10","SAHMREALTIME","NCBCEPNW"):
        for suffix in ("", ".txt"):
            url=f"https://fred.stlouisfed.org/data/{sid}{suffix}"
            try:
                r=managed_get(url,timeout=12,follow_redirects=True)
                text=r.text
                print(json.dumps({
                    "series":sid,"suffix":suffix,"status":r.status_code,
                    "bytes":len(r.content),
                    "content_type":r.headers.get("content-type"),
                    "has_header":"DATE" in text and "VALUE" in text,
                    "date_count":text.count("2026-"),
                    "snippet":text[:80].replace("\n"," "),
                    "final_url":str(r.url),
                    "date_last_pos":text.find("2026-10-29"),
                    "end_context":text[max(0,text.find("2026-10-29")-120):text.find("2026-10-29")+130].replace("\n"," ") if text.find("2026-10-29")>=0 else "",
                    "html_row_count":text.count("<tr"),
                    "text_row_count":text.count("2026-"),
                    "pipe_rows":len(re.findall(r"#\\d{4}-\\d{2}-\\d{2}\\|",text)),
                    "pipe_first":re.findall(r"#\\d{4}-\\d{2}-\\d{2}\\|\\s*[-.0-9]+",text)[:2],
                    "pipe_last":re.findall(r"#\\d{4}-\\d{2}-\\d{2}\\|\\s*[-.0-9]+",text)[-2:],
                    "pre_count":text.count("<pre"),
                    "near_2025":text[max(0,text.find("2025-10-01")-90):text.find("2025-10-01")+120].replace("\n"," ") if text.find("2025-10-01")>=0 else "",
                    "pipe_origin":text[max(0,text.find("#2006-")-200):text.find("#2006-")+90].replace("\n"," ") if text.find("#2006-")>=0 else ""
                }),flush=True)
            except Exception as exc:
                print(json.dumps({"series":sid,"suffix":suffix,"error":type(exc).__name__}),flush=True)
    

def probe_market_feeds():
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
    

def probe_msci_profile():
    from finance_dashboard.source_policy import managed_get
    """Probe MSCI ACWI official web page for dated weight and financial statistics."""
    import httpx,json,re
    urls=[
     "https://www.msci.com/indexes/index/892400/msci-acwi-index",
     "https://www.msci.com/indexes/index/892400/msci-acwi-index?outputType=chromeless"
    ]
    for url in urls:
     try:
        r=managed_get(url,timeout=18,follow_redirects=True,
                    headers={"User-Agent":"Mozilla/5.0","Accept":"text/html"})
        html=r.text
        keys=["Top 10 constituents","NVIDIA","Index Market Cap","P/E","Data as of","MSCI ACWI Index"]
        sample={}
        for key in keys:
            idx=html.find(key)
            sample[key]={"found":idx>=0,"context":re.sub("<[^>]+>"," ",html[max(0,idx-140):idx+300]).replace("\n"," ")[:440] if idx>=0 else ""}
        print(json.dumps({"url":url,"status":r.status_code,"length":len(html),
            "content_type":r.headers.get("content-type"),"samples":sample}),flush=True)
     except Exception as ex:print(json.dumps({"url":url,"error":type(ex).__name__}),flush=True)
    

def probe_pink_sheet():
    from finance_dashboard.source_policy import managed_get
    """Discover official World Bank Pink Sheet monthly workbook structure (bounded)."""
    from io import BytesIO
    import httpx
    from python_calamine import CalamineWorkbook
    
    URL="https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx"
    r=managed_get(URL,timeout=20,follow_redirects=True)
    print("status",r.status_code,"size",len(r.content),"content_type",r.headers.get("content-type"),flush=True)
    r.raise_for_status()
    wb=CalamineWorkbook.from_filelike(BytesIO(r.content))
    print("sheets",wb.sheet_names,flush=True)
    for name in wb.sheet_names:
        if "month" in name.lower() or "price" in name.lower():
            rows=wb.get_sheet_by_name(name).to_python()
            print("header sheets",name,"row_count",len(rows),flush=True)
            for col,name in enumerate(rows[4]):
                if "gold" in str(name).lower():
                    print("GOLD_COLUMN",col,"header",repr(name),"unit",repr(rows[5][col]),"example",repr(rows[-1][col]),flush=True)
            for i in list(range(min(8,len(rows)))) + list(range(max(8,len(rows)-2),len(rows))):
                row=rows[i]
                print("ROW",i,repr(row[:22]),flush=True)
    

def probe_wisesheets():
    """Bounded live verification of the Wisesheets key and historical fundamentals.
    
    No API tokens, company earnings or individual account information are logged.
    Personal plan/quota flags and structural field names are sufficient to design
    an authenticated ingestion adapter.
    """
    import json
    import os
    import sys
    import httpx
    from finance_dashboard.source_policy import managed_client, managed_get
    
    KEY = os.environ.get("WISESHEETS_API_KEY")
    if not KEY:
        print("WISESHEETS_PROBE=FAIL missing Actions secret", flush=True)
        raise SystemExit(2)
    
    ROOT = "https://api.wisesheets.io/v1"
    HEADERS = {"Authorization": "Bearer " + KEY, "Accept": "application/json"}
    requests = [
        ("me", "/me/", {}),
        ("metrics", "/metrics/", {}),
        ("us_company", "/companies/AAPL", {}),
        ("foreign_company", "/companies/ASML", {}),
        ("history", "/financials/", {
            "tickers": "AAPL,MSFT,ASML", "metrics": "net_income",
            "period": "last5y", "frequency": "annual", "layout": "long", "include": "source",
        }),
        ("universe", "/companies/", {"limit": 2}),
    ]
    with managed_client(timeout=15, follow_redirects=False, headers=HEADERS) as client:
        for label, path, params in requests:
            try:
                r = client.get(ROOT + path, params=params)
                status = {"request": label, "status": r.status_code}
                if r.status_code == 200:
                    payload = r.json()
                    status["root_keys"] = sorted(payload) if isinstance(payload, dict) else None
                    if isinstance(payload, dict):
                        data = payload.get("data")
                        status["data_type"] = type(data).__name__
                        if isinstance(data, list):
                            status["count"] = len(data)
                            status["row_fields"] = sorted(data[0]) if data and isinstance(data[0], dict) else []
                            status["first_row_format"] = {
                                k: (type(v).__name__ if not isinstance(v, dict) else sorted(v))
                                for k, v in (data[0] if data and isinstance(data[0], dict) else {}).items()
                            }
                            if label == "history":
                                status["identities"] = sorted(set(str(x.get("ticker")) for x in data))
                                status["periods"] = sorted(set(str(x.get("period")) for x in data))
                                status["units_by_ticker"] = {str(t): sorted(set(str(x.get("unit")) for x in data if str(x.get("ticker"))==t)) for t in status["identities"]}
                                status["fiscal_period_examples"] = sorted(set(str(x.get("fiscalPeriod")) for x in data))
                                status["period_end_examples"] = sorted(set(str(x.get("periodEnd")) for x in data))
                                status["filing_kinds"] = sorted(set(str((x.get("source") or {}).get("kind")) for x in data))
                        elif isinstance(data, dict):
                            status["data_fields"] = sorted(data)
                            if label in ("us_company", "foreign_company"):
                                status["ticker"] = data.get("ticker")
                                status["exchange"] = data.get("exchange")
                        meta = payload.get("meta")
                        status["meta_fields"] = sorted(meta) if isinstance(meta, dict) else []
                        if label == "me":
                            status["account_plan_fields"] = sorted(k for k in payload if k not in ("key", "token", "apiKey"))
                            plan = payload.get("plan") or {}
                            status["plan_code"] = plan.get("planCode")
                            status["plan_features"] = sorted(plan.get("features", [])) if isinstance(plan.get("features"), list) else list(plan.get("features", {}))
                            status["plan_limits"] = {str(k):v for k,v in (plan.get("limits") or {}).items() if isinstance(v,(int,float,str,bool))} if isinstance(plan.get("limits"),dict) else {}
                            for obj in (payload, data, meta):
                                if isinstance(obj, dict):
                                    for k in ("plan", "tier", "features", "limits"):
                                        if k in obj:
                                            v = obj[k]
                                            status[k] = (sorted(v) if isinstance(v, dict) else v)
                    if label == "metrics" and isinstance(data, list):
                        status["net_income_available"] = any(
                            "net_income" in str(item).lower() for item in data
                        )
                print(json.dumps(status, sort_keys=True, default=str), flush=True)
            except Exception as exc:
                print(json.dumps({"request": label, "error_type": type(exc).__name__}), flush=True)
            # Do not throw raw HTTP errors: those could include sensitive request headers.
    

def probe_world_credit_gap():
    """Probe real official coverage of a GDP-weighted BIS-coverage gap composite."""
    from datetime import date
    import json
    import httpx
    from finance_dashboard.source_policy import managed_client, managed_get
    
    with managed_client(timeout=22,follow_redirects=True) as client:
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
    
    # Reconcile BIS actual economy list to World Bank GDP country IDs
    bis_codes=["PL","BR","GB","MX","ZA","CN","SA","US","HU","JP","LU","RU","CL","HK","IT","NL","CZ","SG","ES","IE","AU","XM","MY","AR","SE","CO","TR","DK","ID","IN","NZ","CA","AT","FR","NO","DE","TH","FI","IL","BE","KR","PT","CH","GR"]
    with managed_client(timeout=18) as client:
        wb=client.get("https://api.worldbank.org/v2/country/all/indicator/NY.GDP.MKTP.CD",
            params={"format":"json","per_page":1000,"date":"2024:2025"}).json()[1]
        records={(row["country"]["id"],int(row["date"])):row["value"] for row in wb}
        for year in (2024,2025):
            world=next(row["value"] for row in wb if row["countryiso3code"]=="WLD" and int(row["date"])==year)
            included={code:records.get((code,year)) for code in bis_codes if code!="XM"}
            total=sum(v for v in included.values() if v is not None)
            print(json.dumps({"source":"bis_wdi_coverage","year":year,"world_gdp_usd":world,
                "covered_gdp_percent":round(100*total/world,2),
                "countries_with_gdp":sum(v is not None for v in included.values()),
                "missing_countries":[k for k,v in included.items() if v is None]}),flush=True)
    

def source_discovery():
    from finance_dashboard.source_policy import managed_get
    """Bounded provider-protocol discovery, not production ingestion."""
    import json
    import httpx
    
    URLS = {
      "un_labour_areas": "https://unstats.un.org/SDGAPI/v1/sdg/Series/SL_EMP_GTOTL/GeoAreas",
      "un_labour_world": "https://unstats.un.org/SDGAPI/v1/sdg/Series/SL_EMP_GTOTL/GeoArea/1/DataSlice",
      "un_labour_china": "https://unstats.un.org/SDGAPI/v1/sdg/Series/SL_EMP_GTOTL/GeoArea/156/DataSlice",
      "un_world_productivity": "https://unstats.un.org/SDGAPI/v1/sdg/Series/SL_EMP_PCAP/GeoArea/1/DataSlice",
      "gold_spot_now": "https://goldprice.corgano.com/api/v1/latest",
      "ilo_country": "https://rplumber.ilo.org/data/indicator?id=SDG_1041_NOC_RT&ref_area=USA",
      "ilo_bulk_csv": "https://rplumber.ilo.org/files/indicator/SDG_1041_NOC_RT_A.csv.gz",
      "imf_mapper_debt": "https://www.imf.org/external/datamapper/api/v2/GGXWDG_NGDP",
      "un_labour_share": "https://unstats.un.org/SDGAPI/v1/sdg/Indicator/Data?indicator=10.4.1&areaCode=156&pageSize=2",
      "world_bank_small": "https://api.worldbank.org/v2/country/USA/indicator/NY.GDP.MKTP.KD.ZG?format=json&per_page=150",
    }
    for label,url in URLS.items():
        try:
            response=managed_get(url,timeout=10,follow_redirects=True)
            result={"source":label,"status":response.status_code,"type":response.headers.get("content-type"),"bytes":len(response.content)}
            if label=="imf_mapper_debt" and response.status_code==200:
                payload=response.json()
                result["top_keys"]=list(payload)
                for key in ("values","indicators","countries","groups"):
                    v=payload.get(key,{})
                    result[key+"_keys"]=list(v)[:15] if isinstance(v,dict) else []
                values=payload.get("values",{}).get("GGXWDG_NGDP",{})
                if isinstance(values,dict):
                    result["value_area_keys"]=list(values)[:12]
                    result["world_keys"]=[k for k in values if "WORLD" in k.upper()][:10]
            elif label == "un_world_productivity" and response.status_code == 200:
                payload=response.json()
                result["series"]=payload.get("series")
                result["geoAreaCode"]=payload.get("geoAreaCode")
                result["dims_sample"]=payload.get("dimensions",[])[:3]
            elif label == "gold_spot_now" and response.status_code == 200:
                payload=response.json()
                result["unit_value"]=payload.get("meta",{}).get("unit")
                result["spot_source"]=payload.get("meta",{}).get("source")
                result["root_keys"]=list(payload)[:25] if isinstance(payload,dict) else []
                result["schema"]={key: (list(value)[:12] if isinstance(value,dict) else type(value).__name__) for key,value in payload.items()} if isinstance(payload,dict) else {}
            elif label=="world_bank_small" and response.status_code==200:
                payload=response.json()
                result["pages"]=payload[0].get("pages") if isinstance(payload,list) else None
            else:
                result["sample"]=response.text[:160].replace("\n"," ")
            print(json.dumps(result),flush=True)
        except Exception as e:
            print(json.dumps({"source":label,"error":type(e).__name__}),flush=True)
    

_DIAGNOSTICS = {
    "phase2-gap-discovery": phase2_gap_discovery,
    "probe-bea-msci": probe_bea_msci,
    "probe-fred-public": probe_fred_public,
    "probe-market-feeds": probe_market_feeds,
    "probe-msci-profile": probe_msci_profile,
    "probe-pink-sheet": probe_pink_sheet,
    "probe-wisesheets": probe_wisesheets,
    "probe-world-credit-gap": probe_world_credit_gap,
    "source-discovery": source_discovery,
}

def main(argv=None):
    parser = argparse.ArgumentParser(description="Run an explicit source discovery probe")
    parser.add_argument("name", choices=sorted(_DIAGNOSTICS))
    args = parser.parse_args(argv)
    result = _DIAGNOSTICS[args.name]()
    return result if isinstance(result, int) else 0
