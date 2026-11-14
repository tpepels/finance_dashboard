"""Single operator-facing data health and acquisition API.

The Data page reports aggregate results and exact manual-fallback files only.
Detailed evidence, raw source identities and complete job journals remain in
the existing redacted developer diagnostic ZIP.
"""
from __future__ import annotations

import os

from fastapi import FastAPI, Body, Header, Request
from .original_uploads import _guard
from .runtime_release import release_info


_TERMINAL = {"complete", "partial", "failed", "manual_required", "interrupted"}

def automation_status() -> dict:
    """Only observed scheduler transitions; never infer a deadline from source age."""
    from .standalone import scheduled_refresh_status
    enabled = os.environ.get("FINANCE_AUTO_REFRESH", "1").strip().lower() in (
        "1", "true", "on", "yes")
    raw = scheduled_refresh_status()
    return {
        "scheduled_refresh_enabled": enabled,
        "interval_seconds": int(os.environ.get("REFRESH_INTERVAL_SECONDS", "86400")),
        "automatic_post_ingestion_updates": True,
        "refresh_running": enabled and raw["refresh_running"] is True,
        "refresh_state": raw["refresh_state"] if enabled else "disabled",
        "next_refresh_at": raw["next_refresh_at"] if enabled else None,
        "last_refresh_finished_at": raw["last_refresh_finished_at"] if enabled else None,
    }



def _recent(jobs: list[dict], dataset: str) -> dict | None:
    return next((item for item in jobs if item["dataset"] == dataset), None)


def human_overview(coverage: dict, manual: dict, operations: dict,
                   original: dict | None = None) -> dict:
    """One aggregation boundary; never claim stored history is fully current."""
    summaries = coverage.get("summary", {})
    groups = []
    for family, label in (
        ("macro", "Economic data"),
        ("markets", "Market prices"),
        ("fx", "Exchange rates"),
    ):
        group = summaries.get(family, {})
        groups.append({
            "id": family, "label": label,
            "total": int(group.get("total") or 0),
            "with_data": int(group.get("with_data") or 0),
            "attention": int(group.get("needs_attention") or 0),
        })

    jobs = manual.get("jobs", [])
    latest = [_recent(jobs, d["id"]) for d in manual.get("datasets", [])]
    latest = [item for item in latest if item is not None]
    fallback = []
    for spec in manual.get("datasets", []):
        job = _recent(jobs, spec["id"])
        if not job or job["status"] != "manual_required":
            continue
        roles = {r["id"]: r for r in (spec.get("roles", []) +
                                     spec.get("manual_files", []))}
        for role_id, code in sorted((job.get("failed_roles") or {}).items()):
            role = roles.get(role_id)
            if role is None:
                continue
            fallback.append({
                "job_id": job["id"], "dataset": spec["id"], "source": spec["title"],
                "role": role_id, "name": role["label"],
                "url": role["download_url"], "accept": role["accept"],
                "max_bytes": role["max_bytes"], "reason": code,
            })
    last_sync = next((j for j in operations.get("jobs", [])
                      if j.get("status") in _TERMINAL), None)
    active_sync = next((j for j in operations.get("jobs", [])
                        if j.get("id") == operations.get("active_job_id")), None)
    manual_active = sum(job["status"] in ("queued", "downloading", "running", "deferred")
                        for job in latest)
    return {
        "release": release_info(),
        "asof": coverage.get("asof"),
        "groups": groups,
        "sources": {
            "total": sum(g["total"] for g in groups),
            "with_data": sum(g["with_data"] for g in groups),
            "needs_attention": sum(g["attention"] for g in groups),
        },
        "acquisition": {
            "queued": manual.get("queued", 0),
            "deferred": manual.get("deferred", 0),
            "running": bool(manual.get("active")),
            "active_sources": manual_active,
            "manual_files_needed": len(fallback),
            "successful_sources": sum(job["status"] == "complete" for job in latest),
            "problem_sources": sum(job["status"] in ("partial", "failed", "interrupted")
                                   for job in latest),
            "files_requiring_upload": fallback,
            "recent_jobs": [{
                "dataset": job["dataset"], "status": job["status"],
                "method": job.get("method"),
                "retry_at_unix": job.get("retry_at_unix"),
                "completed_files": len(job.get("downloaded") or {}),
                "failed_files": len(job.get("failed_roles") or {}),
                "error_code": job.get("error_code"),
            } for job in latest],
        },
        "sync": {
            "active": None if not active_sync else {
                "action": active_sync.get("action"), "status": active_sync.get("status"),
                "completed": active_sync.get("completed"),
                "total": active_sync.get("total"),
            },
            "last": None if not last_sync else {
                "action": last_sync.get("action"), "status": last_sync.get("status"),
                "finished_at": last_sync.get("finished_at"),
                "error_code": last_sync.get("error_code"),
            },
        },
        "original_import": None if original is None else {
            "running": bool(original.get("active")),
            "jobs_with_issues": sum(j.get("status") in ("failed", "partial", "interrupted")
                                    for j in original.get("jobs", [])),
        },
    }


