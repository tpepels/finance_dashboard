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


def _original_method_summary(root) -> dict:
    """Bounded advisory diagnostics, without copying gigabyte-scale originals.

    These metadata records are not source-byte verification. Their archived
    original and derived receipts must be independently verified by the
    canonical evidence reader before scientific promotion.
    """
    from pathlib import Path
    from .icio_editions import _read_native_derived
    base = Path(root) / "icio" / "other-editions"
    result = {"source_archive_bytes_reverified": False,
              "source_archive_hashes_not_rechecked_in_debug_export": True,
              "archives": [], "truncated": False}
    if not base.is_dir() or base.is_symlink():
        return result
    count = 0
    for parent in sorted(base.iterdir()):
        if parent.is_symlink() or not parent.is_dir():
            continue
        for manifest in sorted(parent.iterdir()):
            if manifest.is_symlink() or not manifest.is_dir():
                continue
            audit = manifest / "audit.json"
            if not audit.is_file() or audit.is_symlink() or audit.stat().st_size > 8_000_000:
                continue
            count += 1
            if count > 80:
                result["truncated"] = True
                return result
            try:
                row = json.loads(audit.read_bytes())
                sha = row["archive_sha256"]
                addon = _read_native_derived(root, sha)
                derived = addon["native"] if addon else row
                aux = addon["auxiliary"] if addon else row.get("auxiliary_numeric", {})
                years = derived.get("annual_matrices", [])
                result["archives"].append({
                    "filename": row.get("filename"),
                    "edition": row.get("edition"),
                    "table": row.get("table"),
                    "archive_sha256": sha,
                    "original_registration_status": row.get("status"),
                    "current_native_status": derived.get("native_validation_status", "not_evaluated"),
                    "derived_reassessment_present": addon is not None,
                    "native_years": [{
                        "year": y.get("year"),
                        "accounting_passed": y.get("accounting_passed"),
                        "industry_bridge_exclusions": y.get("industry_concordance", {}).get("excluded", []),
                        "incomplete_common_sectors": y.get("industry_concordance", {}).get("incomplete_targets", []),
                        "tiva_method": (y.get("tiva_reconstruction") or {}).get("method"),
                        "tiva_status": (y.get("tiva_reconstruction") or {}).get("status", "not_evaluated"),
                        "tiva_error_code": (y.get("tiva_reconstruction") or {}).get("error_code"),
                        "numerical_residual": (y.get("tiva_reconstruction") or {}).get("max_relative_residual"),
                    } for y in years[:40]],
                    "rejected_years": derived.get("rejected_matrices", []),
                    "expected_years": derived.get("expected_years"),
                    "observed_years": derived.get("observed_years", []),
                    "auxiliary_status": aux.get("status", "not_evaluated"),
                    "auxiliary_parsed_members": aux.get("parsed_members", 0),
                })
            except (ValueError, TypeError, KeyError, OSError):
                # A corrupt method record is a diagnostic finding in its own
                # right, not grounds to abort the complete support bundle.
                result["archives"].append({"status": "original_method_metadata_unreadable"})
    return result


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
            put("diagnostics/original-method-audit.json",
                _original_method_summary(importer.evidence))
            archive.writestr("README.txt",
                "Redacted diagnostic bundle. No secrets, raw HTTP responses, source files, "
                "portfolio holdings, database contents, or raw process stderr are included.\\n")
        bundle.seek(0)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return StreamingResponse(iter([bundle.getvalue()]), media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="finance-debug-' + stamp + '.zip"',
                     "Cache-Control": "no-store"})
