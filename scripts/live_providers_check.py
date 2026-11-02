"""Bounded samples from each *mapped* non-BIS provider, not a full data backfill.

A failed sample fails CI so availability is not silently claimed. Live/periodic
tests are deliberately separate from offline unit tests.
"""
from __future__ import annotations
from datetime import date, timedelta
import json

from finance_dashboard.providers import ProviderRouter

SAMPLES = (
    "policy_rate.ea.ecb_dfr",
    "gdp.real_growth.us",
    "gdp.real_growth.world",
    "valuation.domestic_cap_gdp.us",
    "valuation.domestic_cap_gdp.jp",
    "fiscal.world.public_debt",
)


def main() -> int:
    router = ProviderRouter()
    try:
        for sid in SAMPLES:
            start = date.today() - timedelta(days=1100 if not sid.startswith("valuation.") else 2200)
            result = router.fetch(sid, start)
            assert result.observations, f"No observations for {sid}"
            assert min(result.observations) >= start, f"Upstream ignored window: {sid}"
            assert max(result.observations) <= date.today(), f"Future observation: {sid}"
            print(json.dumps({
                "series_id": sid, "source_url": result.request_url.split("?")[0],
                "count": len(result.observations), "latest": max(result.observations).isoformat(),
            }))
    finally:
        router.close()
    print("PHASE2_NONFRED_LIVE=PASS (FRED requires configured API key)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
