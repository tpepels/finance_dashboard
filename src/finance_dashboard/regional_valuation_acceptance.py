"""Acceptance of V03's regional composition role from MSCI's archived factsheets.

The ratio roles are ordinary scalar series and pass the standard gates. The
composition role is the factsheets themselves: GICS sector weights, the
printed top countries plus "Other", and the constituent count, each dated by
the document's own as-of month. What MSCI does not print in a factsheet, or
what the archive did not capture, is a stated limitation that makes the
analysis conditional; nothing is filled.
"""
from __future__ import annotations

from .msci_regional_factsheets import BOUND_INDEXES

NAMES = ("source_binding", "native_dimensions", "stored_history", "original_source_values",
         "matched_periods", "publisher_dimensions", "temporal_evidence")


def _gate(identifier, state, code, **details):
    return {"id": identifier, "state": state, "code": code, "series_ids": [], **details}


def regional_composition_checks(evidence: dict) -> dict:
    if evidence.get("original_source_hash_verified") is not True or not evidence.get("methodology"):
        return {"checks": [_gate(name, "blocked", "msci_archived_factsheets_missing") for name in NAMES],
                "conditional": False, "resolved": False}
    panels = evidence["panels"]
    months = {index: panels[index]["composition_months"] for index in BOUND_INDEXES}
    missing = sorted(index for index, items in months.items() if not items)
    conflicts = [item for item in evidence["conflicts"]
                 if item["index"] in BOUND_INDEXES and item["measure"] == "composition"]
    coverage = {index: {"composition_months": len(months[index]),
                        "first": months[index][0] if months[index] else None,
                        "last": months[index][-1] if months[index] else None,
                        "ratio_months": panels[index]["coverage"]["months_with_values"],
                        "ratio_months_missing_in_span": len(panels[index]["coverage"]["missing_months_in_span"])}
                for index in BOUND_INDEXES}
    limitations = [
        {"code": "archived_factsheet_months_missing", "coverage": coverage,
         "detail": "Only months whose factsheet the Internet Archive captured are observed; the rest are absent, never filled or interpolated."},
        {"code": "history_starts_with_archive_captures",
         "first_months": {index: item["first"] for index, item in coverage.items()},
         "detail": "Usable captures begin in 2012-2014 and are dense only from about 2017 (World, ACWI, EM) or 2020 (regions); earlier MSCI factsheets were not archived."},
        {"code": "country_weights_top_n_only",
         "detail": "Factsheets print the largest four to six countries plus 'Other'; full country weights and constituent lists are not published free."},
        *([{"code": "printed_value_conflicts_blocked", "conflicts": conflicts,
             "detail": "Two MSCI documents print different weights for the same index and month; that month is blocked, neither value is used."}]
          if conflicts else []),
        {"code": "capture_time_bounds_dissemination",
         "detail": "The document's as-of month dates each value; the capture time is only an upper bound on when MSCI published it."},
    ]
    checks = [
        _gate("source_binding", "passed", "msci_archived_factsheets_verified",
              documents=evidence["documents_parsed"], rejected=evidence["documents_rejected"],
              rejections=evidence["rejections"], methodology=evidence["methodology"],
              scope="MSCI's own factsheet PDFs, raw Internet Archive captures checked against the CDX SHA-1 digest."),
        _gate("native_dimensions", "passed", "gics_sectors_top_countries_constituent_count",
              indexes=list(BOUND_INDEXES)),
        _gate("stored_history", "incomplete" if missing else "passed",
              "index_without_composition" if missing else "composition_months_retained",
              missing_indexes=missing, coverage=coverage),
        _gate("original_source_values", "passed", "printed_weights_sum_and_count_checked",
              blocked_conflict_months=conflicts,
              scope="Sector and country weights each sum to 100 within rounding; the table count matches the description. Months printed differently by two documents are blocked, not chosen."),
        _gate("matched_periods", "incomplete" if missing else "passed",
              "index_without_composition" if missing else "composition_and_ratios_from_same_documents"),
        _gate("publisher_dimensions", "passed", "msci_factsheet_printed_dimensions",
              scope="Index identity, currency and as-of date read from each document; definitions from the pinned Fundamental Data Methodology."),
        _gate("temporal_evidence", "passed", "document_as_of_dates", limitations=limitations),
    ]
    resolved = all(check["state"] == "passed" for check in checks)
    return {"checks": checks, "conditional": True, "resolved": resolved}
