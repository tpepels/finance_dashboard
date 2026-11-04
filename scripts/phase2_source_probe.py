"""Bounded no-write live source probe: fails visibly, never alters stored data."""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from finance_dashboard.providers import ProviderRouter

DEFAULT_IDS = (
    "debt_service.us.private.bis",
    "debt_service.jp.private.bis",
    "debt_service.de.private.bis",
    "prices.us.imf_cpi_inflation",
    "prices.jp.imf_cpi_inflation",
    "prices.commodity.brent_usd",
    "bond.us.nominal_10y",
    "bond.us.breakeven_10y",
    "stress.us.high_yield_oas",
    "stress.us.vix",
    "property.pt.real_residential.bis",
    "property.us.commercial_all.bis",
    "property.pt.commercial_all.bis",
    "valuation.us.tobins_q2",
    "valuation.us.tobins_q3",
)


def probe(router: ProviderRouter, ids=DEFAULT_IDS, since=date(2024, 1, 1)) -> dict:
    """Identity-preserving source sample; no data storage or raw provider URLs."""
    result = []
    for identifier in ids:
        try:
            series = router.fetch(identifier, start=since)
            dates = sorted(series.observations)
            if not dates:
                raise ValueError("No source values")
            result.append({
                "id": identifier, "state": "sampled",
                "sample_observations": len(dates),
                "first": dates[0].isoformat(),
                "last": dates[-1].isoformat(),
                "prepared_at": series.prepared_at.isoformat()
                    if series.prepared_at is not None else None,
                "first_publication_vintage_verified": False,
            })
        except Exception as exc:
            # No messages: provider exception strings can contain credentials,
            # URLs and raw payloads. Fixed type names are sufficient to triage.
            result.append({
                "id": identifier, "state": "source_check_failed",
                "reason_type": type(exc).__name__,
                "first_publication_vintage_verified": False,
            })
    return {
        "probe": "phase2-original-source-samples",
        "no_database_writes": True,
        "requested_from": since.isoformat(),
        "sampled": sum(r["state"] == "sampled" for r in result),
        "failed": sum(r["state"] == "source_check_failed" for r in result),
        "sources": result,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default="2024-01-01",
                        help="First requested original observation (YYYY-MM-DD)")
    parser.add_argument("--only", choices=DEFAULT_IDS, nargs="+",
                        help="Optional subset of exact-source IDs")
    opts = parser.parse_args()
    since = date.fromisoformat(opts.since)
    provider = ProviderRouter()
    try:
        result = probe(provider, tuple(opts.only) if opts.only else DEFAULT_IDS, since)
    finally:
        provider.close()
    print(json.dumps(result, indent=2))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
