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
    for series in ["profit.oecd38.corporate_gross_surplus_gdp"]:
        obj=r.fetch(series)
        print("FETCH_OK",series,len(obj.observations),min(obj.observations),max(obj.observations),flush=True)
except Exception as exc:
    print("FAILURE",type(exc).__name__,str(exc)[:500],flush=True)
    traceback.print_exc(limit=4)
    raise SystemExit(1)
finally:r.close()
