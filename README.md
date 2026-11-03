# Global Capital Monitor

A **single-container, local-only economic research dashboard**. It combines actual public statistical measurements, defensible relationships and economic interpretations in a visible layout. The original raw source chart explorer is available below the main research page.

## Run

```bash
cp .env.example .env
mkdir -p data-local
# Enter your WISESHEETS_API_KEY and optional FRED_API_KEY in .env.
docker compose up -d --build finance-dashboard
docker compose logs --tail=90 finance-dashboard
```

Open `http://localhost:5052/` (or `http://media-server:5052/` on your LAN).

The container includes React/ECharts, Python/FastAPI, persistent SQLite, automatic macro updates and optionally monthly local Wisesheets SEC-company earnings aggregation. **There are no GitHub Actions jobs, Pages sites, extra database containers, or separate workers.** Full source history requires successful initial local ingestion; missing data are shown as missing rather than fabricated.

**Using your existing media-server Docker Compose?** Add only [the finance service snippet](docs/home-server-finance-service.yml) under its `services:` block, clone this repo at `./finance_dashboard`, and set the key in that server's existing `.env`. See [deployment instructions](docs/HOME_SERVER_DOCKER.md).

## Economic research dashboard

The main interface is **always visible**: geographically scoped research tabs, responsive two-column chart layout, source-measured latest readings, actual previous-year changes when valid, economics-focused explanations and original source links. Source observations appear in their native frequency; no smoothing or fictitious periods.

| Geographic/institutional scope | Main economic questions |
|---|---|
| **World & OECD** | Real GDP growth, labour income share, productivity growth, OECD corporate gross surplus/GDP and coverage, global debt, 43-economy BIS credit gap, world listed capitalization/GDP, global equity-index P/E/concentration, gold/equity correlation |
| **United States** | Output-price-adjusted productivity versus hourly pay, PWT labour/GDP share, BLS labour share index, consumer purchasing power, policy and real yields, 10y–3m yield curve, Sahm labour stress, BIS credit, Shiller CAPE, BEA Q1 market/replacement-cost valuation, output growth |
| **Euro area & EU27** | Euro-area growth, policy and credit; EU27 gross corporate surplus and sector value added; separately sourced Germany/France/Italy PWT labour/GDP shares (country measures, not EU27 aggregates) |
| **Japan** | PWT national labour income share and non-labour GDP residual, real GDP growth, BIS rates and private-credit gap, domestic listed market-cap/GDP |
| **Compare regions** | Identically defined country GDP growth, BIS policy rates, BIS national credit gaps, World Bank domestic capitalization/GDP and PWT labour/GDP shares in US, Japan, Germany, France and Italy |

**46 research indicators** are now defined, including new matched-date US/euro-area growth and policy differences, BIS cross-economy credit-gap dispersion and the complementary components of US GDP labour income. All 46 are based on mapped source series; the source catalogue has **53 datasets**, including eleven newly mapped BLS/Penn World Table/FRED source series. Initial ingestion may take time. The existing **21 original curated graphs** remain accessible in **Source data & chart explorer**. US SEC-reporting-company Wisesheets earnings are included in the supplementary explorer but are never presented as worldwide corporate net profits.

Three unobtrusive, **unlabeled gray bands** appear on eligible charts for NBER-defined US contraction months associated with the dot-com crash (April–November 2001), global financial crisis (January 2008–June 2009) and COVID (March–April 2020). These are **US recession dates**, not dates of the European or world recessions.

### Evidence over narrative

