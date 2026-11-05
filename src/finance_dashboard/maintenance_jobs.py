"""Declarative maintenance job registry and strict canonical input normalization.

Every public action has one option contract and one registered handler. The
manager owns scheduling/cancellation, not provider selection or validation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable

from .vintage import SOURCES as VINTAGE_SOURCES

VINTAGE_IDS = frozenset(VINTAGE_SOURCES)
FX_IDS = frozenset(("USD", "GBP", "CHF"))


class MaintenanceBlocked(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class MaintenanceAction:
    action: str
    allowed_options: frozenset[str]
    handler: str
    validator: Callable[[dict, set[str], set[str]], dict]


def _empty(options: dict, sources: set[str], markets: set[str]) -> dict:
    if options:
        raise ValueError("This maintenance operation takes no parameters")
    return {}


def _sync(options: dict, sources: set[str], markets: set[str]) -> dict:
    if options:
        raise ValueError("Sync operations accept no manual source settings")
    return {
        "series_ids": sorted(sources),
        "instrument_ids": sorted(markets),
        "currencies": sorted(FX_IDS),
    }


def _sources(options: dict, sources: set[str], markets: set[str]) -> dict:
    ids = options["series_ids"] if "series_ids" in options else sorted(sources)
    if (not isinstance(ids, list) or not 1 <= len(ids) <= len(sources)
            or len(ids) != len(set(ids)) or not set(ids) <= sources):
        raise ValueError("Invalid canonical series selection")
    return {"series_ids": sorted(ids)}


def _markets(options: dict, sources: set[str], markets: set[str]) -> dict:
    ids = options["instrument_ids"] if "instrument_ids" in options else sorted(markets)
    fx = options["currencies"] if "currencies" in options else sorted(FX_IDS)
    if (not isinstance(ids, list) or len(ids) > 24
            or len(ids) != len(set(ids)) or not set(ids) <= markets
            or not isinstance(fx, list) or len(fx) > 3
            or len(fx) != len(set(fx)) or not set(fx) <= FX_IDS
            or not (ids or fx)):
        raise ValueError("Invalid market or FX selection")
    return {"instrument_ids": sorted(ids), "currencies": sorted(fx)}


def _vintages(options: dict, sources: set[str], markets: set[str]) -> dict:
    selected = options.get("series_ids") or sorted(VINTAGE_IDS)
    start = options.get("start", "2000-01-01")
    end = options.get("end", (date.today().replace(day=1) -
                              timedelta(days=1)).isoformat())
    limit = options.get("max_requests", 60)
    full = options.get("complete_range", True)
    try:
        lower, upper = date.fromisoformat(start), date.fromisoformat(end)
    except (TypeError, ValueError):
        raise ValueError("Invalid historical date range") from None
    if (lower < date(1950, 1, 1) or lower > upper or upper > date.today()
            or not isinstance(selected, list) or not selected
            or not set(selected) <= VINTAGE_IDS or len(selected) != len(set(selected))
            or type(limit) is not int or not 1 <= limit <= 180
            or type(full) is not bool):
        raise ValueError("Invalid ALFRED backfill parameters")
    return {
        "start": lower.isoformat(), "end": upper.isoformat(),
        "series_ids": sorted(selected), "max_requests": limit,
        "complete_range": full,
    }


def _sec(options: dict, sources: set[str], markets: set[str]) -> dict:
    limit = options.get("limit", 12)
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("Invalid SEC matching filing limit")
    return {"limit": limit}


ACTIONS = (
    MaintenanceAction("sync_current", frozenset(), "run_sync", _sync),
    MaintenanceAction("sync_history", frozenset(), "run_sync", _sync),
    MaintenanceAction("refresh_sources", frozenset({"series_ids"}), "run_refresh_sources", _sources),
    MaintenanceAction("refresh_markets", frozenset({"instrument_ids", "currencies"}), "run_refresh_markets", _markets),
    MaintenanceAction("check_alfred", frozenset(), "run_alfred", _empty),
    MaintenanceAction("backfill_alfred", frozenset({
        "series_ids", "start", "end", "max_requests", "complete_range"}), "run_alfred", _vintages),
    MaintenanceAction("check_sec", frozenset(), "run_check_sec", _empty),
    MaintenanceAction("collect_sec", frozenset({"limit"}), "run_collect_sec", _sec),
    MaintenanceAction("refresh_earnings", frozenset(), "run_refresh_earnings", _empty),
    MaintenanceAction("backup", frozenset(), "run_backup", _empty),
)
ACTION_REGISTRY = {spec.action: spec for spec in ACTIONS}
PUBLIC_ACTIONS = frozenset(ACTION_REGISTRY)
if len(ACTION_REGISTRY) != len(ACTIONS):
    raise RuntimeError("Duplicate maintenance action registration")


def normalize_options(
        action: str, options: dict, *,
        valid_sources: set[str], valid_markets: set[str]) -> dict:
    spec = ACTION_REGISTRY.get(action)
    if spec is None:
        raise ValueError("Unknown maintenance operation")
    if not isinstance(options, dict) or not set(options) <= spec.allowed_options:
        raise ValueError("Unexpected maintenance parameters")
    # Browser-provided URLs, commands, file paths and credentials are rejected.
    return spec.validator(options, valid_sources, valid_markets)
