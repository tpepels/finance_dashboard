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


class AcceptanceLoading(RuntimeError):
    """No snapshot yet; the first evaluation is running in the background."""


def _thread(work: Callable[[], None]) -> None:
    threading.Thread(target=work, name="phase2-acceptance", daemon=True).start()


class AcceptanceCache:
    """The Phase 2 snapshot, evaluated in the background.

    The live evaluation takes minutes, so requests never wait for it: a stale
    snapshot is served while one refresh runs (each bundle states when its
    snapshot was evaluated), and before the first snapshot exists callers get
    AcceptanceLoading. A failed evaluation is reported once, then retried.
    """

    def __init__(self, loader: Callable[[], AcceptanceSnapshot], ttl_seconds: float,
                 clock: Callable[[], float] = time.monotonic,
                 spawn: Callable[[Callable[[], None]], None] = _thread):
        self._loader, self._ttl, self._clock, self._spawn = loader, ttl_seconds, clock, spawn
        self._value: AcceptanceSnapshot | None = None
        self._loaded_at = 0.0
        self._loading = False
        self._error: str | None = None
        self._lock = threading.Lock()

    def _run(self) -> None:
        try:
            value, error = self._loader(), None
        except Exception as exc:  # any evaluation failure is reported, never cached as a value
            value, error = None, type(exc).__name__
        with self._lock:
            self._loading = False
            if value is not None:
                self._value, self._loaded_at, self._error = value, self._clock(), None
            else:
                self._error = error or "no snapshot"

    @property
    def loading(self) -> bool:
        with self._lock:
            return self._loading

    def warm(self) -> None:
        with self._lock:
            if self._loading:
                return
            self._loading = True
        self._spawn(self._run)  # outside the lock: a synchronous spawn re-enters it

    def get(self) -> AcceptanceSnapshot:
        with self._lock:
            if self._value is None and self._error is not None and not self._loading:
                error, self._error = self._error, None
                raise AcceptanceUnavailable(error)
            stale = self._value is None or self._clock() - self._loaded_at > self._ttl
            start = stale and not self._loading
            if start:
                self._loading = True
        if start:
            self._spawn(self._run)  # outside the lock: a synchronous spawn re-enters it
        # A synchronous spawn (tests) may have finished the evaluation already.
        with self._lock:
            if self._value is not None:
                return self._value
            if self._error is not None and not self._loading:
                error, self._error = self._error, None
                raise AcceptanceUnavailable(error)
            raise AcceptanceLoading()