- **US labour productivity/pay** uses BLS quarterly `OPHNFB`, `COMPNFB` and output deflator `IPDNBS` with exact source-quarter matching. Output-price-adjusted pay is `100 × COMPNFB/IPDNBS` (both source indices 2017=100); the percentage ratio gap is `100 × (OPHNFB/adjusted_pay−1)`. The separately graphed CPI-compensation series measures consumer purchasing power and must not be substituted.
- **Labour distribution / Marxian analysis:** ILO world labour income share, Penn World Table US GDP labour share, BLS nonfarm labour share, EU27/OECD gross corporate operating surplus, and a peer-reviewed Marxian accounting interpretation with clearly stated limitations. These observable data **do not directly measure Marx's surplus value / variable capital**, and the non-labour GDP residual cannot simply be relabelled as profits or exploitation.
- **Global equities ≠ world output:** MSCI ACWI was **64.21% US** by index country weight on September 30, 2026. Global equity-weighted data and world GDP aggregates are explicitly distinguished.
- **No synthetic facts:** Derived graphs join observations only at precisely matching source dates, and geopolitical/cohort boundaries stay named. Annual changes use actual nearby dates with a documented tolerance; common-date country comparisons do not invent or carry forward missing data.
- **Explicit data sources:** Each research chart shows original source URLs, methodology, exact source dates and missing-data states. All methods and independent research references are documented in [Economic research methods](docs/ECONOMIC_RESEARCH_METHODS.md).

The original source catalogue and 21 original charts remain available. The browser retains CSV/PNG export, native source history, provenance, share links and optional per-chart normalized display in the secondary explorer.

## Phase 4: publisher-defined risk and EUR investment comparison

The main research page now includes **Risk evidence and observed market outcomes** above the original source explorer, with two separate views.

**Economic risk evidence:** source-defined FRED Sahm unemployment deterioration ≥0.50 pp, US Treasury 10-year minus 3-month yield inversion below zero, BIS national credit-to-GDP gap compared with the +2 pp Basel **guide**, Shiller US CAPE's descriptive recorded-history percentile and a separately scoped international credit composite. These statistics explicitly show latest source dates, stale/missing observations, and limitations; none creates a crisis probability or combined score. Read [Phase 4 methodology](docs/PHASE_4.md).

**Optional asset history:** compare 2–5 source-registered ETFs/stocks or gold ETFs in **EUR or USD** with matched actual months, vendor-adjusted price indexes, drawdowns, peak/trough/recovery, monthly-return correlation and sample annualized return/volatility. Optional holdings weights produce a transparently defined monthly-rebalanced *scenario* with no fees/taxes. **True dated fund look-through geographic/sector holdings are not supplied** and are never guessed.

The full-collection home-server configuration uses `FINANCE_INCLUDE_MARKETS=1` to ingest market histories and ECB FX. Verify that your **existing** Compose service passes the value through rather than hardcoding `0`, then recreate it. The existing collector will attempt 24 Yahoo histories and ECB FX; upstream rate limits or missing observations remain visible. In EUR mode, only actually stored ECB-convertible observations are used; mixed-currency USD comparisons are rejected rather than inventing conversion data.

**Resilience:** `GET /api/operations` reports source/market/FX coverage, ingestion failures and the latest verified backup. The existing daily refresh process now creates SQLite **online backups** after ingestion, keeping 14 bundles under `/data/backups` by default. Backups must also be copied to an independent disk. Manual run and check:

```bash
docker compose exec finance-dashboard python -m finance_dashboard.backup --output-dir /data/backups
docker compose exec finance-dashboard python -m finance_dashboard.backup --verify-manifest /data/backups/ACTUAL_FINANCE_MANIFEST.json
```

The second command requires the exact filename emitted by the first (replace the example). The server defaults to LAN binding; `FINANCE_BIND_HOST=127.0.0.1` optionally confines it behind your existing reverse proxy. The service has no built-in user authentication; do not forward its port to the public internet.

## Historical-research evidence: original vintages, fund filings, national accounts

Phase 4 now also exposes a **Historical data and methods** panel with four independent primary-source workflows:

