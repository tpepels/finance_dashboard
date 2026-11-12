"""Private diagnostic status, structured console and redacted support ZIP.

No request URLs, provider payloads, credentials, environment values or raw server
stderr are exposed. The same short bounded diagnostic journal powers the UI and ZIP.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from .developer_logs import read_events


def _console(events: list[dict]) -> list[dict]:
    return [{
        "time": e["at"],
        "level": e["level"],
        "message": " ".join(str(value) for value in (
            e["scope"], e["event"], e.get("action"), e.get("status"),
            e.get("source_id"), e.get("reason"),
            ("HTTP " + str(e["http_status"])) if "http_status" in e else None,
        ) if value is not None),
    } for e in events[-200:]]


def _status(events: list[dict], coverage: dict, accepting: bool, importing: bool) -> dict:
    # A 503 with Retry-After is an expected assessment wait, not a collector failure.
    # Historic logs lacked that distinction: treat old API 503 events as transient.
    now = datetime.now(timezone.utc)
    recent = []
    for event in events:
        try:
            if datetime.fromisoformat(event["at"]) >= now - timedelta(days=1):
                recent.append(event)
        except (ValueError, KeyError):
            continue
    failures = [e for e in recent
                if e["level"] == "error"
                and not (e.get("stage") == "api" and e.get("http_status") == 503)]
    summaries = coverage.get("summary", {})
    attention = sum(group.get("needs_attention", 0) for group in summaries.values()
                    if isinstance(group, dict))
    unresolved_failures = sum(group.get("collection_failed", 0) +
                              group.get("refresh_failed_with_data", 0)
                              for group in summaries.values() if isinstance(group, dict))
    if failures or unresolved_failures:
        colour, label = "red", "Errors require inspection"
    elif accepting or importing or attention or any(e["level"] == "warning" for e in recent):
        colour, label = "orange", "Data or research needs attention"
    else:
        colour, label = "green", "No current diagnostic issues"
    return {"colour": colour, "label": label, "recent_errors": len(failures),
            "sources_needing_attention": attention, "unresolved_source_failures": unresolved_failures,
            "assessment_running": accepting,
            "import_running": importing, "generated_at": now.isoformat()}


def install_diagnostics(app: FastAPI, *, db, catalog, market_registry, maintenance, importer):
    from .source_coverage import build_coverage
    from .source_policy import policy_summary

    def snapshot():
        events = read_events(limit=400)
        coverage = build_coverage(db, catalog["series"], market_registry)
        status = _status(events, coverage, app.state.acceptance.loading, importer.running())
        return status, events, coverage

    @app.get("/api/diagnostics")
    def diagnostics():
        status, events, coverage = snapshot()
        return {"status": status, "console": _console(events),
                "source_summary": coverage.get("summary", {})}

    @app.get("/api/diagnostics/download")
    def download_debug_zip():
        status, events, coverage = snapshot()
        policy = policy_summary()
        operations = maintenance.list()
        bundle = BytesIO()
        with ZipFile(bundle, "w", compression=ZIP_DEFLATED) as archive:
            def put(name, data):
                archive.writestr(name, json.dumps(data, sort_keys=True, indent=2,
                                                 default=str) + "\n")
            put("diagnostics/status.json", status)
            put("diagnostics/console.json", _console(events))
            put("diagnostics/events.json", events)
            put("diagnostics/source-coverage.json", coverage)
            # No source URLs or credentials; the publisher registry exposes
            # publisher names and quota/cooldown metadata only.
            put("diagnostics/publisher-policy.json", {
                "publishers": [{k: p.get(k) for k in ("id", "limit", "window_seconds",
                    "min_spacing_seconds", "operator_acknowledged")}
                    for p in policy.get("publishers", [])],
                "state": policy.get("state", []),
            })
            put("diagnostics/maintenance.json", {
                "active_job_id": operations["active_job_id"],
                "jobs": [{"action": j.get("action"), "status": j.get("status"),
                          "created_at": j.get("created_at"), "finished_at": j.get("finished_at"),
                          "error_code": j.get("error_code")}
                         for j in operations["jobs"]],
            })
            put("diagnostics/original-import.json", importer.public_status())
            archive.writestr("README.txt",
                "Redacted diagnostic bundle. No secrets, raw HTTP responses, source files, "
                "portfolio holdings, database contents, or raw process stderr are included.\\n")
        bundle.seek(0)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return StreamingResponse(iter([bundle.getvalue()]), media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="finance-debug-' + stamp + '.zip"',
                     "Cache-Control": "no-store"})
