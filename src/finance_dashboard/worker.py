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
from .database import make_engine
from .service import IngestionService

log = logging.getLogger(__name__)


def refresh_all(engine, full: bool = False, providers: set[str] | None = None) -> int:
    failures = 0
    client = ProviderRouter()
    try:
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
                    if providers is not None and client.definitions[series_id]["provider"] not in providers:
                        continue
                    try:
                        report = service.refresh(series_id, full=full)
                        log.info("refreshed: %s", json.dumps(report))
                    except Exception:
                        failures += 1
                        log.exception("refresh failed: %s", series_id)
            finally:
                if engine.dialect.name == "postgresql":
                    conn.execute(text("SELECT pg_advisory_unlock(75390812)"))
    finally:
        client.close()
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Perform one bounded refresh")
    parser.add_argument("--full", action="store_true", help="Refetch complete history for each series")
    parser.add_argument("--provider", choices=sorted(PROVIDER_CODES),
                        action="append", help="Limit refresh to named provider (repeatable)")
    parser.add_argument("--interval-seconds", type=int, default=int(os.getenv("REFRESH_INTERVAL_SECONDS", "86400")))
    args = parser.parse_args()
    if args.interval_seconds < 3600:
        parser.error("interval must be at least 3600 seconds")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # API keys in URLs must not enter logs
    engine = make_engine()
    providers = set(args.provider) if args.provider else None
    if args.once:
        return 1 if refresh_all(engine, full=args.full, providers=providers) else 0
    while True:
        refresh_all(engine, full=args.full, providers=providers)
        # Independent from FastAPI; errors remain visible and retry next cycle.
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
