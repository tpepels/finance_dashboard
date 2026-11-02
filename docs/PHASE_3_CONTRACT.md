# Phase 3 — original dashboard scope and minimal implementation contract

> **Local-only scope amendment — 2026-11-02:** The owner subsequently rejected GitHub Actions/Pages and any public-only source gating. The live implementation is now a **single local Docker container**, with on-device source collection and no GitHub-dependent jobs. The earlier Pages checks in this historical contract are **superseded**, not remaining acceptance criteria. The owner also required a genuine readable research dashboard: source-backed graphs visible without opening cards, question-led grouping, comparable economics only and descriptive interpretive readouts. See [the current Phase 3 specification](PHASE_3.md).


**Reviewed:** 2026-11-02, against the user's original finance-dashboard planning conversation, [Phase 3 issue #2](https://github.com/tpepels/finance_dashboard/issues/2), [Phase 1 architecture](ARCHITECTURE.md), [Phase 2 feature contract](PHASE_2_FEATURE_CONTRACT.md), and the [macro-first decision](PHASE_2_MACRO_SCOPE_AMENDMENT.md).

## Original user experience, in order of priority

1. A **single vertically scrolling page** organized into economic themes; collapse themes and expand **individual** charts. An overview must remain readable; no room-filling toolbars or permanent menus. Yardeni-like research view.
2. First chart: actual BIS Fed, ECB/euro-area and BOJ daily policy-rate history. Every chart is sourced from the existing catalog (currently **24 chart definitions and 42 mapped macro series**). Draft chart definitions stay labelled exploratory; no fake data to fill them.
3. On an expanded chart, select visible geography/country series, add suitable comparison series (maximum six to keep legible), and select **5Y, 10Y, 20Y, Max or Custom date range**.
4. **Raw**, **Index 100**, **Percentile** display. No arbitrary twin axes. Raw overlay requires identical frequency and units. Cross-frequency index/percentile is a *visual display operation*, not an economic aggregate; use source-native recorded dates, no interpolation, carry-forward or future data. Index 100 baseline is the first visible observation for each series; zero baselines cannot be indexed. Percentile is the within-selected-range empirical rank, minimum 20 observations, tied observations share mid-rank. Economic derived indicators remain Python-owned; browser display normalizations must be transparent and never represented as source observations.
5. Inspect documented historical event markers, a table of source observations, provenance, source links and recorded data freshness. CSV, PNG, JSON chart-configuration export and deep link sharing preserve the visible user selection.
6. Accessible keyboard-operable controls, responsive desktop/mobile layout, readable axes and source caveats. Empty, stale, missing and rights-blocked data are distinct statuses. Do not interpolate eight actual MSCI index concentration observations into a continuous line.

## Implementation boundaries

- **One Vite/React/TypeScript app**, Apache ECharts. No UI state framework, route library, chart scripting, user accounts, application backend, Redis, microservices, recommendation engine or new market provider.
- Load existing backend `/api/series`, `/api/charts`, `/api/query` and `/api/data-status` for private/local use. Static mode consumes the existing validated `index.json`, `charts.json` and per-series JSON with the same visual components.
- **Public GitHub Pages** can only receive data explicitly approved for redistribution. Current catalog flags **37/42 as rights review required**. A public-safe build must filter those series and all instrument/FX/supplementary files and fail on contamination; missing public series appear unavailable with a rights explanation. The app is fully functional with all 42 when supplied by the local API or private static artifact. Public access does not imply rights clearance.
- Don't silently switch to ETF portfolio behavior. The optional 24 market instruments remain implemented in Phase 2, but are not the focus or required navigation in the macro dashboard.
- Use the **existing theme and graph definitions** as the initial contents; don't invent an unrelated taxonomy or auto-generate new technical indicators.

## Acceptance (all required)

- Every mapped/draft catalog chart appears in its correct collapsible theme; first BIS three-bank graph is operational; all 42 macro sources can be chosen for relevant compatible comparisons.
- All chart controls listed above work end to end, including custom dates, missing/negative/zero data, cross-frequency presentation, sparse history and no fictitious values; tests verify calculations and source alignment.
- Responsive chart/table/provenance, source and freshness, original/exported data and share links are verified.
- React build, tests, and a rights-filtered public static-data preparation path succeed in short CI; a private complete dataset remains usable without public disclosure.
- No public deployment of 37 rights-unreviewed series; Pages publication only if the repository's GitHub Pages configuration and licenses permit the filtered result. An Actions build is **not** a live website.

Phase 4 features (portfolio analysis, arbitrary technical indicators, alerts, derived scores, execution and deployment hardening) are intentionally excluded.
