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
from .source_policy import PolicyDeferred
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
    total = len(tasks)
    # A confirmed publisher-wide hourly quota cannot be repaired by
    # immediately attempting twenty more series using the same source host.
    # Do not mark those unattempted sources as fresh or failed; retain their
    # previous acquisition history for the next scheduled cycle.
    unavailable_groups: set[str] = set()
    suppressed: dict[str, int] = {}
    for index, task in enumerate(tasks, 1):
        if stopped is not None and stopped.is_set():
            break
        if task.provider_group is not None and task.provider_group in unavailable_groups:
            failures += 1  # incomplete refresh, but no new failed IngestionRun
            suppressed[task.provider_group] = suppressed.get(task.provider_group, 0) + 1
            if progress is not None:
                progress(index, total, task.progress_label)
            continue
        try:
            report = task.execute()
            log.info("%s refreshed: %s", task.family, json.dumps(report))
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
            record_event(task.family, "source_failed", level="error",
                         source_id=task.source_id,
                         reason=safe_source_failure_code(exc))
            log.error("%s refresh failed: %s (publisher details redacted)",
                      task.family, task.source_id)
        if progress is not None:
            progress(index, total, task.progress_label)
    for group, count in sorted(suppressed.items()):
        record_event("macro", "stage_finished", level="warning",
                     action="publisher_quota_exhausted", status="deferred",
                     provider=group, sources_not_attempted=count)
        log.warning("%s: %d additional sources left unattempted after source quota exhaustion",
                    group, count)
    return failures


def refresh_all(engine, full: bool = False, providers: set[str] | None = None,
                series_ids: set[str] | None = None, progress=None,
                stopped=None, skip_complete_pinned: bool = False,
                attention_only: bool = False) -> int:
    """Canonical macro refresh uses the same task execution contract as markets."""
    client = ProviderRouter()
    try:
        unknown = series_ids - set(client.supported_ids()) if series_ids is not None else set()
        if unknown:
            raise ValueError("Unknown series IDs: " + ", ".join(sorted(unknown)))
        with reserve_refresh(engine) as acquired:
            if not acquired:
                log.warning("Another process owns the ingestion refresh lock")
                return 1
            service = IngestionService(
                engine, SourceAcquisition(
                    client, Path(os.environ.get(
                        "FINANCE_SOURCE_EVIDENCE_DIR", "/data/source-evidence"))))
            chosen = [sid for sid in client.supported_ids()
                      if (series_ids is None or sid in series_ids)
                      and (providers is None or client.definitions[sid]["provider"] in providers)]
            if attention_only and chosen:
                from .source_coverage import build_coverage
                from .market import instruments
                census = build_coverage(engine, list(client.definitions.values()),
                                        instruments())
                # Attempt only actual gaps. Source-policy-deferred but
                # in-cadence rows remain visible in the operational audit,
                # but do not consume scarce publisher requests in repair mode.
                actionable = {item["id"] for item in census["items"]
                              if item["family"] == "macro" and item["state"] != "available"}
                prior = len(chosen)
                chosen = [sid for sid in chosen if sid in actionable]
                record_event("macro", "stage_finished",
                             action="source_health_selection", status="complete",
                             selected=len(chosen), skipped=prior - len(chosen))
            # A frozen publisher edition does not release more observations
            # every day. Skip already complete versions in *scheduled* cycles;
            # explicit/manual refresh still rechecks them on request.
            # This also avoids repeatedly hammering data-origin redirects for
            # the immutable TiVA and Swinkels archives.
            if skip_complete_pinned and not full and chosen:
                from .source_coverage import PUBLICATION_BOUNDS
                from .database import ObservationVersion
                now = datetime.now(timezone.utc).date()
                known = {sid: PUBLICATION_BOUNDS[sid] for sid in chosen
                         if sid in PUBLICATION_BOUNDS
                         and (PUBLICATION_BOUNDS[sid].get("released")
                              or PUBLICATION_BOUNDS[sid].get("verified_as_of")) <= now
                         and now < PUBLICATION_BOUNDS[sid].get("expires", date.max)}
                if known:
                    with Session(engine) as session:
                        latest = dict(session.execute(
                            select(ObservationVersion.series_id, func.max(ObservationVersion.period))
                            .where(ObservationVersion.series_id.in_(known))
                            .group_by(ObservationVersion.series_id)).all())
                    due = [sid for sid in chosen
                           if sid not in known or latest.get(sid) is None
                           or latest[sid] < known[sid]["through"]]
                    skipped = len(chosen) - len(due)
                    if skipped:
                        record_event("macro", "stage_finished", action="pinned_release_reuse",
                                     status="complete", skipped=skipped)
                    chosen = due
            if not chosen:
                return 0
            # A publisher quota may be smaller than its catalogue. Restarting
            # at the same ID every day would starve the tail indefinitely.
            # Rotate completed attempts, including failures: otherwise a
            # quota-sized permanently failing prefix would still monopolize
            # every cycle. A policy deferral has not used a publisher attempt
            # and must not move an unserved source behind those already tried.
            with Session(engine) as session:
                last_completed = dict(session.execute(
                    select(IngestionRun.series_id, func.max(func.coalesce(
                        IngestionRun.ended_at, IngestionRun.started_at)))
                    .where(IngestionRun.series_id.in_(chosen), IngestionRun.status.in_(("success", "failed")))
                    .group_by(IngestionRun.series_id)).all())
            chosen.sort(key=lambda sid: (sid in last_completed,
                                         last_completed.get(sid) or datetime.min, sid))
            tasks = [
                RefreshTask(
                    family="macro", source_id=sid,
                    execute=lambda sid=sid: service.refresh(sid, full=full),
                    progress_label=sid,
                    provider_group=client.definitions[sid]["provider"],
                )
                for sid in chosen
            ]
            return execute_refresh_tasks(tasks, progress=progress, stopped=stopped)
    finally:
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
        yahoo, ecb = YahooMarketClient(), EcbFxClient()
        try:
            service = MarketIngestionService(engine, yahoo, ecb)
            fx = sorted(currencies if currencies is not None else ("USD", "GBP", "CHF"))
            market = sorted(instrument_ids if instrument_ids is not None else instruments())
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
            return execute_refresh_tasks(tasks, progress=progress, stopped=stopped)
        finally:
            yahoo.close()
            ecb.close()
    

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
        if not args.macro_only and providers is None and selected is None:
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
