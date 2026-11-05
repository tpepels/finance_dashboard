"""Bounded no-write live source probe: fails visibly, never alters stored data."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import date
from hashlib import sha256
from decimal import Decimal, InvalidOperation
import io
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


# OECD Data Explorer's 2025 STAN six-dimension key is:
# FREQ.REF_AREA.ACTIVITY.TRANSACTION.VALUATION.UNIT_MEASURE.
# The original-source candidates intentionally test a single national
# industry cube; they do not bind any L01–L03 scalar role.
STAN_FLOW = "OECD.STI.PIE,DSD_STAN@DF_STAN_2025,1.0"
STAN_MEASURES = frozenset({"B1G", "D1", "B2N", "P51C", "D29X39"})
STAN_REQUIRED_FIELDS = frozenset({
    "FREQ", "REF_AREA", "ACTIVITY", "TRANSACTION", "VALUATION",
    "UNIT_MEASURE", "TIME_PERIOD", "OBS_VALUE",
})


def probe_stan_candidates(client, *, since=date(2023, 1, 1)) -> dict:
    """Read-only bounded publisher response; never infer original-role readiness."""
    url = (
        "https://sdmx.oecd.org/public/rest/data/" + STAN_FLOW
        + "/A.PRT..B1G+D1+B2N+P51C+D29X39.V.XDC"
    )
    result = {
        "probe": "phase2-oecd-stan-source-candidates",
        "publisher": "OECD", "source_family": "STAN_2025",
        "requested_from": since.isoformat(),
        "no_database_writes": True,
        "original_role_bindings_created": 0,
        "all_l01_l03_original_roles_verified": False,
        "first_publication_vintage_verified": False,
        "state": "source_check_failed",
    }
    try:
        response = client.get(url, params={
            "startPeriod": str(since.year), "dimension_at_observation": "AllDimensions",
        }, headers={"Accept": "csvfile"})
        result["http_status"] = response.status_code
        response.raise_for_status()
        raw = response.content
        if not raw or len(raw) > 15_000_000:
            raise ValueError("Invalid or oversized native STAN response")
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        if (not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames)
                or not STAN_REQUIRED_FIELDS.issubset(reader.fieldnames)):
            raise ValueError("STAN original dimensions are missing")
        measures, industries, years, keys = Counter(), set(), set(), set()
        matched_values = {}
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("STAN original row dimensions changed")
            transaction = row["TRANSACTION"]
            if (row["FREQ"] != "A" or row["REF_AREA"] != "PRT"
                    or row["VALUATION"] != "V" or row["UNIT_MEASURE"] != "XDC"
                    or transaction not in STAN_MEASURES
                    or not row["TIME_PERIOD"].isdigit()
                    or int(row["TIME_PERIOD"]) < since.year
                    or not row["ACTIVITY"]):
                raise ValueError("STAN source identity is inconsistent")
            key = (row["ACTIVITY"], transaction, row["TIME_PERIOD"])
            if key in keys:
                raise ValueError("Duplicate STAN original observation")
            keys.add(key)
            if row["OBS_VALUE"] not in ("", ".", "NA"):
                try:
                    number = Decimal(row["OBS_VALUE"])
                    if not number.is_finite():
                        raise InvalidOperation
                except (InvalidOperation, ValueError):
                    raise ValueError("STAN source value is invalid") from None
                measures[transaction] += 1
                industries.add(row["ACTIVITY"])
                years.add(int(row["TIME_PERIOD"]))
                matched_values.setdefault(
                    (row["ACTIVITY"], int(row["TIME_PERIOD"])), {}
                )[transaction] = number
        if not measures:
            raise ValueError("STAN original candidate has no numeric observations")
        # Income-side industry accounts require all five native source measures
        # in the exact same activity/year; do not interpolate absent components.
        residuals = []
        for (activity, year), values in matched_values.items():
            if not STAN_MEASURES.issubset(values):
                continue
            residual = values["B1G"] - (
                values["D1"] + values["B2N"] + values["P51C"] + values["D29X39"]
            )
            residuals.append({"activity": activity, "year": year,
                              "residual": residual})
        residuals.sort(key=lambda item: (-abs(item["residual"]), item["activity"], item["year"]))
        result.update(state="sampled",
            original_response_sha256=sha256(raw).hexdigest(),
            native_measure_observation_counts=dict(sorted(measures.items())),
            missing_candidate_measures=sorted(STAN_MEASURES - set(measures)),
            reported_industries=len(industries),
            reported_years=sorted(years),
            matched_five_measure_industry_years=len(residuals),
            nonzero_nominal_income_identity_residuals=sum(
                item["residual"] != 0 for item in residuals
            ),
            largest_absolute_identity_residual_native=(
                str(abs(residuals[0]["residual"])) if residuals else None
            ),
            largest_identity_residual_examples=[
                {**{k: item[k] for k in ("activity", "year")},
                 "residual_native": str(item["residual"])}
                for item in residuals[:5]
            ],
            income_identity_interpretation="Original same-industry nominal B1G minus "
                "(D1 + B2N including mixed income + P51C + D29X39). "
                "Residuals are observations, not a passed accounting test or "
                "evidence that net mixed income equals net operating surplus.",
            scope="Original publisher source-key and field feasibility only; "
                  "publication-vintage, self-employed imputation, industry/sector "
                  "matching and stock/flow identities remain unverified.")
    except Exception as exc:
        # Upstream exception text and URLs may contain credentials or raw bodies.
        result["reason_type"] = type(exc).__name__
    return result


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
    selected = parser.add_mutually_exclusive_group()
    selected.add_argument("--new-sources", action="store_true",
                          help="Probe a representative set of newly integrated source families, without database writes")
    selected.add_argument("--only", nargs="+",
                          help="Probe any registered exact series IDs, without database writes")
    selected.add_argument("--stan-candidates", action="store_true",
                          help="Read-only bounded official OECD STAN candidate field check for L01-L03")
    opts = parser.parse_args()
    since = date.fromisoformat(opts.since)
    if opts.stan_candidates:
        import httpx
        with httpx.Client(timeout=35, follow_redirects=False) as client:
            result = probe_stan_candidates(client, since=since)
        print(json.dumps(result, indent=2))
        return 0 if result["state"] == "sampled" else 1
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
