# Current architecture — local finance research dashboard


> **Technical reference, not a separate development roadmap.** The sole current implementation path and phase acceptance are in [Development plan](DEVELOPMENT_PLAN.md). Historical phase files have been archived.

Updated 2026-11-02, incorporating owner's local-only deployment decision and Phase 4 additions.

## One-process deployment

The **only runtime container** is `finance-dashboard`, built from [../Dockerfile](../Dockerfile) and added to an existing home-server Compose. It contains the Vite-built React UI, FastAPI API, SQLite WAL database, source ingestion and local Wisesheets/market refresh tasks. **No** GitHub Actions, public Pages exporter, background worker container, Redis, PostgreSQL deployment, separate frontend or Node process at runtime.

FastAPI is served on container port 8080; the host maps port 5052. `FINANCE_BIND_HOST=0.0.0.0` allows local LAN access; optionally `127.0.0.1` binds behind an existing authenticated reverse proxy. An access restriction is **not enabled by default**. Do not expose the unauthenticated port to the public internet.

## Responsibility boundaries

1. **Catalog / definitions**: `definitions/series.json` maps 53 native macro source IDs and institutions, `definitions/charts.json` retains 21 original source charts, `definitions/instruments.json` enumerates 24 validated ETFs/stocks with exchange/quote currency metadata.
2. **Acquisition**: `providers.py`, `market.py`, `wisesheets.py` and attached data-specific adapter modules. No frontend directly contacts FRED, BIS, OECD, Yahoo or external providers. Lack of live data remains explicit; no placeholder observations are invented.
3. **Persistence**: `database.py` contains append-only observations, ingestion runs, equity/FX prices and source corrections in **SQLite WAL**. Alembic migrations run before FastAPI starts. The `/data` bind volume survives image updates. An app-ingestion timestamp does **not** establish when a historical statistic was publicly released.
4. **Background data updates**: `standalone.py` launches **one in-process daemon thread** when configured. `worker.py` contains the shared macro/optional market ingestion functions but does not launch another container. SEC Wisesheets full-universe collection is monthly and quota-aware.
5. **Economic analytics**:
   - `research.py` defines 46 question-led macro series/relationships across world/OECD, United States, euro area/EU27, Japan and cross-economy comparisons.
   - `insights.py` provides source-native annual differences and exact-common-date country spreads, with no synthetic matching.
   - `risk_diagnostics.py` provides source-defined Sahm, Treasury inversion, BIS credit-gap and valuation historical-rank research; no opaque or probabilistic scores.
   - `portfolio_risk.py` computes consecutive-common-calendar-month ETF returns, max drawdown, EUR FX translation, volatility and optional monthly-rebalanced portfolio metrics. Requires actual stored Yahoo/ECB data; no holdings-history or issuer NAV claims.
   - `market_analytics.py` provides the existing GLD/VT return-correlation proxy, distinct from the genuine MSCI ACWI/spot-gold return series.
6. **API**: `api.py` exposes only documented source identifiers and validated request models. New Phase 4 routes `GET /api/risk`, `GET /api/risk/{scope}`, `POST /api/market/compare`, `GET /api/operations`; original research, Wisesheets, market and catalog endpoints remain.
7. **Frontend**: `ResearchDashboard.tsx` renders always-visible regionally organized macro graphs, `Phase4Panel.tsx` presents separate risk and optional market research, and `SourceExplorer.tsx` preserves the original 21 graphs and raw dataset access in a secondary section. ECharts adds light gray unlabeled **US NBER contraction bands**, with explicit geographic caveat.
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

See [Phase 4](PHASE_4.md), [economic methods](ECONOMIC_RESEARCH_METHODS.md), [home-server deployment](HOME_SERVER_DOCKER.md) and [source integrity](DATA_POLICY.md).