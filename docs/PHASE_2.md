# Phase 2 — Ingestion, database, revision handling and API

Phase 2 completed and live-verified on 2026-11-02 for the three BIS central bank policy rate series. This verification ran in disposable GitHub Actions Docker containers; it is not a persistent production deployment.

## Source retrieval

API: \`https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CBPOL/1.0/D.{US|XM|JP}\`

Uses header \`Accept: application/vnd.sdmx.data+json;version=1.0.0\`. Official API documentation: https://stats.bis.org/api-doc/v2/. Country codes and daily observations are decoded from the SDMX structure's dimension-index mappings. Unexpected dimensions, duplicate series, mismatched countries, infinite values and invalid dates cause an error, without database updates. Historical BIS NaN/null values are treated as **missing observations** and skipped, never coerced to zero; a series containing only missing observations still fails.

BIS response \`meta.prepared\` records response preparation, **not historical publication time**. No \`source_vintage\` is fabricated. The worker initially fetches full history, then performs daily polls with a 120-day overlap to catch corrections. Older revisions require \`worker --once --full\`; no claim of discovering all historical revisions automatically.

## Durability

Schema has series identities, ingest-run log and append-only observation versions. Only changed values create versions; unchanged refreshes are idempotent. A per-series transaction saves observations and marks success together. Failures mark the ingest run failed in a separate transaction, retaining prior observations. PostgreSQL row-level locks serialize writes to one series; a PostgreSQL advisory lock serializes worker refreshes.

No deletion is inferred from missing provider observations. Datetimes are UTC. Historical app-snapshot queries filter by \`first_seen_at\` and select the most recent version available by ingestion order; they do **not** replay true historical BIS publication vintages.

## Runtime and tests

\`app\` reads data and metadata; \`worker\` is the only source downloader. Alembic runs once before either service. Postgres remains private; API binds loopback.

Routine CI is bounded to five minutes, with local SDMX fixtures, SQLite and PostgreSQL tests. A separate bounded [live acceptance run](https://github.com/tpepels/finance_dashboard/actions/runs/41449348048) successfully queried the three live BIS series, initialized a Docker Compose PostgreSQL database and applied Alembic migrations, backfilled 26,416 US / 10,130 euro-area / 24,914 Japanese historical observations, and read all three through FastAPI. The euro-area full-history feed exposed null/NaN observations; the adapter now skips these genuine missing data points instead of rejecting an entire series. This run is reproducible via manual workflow dispatch and does not establish a continuously deployed production instance.

## Known gaps / deferred work

- Only BIS harmonized rates are ingested; FRED, ECB, IMF and others are Phase 3+.
- Historical revisions older than the overlap are not detected automatically; a periodic full refresh can be added later.
- No frontend; the Phase 2 live worker/HTTP acceptance succeeded. No always-on production deployment has been made.
- No full licence review. Provider terms must be checked before public redistribution.
- The API is unauthenticated and intentionally loopback-bound.
