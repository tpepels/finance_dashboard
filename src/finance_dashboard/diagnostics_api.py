"""Private diagnostic status, structured console and redacted support ZIP.

Credentials, environment values, HTTP rejection bodies and raw server
stderr are excluded. On explicit ZIP preparation, a bounded set of literal
publisher data rows may be included for regression fixtures, with verified
source hashes and fixed original URLs. Full source payloads stay on the server.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO, StringIO
import csv
import json
import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import FastAPI, Header, Request

from .developer_logs import read_events
from .failure_journal import read_failures
from .runtime_release import release_info


def _console(events: list[dict]) -> list[dict]:
    rows = []
    for e in events[-200:]:
        if not isinstance(e, dict) or not all(
                isinstance(e.get(key), str)
                for key in ("at", "level", "scope", "event")):
            continue
        rows.append({
            "time": e["at"],
            "level": e["level"],
            "message": " ".join(str(value) for value in (
                e["scope"], e["event"], e.get("action"), e.get("status"),
                e.get("source_id"), e.get("reason"),
                ("HTTP " + str(e["http_status"])) if "http_status" in e else None,
            ) if value is not None),
        })
    return rows


def _status(events: list[dict], coverage: dict, accepting: bool, importing: bool) -> dict:
    # A 503 with Retry-After is an expected assessment wait, not a collector failure.
    # Historic logs lacked that distinction: treat old API 503 events as transient.
    now = datetime.now(timezone.utc)
    recent = []
    for event in events:
        if not isinstance(event, dict) or not isinstance(event.get("at"), str):
            continue
        try:
            observed_at = datetime.fromisoformat(event["at"])
            if (observed_at.tzinfo is not None
                    and now - timedelta(days=1) <= observed_at <= now):
                recent.append(event)
        except (ValueError, TypeError, OverflowError):
            continue
    failures = [e for e in recent
                if e.get("level") == "error"
                and not (e.get("stage") == "api" and e.get("http_status") == 503)]
    warnings = sum(e.get("level") == "warning" for e in recent)
    summaries = coverage.get("summary", {})
    groups = [group for group in summaries.values() if isinstance(group, dict)]
    attention = sum(group.get("needs_attention", 0) for group in groups)
    total = sum(group.get("total", 0) for group in groups)
    with_data = sum(group.get("with_data", 0) for group in groups)
    unresolved_failures = sum(group.get("collection_failed", 0) +
                              group.get("refresh_failed_with_data", 0)
                              for group in groups)
    if failures or unresolved_failures:
        colour, label = "red", "Source or processing failures"
    elif attention:
        colour, label = "orange", f"{attention} source histories need review"
    elif warnings:
        colour, label = "orange", "Recent source warnings"
    elif accepting or importing:
        colour, label = "orange", "Background updates in progress"
    else:
        colour, label = "green", "No source or runtime alerts"
    return {"colour": colour, "label": label, "recent_errors": len(failures),
            "warnings_last_24h": warnings, "sources_total": total,
            "sources_with_data": with_data,
            "sources_needing_attention": attention, "unresolved_source_failures": unresolved_failures,
            "assessment_running": accepting,
            "import_running": importing, "generated_at": now.isoformat()}


def _attention_publishers(items: list[dict]) -> list[dict]:
    """Group cached source issues for the status pop-up; no extra SQL/network.

    Each group retains the publisher and oldest stored observation. A healthy
    ingestion attempt can still leave a source stale; the summary does not
    mislabel it as a failed download or imply a manual retry is required.
    """
    providers: dict[str, dict] = {}
    for item in items[:1000]:
        if not isinstance(item, dict):
            continue
        key = str(item.get("provider") or "Other")
        group = providers.setdefault(key, {
            "provider": key, "count": 0, "oldest_observation": None,
            "stale": 0, "failed": 0,
        })
        group["count"] += 1
        if item.get("state") == "stale":
            group["stale"] += 1
        if item.get("last_attempt_state") == "failed":
            group["failed"] += 1
        observed = item.get("latest_source_date")
        if isinstance(observed, str) and (
                group["oldest_observation"] is None
                or observed < group["oldest_observation"]):
            group["oldest_observation"] = observed[:10]
    return sorted(providers.values(),
                  key=lambda x: (-x["count"], x["provider"]))[:8]


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

    def limitation_assessment(coverage: dict, accounting: dict | None = None,
                              dependencies: dict | None = None) -> dict:
        from .limitation_assessment import assess_limitations
        return assess_limitations(
            coverage=coverage, document=research_document,
            snapshot=app.state.acceptance.peek(), accounting=accounting,
            icio_dependencies=dependencies, release=release_info())

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
        from .icio_dependency_audit import classify_icio_dependencies
        return limitation_assessment(coverage, manifest, classify_icio_dependencies(original))

    @app.get("/api/diagnostics")
    def diagnostics():
        """Cheap status lamp; isolate failed observers without expensive retries."""
        unavailable = []
        def observe(name, read, fallback):
            try:
                return read()
            except Exception:
                # Don't spam the disk-backed failure journal on every status
                # poll. Export preparation separately records failure traces.
                unavailable.append(name)
                return fallback
        release = release_info()
        events = observe("event_log",
                         lambda: read_events(limit=400, since=release["activated_at"]), [])
        health = observe("source_health",
                         lambda: app.state.source_health_cache.status(schedule=False),
                         {"state":"unavailable", "snapshot":None,
                          "error":"source_health_unavailable"})
        if not isinstance(health, dict):
            unavailable.append("source_health")
            health = {"state": "unavailable", "snapshot": None}
        cached = health.get("snapshot") or {}
        if not isinstance(cached, dict):
            unavailable.append("source_health_snapshot")
            cached = {}
        if cached and not {"groups", "attention_items"} <= set(cached):
            unavailable.append("source_health_snapshot")
        groups = cached.get("groups", [])
        if (not isinstance(groups, list) or any(
                not isinstance(row, dict)
                or not isinstance(row.get("id"), str)
                or any(type(row.get(key)) is not int
                       for key in ("total", "with_data", "attention"))
                or any(type(row.get(key, 0)) is not int
                       for key in ("collection_failed", "refresh_failed_with_data"))
                for row in groups)):
            if cached:
                unavailable.append("source_health_snapshot")
            groups = []
        attention_items = cached.get("attention_items", [])
        if not isinstance(attention_items, list):
            unavailable.append("source_health_snapshot")
            attention_items = []
        summaries = {
            row["id"]: {
                "total": row["total"], "with_data": row["with_data"],
                "needs_attention": row["attention"],
                "collection_failed": row.get("collection_failed", 0),
                "refresh_failed_with_data": row.get("refresh_failed_with_data", 0),
            } for row in groups
        }
        accepting = observe("assessment_status",
                            lambda: app.state.acceptance.loading, None)
        importing = observe("import_status", importer.running, None)
        status = _status(events, {"summary": summaries}, accepting, importing)
        # Older on-disk health snapshots predate per-state counters. Preserve
        # the red severity from their already-cached attention items without
        # running SQL or waiting for the next background rebuild.
        failed_items = sum(item.get("state") in (
            "collection_failed", "refresh_failed_with_data")
            for item in attention_items if isinstance(item, dict))
        if failed_items and status["unresolved_source_failures"] < failed_items:
            status["unresolved_source_failures"] = failed_items
            status.update(colour="red", label="Source failures require attention")
        status["release_id"] = release["release_id"]
        if (not cached or health.get("state") == "unavailable"
                or "source_health_snapshot" in unavailable):
            if status["colour"] != "red":
                status.update(colour="orange", label="Source health not evaluated")
        if health.get("error") and status["colour"] != "red":
            status.update(colour="orange", label="Source-health check unavailable")
        updates = observe("data_changes", app.state.data_change_coordinator.status,
                          {"state":"unavailable", "events_reconciled":None})
        if updates["state"] == "unavailable":
            status.update(colour="red", label="Data processing status unavailable")
        elif updates["state"] == "failed":
            status.update(colour="red", label="Downstream reconciliation failed")
        elif updates["state"] == "pending" and status["colour"] == "green":
            status.update(colour="orange", label="Processing new source evidence")
        elif health.get("state") == "refreshing" and status["colour"] == "green":
            status.update(colour="orange", label="Updating source-health snapshot")
        acceptance = observe("scientific_assessment", app.state.acceptance.peek, None)
        collection = observe("collection_status",
                             app.state.collection_workflow.status,
                             {"state":"unavailable", "running":None, "repair":{}})
        running = collection.get("running") if collection.get("state") != "unavailable" else None
        status["collection_running"] = running
        repair = collection.get("repair") or {}
        status["collection_progress"] = {
            "completed": repair.get("completed"),
            "total": repair.get("total"),
            "stage": repair.get("stage"),
        } if running else None
        if running:
            if status["colour"] == "green":
                status.update(colour="orange", label="Collecting source histories")
            elif status["colour"] == "red":
                status["label"] = "Collection running; source issues remain"
        from .data_hub import automation_status
        automation = observe("scheduler", automation_status, {"state":"unavailable"})
        persistent = observe("failure_journal", read_failures,
                             {"state":"unavailable", "failures":[]})
        if persistent["state"] == "invalid":
            status.update(colour="red", label="Diagnostic failure journal is corrupt")
        elif unavailable and status["colour"] == "green":
            status.update(colour="orange", label="Some diagnostic components unavailable")
        status["unavailable_diagnostic_components"] = unavailable
        last = persistent["failures"][-1] if persistent["failures"] else None
        recent = None if last is None else {
            "id": last["id"], "release_id": last["release_id"],
            "previous_release": last["release_id"] != release["release_id"],
            "exception_type": last["exception_type"],
            "component": last["component"], "stage": last["stage"],
            "last_at": last["last_at"], "count": last["count"],
        }
        return {"status": status, "release": release,
                "failure_evidence": {"journal_state": persistent["state"],
                                     "latest": recent},
                "console": _console(events), "source_summary": summaries,
                "source_health": {
                    "state": health.get("state"),
                    "checked_at": cached.get("calculated_at"),
                    "error": health.get("error"),
                    "attention_providers": _attention_publishers(
                        attention_items),
                },
                "data_changes": {
                    "state": updates["state"],
                    "events_reconciled": updates["events_reconciled"],
                    "research_evaluated_at": acceptance.evaluated_at.isoformat()
                                             if acceptance else None,
                },
                "update_progress": {
                    "health": {
                        "state": health.get("state"),
                        "snapshot": {
                            "calculated_at": cached.get("calculated_at"),
                            "sources": cached.get("sources"),
                            "attention_items": attention_items,
                        } if cached else None,
                        "automation": automation,
                        "downstream_updates": {"state": updates["state"]},
                        "scientific_assessment": {
                            "running": accepting,
                            "evaluated_at": acceptance.evaluated_at.isoformat()
                                            if acceptance else None,
                        },
                    },
                    "collection": {
                        "running": collection.get("running"),
                        "manual_files_count": len(collection.get("manual_files") or []),
                    },
                }}

    @app.get("/api/data/debug-console")
    def data_debug_console():
        """Independent redacted evidence survives partial subsystem outages."""
        sections_unavailable = []
        def read(name, factory, fallback):
            try:
                return factory()
            except Exception as exc:
                # Debug console is an explicit operator action, unlike the
                # cheap polled status; a redacted error record is useful here.
                from .failure_journal import record_failure
                record_failure("macro", "debug_console_" + name, exc)
                sections_unavailable.append(name)
                return fallback
        release = release_info()
        status, events, coverage = read("source_snapshot", snapshot,
            ({"colour": "red", "label": "Source health unavailable",
              "release_id": release["release_id"]},
             [], {"state": "unavailable", "summary": {}, "items": []}))
        from .data_hub import human_overview
        manual = read("manual_sources", app.state.manual_sources.status,
                      {"state": "unavailable", "datasets": []})
        original = read("original_import", importer.public_status,
                        {"state": "unavailable"})
        operations = read("maintenance", maintenance.list,
                          {"active_job_id": None, "jobs": []})
        overview = read("human_overview",
                        lambda: human_overview(coverage, manual, operations, original),
                        {"state": "unavailable"})
        return {
            "release": release, "status": status,
            "human_overview": overview,
            "events": events, "failure_journal": read(
                "failure_journal", read_failures,
                {"state": "unavailable", "failures": []}),
            "source_coverage": coverage,
            "acquisition": manual,
            "original_import": original,
            "maintenance": operations,
            "publisher_policy": read("publisher_policy", policy_summary,
                                     {"state": "unavailable", "publishers": []}),
            "diagnostic_sections": {
                "status": "complete" if not sections_unavailable else "partial",
                "unavailable": sections_unavailable},
            "note": "Credentials, raw source responses and portfolio holdings are excluded.",
        }

    def _build_debug_zip_bytes() -> bytes:
        # Independent diagnostic sections must survive corruption of an
        # unrelated source/archive subsystem. Every omission is reported
        # explicitly, not replaced with a fabricated clean result.
        problems = []
        def safe_section(name, call, fallback):
            try:
                return call()
            except Exception as exc:
                from .failure_journal import record_failure
                record_failure("macro", "diagnostic_" + name, exc)
                problems.append({"section": name, "state": "unavailable",
                                 "reason": "diagnostic_section_failed"})
                return fallback

        release = release_info()
        status, events, coverage = safe_section(
            "source_snapshot", snapshot, (
                {"colour": "red", "label": "Source health unavailable",
                 "sources_total": None, "sources_with_data": None,
                 "sources_needing_attention": None, "release_id": release["release_id"]},
                [], {"asof": None, "summary": {}, "items": [], "state": "unavailable"}))
        policy = safe_section("publisher_policy", policy_summary,
                              {"publishers": [], "state": []})
        operations = safe_section("maintenance", maintenance.list,
                                  {"active_job_id": None, "jobs": []})
        source_audit = safe_section(
            "original_method_audit", lambda: _original_method_summary(importer.evidence),
            {"archives": [], "truncated": True,
             "source_archive_bytes_reverified": False,
             "state": "unavailable"})
        from .data_hub import human_overview, automation_status
        scheduler = safe_section("scheduler", automation_status,
                                 {"state": "unavailable"})
        manual = safe_section("manual_sources", app.state.manual_sources.status,
                              {"datasets": [], "jobs": [], "queued": 0,
                               "deferred": 0, "active": False})
        importer_status = safe_section("original_import", importer.public_status,
                                      {"state": "unavailable"})
        overview = safe_section(
            "human_overview", lambda: human_overview(
                coverage, manual, operations, importer_status),
            {"state": "unavailable", "acquisition": {"files_requiring_upload": []}})
        failure_csv, failure_manifest = safe_section(
            "icio_failure_ledger",
            lambda: _accounting_failures_csv(source_audit, release["release_id"]),
            ("", {"failure_equations_exported": 0,
                  "complete_for_exported_matrices": False,
                  "annual_matrices_without_complete_failure_ledger": [],
                  "state": "unavailable"}))
        from .icio_dependency_audit import classify_icio_dependencies
        dependencies = safe_section(
            "icio_dependencies", lambda: classify_icio_dependencies(source_audit),
            {"status": "unavailable"})
        limits = safe_section(
            "limitation_assessment",
            lambda: limitation_assessment(coverage, failure_manifest, dependencies),
            {"scientific_acceptance": {"state": "unavailable"},
             "questions": [], "method_register": [], "findings": [],
             "state": "unavailable"})
        bundle = BytesIO()
        with ZipFile(bundle, "w", compression=ZIP_DEFLATED) as archive:
            def put(name, data):
                archive.writestr(name, json.dumps(data, sort_keys=True, indent=2,
                                                 default=str) + "\n")
            put("diagnostics/release.json", {
                **release, "reset_policy": "current_deployed_build_only",
                "immutable_evidence_preserved": True})
            put("diagnostics/status.json", status)
            put("diagnostics/scheduler.json", {
                **scheduler,
                "scope": "observed_in_process_state",
                "note": ("A configured refresh flag does not establish that a cycle "
                         "ran. A missing or unobserved next deadline is not an "
                         "estimate of the next ingestion time."),
            })
            put("diagnostics/console.json", _console(events))
            put("diagnostics/events.json", events)
            put("diagnostics/failure-journal.json", read_failures())
            put("diagnostics/source-coverage.json", {**coverage, "release": release})
            # A small, literal set of publisher rows makes failing source
            # parsers reproducible from the user's next diagnostic ZIP.
            # Each input is checked against the immutable source archive hash;
            # rejected HTML/error responses and complete original files are
            # never placed in the ZIP. Sampling failures do not block export.
            try:
                from .source_fixture_samples import collect_failure_samples
                samples = collect_failure_samples(
                    Path(os.environ.get("FINANCE_SOURCE_EVIDENCE_DIR",
                                        "/data/source-evidence")),
                    coverage.get("items", []))
            except Exception as exc:
                from .failure_journal import record_failure
                record_failure("macro", "diagnostic_fixture_samples", exc)
                problems.append({"section": "fixture_samples", "state": "unavailable",
                                 "reason": "diagnostic_section_failed"})
                samples = {"schema_version": 1, "samples": [],
                           "unavailable": [{"reason": "source_sampling_failed"}],
                           "warning": "Source sample collection failed. Other diagnostics remain available."}
            put("diagnostics/source-fixture-samples.json", samples)
            put("diagnostics/icio-consumer-dependencies.json", dependencies)
            put("diagnostics/limitation-assessment.json", limits)
            put("diagnostics/research-limitation-matrix.json", {
                "scientific_acceptance": limits["scientific_acceptance"],
                "questions": limits["questions"],
                "method_register": limits["method_register"],
            })
            # Record exactly what is blocking each question before the owner
            # exports the next ZIP, without requiring a separate button.
            # A failure here must not discard the rest of the diagnostics.
            try:
                from .research_status import research_next_actions
                next_actions = research_next_actions(
                    app.state.acceptance.peek(), research_document)
            except Exception as exc:
                from .failure_journal import record_failure
                record_failure("macro", "diagnostic_research_next_actions", exc)
                problems.append({"section": "research_next_actions", "state": "unavailable",
                                 "reason": "diagnostic_section_failed"})
                next_actions = {
                    "status": "unavailable", "evaluated_at": None,
                    "questions": [], "next_action_counts": {},
                    "reason": "research_next_actions_failed",
                }
            put("diagnostics/research-next-actions.json", next_actions)
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
            put("diagnostics/downstream-reconciliation.json", {
                "coordinator": app.state.data_change_coordinator.status(),
                "scientific_assessment": {
                    "running": app.state.acceptance.loading,
                    "evaluated_at": (
                        app.state.acceptance.peek().evaluated_at.isoformat()
                        if app.state.acceptance.peek() else None),
                },
                "source_health": app.state.source_health_cache.status(schedule=False),
                "note": "Post-commit source changes trigger a debounced source-health "
                        "scan and scientific acceptance. Current state is operational, "
                        "not proof of a new publisher release.",
            })
            put("diagnostics/original-import.json", importer_status)
            put("diagnostics/original-method-audit.json",
                {**source_audit, "release": release})
            put("diagnostics/icio-accounting-failures-manifest.json",
                {**failure_manifest, "release": release})
            archive.writestr("diagnostics/icio-accounting-failures.csv", failure_csv)
            put("diagnostics/section-health.json", {
                "status": "complete" if not problems else "partial",
                "unavailable_sections": problems,
                "collection_in_progress": safe_section(
                    "collection_state",
                    lambda: bool(app.state.collection_workflow.status().get("running", False)),
                    False),
                "note": ("A partial export retains the available evidence. "
                         "Unavailable sections must never be interpreted as healthy."),
            })
            archive.writestr("README.txt",
                "Global Capital Monitor build: " + release["release_id"] + "\n"
                "Release activated: " + str(release["activated_at"] or "not recorded") + "\n"
                "Current-build events and maintenance jobs are shown. "
                "The independent failure-journal.json retains bounded sanitized "
                "exception classes, application call sites, error stages and release "
                "identities across deployments. A missing journal means no failure "
                "has been recorded by this facility; previous exports cannot be reconstructed. "
                "The latest collection-run snapshot is also retained across builds. "
                "Small hash-verified original publisher row samples for WID, BLS "
                "and World Bank may appear in source-fixture-samples.json. Missing "
                "source bytes are reported without substitutions. The full "
                "original data remain on the server. "
                "Original evidence, research history, and backups are retained.\n"
                "Redacted diagnostic bundle with full source status, per-role publisher "
                "attempts, original hashes, manual fallback links, accounting residuals, "
                "source audit CSV, cross-question limitation assessment (JSON/CSV), "
                "per-question next actions with core and supplemental evidence "
                "counts, registered methodological caveats, and maintenance outcomes. "
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
