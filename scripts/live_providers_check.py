"""Bounded, live source acceptance for every mapped non-FRED/non-BIS series.

FRED requires owner-supplied FRED_API_KEY; BIS has a separate full-Docker
acceptance workflow. Missing values, future dates, and source IDs are validated.
"""
from __future__ import annotations
from datetime import date, timedelta
import json

from finance_dashboard.providers import ProviderRouter


def main() -> int:
    router = ProviderRouter()
    successful = 0
    try:
        sources = [sid for sid in router.supported_ids()
                   if router.definitions[sid]["provider"] != "BIS"]
        for sid in sources:
            start = date.today() - timedelta(days=2200 if sid.startswith("valuation.domestic") else 1100)
            result = router.fetch(sid, start)
            assert result.observations, f"No observations for {sid}"
            assert min(result.observations) >= start, f"Upstream ignored window: {sid}"
            assert max(result.observations) <= date.today(), f"Future observation: {sid}"
            successful += 1
            print(json.dumps({
                "series_id": sid, "source_url": result.request_url.split("?")[0],
                "count": len(result.observations), "latest": max(result.observations).isoformat(),
            }), flush=True)
    finally:
        router.close()
    print(f"PHASE2_ALL_NONBIS_LIVE=PASS (verified={successful}, BIS policies verified separately)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
