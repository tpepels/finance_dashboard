"""Which owner-supplied Phase 2 roles are actually supplied, and by what.

Phase 2 cannot check an owner's portfolio parameters against a publisher, so
it accepts such a role only when the store that supplies it holds valid values:
the owner's saved inputs (never the labelled example), or the curated shock
register with every event dated, labelled and sourced. Each acceptance carries
a limitation saying where the values come from.
"""
from __future__ import annotations

from datetime import date
import re

# (analysis, role) -> owner-input fields that supply it
OWNER_ROLES = {
    ("P04", "currency_portfolio_weights"): ("allocation", "equity_euro_share", "equity_hedged_share", "bonds_hedged"),
    ("P04", "modified_duration"): ("bond_duration_years",),
    ("P05", "target_weights"): ("allocation",),
    ("P05", "actual_weights"): ("allocation", "start_value_eur"),
    ("P05", "rebalance_policy"): ("rebalancing",),
    ("P05", "trading_costs"): ("trading_cost_bps",),
    ("P05", "tax_policy"): ("tax",),
    ("P05", "withdrawal_plan"): ("monthly_contribution_eur", "annual_withdrawal_pct"),
}
REGISTER_ROLES = (("C05", "independent_shock_events"), ("P03", "market_shock_dates"))


def _register_valid(events: list[dict]) -> bool:
    if not events:
        return False
    for event in events:
        try:
            day = date.fromisoformat(event["date"])
        except (KeyError, TypeError, ValueError):
            return False
        if day > date.today() or not str(event.get("label", "")).strip() \
                or not re.match(r"https://\S+$", str(event.get("source_url", ""))):
            return False
    return True


def supplied_roles(owner: dict | None, events: list[dict] | None, *,
                   portfolio: dict | None = None) -> dict[tuple[str, str], dict]:
    out = {}
    if owner and owner.get("is_example") is False:
        for key, fields in OWNER_ROLES.items():
            if all(field in owner for field in fields):
                out[key] = {"supplied_by": "owner_inputs", "fields": list(fields),
                            "limitation": {"code": "owner_supplied_values_not_verified",
                                           "detail": "Supplied by your saved portfolio inputs (the replay starts at the "
                                                     "target mix); validated for range and consistency, not checked "
                                                     "against any account or publisher."}}
    if _register_valid(events or []):
        for key in REGISTER_ROLES:
            out[key] = {"supplied_by": "shock_register", "events": len(events),
                        "limitation": {"code": "curated_shock_register",
                                       "detail": f"{len(events)} events from definitions/shock_events.json, each dated by "
                                                 "the official source it cites; a curated list, not a complete census."}}
    if (portfolio and portfolio.get('as_of') and portfolio.get('scope') == 'full_invested_portfolio'
            and portfolio.get('positions') and (portfolio.get('summary') or {}).get('total_value_eur')
            and all(p.get('isin') and p.get('identity_source') != 'unresolved'
                    for p in portfolio['positions'])):
        out[('P01', 'portfolio_fund_weights')] = {
            'supplied_by': 'portfolio_holdings', 'fields': ['positions', 'as_of', 'scope'],
            'limitation': {'code': 'owner_supplied_values_not_verified',
                           'detail': 'Dated fund positions and values supplied by the owner; '
                                     'full invested-portfolio scope excludes cash. Values and fund '
                                     'identities are not independently checked against a broker.'}}
    return out


def current_supply() -> dict[tuple[str, str], dict]:
    """From the stores the application uses: the owner-input file and the shock register."""
    import json
    from .catalog import DEFAULT_ROOT
    from .owner_inputs import load_owner_inputs
    try:
        events = json.loads((DEFAULT_ROOT / "definitions" / "shock_events.json").read_text())["events"]
    except (OSError, ValueError, KeyError):
        events = []
    from .portfolio_holdings import load_portfolio_holdings, PortfolioHoldingsError
    try:
        portfolio = load_portfolio_holdings()
    except (PortfolioHoldingsError, OSError):
        portfolio = None  # Preserve unreadable state; the holdings API reports the error.
    return supplied_roles(load_owner_inputs(), events, portfolio=portfolio)
