"""Bounded probe of FRED's public observations tables, no API key."""
import json
import httpx
for sid in ("DFEDTARU","DFII10","SAHMREALTIME","NCBCEPNW"):
    for suffix in ("", ".txt"):
        url=f"https://fred.stlouisfed.org/data/{sid}{suffix}"
        try:
            r=httpx.get(url,timeout=10,follow_redirects=False)
            text=r.text
            print(json.dumps({
                "series":sid,"suffix":suffix,"status":r.status_code,
                "bytes":len(r.content),
                "content_type":r.headers.get("content-type"),
                "has_header":"DATE" in text and "VALUE" in text,
                "date_count":text.count("2026-"),
                "snippet":text[:80].replace("\n"," ")
            }),flush=True)
        except Exception as exc:
            print(json.dumps({"series":sid,"suffix":suffix,"error":type(exc).__name__}),flush=True)
