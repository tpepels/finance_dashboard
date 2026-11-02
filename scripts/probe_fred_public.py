"""Bounded probe of FRED's public observations tables, no API key."""
import json
import re
import httpx
for sid in ("DFEDTARU","DFII10","SAHMREALTIME","NCBCEPNW"):
    for suffix in ("", ".txt"):
        url=f"https://fred.stlouisfed.org/data/{sid}{suffix}"
        try:
            r=httpx.get(url,timeout=12,follow_redirects=True)
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
