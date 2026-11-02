"""Bounded direct evidence for BEA Q1 and MSCI ACWI net total return."""
from datetime import date
import json
import httpx
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

with httpx.Client(timeout=12,follow_redirects=True) as client:
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
