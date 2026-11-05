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
