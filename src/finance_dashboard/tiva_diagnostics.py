"""Investigate original TiVA publication inconsistencies without changing values.

The publisher's 2025 Guide (sections 4.2 and 6.3) defines VALU as VA
including intermediate-product net taxes and FFD_DVA/VALU as PT_VA.
This diagnostic asks whether rounding of the native three-decimal CSVs can
explain a discrepancy. It never changes the existing 0.001pp panel check.
"""
from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal, localcontext
from hashlib import sha256
import json
from pathlib import Path

from .oecd_tiva import MAINLV_FLOW, MAINSH_FLOW, TIVA_COUNTRIES, parse_tiva_csv

GUIDE_URL = "https://stats.oecd.org/wbos/fileview2.aspx?IDFile=2143f34e-6feb-41a9-abaf-cb52132608c4"
GUIDE_SHA256 = "ca3f3db9024a6f870ff6bec061537ea2230abf7880a8e56c3f5c16cd5518bdb4"


def audit_tiva_serialization(levels: bytes, shares: bytes) -> dict:
    """Compare all 196 native country-years and conservative rounding intervals.

    Three decimals is the maximum observed serialization precision in these
    publisher responses, not an allowance for a larger economic discrepancy.
    Both levels get +/-0.0005 USD million; shares get +/-0.0005pp. Shorter
    printed strings retain this conservative quantum (omitted trailing zeros).
    """
    batches = (parse_tiva_csv(levels.decode("utf-8-sig"), flow=MAINLV_FLOW),
               parse_tiva_csv(shares.decode("utf-8-sig"), flow=MAINSH_FLOW))
    observations = {key: values for batch in batches for key, values in batch.observations.items()}
    periods = {date(year, 1, 1) for year in range(1995, 2023)}
    if any(set(values) != periods for values in observations.values()):
        raise ValueError("tiva_diagnostic_requires_complete_original_country_periods")
    if any(value.as_tuple().exponent < -3 for values in observations.values() for value in values.values()):
        raise ValueError("tiva_unexpected_publisher_serialization_precision")
    comparisons = []
    half = Decimal("0.0005")
    with localcontext() as context:
        context.prec = 40
        for country, area in sorted(TIVA_COUNTRIES.items()):
            prefix = f"supply_chain.{country}."
            for period in sorted(periods):
                numerator = observations[prefix + "foreign_final_demand_va"][period]
                denominator = observations[prefix + "value_added"][period]
                share = observations[prefix + "foreign_final_demand_share"][period]
                if numerator < half or denominator <= half:
                    raise ValueError("tiva_positive_country_totals_required_for_interval_proof")
                computed = 100 * numerator / denominator
                computed_interval = (100 * (numerator - half) / (denominator + half),
                                     100 * (numerator + half) / (denominator - half))
                published_interval = share - half, share + half
                overlap = (computed_interval[0] <= published_interval[1]
                           and published_interval[0] <= computed_interval[1])
                comparisons.append({"area": area, "period": period.isoformat(),
                    "original_levels": {"FFD_DVA": str(numerator), "VALU": str(denominator)},
                    "original_published_share": str(share),
                    "computed_share": str(computed), "signed_residual_pp": str(computed - share),
                    "computed_share_interval": [str(value) for value in computed_interval],
                    "published_share_interval": [str(value) for value in published_interval],
                    "rounding_intervals_overlap": overlap,
                    "beyond_existing_0_001pp_check": abs(computed - share) > Decimal("0.001")})
    return {"schema_version": 1, "status": ("original_publication_identity_inconsistency"
        if any(not item["rounding_intervals_overlap"] for item in comparisons) else "serialized_identity_consistent"),
        "levels_sha256": sha256(levels).hexdigest(), "shares_sha256": sha256(shares).hexdigest(),
        "publisher": "OECD", "edition": "2025", "dataflow_version": "1.1",
        "formula": "100 * FFD_DVA / VALU", "definition_evidence": {
            "url": GUIDE_URL, "sha256": GUIDE_SHA256, "pages": [13, 34],
            "note": "2025 Guide: VALU includes net taxes on intermediate products; PT_VA is the share of VALU."},
        "rounding_quanta": {"levels_USD_million": "0.001", "shares_percentage_points": "0.001"},
        "pairs_checked": len(comparisons),
        "beyond_existing_0_001pp_check": sum(item["beyond_existing_0_001pp_check"] for item in comparisons),
        "outside_serialization_rounding_intervals": sum(not item["rounding_intervals_overlap"] for item in comparisons),
        "cause_verified": False, "common_release_verified": False, "first_publication_verified": False,
        "limitation": "Publisher explanation or a mutually consistent original replacement is still required; no value, date or tolerance is adjusted.",
        "comparisons": comparisons}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--levels", type=Path, required=True)
    parser.add_argument("--shares", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit_tiva_serialization(args.levels.read_bytes(), args.shares.read_bytes()), indent=2))


if __name__ == "__main__":
    main()
