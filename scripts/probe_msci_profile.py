"""Probe MSCI ACWI official web page for dated weight and financial statistics."""
import httpx,json,re
urls=[
 "https://www.msci.com/indexes/index/892400/msci-acwi-index",
 "https://www.msci.com/indexes/index/892400/msci-acwi-index?outputType=chromeless"
]
for url in urls:
 try:
    r=httpx.get(url,timeout=18,follow_redirects=True,
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
