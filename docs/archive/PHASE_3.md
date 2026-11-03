# Phase 3 dashboard and requested Phase 4 research indicators

The owner's November 2, 2026 brief refined the original contract:

1. **Actual verified economic measurements**, not merely charted source snapshots.
2. Meaningful *relationships* (only matched sector, geography, output price definitions or explicit denominators), backed by source math.
3. Main economic graphs in an **always-visible, logically ordered responsive grid**. Raw series charts remain available separately.
4. Geographic and institutional scope must be explicit: World, OECD38, United States, Euro area/EMU, EU27 and Japan are different aggregates. MSCI ACWI is US-capitalization dominated, **not an equal-weighted global economy**.
5. Labor distribution and Marxian political economy belong to the dashboard **alongside** growth, credit, yield curves, valuation and concentration, with data/methodology caveats.
6. Three **unlabeled light gray NBER US recession windows**, not named stock-crash annotations on the graphs.

## Delivered implementation on `main`

- **46 indicators** with actual source IDs and research questions, grouped across five regional tabs: World & OECD (12), United States (14), Euro area & EU27 (6), Japan (6), and Compare regions (8).
- Seven additional **FRED/BLS/Penn World Table** source contracts (`OPHNFB`, `COMPNFB`, `IPDNBS`, `PRS85006173`, `COMPRNFB`, `LABSHPUSA156NRUG`, `T10Y3M`), using the existing provider adapters. The canonical source catalogue now holds **53** mappings.
- Dedicated Python `research.py` indicator registry and `GET /api/research` and `GET /api/research/{id}`, alongside unchanged `/api/series`, `/api/query`, `/api/charts`, and `/api/data-status` API.
- Real source-dated latest readings and dated annual changes for each plotted series. Multi-country common-date high-low differences are calculated **only when every requested geography has a reading on an identical source date**.
- `us_productivity_pay` joins BLS quarterly nonfarm business output/hour and hourly compensation deflated by the **same-sector output deflator**, with a 2017=100 index and an explicit baseline-relative ratio gap. CPI compensation is separately displayed.
- `us_labour_share_gdp` converts the **annual PWT fractional GDP labour share into percent**, preserving source chronology and warning this is not the BLS sector index or a direct exploitation measure.
- The research frontend renders graph cards as the user scrolls, not after clicking. Each exposes the source data and methodology and includes an explicitly bounded economic interpretation and limitation.
- Original 21 source charts, the source library, 53 source definitions, source provenance, Wisesheets US SEC filings supplemental panel and original chart interaction controls are available inside **Source data & chart explorer** at the bottom, collapsed by default. No losing source functionality for the editorial page.
- Shared ECharts rendering shades **2001-04 through 2001-11, 2008-01 through 2009-06, 2020-03 through 2020-04** in flat gray with **no text, dotted lines or event labels**. These are NBER-dated US contraction months and remain explicitly US-only even on World/OECD/Japan graphs.
- One local Docker service bundles React, FastAPI, SQLite WAL and in-process macro/Wisesheets updates. No GitHub Actions, Pages or local source-use gates.

**Source and methods:** [ECONOMIC_RESEARCH_METHODS.md](ECONOMIC_RESEARCH_METHODS.md) provides formulas, primary links, limitations, measurement scope, NBER definition and academic context.

## Explicit Phase 3/4 boundary

**Phase 3 work requested and implemented here:** meaningful geographic filters, always-on layout, visible charts, primary-source provenance and metadata, macroeconomic chart taxonomy, source explorer, descriptive narrative, 2001/2008/COVID recession shading.

**Phase 4 work requested and implemented here:** newly **calculated** economic relationships (US productivity/output-price-real compensation and indexed ratio gap), source-aligned changes and multi-country comparisons, national-accounts labour distribution interpretation with actual indicators.

**Still outside this work (remaining Phase 4):** any formal Marxian surplus-value rate estimated from harmonized national input-output accounts, systematic profit-rate estimation, decomposition of economic causes, recession forecast probabilities, historical multi-factor backtests, numerical risk score validation, scenario/portfolio models and strategy recommendation. Source-based descriptive insights do **not** establish these.

## Acceptance and verification

New [Python research contract tests](../tests/test_research.py), [frontend view tests](../frontend/src/App.integration.test.tsx) and [gray-band rendering tests](../frontend/src/viz.test.ts) cover actual source mappings, exact-quarter deflator calculations, no fabricated rows, geographic tab switching, source explorer and NBER periods.

The one-container [Dockerfile](../Dockerfile) now runs short frontend tests/TS build and focused Python research/insight tests during the local build. **No GitHub CI** exists. Since the assistant does not have access to the home server or its source database, the revised container and physical browser have **not yet been validated on the user's machine**. A local build and live-source graphical inspection are needed before closing acceptance; no completion claim is based solely on repository changes.

### Run

```bash
git -C finance_dashboard pull --ff-only
docker compose up -d --build finance-dashboard
docker compose logs --tail=100 finance-dashboard
```

Use **http://media-server:5052** to inspect the research tabs, or the new `/api/research` endpoint to verify the research definitions. Original Phase 3 requirements and subsequent superseding local-only decisions are archived in [PHASE_3_CONTRACT.md](PHASE_3_CONTRACT.md).


## November 2026: analytical UI correction

The former generic graph-only default failed the research/dashboard acceptance goal. Current work replaces it with a calculation-aware presentation:

- Historical BLS output-price-deflated pay/productivity ratio gap, **at every exact common quarter**, displayed separately from the original two 2017=100 index levels. The gap is explicitly baseline-relative, not a wage/profit accounting ratio.
- Paired GDP labour/non-labour residuals are displayed as stacked 0–100% compositions. The residual is explicitly **not** gross corporate profit.
- Multi-country charts display **ranked bars at the latest fully common source date** and source-native historical trends separately. No ranking from mixed source dates.
- Annual GDP growth and matched annual differentials use diverging bars with a zero reference. Other quarterly/daily differences retain a continuous source-time axis and zero reference. Credit dispersion has a nonnegative axis.
- Single-series raw source graphs now include a sample-bounded historical min/median/max and latest midrank, where at least twelve real observations exist. Short source snapshots are never interpolated or given artificial historical percentiles.
- Phase 4 risk diagnostics expose their source-history rank and signed distance from original published criteria. ETF comparisons display a correlation matrix, and recession backtests plot observed outcome frequencies versus **mean predicted probabilities** from test cases.
- New frontend rendering contracts verify type-specific chart geometry, stacked accounting relationships, common-date ranking, and the computed productivity-gap panel.

An interactive dashboard does not itself close remaining empirical validation. Models require independent historical release data, original N-PORT filings, and authenticated OECD sector/capital-stock accounts. Source-aware empty states remain required when these data are not imported.


World labour income share is provided by UNSD/ILO **as a percent**, so the World & OECD comparison now plots the original measured labour share with its strictly arithmetic `100 − share` non-labour remainder as a stacked composition. US/Japan Penn World Table shares remain fractions converted to percent. These are deliberately distinct unit-handling branches.
