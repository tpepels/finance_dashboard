"""Owner-readable text for every Phase 2 limitation code and method limitation.

Acceptance emits machine codes; bundles show them with the register's text.
An unmapped code is an error, never silently dropped.
"""
from __future__ import annotations

from functools import lru_cache
import json

from ..catalog import DEFAULT_ROOT


class UnmappedLimitation(KeyError):
    """A limitation code without register text."""


@lru_cache(maxsize=1)
def load_register() -> dict:
    return json.loads((DEFAULT_ROOT / "definitions" / "limitations.json").read_text())


def describe(item: dict) -> dict:
    """The limitation with its readable text added; all original fields kept."""
    code = item.get("code")
    texts = load_register()["phase2"]
    if code not in texts:
        raise UnmappedLimitation(code)
    return {**item, "text": texts[code]}


def method_limitations(analysis_id: str) -> list[dict]:
    """Limits of an analysis's method itself, in register order."""
    return [{"code": code, "text": text}
            for code, text in load_register()["method"].get(analysis_id, {}).items()]
