"""Bounded no-write live source probe: fails visibly, never alters stored data."""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]

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


# Representative, distinct source families introduced by the 2026-11-04
# Claude increment. This tests remote source availability only; it is not a
# complete ingestion or source-reconciliation audit.
CLAUDE_SOURCE_IDS = (
    "activity.us.oecd_cli",
    "activity.us.industrial_production_diffusion_1m",
    "policy_rate.jp.boj_call_daily",
    "policy_rate.jp.boj_call_monthly_average",
    "credit.us.private_nonfinancial_stock_bis",
    "credit.us.private_nonfinancial_gdp_bis",
    "credit_gap.us.bis_trend",
    "stress.global.ofr_fsi",
    "external.us.imf_bop_current_account_usd",
    "external.us.imf_iip_net_position_usd",
    "bank.us.fdic_total_assets",
    "bank.us.fdic_total_equity",
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default="2024-01-01",
                        help="First requested original observation (YYYY-MM-DD)")
    selected = parser.add_mutually_exclusive_group()
    selected.add_argument("--new-sources", action="store_true",
                          help="Probe a representative set of newly integrated source families, without database writes")
    selected.add_argument("--only", nargs="+",
                          help="Probe any registered exact series IDs, without database writes")
    opts = parser.parse_args(argv)
    since = date.fromisoformat(opts.since)
    provider = ProviderRouter()
    try:
        ids = tuple(opts.only) if opts.only else CLAUDE_SOURCE_IDS if opts.new_sources else DEFAULT_IDS
        unknown = sorted(set(ids) - set(provider.definitions))
        if unknown:
            parser.error("Unknown canonical source identifier(s): " + ", ".join(unknown))
        result = probe(provider, ids, since)
    finally:
        provider.close()
    print(json.dumps(result, indent=2))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
