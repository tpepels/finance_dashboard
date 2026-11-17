"""Reference portfolios: the market anchor and the R1-R5 risk ladder (design section 3).

The ladder is general: it depends on no investor's holdings. A rung's weights
are ``growth_share * growth_mix + (1 - growth_share) * defensive_mix``. The
growth mix is measured market weights (supplied from phase D2 onward); the
defensive mix is provisional until it is measured too.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Mapping

from .contracts import ReferencePortfolio

DEFAULT_ROOT = Path(os.environ.get("FINANCE_DASHBOARD_ROOT", str(Path(__file__).resolve().parents[3])))
REFERENCES_FILE = "allocation_references.json"
PREREGISTRATION_FILE = "allocation_preregistration.json"
GROUPS = frozenset({"growth", "defensive", "satellite"})
CATEGORIES = frozenset({"A", "B", "C", "D"})
_TOLERANCE = 1e-9


def load_allocation_documents(root: Path = DEFAULT_ROOT) -> tuple[dict[str, Any], dict[str, Any]]:
    directory = Path(root) / "definitions"
    with (directory / REFERENCES_FILE).open(encoding="utf-8") as f:
        references = json.load(f)
    with (directory / PREREGISTRATION_FILE).open(encoding="utf-8") as f:
        preregistration = json.load(f)
    return references, preregistration


def _fraction(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 0.0 <= value <= 1.0


def validate_references(doc: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if doc.get("schema_version") != 1:
        errors.append("allocation references: schema_version must be 1")
    buckets = doc.get("buckets") or []
    ids = [b.get("id") for b in buckets]
    if len(set(ids)) != len(ids):
        errors.append("allocation references: duplicate bucket ids")
    by_id = {b.get("id"): b for b in buckets}
    for bucket in buckets:
        name = bucket.get("id")
        if bucket.get("group") not in GROUPS:
            errors.append(f"allocation bucket {name}: group must be one of {sorted(GROUPS)}")
        if bucket.get("category") not in CATEGORIES:
            errors.append(f"allocation bucket {name}: evidence category must be A-D")
        if not _fraction(bucket.get("cap")):
            errors.append(f"allocation bucket {name}: cap must be in [0, 1]")
    for group in ("growth", "defensive"):
        if not any(b.get("group") == group for b in buckets):
            errors.append(f"allocation references: no {group} buckets")

    constraints = doc.get("constraints") or {}
    if constraints.get("long_only") is not True:
        errors.append("allocation constraints: long_only must be true")
    te_max = constraints.get("te_max")
    if not (_fraction(te_max) and te_max > 0):
        errors.append("allocation constraints: te_max must be in (0, 1]")
    band = constraints.get("growth_band")
    if not (_fraction(band) and 0 < band < 1):
        errors.append("allocation constraints: growth_band must be in (0, 1)")
    for key in ("cash_max", "satellite_cap", "factor_sleeve_cap"):
        if not _fraction(constraints.get(key)):
            errors.append(f"allocation constraints: {key} must be in [0, 1]")
    if _fraction(constraints.get("satellite_cap")) and _fraction(constraints.get("factor_sleeve_cap")) \
            and constraints["factor_sleeve_cap"] < constraints["satellite_cap"]:
        errors.append("allocation constraints: factor_sleeve_cap must not be below satellite_cap")
    for bucket in buckets:
        if bucket.get("group") == "satellite" and _fraction(bucket.get("cap")) \
                and _fraction(constraints.get("satellite_cap")) and bucket["cap"] > constraints["satellite_cap"]:
            errors.append(f"allocation bucket {bucket.get('id')}: cap exceeds satellite_cap")
    cash = by_id.get("CASH")
    if cash and _fraction(cash.get("cap")) and _fraction(constraints.get("cash_max")) \
            and cash["cap"] > constraints["cash_max"]:
        errors.append("allocation bucket CASH: cap exceeds cash_max")

    anchor = doc.get("anchor") or {}
    if not (anchor.get("growth_mix") or {}).get("method"):
        errors.append("allocation anchor: growth_mix.method is required")
    defensive = anchor.get("defensive_mix") or {}
    shares = defensive.get("shares") or {}
    if not shares:
        errors.append("allocation anchor: defensive_mix.shares is required")
    for bucket, share in shares.items():
        if by_id.get(bucket, {}).get("group") != "defensive":
            errors.append(f"allocation anchor: defensive share for non-defensive bucket {bucket}")
        if not _fraction(share):
            errors.append(f"allocation anchor: defensive share for {bucket} must be in [0, 1]")
    if shares and all(_fraction(v) for v in shares.values()) and abs(sum(shares.values()) - 1.0) > 1e-6:
        errors.append("allocation anchor: defensive shares must sum to 1")

    rungs = doc.get("rungs") or []
    rung_ids = [r.get("id") for r in rungs]
    if not rungs or len(set(rung_ids)) != len(rung_ids):
        errors.append("allocation references: rungs must be non-empty with unique ids")
    growth = [r.get("growth_share") for r in rungs]
    if not all(_fraction(g) for g in growth):
        errors.append("allocation references: every rung growth_share must be in [0, 1]")
    elif growth != sorted(growth) or len(set(growth)) != len(growth):
        errors.append("allocation references: rung growth shares must be strictly increasing")

    defaults = doc.get("backtest_defaults") or {}
    if not isinstance(defaults.get("costs"), bool) or not isinstance(defaults.get("tax"), bool):
        errors.append("allocation backtest_defaults: costs and tax must be booleans")
    compute = doc.get("compute") or {}
    if compute.get("location") not in ("server", "local", "either"):
        errors.append("allocation compute: location must be server, local or either")
    if compute.get("max_concurrent_heavy_jobs") != 1:
        errors.append("allocation compute: only one heavy job may run at a time")
    return errors


def validate_preregistration(doc: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if doc.get("schema_version") != 1:
        errors.append("allocation preregistration: schema_version must be 1")
    status, frozen, spec_hash = doc.get("status"), doc.get("frozen"), doc.get("spec_hash")
    if status not in ("draft", "frozen"):
        errors.append("allocation preregistration: status must be draft or frozen")
    if (status == "frozen") != (frozen is True):
        errors.append("allocation preregistration: status and frozen disagree")
    if frozen is True and not (isinstance(spec_hash, str) and len(spec_hash) == 64):
        errors.append("allocation preregistration: a frozen spec needs a SHA-256 spec_hash")
    if frozen is not True and spec_hash is not None:
        errors.append("allocation preregistration: a draft spec has no spec_hash")
    if (doc.get("holdout") or {}).get("evaluations_allowed_per_spec") != 1:
        errors.append("allocation preregistration: the holdout may be evaluated once per spec")
    return errors


def validate_allocation(references: Mapping[str, Any], preregistration: Mapping[str, Any]) -> list[str]:
    return validate_references(references) + validate_preregistration(preregistration)


def _mix_errors(name: str, mix: Mapping[str, float], allowed: set[str]) -> None:
    unknown = set(mix) - allowed
    if unknown:
        raise ValueError(f"{name} contains buckets outside its group: {sorted(unknown)}")
    if any(not math.isfinite(v) or v < 0 for v in mix.values()) or abs(sum(mix.values()) - 1.0) > 1e-6:
        raise ValueError(f"{name} must be non-negative and sum to 1")


def rung_weights(doc: Mapping[str, Any], rung_id: str, growth_mix: Mapping[str, float],
                 defensive_mix: Mapping[str, float] | None = None) -> dict[str, float]:
    """Compose a rung's reference weights from the anchor's growth and defensive mixes."""
    rung = next((r for r in doc["rungs"] if r["id"] == rung_id), None)
    if rung is None:
        raise KeyError(rung_id)
    groups = {b["id"]: b["group"] for b in doc["buckets"]}
    defensive_mix = dict(doc["anchor"]["defensive_mix"]["shares"] if defensive_mix is None else defensive_mix)
    _mix_errors("growth mix", growth_mix, {k for k, g in groups.items() if g == "growth"})
    _mix_errors("defensive mix", defensive_mix, {k for k, g in groups.items() if g == "defensive"})
    share = rung["growth_share"]
    weights = {bucket: 0.0 for bucket in groups}
    for bucket, w in growth_mix.items():
        weights[bucket] += share * w
    for bucket, w in defensive_mix.items():
        weights[bucket] += (1.0 - share) * w
    return weights


def reference_portfolio(doc: Mapping[str, Any], rung_id: str, growth_mix: Mapping[str, float],
                        risk_aversion: float, defensive_mix: Mapping[str, float] | None = None) -> ReferencePortfolio:
    """Build the contract object for one rung. Risk aversion comes from reverse optimisation (phase D5)."""
    weights = rung_weights(doc, rung_id, growth_mix, defensive_mix)
    constraints = doc["constraints"]
    return ReferencePortfolio(
        id=rung_id,
        weights=tuple(sorted((k, v) for k, v in weights.items() if v > _TOLERANCE)),
        risk_aversion=risk_aversion,
        te_max=constraints["te_max"],
        growth_band=constraints["growth_band"],
        caps=tuple(sorted((b["id"], b["cap"]) for b in doc["buckets"])),
    )
