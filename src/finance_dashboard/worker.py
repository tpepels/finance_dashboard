"""Separate refresh worker; explicit 'once' mode for predictable manual bootstraps."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
import json
import logging
import os
import time

from .providers import ProviderRouter, PROVIDER_CODES
from .source_capture import SourceAcquisition
from pathlib import Path
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .catalog import load_documents
from .database import make_engine, IngestionRun
from .service import IngestionService, safe_source_failure_code
from .source_policy import PolicyDeferred, PolicyViolation
from .refresh_coordinator import reserve_refresh
from .developer_logs import record_event

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RefreshTask:
    """A scheduled source operation independent of provider implementation."""
    family: str
    source_id: str
    execute: Callable[[], dict]
    progress_label: str
    provider_group: str | None = None


def execute_refresh_tasks(tasks: list[RefreshTask], *, progress=None,
                          stopped=None) -> int:
    """One failure/deferral/progress lifecycle for macro, market and FX jobs.

    Policy deferrals are non-retryable within this batch. Every task advances
    progress exactly once. Stored observations remain untouched on failure.
    """
    failures = 0
    unavailable = 0
    processed = 0
    total = len(tasks)
    # A confirmed publisher-wide hourly quota cannot be repaired by
    # immediately attempting twenty more series using the same source host.
    # Do not mark those unattempted sources as fresh or failed; retain their
    # previous acquisition history for the next scheduled cycle.
    unavailable_groups: set[str] = set()
    suppressed: dict[str, int] = {}
    def publish_progress(index: int, task: RefreshTask) -> int:
        if progress is None:
            return 0
        try:
            progress(index, total, task.progress_label)
            return 0
        except Exception as exc:
            # A status observer may fail without cancelling source ingestion.
            from .failure_journal import record_failure
            record_failure("macro", "refresh_progress", exc,
                           series_id=task.source_id)
            record_event("macro", "collector_failed", level="error",
                         action="refresh_progress", stage="progress",
                         source_id=task.source_id, reason="provider_failed")
            return 1

    for index, task in enumerate(tasks, 1):
        if stopped is not None and stopped.is_set():
            break
        if task.provider_group is not None and task.provider_group in unavailable_groups:
            failures += 1  # incomplete refresh, but no new failed IngestionRun
            suppressed[task.provider_group] = suppressed.get(task.provider_group, 0) + 1
            record_event(task.family, "source_deferred", level="warning",
                         action="publisher_quota_exhausted", status="deferred",
                         source_id=task.source_id,
                         reason="source_policy_deferred")
            failures += publish_progress(index, task)
            processed += 1
            continue
        try:
            report = task.execute()
            if isinstance(report, dict) and report.get("status") == "unavailable":
                unavailable += 1
                record_event(task.family, "source_unavailable", level="warning",
                             source_id=task.source_id, reason="wid_measure_unavailable")
            else:
                log.info("%s refreshed: received=%s versions_added=%s",
                         task.family,
                         report.get("received") if isinstance(report, dict) else "unknown",
                         report.get("versions_added") if isinstance(report, dict) else "unknown")
        except PolicyDeferred as exc:
            failures += 1
            if task.provider_group is not None and exc.reason in {
                    "rolling_window_limit", "publisher_cooldown"}:
                unavailable_groups.add(task.provider_group)
            record_event(task.family, "source_deferred", level="warning",
                         source_id=task.source_id,
                         reason="source_policy_deferred")
            log.warning("%s source deferred by canonical publisher policy: %s",
                        task.family, task.source_id)
        except Exception as exc:
            failures += 1
            from .failure_journal import record_failure
            record_failure(task.family, "execute_source_task", exc,
                           series_id=task.source_id)
            record_event(task.family, "source_failed", level="error",
                         source_id=task.source_id,
                         reason=safe_source_failure_code(exc),
                         # These identifiers come exclusively from application-
                         # controlled publisher-policy contracts, never raw
                         # response text, URLs or credentials. This distinguishes
                         # missing origin rules from user network acknowledgement
                         # and transport guards on a failed Swinkels retry.
                         stage=(f"{exc.policy_id}:{exc.reason}"
                                if isinstance(exc, PolicyViolation) else None))
            log.error("%s refresh failed: %s (publisher details redacted)",
                      task.family, task.source_id)
        failures += publish_progress(index, task)
        processed += 1
    for group, count in sorted(suppressed.items()):
        record_event("macro", "stage_finished", level="warning",
                     action="publisher_quota_exhausted", status="deferred",
                     stage=group, failed=count)
        log.warning("%s: %d additional sources left unattempted after source quota exhaustion",
                    group, count)
    if tasks:
        # Emit a final bounded summary after every batch, including partial
        # success or early preemption. The full per-series ingestion history
        # remains in the source audit; quota skips are separate events.
        scope = "macro" if tasks[0].family == "macro" else "markets"
        record_event(scope, "stage_finished", action="source_refresh_batch",
                     status=("interrupted" if processed < total else
                             "partial" if failures or unavailable else "complete"),
                     completed=processed, total=total, failed=failures,
                     unavailable=unavailable)
    return failures


def refresh_all(engine, full: bool = False, providers: set[str] | None = None,
                series_ids: set[str] | None = None, progress=None,
                stopped=None, skip_complete_pinned: bool = False,
                attention_only: bool = False,
                preflight_only: bool = False) -> int:
    """Refresh independent sources even when an advisory planning guard fails."""
    planning_failures = 0

    def planner_fault(phase: str, error: Exception, *, series_id: str | None = None):
        nonlocal planning_failures
        planning_failures += 1
        from .failure_journal import record_failure
        record_failure("macro", phase, error, series_id=series_id)
        category = type(error).__name__
        if category not in {"OperationalError", "IntegrityError", "ProgrammingError",
                            "StatementError", "ValueError", "TypeError", "KeyError",
                            "AttributeError", "RuntimeError", "OSError", "OverflowError"}:
            category = "UnexpectedError"
        record_event("macro", "collector_failed", level="error",
                     action="scheduled_refresh_plan", stage=phase,
                     reason=category, source_id=series_id)

    stage = "instantiate_router"
    client = None
    try:
        client = ProviderRouter()
        stage = "validate_series"
        unknown = series_ids - set(client.supported_ids()) if series_ids is not None else set()
        if unknown:
            raise ValueError("Unknown series IDs: " + ", ".join(sorted(unknown)))
        stage = "reserve_refresh_lock"
        with reserve_refresh(engine) as acquired:
            if not acquired:
                log.warning("Another process owns the ingestion refresh lock")
                return 1
            service = IngestionService(
                engine, SourceAcquisition(
                    client, Path(os.environ.get(
                        "FINANCE_SOURCE_EVIDENCE_DIR", "/data/source-evidence"))))
            stage = "select_catalog"
            chosen = [sid for sid in client.supported_ids()
                      if (series_ids is None or sid in series_ids)
                      and (providers is None or client.definitions[sid]["provider"] in providers)]
            if attention_only and chosen:
                stage = "attention_coverage"
                try:
                    from .source_coverage import build_coverage
                    from .market import instruments
                    census = build_coverage(engine, list(client.definitions.values()),
                                            instruments())
                    # Only skip series after coverage was evaluated reliably.
                    actionable = {item["id"] for item in census["items"]
                                  if item["family"] == "macro" and item["state"] not in (
                                      "available", "source_checked_no_newer_data")}
                    prior = len(chosen)
                    chosen = [sid for sid in chosen if sid in actionable]
                    record_event("macro", "stage_finished",
                                 action="source_health_selection", status="complete",
                                 completed=len(chosen), total=prior)
                except Exception as exc:
                    planner_fault("attention_coverage", exc)
                    # Do not silently skip every source when the coverage
                    # selector itself is broken. The canonical per-series
                    # task loop still honors publisher policy and journaling.
                    record_event("macro", "stage_finished", level="warning",
                                 action="source_health_selection", status="partial",
                                 total=len(chosen), failed=1)
            # A frozen publisher edition does not release more observations
            # every day. Skip already complete versions in *scheduled* cycles;
            # explicit/manual refresh still rechecks them on request.
            # This also avoids repeatedly hammering data-origin redirects for
            # the immutable TiVA and Swinkels archives.
            if skip_complete_pinned and not full and chosen:
                stage = "publication_bounds"
                from .source_coverage import PUBLICATION_BOUNDS
                from .database import ObservationVersion
                now = datetime.now(timezone.utc).date()
                known: dict[str, dict] = {}
                # Invalid individual metadata must not suppress other sources.
                # Invalid bounds never exempt the affected source from refresh.
                for sid in chosen:
                    bound = PUBLICATION_BOUNDS.get(sid)
                    if bound is None:
                        continue
                    try:
                        issued = bound.get("released") or bound.get("verified_as_of")
                        expires = bound.get("expires", date.max)
                        through = bound.get("through")
                        if any(type(v) is not date for v in (issued, expires, through)):
                            raise TypeError("Invalid publisher bound date")
                        if issued <= now < expires:
                            known[sid] = bound
                    except Exception as exc:
                        planner_fault("publication_bound_item", exc, series_id=sid)
                if known:
                    try:
                        with Session(engine) as session:
                            latest = dict(session.execute(
                                select(ObservationVersion.series_id, func.max(ObservationVersion.period))
                                .where(ObservationVersion.series_id.in_(known))
                                .group_by(ObservationVersion.series_id)).all())
                    except Exception as exc:
                        planner_fault("publication_bound_query", exc)
                        # A faulty skip query cannot prevent later attempts.
                        latest = {}
                    due = []
                    for sid in chosen:
                        try:
                            if (sid not in known or latest.get(sid) is None
                                    or latest[sid] < known[sid]["through"]):
                                due.append(sid)
                        except Exception as exc:
                            planner_fault("publication_bound_comparison", exc,
                                          series_id=sid)
                            due.append(sid)
                    skipped = len(chosen) - len(due)
                    if skipped:
                        record_event("macro", "stage_finished",
                                     action="pinned_release_reuse",
                                     status="complete", completed=skipped,
                                     total=len(chosen))
                    chosen = due
            if not chosen:
                return planning_failures
            # A publisher quota may be smaller than its catalogue. Restarting
            # at the same ID every day would starve the tail indefinitely.
            # Rotate completed attempts, including failures: otherwise a
            # quota-sized permanently failing prefix would still monopolize
            # every cycle. A policy deferral has not used a publisher attempt
            # and must not move an unserved source behind those already tried.
            stage = "rotation_query"
            try:
                with Session(engine) as session:
                    last_completed = dict(session.execute(
                        select(IngestionRun.series_id, func.max(func.coalesce(
                            IngestionRun.ended_at, IngestionRun.started_at)))
                        .where(IngestionRun.series_id.in_(chosen),
                               IngestionRun.status.in_(("success", "failed", "unavailable")))
                        .group_by(IngestionRun.series_id)).all())
            except Exception as exc:
                planner_fault("rotation_query", exc)
                last_completed = {}
            def order_date(sid: str):
                item = last_completed.get(sid)
                if not isinstance(item, datetime):
                    return datetime.min
                # Normalize timestamps returned by different SQL backends.
                return (item.astimezone(timezone.utc).replace(tzinfo=None)
                        if item.tzinfo is not None else item)
            chosen.sort(key=lambda sid: (sid in last_completed,
                                         order_date(sid), sid))
            # Fairly interleave provider groups within each freshness class:
            # all never-attempted sources precede previously attempted ones,
            # while an exceptionally slow/rate-limited WID publisher cannot
            # monopolize the front of the batch ahead of FRED/BLS/OECD.
            from collections import deque
            interleaved = []
            for previously_attempted in (False, True):
                queues = {}
                for sid in chosen:
                    if (sid in last_completed) == previously_attempted:
                        group = client.definitions.get(sid, {}).get("provider", "UNKNOWN")
                        queues.setdefault(group, deque()).append(sid)
                while queues:
                    for group in sorted(tuple(queues)):
                        interleaved.append(queues[group].popleft())
                        if not queues[group]:
                            del queues[group]
            chosen = interleaved
            stage = "construct_tasks"
            tasks = []
            for sid in chosen:
                try:
                    provider_group = client.definitions[sid]["provider"]
                    tasks.append(RefreshTask(
                        family="macro", source_id=sid,
                        execute=lambda sid=sid: service.refresh(sid, full=full),
                        progress_label=sid,
                        provider_group=provider_group))
                except Exception as exc:
                    planner_fault("construct_source_task", exc, series_id=sid)
            if preflight_only:
                # Validate current deployment, registered sources, immutable
                # publication guards and real DB refresh-plan SQL without
                # executing any provider, issuing HTTP, or inserting runs.
                record_event("macro", "stage_finished",
                             action="source_refresh_preflight",
                             stage="construct_tasks", status="complete",
                             total=len(tasks))
                return planning_failures
            stage = "execute_tasks"
            return planning_failures + execute_refresh_tasks(
                tasks, progress=progress, stopped=stopped)
    except Exception as exc:
        # Persist sanitized Python module/function/line and exception kind
        # BEFORE the scheduler catches the exception or a new build clears
        # the transient event journal. Raw error messages are never stored.
        from .failure_journal import record_failure
        record_failure("macro", stage, exc)
        category = type(exc).__name__ if type(exc).__name__ in {
            "OperationalError", "IntegrityError", "ProgrammingError",
            "StatementError", "ValueError", "TypeError", "KeyError",
            "AttributeError", "RuntimeError", "OSError", "OverflowError",
        } else "UnexpectedError"
        record_event("macro", "collector_failed", level="error",
                     action="scheduled_refresh_plan", stage=stage,
                     reason=category)
        raise
    finally:
        if client is not None:
            client.close()


def refresh_market_all(engine, *, instrument_ids: set[str] | None = None,
                       currencies: set[str] | None = None,
                       full: bool = False, progress=None, stopped=None) -> int:
    """FX-first market refresh without its former per-market throttle loop.

    The canonical policy gate owns request spacing, shared publisher quotas,
    transport failures and durable cooldowns for both clients.
    """
    from .market import EcbFxClient, YahooMarketClient, instruments
    from .market_service import MarketIngestionService

    with reserve_refresh(engine) as acquired:
        if not acquired:
            log.warning("Another process owns the ingestion refresh lock")
            return 1
        yahoo = None
        ecb = None
        client_failures = 0
        def client_fault(component: str, exc: Exception):
            nonlocal client_failures
            client_failures += 1
            from .failure_journal import record_failure
            record_failure("markets", component, exc)
            record_event("markets", "collector_failed", level="error",
                         action="market_source_setup", stage=component,
                         reason="provider_failed")
        try:
            fx = sorted(currencies if currencies is not None else ("USD", "GBP", "CHF"))
            market = sorted(instrument_ids if instrument_ids is not None else instruments())
            # A broken Yahoo constructor cannot suppress independent ECB FX
            # collection, nor vice versa. The canonical service can initialize
            # an unavailable client per task, so that every affected source
            # obtains its own failure record without stopping siblings.
            if market:
                try:
                    yahoo = YahooMarketClient()
                except Exception as exc:
                    client_fault("market_client_setup", exc)
            if fx:
                try:
                    ecb = EcbFxClient()
                except Exception as exc:
                    client_fault("fx_client_setup", exc)
            service = MarketIngestionService(engine, yahoo, ecb)
            tasks = [
                RefreshTask(
                    family="fx", source_id=currency,
                    execute=lambda currency=currency: service.refresh_fx(
                        currency, full=full),
                    progress_label="FX:" + currency,
                ) for currency in fx
            ]
            tasks.extend(
                RefreshTask(
                    family="markets", source_id=sid,
                    execute=lambda sid=sid: service.refresh_instrument(
                        sid, full=full),
                    progress_label=sid,
                ) for sid in market
            )
            return client_failures + execute_refresh_tasks(
                tasks, progress=progress, stopped=stopped)
        finally:
            for name, client in (("market_client_close", yahoo),
                                 ("fx_client_close", ecb)):
                if client is not None:
                    try:
                        client.close()
                    except Exception as exc:
                        # A cleanup failure must not discard successful
                        # observations or abort remaining client cleanup.
                        from .failure_journal import record_failure
                        record_failure("markets", name, exc)
                        record_event("markets", "collector_failed",
                                     level="warning", action="market_cleanup",
                                     stage=name, reason="provider_failed")
    

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Perform one bounded refresh")
    parser.add_argument("--market-only", action="store_true", help="Only refresh all market instruments and ECB FX")
    parser.add_argument("--macro-only", action="store_true", help="Only refresh macro indicators")
    parser.add_argument("--full", action="store_true", help="Refetch complete history for each series")
    parser.add_argument("--provider", choices=sorted(PROVIDER_CODES),
                        action="append", help="Limit refresh to named provider (repeatable)")
    parser.add_argument("--series", action="append",
                        help="Refresh exactly this canonical macro series (repeatable)")
    parser.add_argument("--health-repair", action="store_true",
                        help="Only refresh macro sources with actionable missing, stale or failed data")
    parser.add_argument("--interval-seconds", type=int, default=int(os.getenv("REFRESH_INTERVAL_SECONDS", "86400")))
    args = parser.parse_args(argv)
    if args.market_only and (args.macro_only or args.provider or args.series or args.health_repair):
        parser.error("--market-only cannot be combined with --macro-only, --provider or --series")
    if args.series:
        known = {row["id"]: row for row in load_documents()[0]["series"]
                 if row["status"] == "mapped" and row["provider"] in PROVIDER_CODES}
        unknown = set(args.series) - set(known)
        if unknown:
            parser.error("Unknown mapped source: " + ", ".join(sorted(unknown)))
        if args.provider and any(known[sid]["provider"] not in args.provider
                                 for sid in args.series):
            parser.error("--series contains an ID outside the selected provider")
    if args.interval_seconds < 3600:
        parser.error("interval must be at least 3600 seconds")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # API keys in URLs must not enter logs
    engine = make_engine()
    providers = set(args.provider) if args.provider else None
    selected = set(args.series) if args.series else None
    def refresh_cycle():
        errors = 0
        if not args.market_only:
            errors += refresh_all(engine, full=args.full, providers=providers,
                                  series_ids=selected,
                                  attention_only=args.health_repair,
                                  skip_complete_pinned=not args.once and not args.full)
        if (not args.macro_only and not args.health_repair
                and providers is None and selected is None):
            errors += refresh_market_all(engine)
        return errors

    if args.once:
        return 1 if refresh_cycle() else 0
    while True:
        refresh_cycle()
        # Independent from FastAPI; errors remain visible and retry next cycle.
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
