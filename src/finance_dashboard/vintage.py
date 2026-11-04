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
import re
from pathlib import Path
import time

import httpx

FRED_OBSERVATIONS = "https://api.stlouisfed.org/fred/series/observations"
FRED_VINTAGE_DATES = "https://api.stlouisfed.org/fred/series/vintagedates"
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
    "DGS10": {
        "name": "US nominal 10-year constant maturity Treasury yield",
        "frequency": "D", "maximum_age_days": 14,
        "reference": "https://fred.stlouisfed.org/series/DGS10",
    },
    "T10YIE": {
        "name": "US market ten-year TIPS inflation breakeven",
        "frequency": "D", "maximum_age_days": 14,
        "reference": "https://fred.stlouisfed.org/series/T10YIE",
    },
    "WFRBST01134": {
        "name": "Fed DFA US top one-percent household net-worth share",
        "frequency": "Q", "maximum_age_days": 225,
        "reference": "https://fred.stlouisfed.org/series/WFRBST01134",
    },
    "WFRBSN09161": {
        "name": "Fed DFA US next nine-percent household net-worth share",
        "frequency": "Q", "maximum_age_days": 225,
        "reference": "https://fred.stlouisfed.org/series/WFRBSN09161",
    },
    "WFRBSN40188": {
        "name": "Fed DFA US middle forty-percent household net-worth share",
        "frequency": "Q", "maximum_age_days": 225,
        "reference": "https://fred.stlouisfed.org/series/WFRBSN40188",
    },
    "WFRBSB50215": {
        "name": "Fed DFA US bottom half household net-worth share",
        "frequency": "Q", "maximum_age_days": 225,
        "reference": "https://fred.stlouisfed.org/series/WFRBSB50215",
    },
}


class VintageError(ValueError):
    pass


def _key_format_ok(key: str) -> bool:
    """FRED V1 documents exactly 32 lowercase ASCII letters/digits."""
    return bool(re.fullmatch(r"[a-z0-9]{32}", key))


def _safe_http_diagnostic(response: httpx.Response) -> dict:
    """Only fixed classifications and numeric HTTP status; never echo request URLs,
    upstream text, authorization values, or the secret-bearing query string."""
    status = response.status_code
    try:
        payload = response.json()
        message = str(payload.get("error_message", payload.get("message", ""))).lower()
    except (ValueError, TypeError, AttributeError):
        message = ""
    if status == 429:
        reason = "fred_rate_limited"
    elif ("api_key" in message or "api key" in message or "api-key" in message or
          "registered" in message or "unauthorized" in message or "authentication" in message):
        reason = "fred_api_key_rejected"
    elif status in (401, 403):
        reason = "fred_access_denied"
    elif status == 404:
        reason = "fred_series_or_endpoint_unavailable"
    elif status == 400:
        # Map only well-defined FRED parameter names. Do not expose the
        # upstream response body, which can echo the credential or URL.
        if "realtime_start" in message or "realtime_end" in message:
            reason = "fred_realtime_parameter_rejected"
        elif "observation_start" in message or "observation_end" in message:
            reason = "fred_observation_parameter_rejected"
        elif "series_id" in message or "series id" in message:
            reason = "fred_series_parameter_rejected"
        elif "limit" in message:
            reason = "fred_limit_rejected"
        else:
            reason = "fred_bad_request"
    elif status >= 500:
        reason = "fred_server_error"
    else:
        reason = "fred_unexpected_response"
    return {"http_status": status, "reason": reason}


_VINTAGE_VALIDATION_FAILURES = {
    "Malformed ALFRED response": "fred_response_schema_invalid",
    "Incorrect ALFRED realtime interval": "fred_realtime_mismatch",
    "ALFRED observation precedes requested historical window": "fred_observation_before_window",
    "ALFRED observation is after requested as-of date": "fred_observation_after_asof",
    "Response contains observation released after as-of date": "fred_observation_after_publication",
    "Observation ceased being valid before as-of date": "fred_observation_expired",
    "Invalid published ALFRED numeric value": "fred_observation_value_invalid",
    "Invalid nonfinite published ALFRED value": "fred_observation_value_invalid",
    "Future or unordered point-in-time observation": "vintage_observation_unordered",
    "Source vintage identity mismatch": "vintage_cache_identity_invalid",
    "Nonfinite vintage observation": "vintage_observation_value_invalid",
    "Claimed populated vintage has no observations": "vintage_cache_status_invalid",
    "Invalid vintage status": "vintage_cache_status_invalid",
}


