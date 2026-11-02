"""Assert the scheduled Pages-ready artifact contains the safe SEC aggregate."""
from pathlib import Path
import json

root=Path("build/static-data")
manifest=json.loads((root/"index.json").read_text())
matches=[x for x in manifest.get("supplementary_sources",[])
         if x.get("id")=="profit.us_sec_filers.world_gdp_share"]
assert len(matches)==1, "Wisesheets source missing from static manifest"
record=matches[0]
assert record["status"]=="partial_us_sec_reporter_coverage", "Aggregate not yet available"
assert record["snapshot_status"] in ("current","stale")
path=root/record["file"]
assert path.is_file(), "Supplementary Wisesheets data file missing"
data=json.loads(path.read_text())
assert data["id"]=="profit.us_sec_filers.world_gdp_share"
assert len(data["observations"])>=3
assert data["unique_issuers_with_financials"]>=5000
assert data["currency"]=="USD"
assert "Bearer " not in path.read_text()
assert "WISESHEETS_API_KEY" not in path.read_text()
assert all("sec_filer_income_as_pct_of_world_gdp" in x for x in data["observations"])
print(f"STATIC_WISESHEETS=PASS verified_issuers={data['unique_issuers_with_financials']} "
      f"years={len(data['observations'])} status={record['snapshot_status']}")
