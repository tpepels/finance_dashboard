# Current architecture — local finance research dashboard


> Deployment, persistence and evidence sections date from 2026-11-02; the analytics, API and frontend sections were updated when Phase 3 closed (2026-11-10). The roadmap is [the development plan](DEVELOPMENT_PLAN.md).

## One-process deployment

The **only runtime container** is `finance-dashboard`, built from [../Dockerfile](../Dockerfile) and added to an existing home-server Compose. It contains the Vite-built React UI, FastAPI API, SQLite WAL database, source ingestion and local Wisesheets/market refresh tasks. **No** GitHub Actions, public Pages exporter, background worker container, Redis, PostgreSQL deployment, separate frontend or Node process at runtime.

FastAPI is served on container port 8080; the host maps port 5052. `FINANCE_BIND_HOST=0.0.0.0` allows local LAN access; optionally `127.0.0.1` binds behind an existing authenticated reverse proxy. An access restriction is **not enabled by default**. Do not expose the unauthenticated port to the public internet.

## Responsibility boundaries

1. **Catalog / definitions**: `definitions/series.json` maps 53 native macro source IDs and institutions, `definitions/charts.json` retains 21 original source charts, `definitions/instruments.json` enumerates 24 validated ETFs/stocks with exchange/quote currency metadata.
2. **Acquisition**: `providers.py`, `market.py`, `wisesheets.py` and attached data-specific adapter modules. No frontend directly contacts FRED, BIS, OECD, Yahoo or external providers. Lack of live data remains explicit; no placeholder observations are invented.
3. **Persistence**: `database.py` contains append-only observations, ingestion runs, equity/FX prices and source corrections in **SQLite WAL**. Alembic migrations run before FastAPI starts. The `/data` bind volume survives image updates. An app-ingestion timestamp does **not** establish when a historical statistic was publicly released.
4. **Background data updates**: `standalone.py` launches **one in-process daemon thread** when configured. `worker.py` contains the shared macro/optional market ingestion functions but does not launch another container. SEC Wisesheets full-universe collection is monthly and quota-aware.
5. **Analytical engine** (`engine/`, Phase 3): one result bundle per analysis (`/api/analysis/{id}`) with its Phase 2 state and every limitation, its inputs and their provenance, the named transforms applied (`transforms.py` registry), values and estimates, and an AI export (`/api/analysis/{id}/export`). `analyses.py` defines all 37 corpus analyses; `artifacts.py` loads the archives some read (holdings filings, framework originals, input-output tables, chronologies, owner inputs). Only analyses Phase 2 resolves, or the alternatives Phase 2 verified for them (labelled `basis: verified_alternatives`), carry values. There is no other calculation path.
6. **API**: `api.py` serves the engine (`/api/analysis*`, `/api/conditionals`, `/api/recessions`), the owner inputs (`/api/owner-inputs`), the provenance layer (`/api/series`, `/api/query`, `/api/charts`, market and holdings sources, source coverage and evidence) and operations. The pre-engine research, risk, insight, comparison, backtest and Marxian-accounting routes are retired.
7. **Frontend**: eight analysis panels (`DecisionPanel`, `GrowthPanel`, `MonetaryPanel`, `CreditPanel`, `ValuationPanel`, `PortfolioPanel`, `GlobalPanel`, `LabourPanel`) draw only from engine bundles, with one graphic per idea (`heroes.tsx`) and zoomable time charts with NBER recession bands (`chartKit.ts`, `TimePanel.tsx`). `SourceExplorer.tsx` keeps the original source charts and raw dataset access as the provenance layer, without calculations.
8. **Resilience**: `backup.py` uses SQLite's consistent online-backup API, verifies SQLite integrity, and records SHA-256 checksums. Automatic backups run after the daily refresh in the same process with 14 manifest bundles retained under `/data/backups`. Manual verification is available. Copy bundles to separate physical storage.

## Time and evidence contracts

- Source periods remain native daily/monthly/quarterly/annual observation dates and their revisions.
- `snapshot_at` is application first-seen history, **never** retroactively claimed as a true publication vintage. Formal as-known-then modelling needs genuine original release vintages (ALFRED or equivalent) and is not yet implemented.
- Corporate gross surplus, listed net income, labour share, and Marxian surplus-value calculations have different conceptual and sector denominators. The UI keeps them separate; no composite exploitation rate is fabricated.
- Market evidence is Yahoo vendor-adjusted closes, not issuer NAV; ETF country holdings exposure is not inferred from domicile or exchange quote currency. Portfolio simulations assume monthly rebalancing and exclude taxes/fees.
- No synthetic risk score or unsupported crisis probability is calculated. Publisher thresholds are contextual, not prediction rules.
- External source rights remain attached as **descriptive metadata** for provenance and third-party redistribution requirements. There is no local source-usage gate.

## Validation

The single Docker build runs short Vitest/TypeScript and Python contract tests for source definitions, macro research, Phase 4 signals/portfolio APIs, and backups. No GitHub Actions, remote CI or long scheduled checks are enabled. Local deployment and actual browser/market ingestion still need user-run verification.

See [historical Phase 4 implementation](archive/PHASE_4.md), [economic methods](ECONOMIC_RESEARCH_METHODS.md), [home-server deployment](HOME_SERVER_DOCKER.md) and [source integrity](DATA_POLICY.md).