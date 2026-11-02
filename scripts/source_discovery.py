"""One-off source feasibility probes, bounded to 12s per endpoint.

Never logs credentials or confidential values. This is a discovery aid, not
a substitute for a validated provider adapter.
"""
import json
import httpx

URLS = {
    "ilo_labour_share_us": "https://rplumber.ilo.org/data/indicator?id=SDG_1041_NOC_RT&ref_area=USA",
    "imf_mapper_debt": "https://www.imf.org/external/datamapper/api/v2/GGXWDG_NGDP",
    "un_labour_share_us": "https://unstats.un.org/SDGAPI/v1/sdg/Indicator/Data?indicator=10.4.1&areaCode=840&pageSize=2",
}
for label, url in URLS.items():
    try:
        r = httpx.get(url, timeout=12, follow_redirects=True)
        snippet = r.text[:350].replace("\n", " ")
        print(json.dumps({
            "source": label, "status": r.status_code,
            "content_type": r.headers.get("content-type"),
            "bytes": len(r.content), "sample": snippet,
        }))
    except Exception as e:
        print(json.dumps({"source": label, "error": type(e).__name__}))
