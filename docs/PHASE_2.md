# Phase 2 — Ingestion, database, revision handling and API

Implemented for three BIS central bank policy rate series only. This document distinguishes implementation from validation.

## Source retrieval

API: \`https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/D.{US|XM|JP}\`

Uses header \`Accept: application/vnd.sdmx.data+json;version=1.0.0\`. Official API documentation: https://stats.bis.org/api-doc/v2/. Country codes and daily observations are decoded from the SDMX structure's dimension-index mappings. Unexpected dimensions, duplicate series, mismatched countries, infinite values and invalid dates cause an error, without database updates. Historical BIS NaN/null values are treated as **missing observations** and skipped, never coerced to zero; a series containing only missing observations still fails.

BIS response \`meta.prepared\` records response preparation, **not historical publication time**. No \`source_vintage\` is fabricated. The worker initially fetches full history, then performs daily polls with a 120-day overlap to catch corrections. Older revisions require \`worker --once --full\`; no claim of discovering all historical revisions automatically.

## Durability

Schema has series identities, ingest-run log and append-only observation versions. Only changed values create versions; unchanged refreshes are idempotent. A per-series transaction saves observations and marks success together. Failures mark the ingest run failed in a separate transaction, retaining prior observations. PostgreSQL row-level locks serialize writes to one series; a PostgreSQL advisory lock serializes worker refreshes.

No deletion is inferred from missing provider observations. Datetimes are UTC. Historical app-snapshot queries filter by \`first_seen_at\` and select the most recent version available by ingestion order; they do **not** replay true historical BIS publication vintages.

## Runtime and tests

\`app\` reads data and metadata; \`worker\` is the only source downloader. Alembic runs once before either service. Postgres remains private; API binds loopback.

CI is bounded to five minutes, uses local SDMX fixtures and SQLite integration tests for ingestion, snapshots, failures, API responses and migration. Network access, live BIS observations, an actual PostgreSQL service and Docker deployment still need environment-level validation.

## Known gaps / deferred work

- Only BIS harmonized rates are ingested; FRED, ECB, IMF and others are Phase 3+.
- Historical revisions older than the overlap are not detected automatically; a periodic full refresh can be added later.
- No frontend. No live-success claim until worker runs against BIS.
- No full licence review. Provider terms must be checked before public redistribution.
- The API is unauthenticated and intentionally loopback-bound.
