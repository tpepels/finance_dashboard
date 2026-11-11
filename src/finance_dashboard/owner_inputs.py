"""The owner's own portfolio parameters: entered in the application, stored locally, never fetched.

Until the owner saves their own figures, an explicit example is used and every
result built on it says so (`is_example`).
"""
from __future__ import annotations

import copy
import json
import math
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
    # none | realised_gains (rate on gains realised when selling) | yearly_on_value (rate of value each year, like Dutch box 3)
    "tax": {"mode": "none", "rate_pct": 0.0},
}


class OwnerInputError(ValueError):
    """Inputs that cannot be used, with a reason a person can act on."""


def default_path() -> Path:
    return Path(os.environ.get("FINANCE_OWNER_INPUTS", "/data/owner-inputs.json"))


def _number(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise OwnerInputError(f"{name} must be a finite number")
    try:
        number = float(value)
    except (ValueError, OverflowError) as exc:
        raise OwnerInputError(f"{name} must be a finite number") from exc
    if not math.isfinite(number):
        raise OwnerInputError(f"{name} must be a finite number")
    return number


def _fraction(value, name: str) -> float:
    number = _number(value, name)
    if not 0 <= number <= 1:
        raise OwnerInputError(f"{name} must be between 0 and 1")
    return number


def validate(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise OwnerInputError("owner inputs must be an object")
    data = copy.deepcopy({**EXAMPLE, **{k: v for k, v in raw.items() if k in EXAMPLE}})
    for field in ("allocation", "rebalancing", "tax"):
        if not isinstance(data[field], dict):
            raise OwnerInputError(f"{field} must be an object")
    if not isinstance(data["bonds_hedged"], bool):
        raise OwnerInputError("bonds_hedged must be true or false")
    allocation = {k: _fraction(data["allocation"].get(k, 0), f"allocation to {k}") for k in ("equity", "bonds", "gold")}
    if abs(sum(allocation.values()) - 1) > 0.001:
        raise OwnerInputError("allocation to equities, bonds and gold must add up to 100%")
    rebalancing = data["rebalancing"]
    if rebalancing.get("rule") not in ("never", "calendar", "threshold"):
        raise OwnerInputError("rebalancing rule must be never, calendar or threshold")
    month_number = _number(rebalancing.get("months", 12), "rebalancing months")
    if not month_number.is_integer():
        raise OwnerInputError("rebalancing months must be a whole number")
    months, band = int(month_number), _number(rebalancing.get("band_pp", 5), "rebalancing band")
    if not 1 <= months <= 60 or not 0.5 <= band <= 50:
        raise OwnerInputError("rebalancing every 1 to 60 months, with a band of 0.5 to 50 percentage points")
    numbers = {k: _number(data[k], k) for k in ("bond_duration_years", "trading_cost_bps", "start_value_eur",
                                              "monthly_contribution_eur")}
    if not 0 <= numbers["bond_duration_years"] <= 30 or not 0 <= numbers["trading_cost_bps"] <= 500:
        raise OwnerInputError("bond duration must be 0 to 30 years and trading costs 0 to 500 basis points")
    if numbers["start_value_eur"] <= 0 or numbers["monthly_contribution_eur"] < 0:
        raise OwnerInputError("starting value must be positive and contributions zero or more")
    tax = data["tax"]
    if tax.get("mode") not in ("none", "realised_gains", "yearly_on_value"):
        raise OwnerInputError("tax must be none, on realised gains, or yearly on value")
    rate = _number(tax.get("rate_pct", 0), "tax rate")
    if not 0 <= rate <= 60:
        raise OwnerInputError("tax rate must be between 0% and 60%")
    return {"allocation": allocation, "tax": {"mode": tax["mode"], "rate_pct": rate},
            "equity_hedged_share": _fraction(data["equity_hedged_share"], "share of foreign equity hedged"),
            "equity_euro_share": _fraction(data["equity_euro_share"], "euro-area share of equities"),
            "bonds_hedged": data["bonds_hedged"],
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
