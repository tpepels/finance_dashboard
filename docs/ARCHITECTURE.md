# Architecture baseline (decision record)

Status: proposed and scoped; only Phase 1 contracts are implemented.

## System boundaries

1. **Acquisition**: one provider adapter per external API; no charts fetch provider data.
2. **Storage**: PostgreSQL stores normalized series identities, observations, publication vintages, ingest run metadata and provenance. Latest value is a projection of observation history, never a destructive overwrite.
3. **Analytics**: pure, versioned Python calculations over explicitly frequency-aligned series. Input vintages and formula versions identify a result.
4. **HTTP API**: FastAPI exposes catalog metadata, observations, chart definitions, freshness and downloads.
5. **UI**: React/TypeScript and Apache ECharts render declarative multi-series charts; no economic calculations in the browser.
6. **Worker**: separate scheduled process in the same backend package. Bounded retries and last-known-good data. No Celery/Redis/Kafka.

Compose services in Phase 2+: app, worker, postgres. The frontend is compiled into the app container for self-hosting.

## Temporal semantics

A future observation records: series ID, reference period, value, unit, provider, source vintage (if supplied), first observed by us, ingestion run, quality flags. A download timestamp is not equivalent to a release timestamp. Historical 'as known then' queries are only supported where a source exposes genuine vintages (for example ALFRED).

Provider updates can revise prior observations. New versions must be kept while the latest projection selects the currently valid value. Original date frequency remains native: annual GDP must not be fabricated into daily values.

## Canonical identity

Identifiers like `policy_rate.us.bis` refer to a specific economic measure and provider mapping. The display title is not an identifier. A replacement of a source with a conceptually different instrument requires a new canonical ID, not silent remapping.

`definitions/series.json` is the source catalog. `definitions/charts.json` specifies graphs. Only mappings confirmed from provider documentation are called `mapped`, and that state is **not** a claim that a live API round trip has succeeded.

## Chart contracts

A raw multi-series chart must use the same unit and frequency unless a future version supports explicit axis and alignment declarations. Percent and percentage points cannot be mixed implicitly. Index-to-100 and percentiles require methodological metadata, minimum histories and reference-period controls before becoming executable.

Source usage restrictions are carried alongside the data and checked before public hosting or redistribution.

## Not in the initial system

No microservices, cloud orchestration, real-time quotes, trading/alerts, unconstrained user Python code, automatically generated investment recommendations, or unlicensed proprietary datasets.
