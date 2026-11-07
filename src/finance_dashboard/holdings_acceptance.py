"""Acceptance of holdings-backed roles against a declared fund contract.

A holdings role (fund constituents, security identity, issuer country and
sector, index-proxy weights, issuer crosswalk) has no scalar series. It is
judged on each declared fund's latest hash-verified original snapshot:

* the snapshot is current and unambiguous;
* its accounting control passes (a fund balance sheet or NAV statement; a
  rounded-weight sum where the publisher's file carries no NAV);
* every required field the publisher reports covers at least the declared
  share of security value; a field the publisher does not report is carried
  as a per-fund limitation, and an archived original that does report it
  contradicts the cited review;
* where declared, reported issuers group without LEI/name conflicts.

Publisher absences and weights-only controls make the analysis conditional,
never accepted. Nothing is filled, matched by name or inferred.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import json
from pathlib import Path

from .catalog import DEFAULT_ROOT as ROOT  # honours FINANCE_DASHBOARD_ROOT in installed runtimes
from .holdings_coverage import FIELDS

HOLDINGS_ARTIFACTS = ("sec_holdings", "ucits_holdings")
CONDITIONAL_CODES = ("holdings_field_not_reported_by_publisher",
                     "holdings_weights_only_accounting_control")


@lru_cache(maxsize=4)
def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_holdings_sources(root: Path = ROOT) -> dict:
    document = _load(str(Path(root) / "definitions" / "holdings_sources.json"))
    if document.get("schema_version") != 1 or not isinstance(document.get("sources"), dict):
        raise ValueError("invalid_holdings_source_reviews")
    return document["sources"]


def valid_source_review(review) -> bool:
    return (isinstance(review, dict)
            and isinstance(review.get("evidence_url"), str) and review["evidence_url"].startswith("https://")
            and _iso(review.get("reviewed_on"))
            and isinstance(review.get("reports"), dict) and set(review["reports"]) == set(FIELDS)
            and all(type(value) is bool for value in review["reports"].values()))


def _iso(value) -> bool:
    try:
        return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _fraction(value) -> Decimal | None:
    try:
        number = Decimal(value) if isinstance(value, str) else None
    except InvalidOperation:
        return None
    return number if number is not None and 0 < number <= 1 else None


def valid_holdings_contract(contract) -> bool:
    if not isinstance(contract, dict) or set(contract) - {
            "funds", "required_fields", "minimum_weight_coverage",
            "maximum_snapshot_age_days", "issuer_grouping"}:
        return False
    funds = contract.get("funds")
    if (not isinstance(funds, list) or not funds
            or any(not isinstance(item, dict) or set(item) != {"fund", "artifact_id", "source"}
                   or not all(isinstance(item[key], str) and item[key] for key in item)
                   or item["artifact_id"] not in HOLDINGS_ARTIFACTS for item in funds)
            or len({item["fund"] for item in funds}) != len(funds)):
        return False
    fields = contract.get("required_fields")
    age = contract.get("maximum_snapshot_age_days")
    return (isinstance(fields, list) and len(fields) == len(set(fields)) and set(fields) <= set(FIELDS)
            and _fraction(contract.get("minimum_weight_coverage")) is not None
            and type(age) is int and 1 <= age <= 3660
            and type(contract.get("issuer_grouping", False)) is bool)


def _gate(identifier, state, code, **details):
    return {"id": identifier, "state": state, "code": code, "series_ids": [], **details}


def _latest(evidence: dict, spec: dict) -> tuple[dict | None, bool]:
    artifact = evidence.get(spec["artifact_id"], {})
    if artifact.get("original_source_hash_verified") is not True:
        return None, False
    candidates = [source for source in artifact.get("sources", [])
                  if source.get("fund") == spec["fund"] and source.get("source") == spec["source"]
                  and _iso(source.get("holdings_date"))]
    if not candidates:
        return None, False
    newest = max(source["holdings_date"] for source in candidates)
    at_date = [source for source in candidates if source["holdings_date"] == newest]
    # Two different originals for one fund and date (an amendment, say) are
    # not resolved by guessing which one supersedes the other.
    ambiguous = len({source.get("bundle_digest") for source in at_date}) != 1
    return at_date[0], ambiguous


def holdings_role_checks(contract: dict, evidence: dict, reviews: dict, *, as_of: date) -> dict:
    """The standard role gates, evaluated on each declared fund's latest snapshot."""
    minimum = _fraction(contract["minimum_weight_coverage"])
    required = contract["required_fields"]
    funds, missing, stale, ambiguous, failed_controls = [], [], [], [], []
    absent, short, contradicted, unreviewed, grouping = [], [], [], [], []
    limitations = []
    for spec in contract["funds"]:
        source, unclear = _latest(evidence, spec)
        if source is None:
            missing.append(spec["fund"])
            continue
        age = (as_of - date.fromisoformat(source["holdings_date"])).days
        if unclear:
            ambiguous.append(spec["fund"])
        if age > contract["maximum_snapshot_age_days"] or age < 0:
            stale.append({"fund": spec["fund"], "holdings_date": source["holdings_date"], "age_days": age})
        control = source.get("accounting_control") or {}
        if control.get("passed") is not True:
            failed_controls.append({"fund": spec["fund"], "kind": control.get("kind")})
        elif control.get("reconciles_to_nav") is not True:
            limitations.append({"code": "holdings_weights_only_accounting_control", "fund": spec["fund"],
                                "source": spec["source"], "control": control.get("kind"),
                                "detail": "The publisher's current file states rounded weights but no NAV; positions are checked against their weight sum only."})
        review = reviews.get(spec["source"])
        coverage = (source.get("field_weight_coverage") or {}).get("fields", {})
        if not valid_source_review(review):
            unreviewed.append(spec["source"])
        else:
            for field in FIELDS:
                share = Decimal(coverage[field]) if coverage.get(field) is not None else None
                if not review["reports"][field] and share is not None and share > 0:
                    contradicted.append({"fund": spec["fund"], "field": field, "coverage": coverage[field]})
            for field in required:
                share = Decimal(coverage[field]) if coverage.get(field) is not None else None
                if not review["reports"][field]:
                    absent.append({"fund": spec["fund"], "field": field})
                    limitations.append({"code": "holdings_field_not_reported_by_publisher", "fund": spec["fund"],
                                        "source": spec["source"], "field": field,
                                        "evidence_url": review["evidence_url"]})
                elif share is None or share < minimum:
                    short.append({"fund": spec["fund"], "field": field, "coverage": coverage.get(field)})
        if contract.get("issuer_grouping"):
            concentration = source.get("reported_issuer_concentration")
            if (not isinstance(concentration, dict)
                    or Decimal(concentration.get("unassigned_issuer_name_equity_value_usd", "1")) != 0
                    or concentration.get("lei_name_conflicts") != 0
                    or concentration.get("name_multiple_lei_conflicts") != 0):
                grouping.append(spec["fund"])
        funds.append({"fund": spec["fund"], "source": spec["source"], "holdings_date": source["holdings_date"],
                      "bundle_digest": source.get("bundle_digest"), "age_days": age,
                      "accounting_control": control, "required_field_coverage": {
                          field: coverage.get(field) for field in required}})
    found = [item["fund"] for item in funds]
    # An unverified holdings artifact blocks the role; a verified one that
    # lacks a declared fund's snapshot is incomplete collection.
    unverified = any(evidence.get(spec["artifact_id"], {}).get("original_source_hash_verified") is not True
                     for spec in contract["funds"] if spec["fund"] in missing)
    publisher_state = ("failed" if contradicted else "blocked" if unreviewed
                       else "incomplete" if short else "passed")
    values_state = "failed" if failed_controls else "incomplete" if grouping else "passed"
    checks = [
        _gate("source_binding", "passed" if not missing else "blocked" if unverified else "incomplete",
              "holdings_sources_bound" if not missing else "holdings_source_missing",
              missing_funds=missing, funds=found),
        _gate("native_dimensions", "incomplete" if missing else "passed",
              "holdings_fund_identity_unchecked" if missing else "holdings_fund_identity_verified",
              scope="Each snapshot is selected by its own fund identity (SEC series, UCITS share-class ISIN) and declared source format."),
        _gate("stored_history", "incomplete" if stale or ambiguous else "passed",
              "holdings_snapshot_stale_or_ambiguous" if stale or ambiguous else "holdings_snapshots_current",
              stale=stale, ambiguous=ambiguous,
              maximum_snapshot_age_days=contract["maximum_snapshot_age_days"]),
        _gate("original_source_values", values_state,
              "holdings_accounting_control_failed" if failed_controls else
              "issuer_grouping_unresolved" if grouping else "holdings_accounting_controls_passed",
              failed=failed_controls, issuer_grouping_unresolved=grouping,
              issuer_grouping_required=bool(contract.get("issuer_grouping")),
              scope="Hash-verified originals; fund balance sheet or NAV statement, or the publisher's rounded-weight sum where no NAV is published. Where required, exact reported issuer names group share classes without LEI/name conflicts; no parent consolidation."),
        _gate("matched_periods", "incomplete" if missing else "passed",
              "holdings_snapshot_missing" if missing else "single_dated_snapshot_per_fund",
              scope="Each fund's own latest dated original snapshot; funds are not joined across dates."),
        # What the publisher reports is the publisher dimension of a holdings
        # file: the cited review, uncontradicted, and required-field coverage.
        _gate("publisher_dimensions", publisher_state,
              {"failed": "holdings_field_review_contradicted", "blocked": "holdings_field_review_missing",
               "incomplete": "holdings_field_coverage_below_minimum",
               "passed": "holdings_reported_fields_covered"}[publisher_state],
              contradicted=contradicted, unreviewed_sources=sorted(set(unreviewed)),
              required_fields=required, minimum_weight_coverage=contract["minimum_weight_coverage"],
              below_minimum=short, not_reported_by_publisher=absent, limitations=limitations),
        _gate("temporal_evidence", "incomplete" if missing else "passed",
              "holdings_as_of_date_missing" if missing else "original_holdings_as_of_date",
              as_of_dates={item["fund"]: item["holdings_date"] for item in funds},
              scope="Holdings are dated as-of snapshots from the original; publication instants are not inferred."),
    ]
    return {"checks": checks, "funds": funds,
            "conditional": any(item["code"] in CONDITIONAL_CODES for item in limitations)}
