"""Genuine ALFRED point-in-time US macro observations, not app-ingestion timestamps.

Use FRED's realtime_start=realtime_end=asof API contract. The writer is an
explicit local CLI, rate-bounded and opt-in. The API only reads validated
snapshots already downloaded to /data/vintages; it never triggers external
requests through a browser query.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import argparse
import json
import os
from pathlib import Path
import time

import httpx

FRED_OBSERVATIONS = "https://api.stlouisfed.org/fred/series/observations"
ROOT = Path(os.environ.get("FINANCE_VINTAGE_DIR", "/data/vintages"))
# Selected source series have documented release/vintage semantics. No
# assumption that every third-party FRED series has historical ALFRED vintages.
SOURCES = {
    "T10Y3M": {
        "name": "US Treasury 10-year minus 3-month nominal spread",
        "frequency": "D", "maximum_age_days": 14,
        "reference": "https://fred.stlouisfed.org/series/T10Y3M",
    },
    "SAHMREALTIME": {
        "name": "Sahm Rule real-time-method recession indicator",
        "frequency": "M", "maximum_age_days": 76,
        "reference": "https://fred.stlouisfed.org/series/SAHMREALTIME",
    },
    "USREC": {
        "name": "NBER US recession indicator, monthly, announced retrospectively",
        "frequency": "M", "maximum_age_days": 76,
        "reference": "https://fred.stlouisfed.org/series/USREC",
    },
}


class VintageError(ValueError):
    pass


def snapshot_path(root: Path, series_id: str, asof: date) -> Path:
    if series_id not in SOURCES:
        raise VintageError("Unsupported point-in-time source")
    return root / series_id / (asof.isoformat() + ".json")


def _validated(content: dict, series_id: str, asof: date) -> dict:
    if (content.get("schema_version") != 1 or content.get("provider") != "ALFRED"
        or content.get("series_id") != series_id or content.get("asof") != asof.isoformat()
        or content.get("realtime_start") != asof.isoformat()
        or content.get("realtime_end") != asof.isoformat()):
        raise VintageError("Source vintage identity mismatch")
    previous = None
    cleaned = []
    for row in content.get("observations", []):
        day = date.fromisoformat(row["date"])
        if day > asof or (previous is not None and day <= previous):
            raise VintageError("Future or unordered point-in-time observation")
        val = Decimal(str(row["value"]))
        if not val.is_finite():
            raise VintageError("Nonfinite vintage observation")
        previous = day
        cleaned.append({"date": day.isoformat(), "value": str(val)})
    if content.get("status") == "ready" and not cleaned:
        raise VintageError("Claimed populated vintage has no observations")
    if content.get("status") not in ("ready", "no_data"):
        raise VintageError("Invalid vintage status")
    return {**content, "observations": cleaned}


def read_snapshot(root: Path, series_id: str, asof: date) -> dict | None:
    path = snapshot_path(root, series_id, asof)
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return _validated(raw, series_id, asof)


def fetch_snapshot(series_id: str, asof: date, *, api_key: str,
                   client: httpx.Client, root: Path = ROOT) -> dict:
    """Official ALFRED as-of snapshot. No synthetic 'release at period' dating."""
    if series_id not in SOURCES:
        raise VintageError("Unmapped ALFRED source")
    if not api_key:
        raise VintageError("FRED_API_KEY required for historical vintages")
    existing = read_snapshot(root, series_id, asof)
    if existing is not None:
        return existing
    # One as-of date per request; fetch only a bounded history required for
    # feature look-back without resampling or fabricating observation dates.
    start = asof - timedelta(days=430)
    response = client.get(FRED_OBSERVATIONS, params={
        "series_id": series_id, "api_key": api_key, "file_type": "json",
        "realtime_start": asof.isoformat(), "realtime_end": asof.isoformat(),
        "observation_start": start.isoformat(),
        "observation_end": asof.isoformat(),
        "output_type": 1, "units": "lin", "limit": 10000,
    }, timeout=25)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload.get("observations"), list):
        raise VintageError("Malformed ALFRED response")
    if (payload.get("realtime_start") not in (None, asof.isoformat())
        or payload.get("realtime_end") not in (None, asof.isoformat())):
        raise VintageError("Incorrect ALFRED realtime interval")
    rows = []
    for row in payload["observations"]:
        value = row.get("value")
        if value in (".", "", None):
            continue
        day = date.fromisoformat(row["date"])
        if day < start or day > asof:
            raise VintageError("ALFRED response outside requested as-of range")
        if row.get("realtime_start") and date.fromisoformat(row["realtime_start"]) > asof:
            raise VintageError("Response contains observation released after as-of date")
        if row.get("realtime_end") and date.fromisoformat(row["realtime_end"]) < asof:
            raise VintageError("Observation ceased being valid before as-of date")
        try:
            number = Decimal(str(value))
        except (ValueError, TypeError, InvalidOperation) as exc:
            raise VintageError("Invalid published ALFRED numeric value") from exc
        if not number.is_finite():
            raise VintageError("Invalid nonfinite published ALFRED value")
        rows.append({"date": day.isoformat(), "value": str(number)})
    rows.sort(key=lambda row: row["date"])
    result = _validated({
        "schema_version": 1, "provider": "ALFRED",
        "series_id": series_id, "asof": asof.isoformat(),
        "realtime_start": asof.isoformat(), "realtime_end": asof.isoformat(),
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_url": SOURCES[series_id]["reference"],
        "status": "ready" if rows else "no_data",
        "observations": rows,
        "publication_semantics": ("ALFRED source information available on this "
                                  "calendar date; not the app's first-seen timestamp."),
    }, series_id, asof)
    target = snapshot_path(root, series_id, asof)
    target.parent.mkdir(parents=True, exist_ok=True)
    from tempfile import NamedTemporaryFile
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                            prefix=".vintage-", delete=False) as temp:
        json.dump(result, temp, separators=(",", ":"))
        temporary = Path(temp.name)
    try:
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return result


def latest_asof_reading(snapshot: dict, *, tolerance_days: int | None = None) -> dict | None:
    valid = snapshot.get("observations") or []
    if not valid:
        return None
    last = valid[-1]
    gap = (date.fromisoformat(snapshot["asof"]) - date.fromisoformat(last["date"])).days
    max_age = tolerance_days if tolerance_days is not None else SOURCES[snapshot["series_id"]]["maximum_age_days"]
    if gap > max_age:
        return None
    return {"date": last["date"], "value": last["value"], "age_days": gap}


def available_snapshots(root: Path = ROOT) -> dict:
    series = []
    for sid, metadata in SOURCES.items():
        folder = root / sid
        dates = []
        for path in sorted(folder.glob("????-??-??.json")) if folder.exists() else []:
            try:
                asof = date.fromisoformat(path.stem)
                item = read_snapshot(root, sid, asof)
                if item is not None:
                    dates.append(asof.isoformat())
            except (ValueError, OSError, json.JSONDecodeError, KeyError):
                continue
        series.append({"series_id": sid, **metadata, "snapshot_dates": dates,
                       "count": len(dates)})
    return {"provider": "ALFRED", "source": "https://fred.stlouisfed.org/docs/api/fred/",
            "series": series, "source_publication_vintages": True,
            "current_market_prices_asof": False,
            "notes": "Only explicit local ALFRED dates; missing source histories are never imputed."}


def _month_ends(start: date, end: date) -> list[date]:
    cursor = date(start.year, start.month, 1)
    result = []
    while cursor <= end:
        nextmonth = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
        last = nextmonth - timedelta(days=1)
        if start <= last <= end:
            result.append(last)
        cursor = nextmonth
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch genuine dated ALFRED series snapshots")
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--series", action="append", choices=sorted(SOURCES),
                        required=True, help="Repeat to select multiple data series")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    if args.end > date.today() or args.start > args.end:
        parser.error("Historical as-of dates must be ordered and not in the future")
    if len(args.series) != len(set(args.series)):
        parser.error("Do not repeat the same series ID")
    months = _month_ends(args.start, args.end)
    if len(months) * len(args.series) > 180:
        parser.error("At most 180 snapshot requests per run; partition longer history")
    key = os.environ.get("FRED_API_KEY", "")
    if not key:
        parser.error("FRED_API_KEY is required for ALFRED")
    ok, failed = 0, 0
    with httpx.Client(timeout=25, headers={"User-Agent": "GlobalCapitalMonitor/0.2"}) as client:
        for day in months:
            for sid in args.series:
                try:
                    item = fetch_snapshot(sid, day, api_key=key, client=client, root=args.root)
                    ok += 1
                    print(f"{sid} {day}: {item['status']} ({len(item['observations'])} values)")
                except (VintageError, httpx.HTTPError, ValueError) as exc:
                    failed += 1
                    # Never print provider request URLs: they contain the API key.
                    print(f"{sid} {day}: unavailable ({type(exc).__name__})")
                time.sleep(0.2)
    print(f"ALFRED snapshots: stored/reused={ok}, failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
