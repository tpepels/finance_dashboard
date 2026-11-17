"""Feature flag for the allocation module.

The module stays hidden until its acceptance gates pass (plan phase D10).
``FINANCE_ALLOCATION=1`` enables it; anything else, including an unset
variable, keeps every allocation route and UI entry unavailable.
"""
from __future__ import annotations

import os
from typing import Mapping

from fastapi import HTTPException

FLAG = "FINANCE_ALLOCATION"
_TRUE = frozenset({"1", "true", "yes", "on"})


def allocation_enabled(environ: Mapping[str, str] | None = None) -> bool:
    value = (os.environ if environ is None else environ).get(FLAG, "")
    return value.strip().lower() in _TRUE


def require_allocation() -> None:
    """FastAPI dependency: allocation routes answer 404 while the flag is off."""
    if not allocation_enabled():
        raise HTTPException(status_code=404, detail="Not Found")