def install_data_hub(app: FastAPI, *, db, catalog, market_registry,
                     maintenance, valid_sources: set[str], valid_markets: set[str]):
    from .source_coverage import build_coverage

    from .collection_workflow import CollectionWorkflow, SourceHealthCache

    app.state.collection_workflow = CollectionWorkflow(
        app.state.manual_sources, maintenance,
        valid_sources=valid_sources, valid_markets=valid_markets)
    app.state.source_health_cache = SourceHealthCache(
        lambda: build_coverage(db, catalog["series"], market_registry))
    # Committed ingestion and accepted original files fan out to both
    # downstream assessments. A coalesced queue prevents 426 independent
    # expensive scientific evaluations during a bulk refresh.
    from .data_change_bus import DataChangeCoordinator, subscribe
    app.state.data_change_coordinator = DataChangeCoordinator(
        app.state.acceptance, app.state.source_health_cache)
    subscribe(db, app.state.data_change_coordinator)
    app.state.manual_sources.accepted = app.state.data_change_coordinator.changed

    @app.get("/api/data/collection")
    def collection_status():
        """Fast status: no SQL, publisher requests or original-file hashing."""
        return app.state.collection_workflow.status()

    @app.post("/api/data/collection/start", status_code=202)
    def collection_start(request: Request, browser: dict | None = Body(default=None),
                         x_gcm_action: str | None = Header(default=None)):
        _guard(request, x_gcm_action)
        profile = browser.get("browser") if isinstance(browser, dict) else None
        return app.state.collection_workflow.start(profile)

    @app.get("/api/data/health")
    def data_health(refresh: bool = False):
        """Cached coverage snapshot, refreshed by an independent worker."""
        evaluated = app.state.acceptance.peek()
        return {**app.state.source_health_cache.status(refresh=refresh),
                "automation": automation_status(),
                "downstream_updates": app.state.data_change_coordinator.status(),
                "scientific_assessment": {
                    "running": app.state.acceptance.loading,
                    "evaluated_at": evaluated.evaluated_at.isoformat() if evaluated else None,
                }}

    @app.get("/api/data/overview")
    def data_overview():
        """Compatibility endpoint for detailed research and agent auditing."""
        return human_overview(
            build_coverage(db, catalog["series"], market_registry),
            app.state.manual_sources.status(), maintenance.list(),
            app.state.original_imports.public_status())

    @app.post("/api/data/acquire", status_code=202)
    def acquire_all(request: Request, browser: dict | None = Body(default=None),
                    x_gcm_action: str | None = Header(default=None)):
        """Compatibility alias for a single durable collection run."""
        _guard(request, x_gcm_action)
        profile = browser.get("browser") if isinstance(browser, dict) else None
        return app.state.collection_workflow.start(profile)
