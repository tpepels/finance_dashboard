"""Separate refresh worker; explicit 'once' mode for predictable manual bootstraps."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import logging
import os
import time

from sqlalchemy import text

from .providers import ProviderRouter, PROVIDER_CODES
from .catalog import load_documents
from .database import make_engine
from .service import IngestionService

log = logging.getLogger(__name__)


def refresh_all(engine, full: bool = False, providers: set[str] | None = None,
                series_ids: set[str] | None = None) -> int:
    failures = 0
    client = ProviderRouter()
    try:
        unknown = series_ids - set(client.supported_ids()) if series_ids is not None else set()
        if unknown:
            raise ValueError("Unknown series IDs: " + ", ".join(sorted(unknown)))
        with engine.connect() as conn:
            # PostgreSQL advisory lock stops two scheduled workers changing one series concurrently.
            if engine.dialect.name == "postgresql":
                locked = conn.execute(text("SELECT pg_try_advisory_lock(75390812)")).scalar()
                if not locked:
                    log.warning("Another refresh worker owns the advisory lock")
                    return 1
            try:
                service = IngestionService(engine, client)
                for series_id in client.supported_ids():
                    if series_ids is not None and series_id not in series_ids:
                        continue
                    if providers is not None and client.definitions[series_id]["provider"] not in providers:
                        continue
                    try:
                        report = service.refresh(series_id, full=full)
                        log.info("refreshed: %s", json.dumps(report))
                    except Exception:
                        failures += 1
                        log.error("macro refresh failed: %s (provider error redacted to protect credentials)", series_id)
            finally:
                if engine.dialect.name == "postgresql":
                    conn.execute(text("SELECT pg_advisory_unlock(75390812)"))
    finally:
        client.close()
    return failures


def refresh_market_all(engine) -> int:
    """Full-history EOD adjustment refresh plus overlapping ECB currency history.

    A provider failure remains visible and does not destroy last-known-good
    values. Prices always refresh complete history because historical dividend
    adjustments can revise dates far older than a recent overlap.
    """
    from .market import EcbFxClient, YahooMarketClient, instruments
    from .market_service import MarketIngestionService

    failures = 0
    yahoo, ecb = YahooMarketClient(), EcbFxClient()
    try:
        service = MarketIngestionService(engine, yahoo, ecb)
        # FX first: market queries can convert to EUR as soon as prices arrive.
        for currency in ("USD", "GBP", "CHF"):
            try:
                log.info("fx refresh: %s", json.dumps(service.refresh_fx(currency)))
            except Exception:
                failures += 1
                log.error("fx refresh failed: %s (source error redacted)", currency)
        for sid in sorted(instruments()):
            try:
                log.info("market refresh: %s", json.dumps(service.refresh_instrument(sid)))
            except Exception:
                failures += 1
                log.error("market refresh failed: %s (source error redacted)", sid)
            time.sleep(0.15)  # avoid tight request bursts on the unofficial API
    finally:
        yahoo.close()
        ecb.close()
    return failures


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
    parser.add_argument("--interval-seconds", type=int, default=int(os.getenv("REFRESH_INTERVAL_SECONDS", "86400")))
    args = parser.parse_args(argv)
    if args.market_only and (args.macro_only or args.provider or args.series):
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
                                  series_ids=selected)
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
