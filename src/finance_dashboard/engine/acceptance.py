"""The Phase 2 acceptance result as the engine reads it.

A bundle states its analysis's Phase 2 state and, for each input series, the
analysis and role under which Phase 2 accepted it, with that role's
limitations. A series may be borrowed from another analysis's resolved role;
a series no resolved role accepts is refused.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import threading
import time
from typing import Callable

from ..research_acceptance import RESOLVED_ROLE_STATES
from .limitations import describe

RESOLVED_ANALYSIS_STATES = ("accepted", "conditional")


@dataclass(frozen=True)
class AcceptanceSnapshot:
    evaluated_at: datetime
    analyses: dict[str, dict]


class UnacceptedInput(ValueError):
    """An input series that no resolved Phase 2 role accepts."""


class AcceptanceUnavailable(RuntimeError):
    """The Phase 2 acceptance evaluation could not be completed."""


def snapshot_from_report(public_report: dict, evaluated_at: datetime) -> AcceptanceSnapshot:
    """research_corpus_report moves each analysis's role results from its
    acceptance onto the analysis row; both shapes are read."""
    return AcceptanceSnapshot(evaluated_at, {
        row["id"]: {**row["acceptance"],
                    "requirements": row.get("requirements", row["acceptance"].get("requirements", []))}
        for row in public_report["analyses"]})


def grouped(items: list[dict]) -> list[dict]:
    """One described limitation per (code, detail), naming every affected series.

    The original items are kept under "items", so nothing the acceptance
    engine recorded is lost; the text is shown once.
    """
    groups: dict[tuple, dict] = {}
    for item in items:
        key = (item.get("code"), item.get("detail"))
        if key not in groups:
            groups[key] = {**describe({"code": item.get("code")}),
                           **({"detail": item["detail"]} if item.get("detail") else {}),
                           "series_ids": set(), "occurrences": 0, "items": []}
        group = groups[key]
        group["series_ids"].update(item.get("series_ids") or [])
        if item.get("series_id"):
            group["series_ids"].add(item["series_id"])
        group["occurrences"] += 1
        group["items"].append(item)
    return [{**group, "series_ids": sorted(group["series_ids"])} for group in groups.values()]


def analysis_phase2(snapshot: AcceptanceSnapshot, analysis_id: str) -> dict:
    acceptance = snapshot.analyses.get(analysis_id)
    if acceptance is None:
        return {"state": "not_checked", "evaluated_at": snapshot.evaluated_at.isoformat(),
                "limitations": [], "open_gates": []}
    return {"state": acceptance["state"], "evaluated_at": snapshot.evaluated_at.isoformat(),
            "limitations": grouped(acceptance.get("limitations", [])),
            "open_gates": list(acceptance.get("blocking_roles", []))}


def _effective_series(role: dict) -> list[str]:
    if role["state"] == "unavailable_with_fallback":
        return (role.get("fallback_evaluation") or {}).get("series_ids", [])
    return role["series_ids"]


def _accepting_role(acceptance: dict, series_id: str) -> dict | None:
    if acceptance["state"] not in RESOLVED_ANALYSIS_STATES:
        return None
    return next((role for role in acceptance.get("requirements", [])
                 if role["state"] in RESOLVED_ROLE_STATES and series_id in _effective_series(role)), None)


def input_provenance(snapshot: AcceptanceSnapshot, analysis_id: str, series_id: str) -> dict:
    """Where Phase 2 accepted this input: the analysis's own role first, else the first other one."""
    order = [analysis_id] + sorted(key for key in snapshot.analyses if key != analysis_id)
    for owner in order:
        acceptance = snapshot.analyses.get(owner)
        role = _accepting_role(acceptance, series_id) if acceptance else None
        if role is not None:
            return {"accepted_under": {"analysis_id": owner, "role": role["role"]},
                    "limitations": grouped(role.get("limitations", []))}
    raise UnacceptedInput(series_id)


class AcceptanceCache:
    """Evaluate acceptance lazily and reuse it for ttl_seconds; failures are not kept."""

    def __init__(self, loader: Callable[[], AcceptanceSnapshot], ttl_seconds: float,
                 clock: Callable[[], float] = time.monotonic):
        self._loader, self._ttl, self._clock = loader, ttl_seconds, clock
        self._value: AcceptanceSnapshot | None = None
        self._loaded_at = 0.0
        self._lock = threading.Lock()

    def get(self) -> AcceptanceSnapshot:
        with self._lock:
            if self._value is None or self._clock() - self._loaded_at > self._ttl:
                try:
                    value = self._loader()
                except Exception as error:  # any evaluation failure is reported as unavailable
                    raise AcceptanceUnavailable(type(error).__name__) from error
                self._value, self._loaded_at = value, self._clock()
            return self._value
