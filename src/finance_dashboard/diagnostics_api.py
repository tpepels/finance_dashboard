"""Private diagnostic status, structured console and redacted support ZIP.

No request URLs, provider payloads, credentials, environment values or raw server
stderr are exposed. The same short bounded diagnostic journal powers the UI and ZIP.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO, StringIO
import csv
import json
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import FastAPI, Header, Request

from .developer_logs import read_events
from .runtime_release import release_info


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
            try:
                row = json.loads(audit.read_bytes())
                sha = row["archive_sha256"]
                addon = _read_native_derived(root, sha)
                derived = addon["native"] if addon else row
                aux = addon["auxiliary"] if addon else row.get("auxiliary_numeric", {})
                years = derived.get("annual_matrices", [])
                result["archives"].append({
                    "filename": row.get("filename"),
                    "edition": derived.get("edition", row.get("edition")),
                    "table": derived.get("table", row.get("table")),
                    "sealed_edition": row.get("edition"),
                    "sealed_table": row.get("table"),
                    "source_identity_reconciliation": derived.get("source_identity_reconciliation"),
                    "header_schema": derived.get("header_schema"),
                    "archive_sha256": sha,
                    "original_registration_status": row.get("status"),
                    "current_native_status": derived.get("native_validation_status", "not_evaluated"),
                    "derived_reassessment_present": addon is not None,
                    "derived_method": addon.get("method") if addon else None,
                    "native_years": [{
                        "year": y.get("year"),
                        "original_member_sha256": y.get("original_member_sha256"),
                        "accounting_passed": y.get("accounting_passed"),
                        "accounting_failure_summary": y.get("accounting_failure_summary"),
                        "accounting_failure_details": y.get("accounting_failure_details"),
                        "publisher_account_schema": y.get("publisher_account_schema"),
                        "publisher_account_rows_present": y.get("publisher_account_rows_present"),
                        "observed_source_account_row_labels": y.get("observed_source_account_row_labels", []),
                        "row_failures": y.get("row_failures"),
                        "column_failures": y.get("column_failures"),
                        "output_vector_mismatches": y.get("output_vector_mismatches"),
                        "max_row_residual": y.get("max_row_residual"),
                        "max_column_residual": y.get("max_column_residual"),
                        "final_demand_categories": y.get("final_demand_categories"),
                        "country_split_conflicts": y.get("country_concordance", {}).get("ambiguous_unsplit_parents", []),
                        "industry_bridge_exclusions": y.get("industry_concordance", {}).get("excluded", []),
                        "incomplete_common_sectors": y.get("industry_concordance", {}).get("incomplete_targets", []),
                        "tiva_method": (y.get("tiva_reconstruction") or {}).get("method"),
                        "tiva_status": (y.get("tiva_reconstruction") or {}).get("status", "not_evaluated"),
                        "tiva_error_code": (y.get("tiva_reconstruction") or {}).get("error_code"),
                        "numerical_residual": (y.get("tiva_reconstruction") or {}).get("max_relative_residual"),
                    } for y in years],
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
    # Match annual source-content identities, not only ZIP container hashes.
    # Advisory inventory: original archive bytes are deliberately not reread
    # within this diagnostic endpoint.
    from .icio_editions import _annotate_source_year_collisions
    inventory = [{
        "filename": row.get("filename"), "edition": row.get("edition"),
        "table": row.get("table"), "archive_sha256": row.get("archive_sha256"),
        "expected_years": row.get("expected_years"),
        "annual_matrices": row.get("native_years", []),
    } for row in result["archives"] if row.get("archive_sha256")]
    _annotate_source_year_collisions(inventory)
    indexed = {row["archive_sha256"]: row for row in inventory}
    for row in result["archives"]:
        identity = indexed.get(row.get("archive_sha256"))
        if identity is not None:
            row["conflicting_years"] = identity["conflicting_years"]
            row["equivalent_annual_years"] = identity["equivalent_annual_years"]
            row["suppressed_equivalent_years"] = identity["suppressed_equivalent_years"]
    return result


ACCOUNTING_FAILURE_COLUMNS = (
    "release_id", "archive_filename", "archive_sha256", "derived_method",
    "edition", "table", "year", "original_member_sha256",
    "axis", "node_label", "csv_line_number", "country", "native_industry_code",
    "equation", "precision_classification",
    "signed_residual_usd_million", "absolute_residual_usd_million",
    "permissible_serialization_error_usd_million",
    "hypothetical_binary64_error_usd_million",
    "hypothetical_combined_error_usd_million",
    "intermediate_usd_million", "final_demand_usd_million",
    "row_output_usd_million", "net_taxes_usd_million",
    "value_added_usd_million", "publisher_output_usd_million",
)


def _accounting_failures_csv(summary: dict, release_id: str) -> tuple[str, dict]:
    """Full failure ledger from immutable derived reports, no originals reread.

    A complete v8+ report includes every failed identity, not just the worst
    residual or a sampled subset. Earlier versions are explicitly reported
    as unavailable, never as a scientifically clean pass.
    """
    dest = StringIO()
    writer = csv.DictWriter(dest, fieldnames=ACCOUNTING_FAILURE_COLUMNS,
                            lineterminator="\r\n")
    writer.writeheader()
    failures = 0
    missing_years = []
    for archive in summary.get("archives", []):
        for year in archive.get("native_years", []):
            breakdown = year.get("accounting_failure_summary")
            details = year.get("accounting_failure_details")
            expected = sum(year.get(k) or 0 for k in
                           ("row_failures", "column_failures", "output_vector_mismatches"))
            if (not isinstance(details, list) or not isinstance(breakdown, dict)
                    or breakdown.get("total_failed_equations") != len(details)
                    or len(details) != expected or
                    breakdown.get("all_failed_equations_recorded") is not True):
                missing_years.append({"filename": archive.get("filename"),
                                      "year": year.get("year"),
                                      "expected_failures": expected,
                                      "reason": "v8_failure_ledger_unavailable_or_incomplete"})
                continue
            for item in details:
                row = {key: item.get(key) for key in ACCOUNTING_FAILURE_COLUMNS}
                row.update({
                    "release_id": release_id,
                    "archive_filename": archive.get("filename"),
                    "archive_sha256": archive.get("archive_sha256"),
                    "derived_method": archive.get("derived_method"),
                    "edition": archive.get("edition"),
                    "table": archive.get("table"),
                    "year": year.get("year"),
                    "original_member_sha256": year.get("original_member_sha256"),
                })
                parts = item.get("source_components_usd_million") or {}
                for name in ("intermediate", "final_demand", "row_output",
                             "net_taxes", "value_added", "publisher_output"):
                    row[name + "_usd_million"] = parts.get(name)
                writer.writerow(row)
                failures += 1
    return dest.getvalue(), {
        "failure_equations_exported": failures,
        "annual_matrices_without_complete_failure_ledger": missing_years,
        "complete_for_exported_matrices": not missing_years,
        "classification_note":
            "Serialization bounds enforce the unchanged source-accounting gate. "
            "Binary64 summation bounds are hypothetical diagnostic models; "
            "they never certify failed original source accounts."
    }


def install_diagnostics(app: FastAPI, *, db, catalog, market_registry,
                        research_document, maintenance, importer):
    from .source_coverage import build_coverage
    from .source_policy import policy_summary

    def snapshot():
        release = release_info()
        events = read_events(limit=400, since=release["activated_at"])
        coverage = build_coverage(db, catalog["series"], market_registry)
        status = _status(events, coverage, app.state.acceptance.loading, importer.running())
        status["release_id"] = release["release_id"]
        return status, events, coverage

    def limitation_assessment(coverage: dict, accounting: dict | None = None) -> dict:
        from .limitation_assessment import assess_limitations
        return assess_limitations(
            coverage=coverage, document=research_document,
            snapshot=app.state.acceptance.peek(), accounting=accounting,
            release=release_info())

    @app.get("/api/diagnostics/limitation-assessment")
    def diagnostic_limitation_assessment():
        """On-demand full audit; do not burden dashboard status polling.

        Uses the already evaluated Phase 2 snapshot if present. If acceptance
        has not completed, research status is explicitly unavailable; this
        endpoint never starts another expensive acceptance evaluation.
        """
        _, _, coverage = snapshot()
        original = _original_method_summary(importer.evidence)
        _, manifest = _accounting_failures_csv(original, release_info()["release_id"])
        return limitation_assessment(coverage, manifest)

    @app.get("/api/diagnostics")
    def diagnostics():
        """Cheap status lamp; never recompute entire database coverage."""
        release = release_info()
        events = read_events(limit=400, since=release["activated_at"])
        health = app.state.source_health_cache.status(schedule=False)
        cached = health.get("snapshot") or {}
        summaries = {
            row["id"]: {
                "total": row["total"], "with_data": row["with_data"],
                "needs_attention": row["attention"],
            } for row in cached.get("groups", [])
        }
        status = _status(events, {"summary": summaries},
                         app.state.acceptance.loading, importer.running())
        status["release_id"] = release["release_id"]
        if not cached or health.get("state") == "unavailable":
            status.update(colour="orange", label="Source health snapshot not yet available")
        if health.get("error"):
            status.update(colour="orange", label="Cached source-health refresh unavailable")
        return {"status": status, "release": release,
                "console": _console(events), "source_summary": summaries}

    @app.get("/api/data/debug-console")
    def data_debug_console():
        """Full redacted current-state console, separate from human Data view."""
        status, events, coverage = snapshot()
        from .data_hub import human_overview
        manual = app.state.manual_sources.status()
        original = importer.public_status()
        operations = maintenance.list()
        return {
            "release": release_info(), "status": status,
            "human_overview": human_overview(coverage, manual, operations, original),
            "events": events, "source_coverage": coverage,
            "acquisition": manual,
            "original_import": original,
            "maintenance": operations,
            "publisher_policy": policy_summary(),
            "note": "Credentials, raw source responses and portfolio holdings are excluded.",
        }

    def _build_debug_zip_bytes() -> bytes:
        status, events, coverage = snapshot()
        release = release_info()
        policy = policy_summary()
        operations = maintenance.list()
        source_audit = _original_method_summary(importer.evidence)
        from .data_hub import human_overview
        manual = app.state.manual_sources.status()
        overview = human_overview(coverage, manual, operations,
                                  importer.public_status())
        failure_csv, failure_manifest = _accounting_failures_csv(
            source_audit, release["release_id"])
        limits = limitation_assessment(coverage, failure_manifest)
        bundle = BytesIO()
        with ZipFile(bundle, "w", compression=ZIP_DEFLATED) as archive:
            def put(name, data):
                archive.writestr(name, json.dumps(data, sort_keys=True, indent=2,
                                                 default=str) + "\n")
            put("diagnostics/release.json", {
                **release, "reset_policy": "current_deployed_build_only",
                "immutable_evidence_preserved": True})
            put("diagnostics/status.json", status)
            put("diagnostics/console.json", _console(events))
            put("diagnostics/events.json", events)
            put("diagnostics/source-coverage.json", {**coverage, "release": release})
            put("diagnostics/limitation-assessment.json", limits)
            put("diagnostics/research-limitation-matrix.json", {
                "scientific_acceptance": limits["scientific_acceptance"],
                "questions": limits["questions"],
                "method_register": limits["method_register"],
            })
            limitation_csv = StringIO()
            columns = ("id", "category", "severity", "status", "title",
                       "detail", "next_action", "analysis_ids", "source_ids",
                       "provenance", "evidence")
            limitation_writer = csv.DictWriter(limitation_csv,
                                               fieldnames=columns, lineterminator="\r\n")
            limitation_writer.writeheader()
            for finding in limits["findings"]:
                limitation_writer.writerow({
                    **finding,
                    "analysis_ids": json.dumps(finding["analysis_ids"]),
                    "source_ids": json.dumps(finding["source_ids"]),
                    "evidence": json.dumps(finding["evidence"], sort_keys=True),
                })
            archive.writestr("diagnostics/limitation-assessment.csv",
                             limitation_csv.getvalue())
            audit_items = coverage.get("items", [])
            audit_columns = ["release_id", "asof"] + sorted({
                key for row in audit_items for key in row.keys()})
            audit_csv = StringIO()
            writer = csv.DictWriter(audit_csv, fieldnames=audit_columns,
                                    lineterminator="\r\n")
            writer.writeheader()
            for row in audit_items:
                writer.writerow({
                    **{"release_id": release["release_id"], "asof": coverage.get("asof")},
                    **{key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list))
                       else value for key, value in row.items()},
                })
            archive.writestr("diagnostics/source-audit.csv", audit_csv.getvalue())
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
            put("diagnostics/data-overview.json", overview)
            put("diagnostics/manual-fallback-links.json",
                overview["acquisition"]["files_requiring_upload"])
            put("diagnostics/publisher-download-queue.json", {
                "datasets": manual["datasets"],
                "jobs": manual["jobs"],
                "queued": manual["queued"],
                "deferred": manual["deferred"],
                "active": manual["active"],
                "note": "Downloaded bytes are represented by SHA-256 receipts, not included.",
            })
            put("diagnostics/maintenance-complete.json", {
                "active_job_id": operations["active_job_id"],
                "jobs": [{
                    key: job.get(key) for key in (
                        "id", "action", "status", "created_at", "started_at",
                        "finished_at", "completed", "total", "current_item",
                        "stage", "error_code", "result")
                } for job in operations["jobs"]],
            })
            # The maintenance endpoint intentionally filters to the current
            # release. Preserve the separate server-owned collection outcome
            # across releases to avoid apparently empty troubleshooting ZIPs.
            put("diagnostics/collection-run.json",
                app.state.collection_workflow.status())
            put("diagnostics/original-import.json", importer.public_status())
            put("diagnostics/original-method-audit.json",
                {**source_audit, "release": release})
            put("diagnostics/icio-accounting-failures-manifest.json",
                {**failure_manifest, "release": release})
            archive.writestr("diagnostics/icio-accounting-failures.csv", failure_csv)
            archive.writestr("README.txt",
                "Global Capital Monitor build: " + release["release_id"] + "\n"
                "Release activated: " + str(release["activated_at"] or "not recorded") + "\n"
                "Current-build diagnostic events and maintenance jobs are shown. "
                "The latest collection-run snapshot is also retained across builds. "
                "Original evidence, research history, and backups are retained.\n"
                "Redacted diagnostic bundle with full source status, per-role publisher "
                "attempts, original hashes, manual fallback links, accounting residuals, "
                "source audit CSV, cross-question limitation assessment (JSON/CSV), "
                "registered methodological caveats, and maintenance outcomes. "
                "Browser cookies, credentials, "
                "signed redirect parameters, raw HTTP bodies, portfolio holdings and "
                "database contents are excluded.\n")
        return bundle.getvalue()

    from .diagnostic_exports import DiagnosticExportManager
    from .original_uploads import _guard
    from fastapi.responses import FileResponse, JSONResponse
    exports = DiagnosticExportManager(_build_debug_zip_bytes)
    app.state.diagnostic_exports = exports

    @app.get("/api/diagnostics/export-status")
    def diagnostic_export_status():
        """Always cheap: no source scans, SQL, or ZIP compression."""
        return exports.status()

    @app.post("/api/diagnostics/prepare", status_code=202)
    def prepare_diagnostics(request: Request, force: bool = False,
                            x_gcm_action: str | None = Header(default=None)):
        _guard(request, x_gcm_action)
        return exports.prepare(force=force)

    def send_prepared_export():
        path = exports.ready_file()
        if path is None:
            return JSONResponse(
                status_code=202, content={"state": exports.status()["state"],
                                          "detail": "Diagnostic export is not ready"},
                headers={"Cache-Control": "no-store", "Retry-After": "5"})
        stamp = exports.status()["prepared_at"] or ""
        slug = stamp.replace("-", "").replace(":", "")[:15]
        return FileResponse(
            path, media_type="application/zip",
            filename="finance-debug-" + release_info()["release_id"] + "-" + slug + ".zip",
            headers={"Cache-Control": "no-store"})

    @app.get("/api/diagnostics/export-file")
    def download_prepared_export():
        return send_prepared_export()

    @app.get("/api/diagnostics/download")
    def download_debug_zip():
        """Compatibility URL: return a cached file, never build synchronously."""
        return send_prepared_export()
