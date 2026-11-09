"""NBER US recession periods from the stored monthly recession indicator.

The indicator is 1 in each month from the month after a business-cycle peak
through the trough month. Consecutive recession months form one period. Three
episodes carry the names readers know them by; every other period is named by
its years. These are US dates, never world or regional recession dates.
"""
from __future__ import annotations

import calendar
from datetime import date

SERIES_ID = "recession.us.nber_indicator"
NAMED = {2001: "Dot-com recession", 2007: "Financial crisis", 2008: "Financial crisis", 2020: "COVID-19 recession"}


def _name(start: tuple[int, int], end: tuple[int, int] | None) -> str:
    if start[0] in NAMED:
        return NAMED[start[0]]
    if end is None or end[0] == start[0]:
        return f"US recession {start[0]}"
    return f"US recession {start[0]}–{str(end[0])[-2:]}"


def _next(key: tuple[int, int]) -> tuple[int, int]:
    return (key[0] + 1, 1) if key[1] == 12 else (key[0], key[1] + 1)


def recession_periods(points: list[tuple[date, float]]) -> list[dict]:
    months = {}
    for day, value in sorted(points):
        months[(day.year, day.month)] = value >= 0.5
    ordered = sorted(months)
    periods, run = [], []
    for key in ordered:
        if months[key] and run and key != _next(run[-1]):
            periods.append((run[0], run[-1]))   # an unobserved month ends a run; nothing is filled
            run = []
        if months[key]:
            run.append(key)
            continue
        if run:
            periods.append((run[0], run[-1]))
            run = []
    if run:
        periods.append((run[0], None))
    out = []
    for start, end in periods:
        out.append({
            "start": date(start[0], start[1], 1).isoformat(),
            "end": date(end[0], end[1], calendar.monthrange(*end)[1]).isoformat() if end else None,
            "name": _name(start, end),
            "scope": "US (NBER)",
        })
    return out
