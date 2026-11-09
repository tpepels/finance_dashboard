"""The owner's own portfolio parameters: entered in the application, stored locally, never fetched.

Until the owner saves their own figures, an explicit example is used and every
result built on it says so (`is_example`).
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile

EXAMPLE = {
    "allocation": {"equity": 0.7, "bonds": 0.25, "gold": 0.05},
    "equity_hedged_share": 0.0,
    "equity_euro_share": 0.1,
    "bonds_hedged": True,
    "bond_duration_years": 7.0,
    "rebalancing": {"rule": "threshold", "months": 12, "band_pp": 5.0},
    "trading_cost_bps": 10.0,
    "start_value_eur": 100000.0,
    "monthly_contribution_eur": 0.0,
    "annual_withdrawal_pct": 0.0,
}


class OwnerInputError(ValueError):
    """Inputs that cannot be used, with a reason a person can act on."""


def default_path() -> Path:
    return Path(os.environ.get("FINANCE_OWNER_INPUTS", "/data/owner-inputs.json"))


def _fraction(value, name: str) -> float:
    number = float(value)
    if not 0 <= number <= 1:
        raise OwnerInputError(f"{name} must be between 0 and 1")
    return number


def validate(raw: dict) -> dict:
    data = copy.deepcopy({**EXAMPLE, **{k: v for k, v in raw.items() if k in EXAMPLE}})
    allocation = {k: _fraction(data["allocation"].get(k, 0), f"allocation to {k}") for k in ("equity", "bonds", "gold")}
    if abs(sum(allocation.values()) - 1) > 0.001:
        raise OwnerInputError("allocation to equities, bonds and gold must add up to 100%")
    rebalancing = data["rebalancing"]
    if rebalancing.get("rule") not in ("never", "calendar", "threshold"):
        raise OwnerInputError("rebalancing rule must be never, calendar or threshold")
    months, band = int(rebalancing.get("months", 12)), float(rebalancing.get("band_pp", 5))
    if not 1 <= months <= 60 or not 0.5 <= band <= 50:
        raise OwnerInputError("rebalancing every 1 to 60 months, with a band of 0.5 to 50 percentage points")
    numbers = {k: float(data[k]) for k in ("bond_duration_years", "trading_cost_bps", "start_value_eur",
                                            "monthly_contribution_eur")}
    if not 0 <= numbers["bond_duration_years"] <= 30 or not 0 <= numbers["trading_cost_bps"] <= 500:
        raise OwnerInputError("bond duration must be 0 to 30 years and trading costs 0 to 500 basis points")
    if numbers["start_value_eur"] <= 0 or numbers["monthly_contribution_eur"] < 0:
        raise OwnerInputError("starting value must be positive and contributions zero or more")
    return {"allocation": allocation,
            "equity_hedged_share": _fraction(data["equity_hedged_share"], "share of foreign equity hedged"),
            "equity_euro_share": _fraction(data["equity_euro_share"], "euro-area share of equities"),
            "bonds_hedged": bool(data["bonds_hedged"]),
            "rebalancing": {"rule": rebalancing["rule"], "months": months, "band_pp": band},
            "annual_withdrawal_pct": _fraction(data["annual_withdrawal_pct"], "yearly withdrawal"),
            **numbers}


def load_owner_inputs(path: Path | None = None) -> dict:
    path = path or default_path()
    try:
        return {**validate(json.loads(path.read_text())), "is_example": False}
    except (OSError, ValueError, TypeError, KeyError):
        return {**copy.deepcopy(EXAMPLE), "is_example": True}


def save_owner_inputs(path: Path | None, raw: dict) -> dict:
    """Validate, then write atomically; invalid inputs never touch the stored file."""
    path = path or default_path()
    clean = validate(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, suffix=".tmp") as handle:
        json.dump(clean, handle, indent=2)
        temporary = Path(handle.name)
    temporary.replace(path)
    return {**clean, "is_example": False}
