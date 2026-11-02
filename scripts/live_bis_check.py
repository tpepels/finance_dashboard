"""Bounded live provider acceptance; no hard-coded interest rates, no synthetic values.

Run by Phase 2 live CI separately from deterministic offline tests.
"""
from __future__ import annotations

from datetime import date, timedelta
import json

from finance_dashboard.bis import BisPolicyClient, COUNTRIES


def main() -> int:
    start = date.today() - timedelta(days=45)
    client = BisPolicyClient(retries=1)
    try:
        for sid in COUNTRIES:
            data = client.fetch(sid, start=start)
            dates = list(data.observations)
            assert dates, f"Empty recent series: {sid}"
            assert min(dates) >= start, f"Observations before start: {sid}"
            assert max(dates) <= date.today(), f"Future-dated observation: {sid}"
            assert all(v.is_finite() for v in data.observations.values()), sid
            print(json.dumps({
                "series_id": sid,
                "source": data.request_url,
                "first_observation": dates[0].isoformat(),
                "last_observation": dates[-1].isoformat(),
                "observations": len(dates),
                "bis_response_prepared": data.prepared_at.isoformat() if data.prepared_at else None,
            }))
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
