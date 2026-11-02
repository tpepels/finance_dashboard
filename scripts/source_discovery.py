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
        response=httpx.get(url,timeout=10,follow_redirects=True)
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
