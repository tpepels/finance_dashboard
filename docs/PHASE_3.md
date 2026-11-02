# Phase 3 — completed frontend scope, local-only implementation

**Scope:** a compact, scrollable, research-oriented macro dashboard with immediate combined graphs, coherent source comparisons and source-checked interpretation. This replaces the previous click-only chart list. Read the [original contract](PHASE_3_CONTRACT.md) for history and this revision for the approved local-only adaptation.

## Why the initial UI was incomplete

- The default catalogue required a user click before each chart could be seen.
- `world_productivity_labour_income` incorrectly graphed the **growth rate** of productivity alongside the **level** of labour share, since both appeared in percent units. The draft debt/rate, gold/yield and recession/gap overlays also lacked a defensible alignment or normalization method. They are not part of the curated dashboard.
- No systematic question-led layout, visible interpretation or recorded date/value readouts were provided.

## Revised functional layout

[frontend/src/editorial.ts](../frontend/src/editorial.ts) defines eight clear economic chapters and source-by-source research questions, explanations and caveats. The first multi-country chart per applicable chapter is featured, with other charts in a responsive grid and **visible native-date previews**. Charts are lazily loaded near the viewport and expanded only for controls, source observation table, provider freshness and exports.

The backend [insights.py](../src/finance_dashboard/insights.py) and `POST /api/chart-insight` produce local, deterministic descriptive readouts: latest observed values and source dates, approximate one-year observed changes (exact comparison dates displayed), and high/low geographic spreads only where **every series has an observation on the same source date**. No resampling or cross-universe inference. Insufficient evidence produces no interpretation. Chart-specific educational context and limitations remain visible. These are **Phase 3** features.

Only semantically identical measurements may be overlaid. The source identity family is checked in both the frontend and Python backend; indexing to 100 or percentile display cannot override that restriction. Original unit/frequency checks remain. Every canonical source absent from featured chapters can still be examined individually through the source library.

The source collection, all charts and analysis run entirely inside your local FastAPI/SQLite container. No public-only/source-licence feature gates are present. The optional Wisesheets monthly local collector uses `WISESHEETS_API_KEY` from your server's `.env`; the supplementary earnings panel shows actual annual US SEC filer net income/world GDP plus FX and issuer coverage separately from OECD/EU national corporate gross-surplus measures.

## What remains Phase 4

Derived standardized risk indicators, cross-frequency models, historically sourced multi-indicator regressions, probabilistic interpretation, instrument/portfolio exposures, gold/ETF performance attribution, investment decision logic and economic forecasting. The descriptive source commentary and changes on the dashboard are not those features and do **not** justify delaying the UI to Phase 4.

## Validation and deployment

No GitHub Actions workflows, Pages deployment, public-data filters, GitHub-sourced Wisesheets sync or extra Docker services remain. Run [local tests](../README.md) and the one-service Docker setup yourself; do not claim Docker/browser checks after the local-only refactor until run on your machine. Source-catalog and previous live-source evidence are preserved in [Phase 2](PHASE_2.md). The [one-service Compose snippet](home-server-finance-service.yml) adds the dashboard to the existing home-server stack.
