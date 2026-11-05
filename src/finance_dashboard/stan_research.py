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
        ("B1G", "D1", "B2N_B3_N", "P51C", "D29X39"), "B2N_B3_N"),
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
        if surplus == "B2N_B3_N":
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
    coverage = summarize_scope_coverage(raw, measures=measures)
    return {
        "requested_native_measures": list(measures),
        "distinct_industry_years": len(groups),
        "coverage": coverage,
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
        verified_rows = []
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
            verified_rows.append((scope, _source_value_rows(raw)))
        comparison = reconcile_stan_source_scopes(
            country=country, verified_scope_rows=verified_rows)
        report.append({
            "country": country, "status": "verified_independent_scope_audits",
            "scope_audits": scopes,
            "cross_scope_reconciliation": comparison,
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



def summarize_scope_coverage(raw: bytes, *, measures: tuple[str, ...]) -> dict:
    """Bounded per-year support, source flags and units from one original CSV.

    Activity classifications can contain both total/parent and child sectors.
    Counts here are non-additive descriptive source coverage, not GDP weights.
    """
    per_year: dict[int, dict] = {}
    flags: Counter[str] = Counter()
    by_measure: dict[str, Counter[int]] = {}
    missing: Counter[str] = Counter()
    measure_flags: dict[str, Counter[str]] = {}
    units: dict[str, set[tuple[str, str]]] = {}
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
        year, measure = int(row["TIME_PERIOD"]), row["MEASURE"]
        flag = row.get("OBS_STATUS", "") or "unreported"
        flags[flag] += 1
        measure_flags.setdefault(measure, Counter())[flag] += 1
        unit = (row.get("UNIT_MULT", ""), row.get("CURRENCY", ""))
        units.setdefault(measure, set()).add(unit)
        if row["OBS_VALUE"] in MISSING_VALUES:
            missing[measure] += 1
            continue
        by_measure.setdefault(measure, Counter())[year] += 1
        bucket = per_year.setdefault(year, {
            "numeric": 0, "measure_counts": Counter(), "flags": Counter(),
        })
        bucket["numeric"] += 1
        bucket["measure_counts"][measure] += 1
        bucket["flags"][flag] += 1
    year_details = {
        str(y): {
            "numeric": per_year[y]["numeric"],
            "measure_counts": dict(sorted(per_year[y]["measure_counts"].items())),
            "source_flags": dict(sorted(per_year[y]["flags"].items())),
        }
        for y in sorted(per_year)
    }
    summary = {}
    for measure in sorted(set(measures) | set(measure_flags)):
        periods = sorted(by_measure.get(measure, {}))
        summary[measure] = {
            "numeric_observations": sum(by_measure.get(measure, {}).values()),
            "years_with_observations": len(periods),
            "first_observed_year": periods[0] if periods else None,
            "last_observed_year": periods[-1] if periods else None,
            "missing_source_values": missing[measure],
            "source_flags": dict(sorted(measure_flags.get(measure, {}).items())),
            "published_unit_currency_pairs": [
                {"unit_multiplier": mult, "currency": currency}
                for mult, currency in sorted(units.get(measure, set()))
            ],
        }
    return {
        "min_year": min(per_year, default=None),
        "max_year": max(per_year, default=None),
        "observed_year_count": len(per_year),
        "per_year": year_details,
        "per_measure": summary,
        "source_status_flag_counts": dict(sorted(flags.items())),
        "source_estimate_share_of_rows": (
            str(Decimal(flags["E"]) / sum(flags.values()))
            if flags else None),
        "contains_industry_hierarchies": True,
        "observations_not_additively_aggregated": True,
        "publisher_flag_meanings_independently_verified": False,
    }


def _source_value_rows(raw: bytes) -> dict[tuple[str, int, str], tuple]:
    values = {}
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
        if row["OBS_VALUE"] in MISSING_VALUES:
            continue
        key = (row["ACTIVITY"], int(row["TIME_PERIOD"]), row["MEASURE"])
        values[key] = (
            Decimal(row["OBS_VALUE"]), row.get("UNIT_MULT", ""),
            row.get("CURRENCY", ""), row.get("OBS_STATUS", "") or "unreported",
        )
    return values


def reconcile_stan_source_scopes(
        *, country: str, verified_scope_rows: list[tuple[dict, dict]]) -> dict:
    """Compare overlapping independently verified originals without merging.

    The caller supplies rows from the original verified in this same audit
    pass, so large archives do not require a redundant third full read.
    """
    results = []
    for (left, left_values), (right, right_values) in combinations(
            verified_scope_rows, 2):
        overlap = sorted(left_values.keys() & right_values.keys())
        numeric_changes = unit_changes = flag_changes = equal = 0
        examples = []
        for key in overlap:
            a, b = left_values[key], right_values[key]
            comparable = a[1:3] == b[1:3] and all(a[1:3])
            if not comparable:
                unit_changes += 1
            elif a[0] != b[0]:
                numeric_changes += 1
            else:
                equal += 1
            if a[3] != b[3]:
                flag_changes += 1
            if len(examples) < 5 and (not comparable or a[0] != b[0] or a[3] != b[3]):
                examples.append({
                    "activity": key[0], "year": key[1], "measure": key[2],
                    "left_value": str(a[0]), "right_value": str(b[0]),
                    "left_unit": [a[1], a[2]],
                    "right_unit": [b[1], b[2]],
                    "left_flag": a[3], "right_flag": b[3],
                })
        results.append({
            "left_scope": left["scope"],
            "left_start_year": left["requested_since"],
            "left_sha256": left["original_response_sha256"],
            "right_scope": right["scope"],
            "right_start_year": right["requested_since"],
            "right_sha256": right["original_response_sha256"],
            "same_measure_industry_year_overlap": len(overlap),
            "equal_value_same_unit": equal,
            "numeric_value_disagreements_same_unit": numeric_changes,
            "incompatible_or_unreported_units": unit_changes,
            "source_flag_changes": flag_changes,
            "examples": examples,
            "release_vintage_agreement_established": False,
        })
    return {
        "distinct_original_scope_count": len(verified_scope_rows),
        "compared_scope_pairs": len(results),
        "comparisons": results,
        "cross_scope_values_merged": False,
        "identities_computed_from_joined_scopes": False,
    }


def summarize_stan_readiness(root: Path, *, countries: tuple[str, ...]) -> dict:
    """Assess independently verified native STAN scopes for research preparation.

    One original may cover a subset of industries, years and measures. Never
    combine separate retrievals or sum country/industry totals. An identity
    matching printed precision is only a diagnostic, not a certification.
    """
    from .stan_metadata import read_stan_structure

    audits = audit_stan_originals(root, countries=countries)
    metadata = read_stan_structure(root)
    statuses = Counter()
    countries_result = []
    invalid = []
    same_scope_countries = 0
    verified_countries = 0
    for item in audits["country_audits"]:
        country = item["country"]
        if item["status"] != "verified_independent_scope_audits":
            status = ("invalid_original_archive" if item["status"] == "invalid_original_stan"
                      else "missing_verified_original")
            if status == "invalid_original_archive":
                invalid.append(country)
            statuses[status] += 1
            countries_result.append({
                "country": country, "status": status,
                "verified_scopes": 0, "same_scope_identity_observations": False,
            })
            continue
        verified_countries += 1
        scopes = item["scope_audits"]
        net = [s["identity_checks"]["net_surplus_and_mixed_income"] for s in scopes]
        gross = [s["identity_checks"]["gross_surplus_and_mixed_income"] for s in scopes]
        any_matched = any(
            check["eligible_matched_industry_years"] > 0
            for check in (*net, *gross))
        any_residual = any(
            check["outside_printed_precision_bounds"] > 0
            for check in (*net, *gross))
        any_flag = any(
            check["groups_with_non_A_source_flags"] > 0
            for check in (*net, *gross))
        per_measure_max = {
            measure: max(
                s["numeric_measure_counts"].get(measure, 0) for s in scopes)
            for measure in CORE
        }
        absent_measures = sorted(
            measure for measure, count in per_measure_max.items() if count == 0)
        if any_matched:
            same_scope_countries += 1
        cross = item["cross_scope_reconciliation"]["comparisons"]
        cross_conflicts = any(
            s["numeric_value_disagreements_same_unit"]
            or s["incompatible_or_unreported_units"]
            or s["source_flag_changes"]
            for s in cross)
        if any_residual:
            status = "accounting_residuals_require_investigation"
        elif cross_conflicts:
            status = "retrieval_disagreements_require_investigation"
        elif any_matched and any_flag:
            status = "identity_overlap_contains_uninterpreted_flags"
        elif any_matched:
            status = "same_scope_identity_diagnostic_available"
        elif any(s["core_four_matched_industry_years"] > 0 for s in scopes):
            status = "four_measure_coverage_only"
        else:
            status = "insufficient_same_scope_measure_coverage"
        statuses[status] += 1
        countries_result.append({
            "country": country, "status": status,
            "verified_scopes": len(scopes),
            "same_scope_identity_observations": any_matched,
            "core_four_max_industry_years_in_single_scope": max(
                s["core_four_matched_industry_years"] for s in scopes),
            "per_measure_max_numeric": per_measure_max,
            "core_measures_absent_in_all_scopes": absent_measures,
            "no_core_overlap_reason": (
                "measures_missing_from_archived_responses" if absent_measures
                else "measures_have_no_common_industry_year"
                if not any(s["core_four_matched_industry_years"] for s in scopes)
                else None),
            "per_scope_coverage": [{
                "scope": s["scope"],
                "requested_since": s["requested_since"],
                "original_response_sha256": s["original_response_sha256"],
                "measure_observations": s["numeric_measure_counts"],
                "year_spans_by_measure": {
                    k: [v["first_observed_year"], v["last_observed_year"]]
                    for k, v in s["coverage"]["per_measure"].items()
                },
                "native_status_flags": s["coverage"]["source_status_flag_counts"],
                "matched_four_measure_industry_years": s["core_four_matched_industry_years"],
            } for s in scopes],
            "net_max_matched_in_single_scope": max(
                c["eligible_matched_industry_years"] for c in net),
            "gross_max_matched_in_single_scope": max(
                c["eligible_matched_industry_years"] for c in gross),
            "native_measure_sets": [
                s["requested_native_measures"] for s in scopes],
            "retrieval_scope_disagreements": cross_conflicts,
            "non_A_identity_flags_present": any_flag,
            "identity_residuals_outside_printed_precision": any_residual,
        })
    return {
        "phase": "phase2", "operation": "stan_readiness",
        "countries_checked": list(countries),
        "verified_scope_countries": verified_countries,
        "same_scope_identity_countries": same_scope_countries,
        "invalid_original_countries": invalid,
        "status_counts": dict(sorted(statuses.items())),
        "country_readiness": countries_result,
        "publisher_measure_metadata": metadata["status"],
        "publisher_structure_source_sha256": metadata.get("source_sha256"),
        "official_structure_has_net_surplus_code": (
            "B2N_B3_N" in metadata.get("historical_candidates_present", [])
            if metadata["status"] == "verified_publisher_structure" else None),
        "official_structure_has_gross_surplus_code": (
            "B2G_B3G" in metadata.get("historical_candidates_present", [])
            if metadata["status"] == "verified_publisher_structure" else None),
        "observations_merged_across_retrievals": False,
        "industries_aggregated": False,
        "source_status_flag_meanings_verified": False,
        "publication_vintages_aligned": False,
        "first_publication_verified": False,
        "scientific_analysis_certified": False,
        "publisher_requests": 0, "no_archive_writes": True,
        "no_macro_database_writes": True,
    }