def _snapshot_failure_diagnostic(exc: Exception) -> dict:
    """Classify a failed snapshot using only local, fixed codes.

    Never return an HTTP exception's URL, response body, query parameters,
    or free-form error text: FRED API keys are part of its request URL.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        return _safe_http_diagnostic(exc.response)
    if isinstance(exc, httpx.HTTPError):
        return {"reason": "fred_network_error"}
    if isinstance(exc, OSError):
        return {"reason": "vintage_storage_failed"}
    if isinstance(exc, json.JSONDecodeError):
        return {"reason": "fred_response_not_json"}
    if isinstance(exc, KeyError):
        return {"reason": "fred_response_schema_invalid"}
    if isinstance(exc, VintageError):
        return {"reason": _VINTAGE_VALIDATION_FAILURES.get(
            str(exc), "vintage_validation_failed")}
    return {"reason": "vintage_validation_failed"}


def probe_access(*, api_key: str, client: httpx.Client) -> dict:
    """Single bounded request, no persisted writes, with redacted diagnostics."""
    if not _key_format_ok(api_key):
        return {"status": "blocked", "reason": "fred_key_format_invalid",
                "key_format": "FRED V1 requires 32 lowercase alphanumeric characters",
                "requests": 0}
    try:
        response = client.get(FRED_OBSERVATIONS, params={
            # Mirror actual ALFRED as-of parameters; a plain FRED request
            # proves authentication but does not prove historical-vintage access.
            "series_id": "USREC", "api_key": api_key, "file_type": "json",
            "realtime_start": "2020-01-31", "realtime_end": "2020-01-31",
            "observation_start": "2019-01-01", "observation_end": "2020-01-31",
            "output_type": 1, "units": "lin", "limit": 10,
        }, timeout=25)
    except httpx.RequestError as exc:
        return {"status": "blocked", "reason": "fred_network_error",
                "error_type": type(exc).__name__, "requests": 1}
    if response.status_code != 200:
        return {"status": "blocked", **_safe_http_diagnostic(response), "requests": 1}
    try:
        payload = response.json()
        if not isinstance(payload.get("observations"), list):
            return {"status": "blocked", "reason": "fred_response_not_observations", "requests": 1}
        if (payload.get("realtime_start") not in (None, "2020-01-31") or
            payload.get("realtime_end") not in (None, "2020-01-31")):
            return {"status": "blocked", "reason": "fred_historical_asof_mismatch", "requests": 1}
    except (ValueError, AttributeError):
        return {"status": "blocked", "reason": "fred_response_not_json", "requests": 1}
    return {"status": "ready", "series_id": "USREC",
            "requests": 1, "note": "Historical ALFRED 2020-01-31 as-of endpoint and authentication succeeded"}


def first_available_vintages(series_ids: list[str], *, api_key: str,
                             client: httpx.Client) -> dict[str, date]:
    """Ask ALFRED for each source's earliest real publication vintage.

    A series introduced after the research start date has no genuine earlier
    point-in-time observations. Those dates must be excluded, never imputed.
    """
    if any(sid not in SOURCES for sid in series_ids):
        raise VintageError("Unmapped ALFRED source")
    result = {}
    for sid in series_ids:
        response = client.get(FRED_VINTAGE_DATES, params={
            "series_id": sid, "api_key": api_key, "file_type": "json",
            "sort_order": "asc", "limit": 1,
        }, timeout=25)
        response.raise_for_status()
        try:
            payload = response.json()
            dates = payload["vintage_dates"]
            if not isinstance(dates, list) or not dates:
                raise VintageError("ALFRED series has no verified publication vintages")
            result[sid] = date.fromisoformat(dates[0])
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise VintageError("Invalid ALFRED first-publication response") from exc
    return result


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
    # SAHMREALTIME has published monthly observations beginning in 1959-12.
    # The 430-day market-feature lookback is too narrow for its historical
    # recession-indicator series: request the original full historical span.
    # This does not claim that early observations were available before the
    # source's first ALFRED publication vintage (checked separately).
    # USREC likewise requires long historical recession labels. Daily T10Y3M
    # remains bounded to avoid truncation at the 10,000-observation API limit.
    # The four Fed DFA history series extend back to 1989. Request original
    # historical observations inside an ALFRED point-in-time vintage. This
    # NEVER proves they were published in 1989; the actual first published
    # source date is validated by first_available_vintages separately.
    dfa_series = {"WFRBST01134", "WFRBSN09161", "WFRBSN40188", "WFRBSB50215"}
    start = (date(1959, 12, 1) if series_id == "SAHMREALTIME"
             else date(1900, 1, 1) if series_id == "USREC"
             else date(1989, 1, 1) if series_id in dfa_series
             else asof - timedelta(days=430))
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
        if day < start:
            raise VintageError("ALFRED observation precedes requested historical window")
        if day > asof:
            raise VintageError("ALFRED observation is after requested as-of date")
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


def capture_previous_month(root: Path = ROOT, *,
                           today: date | None = None,
                           api_key: str | None = None,
                           client: httpx.Client | None = None) -> dict:
    """Idempotent monthly ALFRED source capture in the existing refresh loop."""
    day = today or date.today()
    asof = day.replace(day=1) - timedelta(days=1)
    key = api_key if api_key is not None else os.environ.get("FRED_API_KEY","")
    if not key:
        return {"asof":asof.isoformat(),"status":"disabled_no_key","captured":0,"errors":0}
    owns = client is None
    source = client or httpx.Client(timeout=25,headers={
        "User-Agent":"GlobalCapitalMonitor/0.2"})
    captured=0
    errors=0
    try:
        for sid in SOURCES:
            try:
                fetch_snapshot(sid,asof,api_key=key,client=source,root=root)
                captured+=1
            except (httpx.HTTPError,ValueError,OSError,KeyError):
                errors+=1
            if owns:
                time.sleep(.2)
    finally:
        if owns:
            source.close()
    return {"asof":asof.isoformat(),"status":"partial" if errors else "complete",
            "captured":captured,"errors":errors}


def backfill_batch(start: date, end: date, series_ids: list[str], *,
                   api_key: str, client: httpx.Client, root: Path = ROOT,
                   max_requests: int = 180, pause_seconds: float = 0.2,
                   first_available: dict[str, date] | None = None,
                   skip_failed: set[tuple[str, date]] | None = None) -> dict:
    """Resume full-range publication-vintage ingestion in bounded API batches.

    Missing dates remain missing after failures. Successful source snapshots
    are reused without rewriting their original as-of/retrieval provenance.
    """
    if (start > end or end > date.today() or not series_ids
        or len(series_ids) != len(set(series_ids))
        or any(sid not in SOURCES for sid in series_ids)):
        raise VintageError("Invalid ALFRED historical backfill range or sources")
    if not 1 <= max_requests <= 180 or pause_seconds < 0:
        raise VintageError("ALFRED request budget must be between 1 and 180")
    if first_available is not None and set(first_available) != set(series_ids):
        raise VintageError("ALFRED publication bounds must cover every requested series")
    if skip_failed and any(
            sid not in series_ids or not isinstance(day, date)
            for sid, day in skip_failed):
        raise VintageError("Invalid ALFRED failed-month exclusion")
    requested_periods = [(sid, asof) for asof in _month_ends(start, end)
                         for sid in series_ids]
    periods = [(sid, asof) for sid, asof in requested_periods
               if first_available is None or asof >= first_available[sid]]
    excluded = len(requested_periods) - len(periods)
    pending = [(sid, day) for sid, day in periods
               if read_snapshot(root, sid, day) is None]
    # Failures from an earlier batch of this *same* UI job are held aside,
    # not treated as observed or erased. This prevents a failing month near
    # the start of history from starving later valid historical months.
    eligible = [item for item in pending if item not in (skip_failed or set())]
    fetched, failures = 0, []
    halted = None
    for sid, day in eligible[:max_requests]:
        try:
            fetch_snapshot(sid, day, api_key=api_key, client=client, root=root)
            fetched += 1
        except (VintageError, httpx.HTTPError, OSError, ValueError, KeyError) as exc:
            # A failing provider request must not dump a secret-bearing URL.
            failure = {"series_id": sid, "asof": day.isoformat()}
            failure.update(_snapshot_failure_diagnostic(exc))
            if isinstance(exc, httpx.HTTPStatusError):
                # 400/401/403 imply bad configuration or request schema;
                # 429 means immediate retry would worsen rate limiting.
                if exc.response.status_code in (400, 401, 403, 429):
                    halted = failure["reason"]
            failures.append(failure)
            if halted:
                break
        if pause_seconds:
            time.sleep(pause_seconds)
    outstanding = [(sid, day) for sid, day in periods
                   if read_snapshot(root, sid, day) is None]
    return {
        "provider": "ALFRED",
        "status": "blocked" if halted else "complete" if not outstanding else "partial",
        "halted_reason": halted,
        "source_vintages_requested": len(periods),
        "prepublication_excluded": excluded,
        "already_cached_before_run": len(periods)-len(pending),
        "downloaded_now": fetched, "failed_now": failures,
        "attempted_now": fetched + len(failures),
        "missing_after_run": len(outstanding),
        "next_missing": ({"series_id": outstanding[0][0],
                          "asof": outstanding[0][1].isoformat()}
                         if outstanding else None),
        "max_requests_per_invocation": max_requests,
        "notes": ("Resolve FRED authentication/request failure before retrying. "
                  "Already cached source snapshots are preserved."
                  if halted else
                  "Repeat the identical --backfill command until missing_after_run "
                  "is zero. A missing source snapshot is never interpolated."),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch genuine dated ALFRED series snapshots")
    parser.add_argument("--check", action="store_true",
                        help="Probe one USREC request safely before a large historical import")
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--series", action="append", choices=sorted(SOURCES),
                        help="Repeat to select multiple data series")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--backfill", action="store_true",
                        help="Resume multi-year range, up to 180 missing requests per run")
    parser.add_argument("--max-requests", type=int, default=180,
                        help="Per-run backfill API budget (1–180)")
    args = parser.parse_args()
    key = os.environ.get("FRED_API_KEY", "").strip()
    if args.check:
        with httpx.Client(timeout=25, headers={"User-Agent": "GlobalCapitalMonitor/0.2"}) as client:
            result = probe_access(api_key=key, client=client)
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "ready" else 1
    if not args.start or not args.end or not args.series:
        parser.error("--start, --end and at least one --series are required for import")
    if args.end > date.today() or args.start > args.end:
        parser.error("Historical as-of dates must be ordered and not in the future")
    if len(args.series) != len(set(args.series)):
        parser.error("Do not repeat the same series ID")
    months = _month_ends(args.start, args.end)
    if not args.backfill and len(months) * len(args.series) > 180:
        parser.error("At most 180 source requests per run; use --backfill for longer history")
    if not 1 <= args.max_requests <= 180:
        parser.error("--max-requests must be 1–180")
    if not _key_format_ok(key):
        parser.error("FRED_API_KEY must be a registered 32-character lowercase alphanumeric key")
    if args.backfill:
        with httpx.Client(timeout=25, headers={"User-Agent": "GlobalCapitalMonitor/0.2"}) as client:
            first_available = first_available_vintages(
                args.series, api_key=key, client=client)
            result = backfill_batch(args.start, args.end, args.series,
                                    api_key=key, client=client, root=args.root,
                                    max_requests=args.max_requests,
                                    first_available=first_available)
        print(json.dumps(result, indent=2))
        return 1 if result["failed_now"] else 0
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
