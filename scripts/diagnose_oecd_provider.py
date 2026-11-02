"""Bounded no-secret end-to-end OECD provider diagnosis; remove after verification."""
import traceback
from finance_dashboard.providers import ProviderRouter
from finance_dashboard.oecd_corporate import OECD_DATA_URL, oecd_annual_data_key, parse_oecd_annual_sector_csv

r=ProviderRouter()
try:
    response=r._get(OECD_DATA_URL+"/"+oecd_annual_data_key(),
        params={"format":"csvfile","startPeriod":"1990"},
        headers={"Accept":"*/*"})
    print("SOURCE",response.status_code,len(response.content),response.headers.get("content-type"),flush=True)
    print("RAW_HEAD",repr(response.text[:220]),flush=True)
    parsed=parse_oecd_annual_sector_csv(response.text)
    print("PARSED",len(parsed),max(parsed),len(parsed[max(parsed)]),flush=True)
    from finance_dashboard.oecd_corporate import OECD_WDI_URL, parse_oecd_gdp_weights, OECD_MEMBER_ISO3
    wdi_response=r._get(OECD_WDI_URL,params={"format":"json","per_page":20000,
                                               "date":"1990:2026"})
    print("WDI_BODY",wdi_response.status_code,len(wdi_response.content),str(wdi_response.json()[0])[:350],flush=True)
    weights=parse_oecd_gdp_weights(wdi_response.json())
    for yr in (2000,2010,2015,2020,2021,2022,2023,2024,2025):
        blocks=parsed.get(yr,{})
        gdp=weights.get(yr,{})
        eligible=[k for k,v in blocks.items()
                  if k in gdp and {"nfc","fc","gva","net_product_taxes"}.issubset(v)]
        covered=sum((gdp[k] for k in eligible),0)
        total=sum(gdp.values(),0)
        print("AUDIT",yr,"components",len(blocks),"wdi",len(gdp),
              "eligible",len(eligible),
              "coverage",(float(covered/total) if total else None),
              "missing",sorted(OECD_MEMBER_ISO3-set(eligible)),flush=True)
    out=r.fetch("profit.oecd38.corporate_gross_surplus_gdp")
    print("FETCH_OK",len(out.observations),min(out.observations),max(out.observations),flush=True)
except Exception as exc:
    print("FAILURE",type(exc).__name__,str(exc)[:500],flush=True)
    traceback.print_exc(limit=4)
    raise SystemExit(1)
finally:r.close()
