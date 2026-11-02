"""Validate complete monthly SEC-reporting earnings aggregate before publication."""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal

path = Path(sys.argv[1]) if len(sys.argv)>1 else Path("data/wisesheets/sec_filer_profit.json")
payload = json.loads(path.read_text())
assert payload["schema_version"] == 1
assert payload["id"] == "profit.us_sec_filers.world_gdp_share"
assert payload["status"] == "partial_us_sec_reporter_coverage"
assert payload["currency"] == "USD"
assert payload["unique_issuers_with_financials"] >= 5000
assert 1 <= payload["wisesheets_requests_used_this_run"] <= 800
rows = payload["observations"]
assert len(rows) >= 3 and len({x["year"] for x in rows}) == len(rows)
for row in rows:
    assert row["world_gdp_usd"] and Decimal(row["world_gdp_usd"]) > 0
    assert row["reporting_issuers"] >= 1000
    assert 0 < row["usd_converted_issuers"] <= row["reporting_issuers"]
    assert Decimal(row["usd_conversion_coverage_pct_of_reporting_issuers"]) <= 100
    assert Decimal(row["sec_filer_net_income_usd"]).is_finite()
    assert Decimal(row["sec_filer_income_as_pct_of_world_gdp"]).is_finite()
snapshot=datetime.fromisoformat(payload["source_snapshot_at_utc"])
assert snapshot.tzinfo is not None
assert abs((datetime.now(timezone.utc)-snapshot).total_seconds())<86400
raw = path.read_text()
assert "WISESHEETS_API_KEY" not in raw and "Bearer " not in raw
print("WISESHEETS_SEC_AGGREGATE=PASS "
      f"years={len(rows)} issuers={payload['unique_issuers_with_financials']} "
      f"requests={payload['wisesheets_requests_used_this_run']}", flush=True)