- **ALFRED as-of comparison:** original historical FRED release-time series and revision differences. Three source IDs are supported: T10Y3M, SAHMREALTIME and USREC. The in-process collector automatically captures the previous completed month when `FRED_API_KEY` is present. Backfill older historical vintages using the bounded `python -m finance_dashboard.vintage` CLI.
- **SEC dated ETF holdings:** exact public N-PORT accession, verified CIK and fund series, original filing XML, issuer-country weights and missing-weight coverage. Historical eligibility uses a disclosed conservative filing-date buffer, **not** an invented actual publication timestamp. Irish UCITS are excluded rather than misidentified as US registered funds.
- **OECD 2025 industry accounts:** explicitly source-normalized value-added and depreciation accounting, theory-dependent ISIC scenarios and optional imputed self-employment. Capital-stock profit-rate analogues remain unavailable without complete corresponding capital-stock observations. A national-account accounting ratio is not an observed Marxian exploitation rate.
- **Recession backtest:** a predetermined expanding-window logistic model using **ALFRED as-of source features and labels actually known when training**, evaluated only on complete later recession windows. Brier, AUC and calibration are **withheld** until the source sample has adequate event and non-event coverage. Retrospective evaluation never becomes a claim of validated live crisis probability.

Full source data acquisition, responsible issuer/CIK identification, dataset limitations, verification gates and example local commands: **[Phase 4 primary-source research workflow](docs/PHASE_4_RESEARCH_SOURCES.md)**. The four integrations are source-data-gated; these are research capabilities, **not a claim that the home server has already imported and scientifically validated the historical datasets**.

## Phase boundaries

**Phase 3:** permanently visible dashboard, ordered chart layout, original source explorer, meaningful geographic divisions, subdued recession backgrounds, documentation and presentation of descriptive findings.

**Phase 4 (the portion implemented here):** an analytically derived BLS same-sector compensation/productivity comparison and indexed distribution gap, PWT labour/non-labour national income components (the residual is not profits), exact-date cross-economy GDP-growth/policy-rate differences, credit-gap dispersion and consistent year-change statistics. The broader planned Phase 4—predictive macroeconomic models, causal attribution, formal surplus-value accounting, validated scenario models and robust economic risk scores—**is not complete** and is not claimed.

## Local tests

No GitHub CI is configured. The local Docker build runs quick Python research/insight tests, frontend Vitest tests, TypeScript checks and production bundling:

```bash
docker compose up -d --build finance-dashboard
docker compose ps finance-dashboard
docker compose logs --tail=90 finance-dashboard
```

For direct development:

```bash
python -m pip install -e .
python -m unittest discover -s tests -p 'test_research.py' -v
python -m unittest discover -s tests -p 'test_insights.py' -v
cd frontend
npm install
npm test
npm run build
npm run dev
```

Vite proxies `/api` to `http://127.0.0.1:5052` by default; set `VITE_API_PROXY_TARGET` if your Docker port differs. `/api/health`, `/api/research`, `/api/data-status` and `/api/earnings/sec-filers` are available under the same-origin local API.

**Verification:** Source IDs, documentation and tests have been added to the repository, but the revised code has not been run in a real graphical browser or deployed on your machine through this chat. The local Docker build and your real-data visual inspection remain necessary before closing acceptance.

Third-party provider copyright and redistribution rights still apply outside this local application; no local source rights gating is implemented.

## Complete data-source setup, audit and indicator acceptance

For the existing home-server deployment configure **all** collectors, source credentials, historical backfill and verified backup components with [the complete source checklist](docs/SERVER_SOURCE_SETUP.md). The [46-indicator acceptance matrix](docs/INDICATOR_ACCEPTANCE_MATRIX.md) separates implemented research views from evidence actually verified on the server. A GitHub Actions API secret does not configure the home-server container; keep the existing bind-mounted `/data` intact.

## Research interface and remaining exact indicators (2026-11-03)

The same **one-page** interface has a compact selected-scope header, region/time controls, date-correct charts, readable bars for sparse records, stronger NBER recession bands, semantic chart/risk colors and a persistent light/dark setting. Chart interpretations and technical source details are closed until requested. Appearance changes preserve the underlying rendered components and stored source state rather than remounting the entire page.

The full unresolved-definition list, original-versus-proxy distinction, live local gaps and whole-scope implementation/acceptance order are in [Missing indicators and plan](docs/MISSING_INDICATORS_PLAN.md). These changes are only considered runtime-verified after a successful local build and desktop/mobile, light/dark browser inspection.
