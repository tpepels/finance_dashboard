"""Read-only, within-publication STAN industry/year accounting diagnostics.

Never pool industry aggregates or observations from separate OECD retrievals.
These diagnostics do not establish a source vintage, an official national
submission, or a Marxian surplus-value/profit-rate measure.
"""
from __future__ import annotations

from collections import Counter
import csv
from decimal import Decimal
import io
from itertools import combinations
from pathlib import Path

from .stan_originals import (
    read_stan_evidence, read_verified_stan_scope_csv,
)

CORE = ("B1G", "D1", "P51C", "D29X39")
INCOME_IDENTITIES = {
    "net_surplus_and_mixed_income": (
        ("B1G", "D1", "B2N_B3N", "P51C", "D29X39"), "B2N_B3N"),
    "gross_surplus_and_mixed_income": (
        ("B1G", "D1", "B2G_B3G", "D29X39"), "B2G_B3G"),
}
MISSING_VALUES = frozenset({"", ".", ":", "NA", "N/A"})


def _income_identity(groups: dict, required: tuple[str, ...],
                     surplus: str) -> dict:
    checked = 0
    incompatible = 0
    exact_fail = 0
    rounding_fail = 0
    non_a = 0
    max_examples = []
    for (activity, year), observations in sorted(groups.items()):
        if not set(required).issubset(observations):
            continue
        units = {(observations[measure][1], observations[measure][2])
                 for measure in required}
        if len(units) != 1 or any(not part for part in next(iter(units))):
            incompatible += 1
            continue
        checked += 1
        if any(observations[measure][3] != "A" for measure in required):
            non_a += 1
        numbers = {measure: observations[measure][0] for measure in required}
        operands = ["D1", surplus, "D29X39"]
        if surplus == "B2N_B3N":
            operands.append("P51C")
        residual = numbers["B1G"] - sum(
            (numbers[measure] for measure in operands), Decimal(0))
        # Maximum error due exclusively to printed decimal-place rounding.
        # This is a serialization diagnostic, not a publisher tolerance.
        precision_bound = sum(
            (Decimal("0.5").scaleb(number.as_tuple().exponent)
             for number in numbers.values()), Decimal(0))
        if residual:
            exact_fail += 1
        if abs(residual) > precision_bound:
            rounding_fail += 1
        max_examples.append({
            "activity": activity, "year": year,
            "residual_original_units": str(residual),
            "printed_precision_bound": str(precision_bound),
        })
    max_examples.sort(key=lambda item: (
        -abs(Decimal(item["residual_original_units"])),
        item["activity"], item["year"]))
    return {
        "required_native_measures": list(required),
        "surplus_measure": surplus,
        "eligible_matched_industry_years": checked,
        "incompatible_or_unreported_unit_groups": incompatible,
        "groups_with_non_A_source_flags": non_a,
        "nonzero_exact_residuals": exact_fail,
        "outside_printed_precision_bounds": rounding_fail,
        "largest_residual_examples": max_examples[:5],
        "identity_status": ("not_testable_no_same_scope_overlap"
                            if checked == 0 else
                            "residuals_exceed_printed_precision"
                            if rounding_fail else
                            "consistent_with_printed_precision"),
        "certified_accounting_identity": False,
    }


def audit_stan_scope(raw: bytes, *, measures: tuple[str, ...]) -> dict:
    """Analyse a canonically validated native response without aggregation."""
    groups = {}
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
        if row["OBS_VALUE"] in MISSING_VALUES:
            continue
        group = (row["ACTIVITY"], int(row["TIME_PERIOD"]))
        groups.setdefault(group, {})[row["MEASURE"]] = (
            Decimal(row["OBS_VALUE"]), row.get("UNIT_MULT", ""),
            row.get("CURRENCY", ""), row.get("OBS_STATUS", ""))
    available = Counter()
    pairwise = Counter()
    all_four_by_year = Counter()
    all_four_groups = 0
    for (_, year), sample in groups.items():
        for measure in sample:
            available[measure] += 1
        for a, b in combinations(sorted(sample), 2):
            pairwise[f"{a}|{b}"] += 1
        if set(CORE).issubset(sample):
            all_four_groups += 1
            all_four_by_year[year] += 1
    return {
        "requested_native_measures": list(measures),
        "distinct_industry_years": len(groups),
        "numeric_measure_counts": dict(sorted(available.items())),
        "core_four_measures": list(CORE),
        "core_four_matched_industry_years": all_four_groups,
        "core_four_overlap_by_year": {
            str(year): all_four_by_year[year] for year in sorted(all_four_by_year)},
        "pairwise_matched_industry_years": dict(sorted(pairwise.items())),
        "identity_checks": {
            name: _income_identity(groups, required, surplus)
            for name, (required, surplus) in INCOME_IDENTITIES.items()
        },
        "industries_aggregated": False,
        "different_retrievals_joined": False,
    }


def audit_stan_originals(root: Path, *, countries: tuple[str, ...]) -> dict:
    """Use independently verified scopes only; preserve every raw original."""
    evidence = read_stan_evidence(Path(root), countries=countries)
    report = []
    for country_evidence in evidence["country_results"]:
        country = country_evidence["country"]
        if country_evidence["status"] != "verified_original_stan_partial":
            report.append({"country": country,
                           "status": country_evidence["status"],
                           "scope_audits": []})
            continue
        scopes = []
        for scope in country_evidence["source_scopes"]:
            measures = tuple(scope["scope"].removeprefix("measure-").split("+"))
            raw = read_verified_stan_scope_csv(
                root, country=country, start_year=scope["requested_since"],
                measures=measures)
            scopes.append({
                "scope": scope["scope"],
                "requested_since": scope["requested_since"],
                "original_response_sha256": scope["original_response_sha256"],
                **audit_stan_scope(raw, measures=measures),
            })
        report.append({
            "country": country, "status": "verified_independent_scope_audits",
            "scope_audits": scopes,
            "scopes_are_distinct_publication_retrievals": len(scopes) > 1,
        })
    return {
        "phase": "phase2", "operation": "stan_original_industry_accounting_audit",
        "countries_checked": list(countries), "country_audits": report,
        "no_archive_writes": True, "no_macro_database_writes": True,
        "cross_scope_join_performed": False,
        "published_data_vintage_synchronization_verified": False,
        "scientific_analysis_certified": False,
        "first_publication_verified": False,
    }
