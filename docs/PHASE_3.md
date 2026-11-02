# Phase 3 — focused macro dashboard

**Scope source:** [original requirements and frozen Phase 3 contract](PHASE_3_CONTRACT.md). The user requested a single, simple, long thematic page. The frontend is not a portfolio tool.

## Architecture (minimal)

- **One** Vite + React 19 + TypeScript frontend and Apache ECharts 6; no router library, chart framework wrapper, state container, additional service, database or backend routes.
- Existing canonical **42 macro/index series and 24 chart definitions** drive the visible themes and per-chart menus. Draft comparison definitions are labelled exploratory, never promoted to official/source-matched indicators.
- Two interfaces share one chart UI:
  - **Local/private:** `/api/series`, `/api/charts`, `/api/data-status` and `/api/query` through Vite's local proxy to the already-running FastAPI server. All 42 official/provider/derived macro mappings can be explored. Individual API observation rows carry their `ingestion_run_id` and `first_seen_at` when stored.
  - **Static:** consumes the Phase 2 source-validated `index.json`, `charts.json`, `series/<id>.json` with no live provider requests, database or keys in the browser. For a **public** deployment the separate fail-closed allowlist allows only explicitly rights-approved source data.
- The first expanded chart is actual BIS Fed/euro-area/BOJ harmonized daily policy rates. The other catalogued charts remain collapsed in eight economic themes.
- Only the selected, expanded chart's data is fetched. The ECharts canvas instance is created only while visible, then disposed. No background refresh loops or state synchronization service.

## Run locally with **all** macro sources

Start the existing Phase 2 Docker Compose stack, including PostgreSQL and the worker, as documented in [README](../README.md). No changes to `docker-compose.yml` are required.

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. The development server proxies read-only `/api` requests to `127.0.0.1:8080`. **Do not expose** the FastAPI server to the internet. `VITE_DATA_MODE=api` can be supplied explicitly, but is the development default.

To test the complete static data source locally without PostgreSQL:

```bash
python -m finance_dashboard.static_export --macro-only --output-dir frontend/public/data
cd frontend
npm install
VITE_DATA_MODE=static npm run dev
```

This **local private** static export includes all 42 available macro/index datasets, including series still marked `review_required`. It is in `.gitignore`; never commit, upload to Pages or redistribute it publicly.

## Chart interactions

The complete original interaction set is implemented on each expanded chart:

- Add or remove up to six available comparison series, including country/region alternatives; change 5Y, 10Y, 20Y, Max or Custom period. Preset years are anchored to the actual latest plotted observation, not to an invented current reading.
- Raw value charts admit series with identical units **and** native frequency. Index 100 and percentile permit cross-frequency comparisons as *view-only normalization*, retaining all original dates and source values. **No economic derived-indicator calculation is moved out of Python**.
- Index 100: each series' first positive observation in selected range is its own 100 basis. A zero/negative starting value is reported as unsupported, not silently skipped. Baseline dates are shown. Percentile: within selected window, empirical tied-value **midrank**, requires >=20 observations and nonflat values; not a forecast/probability.
- Gaps longer than expected native cadence break drawn lines. The inherently sparse MSCI and Siblis histories display isolated points, without fictitious connecting months.
- Toggle three dated, sourced historical context markers (not causal claims); view native raw-data table, source URL, methodology, provider, geography, exact data range and ingestion run or static build timestamp; export CSV/PNG and JSON chart view; copy a shareable chart deep link. Source recency warnings and rights blocks are explicit.

## Licence and deployment policy

**37 of 42** macro series currently have `review_required` rights, including some BIS, FRED, MSCI and proprietary Siblis series. Even with no secret inside an artifact, publication of those observations has **not** been authorized.

`scripts/prepare_public_dashboard.py` consumes the complete private Phase 2 export, **copies only positively identified `cc_by_4_0` datasets** (currently five) into `frontend/public/data`, keeps chart definitions as metadata and omits markets, FX and Wisesheets. A public view explicitly describes withheld data instead of silently substituting it.

A manually dispatched, **rights-filtered** [GitHub Pages workflow](../.github/workflows/phase3-pages.yml) collects private observations within Actions, prepares the public subset, compiles the frontend with base path `/finance_dashboard/`, verifies exclusion and deploys the static site. It requires Pages to be enabled with Actions as the deployment source. The workflow has **no scheduled public deployment**. The private complete export is never a Pages artifact.

The standalone [short frontend CI](../.github/workflows/phase3-ui.yml) runs rights-leakage tests, display-method tests, TypeScript checks and Vite build. No browser requests are made to the private API in the public build.

## Implementation/acceptance status

The frontend's full user controls are implemented. [Latest short frontend CI runs](https://github.com/tpepels/finance_dashboard/actions/workflows/phase3-ui.yml) validate bundling, 11+ data-view cases and public rights policy. [Phase 2 full 42/42 historical data ingestion/API](https://github.com/tpepels/finance_dashboard/actions/runs/41503545569) and [42/42 static data export](https://github.com/tpepels/finance_dashboard/actions/runs/41503489558) were independently verified earlier.

**Not yet verified:** a completed public Pages deployment and graphical interaction against a real browser with every backend/source combination. The [Phase 3 issue](https://github.com/tpepels/finance_dashboard/issues/2) remains open until full user-facing acceptance is confirmed. The full source explorer works in local private mode; the public version will necessarily show only the five cleared datasets until further distribution rights are established.

Phase 4 is intentionally excluded: portfolio analytics, trading indicators, alerts, risk scores, auth, external chart scripting and extra data providers.

## One-container home-server deployment

A consolidated, verified deployment is available in [HOME_SERVER_DOCKER.md](HOME_SERVER_DOCKER.md): one multi-stage [Dockerfile.standalone](../Dockerfile.standalone) bundles the built React site, existing FastAPI routes, one internal background refresh thread and a persistent SQLite (WAL) database. Add just [one service](home-server-finance-service.yml) to your existing media-server Compose; the original PostgreSQL multi-container stack is not required. [Docker UI/API/migration/SQLite restart smoke passed](https://github.com/tpepels/finance_dashboard/actions/runs/41513402528). The optional market feed is disabled by default to keep a macro-first dashboard, enabled through FINANCE_INCLUDE_MARKETS=1. This is an additional deployment mode, not a new analytics backend and not a publicly licensed chart website.

### Wisesheets SEC filer supplementary chart

The user-supplied `WISESHEETS_API_KEY` belongs to the monthly GitHub Actions collector, not to React or the Docker Compose service. The standalone image bundles the already verified SEC annual earnings snapshot (2021–2025); the existing daily process periodically downloads only the validated updated **committed aggregate** without consuming Wisesheets API quota. The existing `GET /api/earnings/sec-filers` endpoint serves the local persistent copy or bundled fallback. The frontend has **one** extra collapsible supplementary chart, exposing annual US SEC-reporting-filer net income relative to world GDP and per-year issuer/FX coverage. This does not modify the canonical 42-series macro catalogue or claim complete global listed-company profits. Public static Pages builds still withhold the supplementary source pending redistribution rights. [Home-server instructions](HOME_SERVER_DOCKER.md) · [Wisesheets methodology](WISESHEETS.md).
