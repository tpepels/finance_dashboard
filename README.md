# Global Capital Monitor

A source-traceable financial and macroeconomic research application for global equity, labour, credit, valuation, and gold risk.

## Phased delivery

| Phase | Deliverable | Status |
|---|---|---|
| 1 — Data contracts | Validated source and chart catalog, methodology/rights flags | Complete |
| 2 — Macro data infrastructure | Macro feeds, worldwide capitalization/GDP and earnings-yield aggregates, optional 24 market listings/ECB FX, PostgreSQL, worker and FastAPI | **42 mapped macro/index series live-source-verified and integrated; original unavailable definitions explicitly superseded and archived** |
| 3 — Dashboard | Minimal React/ECharts thematic chart explorer with interaction, local API/static data, public rights-filter and Pages workflow | **Frontend implemented; browser/live deployment acceptance pending** |
| 4 — Analytics | Derived economic indicators, ETF/gold portfolio and risk comparison | Not started |

The active catalog now contains **42 mapped macro/index series**: 36 previously verified sources, three free public-source replacements, and three OECD38 country-weighted corporate-surplus and participation series. The two unavailable original series definitions are retained, with the exact change-of-scope rationale, in [`definitions/superseded_series.json`](definitions/superseded_series.json). “Mapped” does not imply the provider has granted public redistribution rights. The original 32 mapped series have been checked against live source responses, including the three BIS policy rates in a separate Docker/PostgreSQL acceptance run and all 23 other series through the source acceptance workflow.

**The owner approved replacements** for the original two inaccessible historical indicators: [publicly documented MSCI ACWI top-ten index snapshots](data/msci_acwi_published_snapshots.json), which are sparse rather than monthly, and [official Eurostat EU27 corporate operating surplus relative to EU GDP](docs/PHASE_2_FREE_SOURCE_REPLACEMENTS.md), which includes unlisted corporations and is not worldwide listed-company net profits. A second official Eurostat indicator measures nonfinancial corporate gross surplus/sector gross value added. No original global-earnings or complete monthly index-weight coverage is claimed. Independent ETF NAV and ticker-change audits are no longer macro Phase 2 exit gates, per the [owner-approved scope amendment](docs/PHASE_2_MACRO_SCOPE_AMENDMENT.md). The existing optional market-data layer is already integrated: 24 global/EU/US ETF and stock listings, three ECB FX feeds, source-adjusted closes, dividend and split history, EUR performance, and two labelled GLD/VT proxy correlations. See [market-data contracts](docs/MARKET_DATA.md) and [data coverage](docs/DATA_COVERAGE.md).

## Phase 3 — the macro dashboard

The [original user-approved Phase 3 scope](docs/PHASE_3_CONTRACT.md) is a **single vertically scrolling thematic research page**, not a portfolio system. A small Vite/React/TypeScript frontend uses Apache ECharts and the already validated 42-source Python data layer. Collapsible themes and individually expanded charts expose source-native comparison, periods (5Y/10Y/20Y/Max/Custom), original/index-100/percentile views, context events, sources/ingestion runs, table, CSV, PNG, JSON config and shareable chart URL.

**Private/local with all mapped macro data:** run the existing Docker Compose/FastAPI/PostgreSQL stack, then run:

```bash
cd frontend
npm install                 # Node 24 recommended (npm 11)
npm run dev                 # http://127.0.0.1:5173
```

The frontend uses Vite's local `/api` proxy to `127.0.0.1:8080`; it does **not** expose the home server. Alternative local static mode: from the repository root run `python -m finance_dashboard.static_export --macro-only --output-dir frontend/public/data`, then `VITE_DATA_MODE=static npm run dev` inside `frontend` (private data, do **not** publish).

**Pages:** [manual licence-filtered deployment workflow](.github/workflows/phase3-pages.yml) includes only source data with explicitly confirmed `cc_by_4_0` rights (currently **5 of 42**); all 37 restricted/review-required datasets are withheld from the public artifact. The entire macro explorer is available in local/private mode; the limited public site cannot show restricted Fed/ECB/BOJ data until data redistribution rights are cleared. No permanent Pages publication is claimed. The implementation and publication constraints are documented in [Phase 3](docs/PHASE_3.md).

### Wisesheets in the one-container dashboard

Your `WISESHEETS_API_KEY` stays in the existing GitHub Actions monthly collector; the local Docker Compose **does not need that secret**. Each complete monthly run writes a validated, SEC-reporting-US-listed-filer **annual net income / world GDP** aggregate to `data/wisesheets/sec_filer_profit.json` (2021–2025 currently). The standalone Docker image includes the verified snapshot; its existing daily refresh thread checks the committed GitHub version and updates the persistent local copy when newer, using **no additional Wisesheets API requests or containers**. Open **Supplementary company earnings** in the dashboard or visit `/api/earnings/sec-filers`. Historical issuer/FX coverage is displayed; the measure does **not** represent worldwide listed-company net profits. Disable the no-key GitHub aggregate check with `FINANCE_WISESHEETS_SYNC=0`. [Details](docs/WISESHEETS.md).

## Home-server installation: one additional container

For your existing Plex/Pi-hole/Transmission/media-server Compose stack, use the [single-container finance service definition](docs/home-server-finance-service.yml) and [one-container deployment guide](docs/HOME_SERVER_DOCKER.md). The finance image contains the React UI + FastAPI + an automatic macro refresh thread + **persistent SQLite**; you do **not** need the repository's separate PostgreSQL, migration, app and worker containers. It uses host port **5052** with `/srv/finance-dashboard` as the persistent database folder. The [full Docker smoke acceptance passed](https://github.com/tpepels/finance_dashboard/actions/runs/41513402528) with actual API/UI responses, migration and volume-backed restart. This mode is local/LAN only; it does not grant public data-redistribution rights.

## Run locally

Requires Docker Compose, a network connection, and a PostgreSQL password.

```bash
cp .env.example .env
# Change POSTGRES_PASSWORD in .env to a long random secret
docker compose up --build -d
docker compose logs --tail=50 worker
curl http://127.0.0.1:8080/api/data-status
```

The `worker` fetches and stores every mapped macro series, all 24 registered exchange listings, and three ECB FX pairs by default, including FRED without a key via its public observations table. `FRED_API_KEY` is optional and enables the official keyed JSON interface instead. Ingestion errors preserve the last successful observations, log an ingest-run failure, and are exposed in the status API.

For a manual refresh:

```bash
docker compose exec worker python -m finance_dashboard.worker --once
# Optional: select a provider from the supported provider list
docker compose exec worker python -m finance_dashboard.worker --once --provider FRED
# Or explicitly rescan full history for older revisions
docker compose exec worker python -m finance_dashboard.worker --once --full
# Market-only backfill/refresh, including corporate actions and FX:
docker compose exec worker python -m finance_dashboard.worker --once --market-only
```

Queries are read-only; the API is bound to local loopback by default.

```bash
curl -sS http://127.0.0.1:8080/api/series
curl -sS http://127.0.0.1:8080/api/charts
curl -sS -X POST http://127.0.0.1:8080/api/query \
  -H 'Content-Type: application/json' \
  -d '{"series_ids":["policy_rate.us.bis","policy_rate.ea.bis","policy_rate.jp.bis"],"start":"2025-01-01"}'
```

Other API routes: `GET /api/health`, `GET /api/series/{id}`, `GET /api/data-status`. OpenAPI at `/docs`.

Market data API:

```bash
curl -sS http://127.0.0.1:8080/api/markets
curl -sS http://127.0.0.1:8080/api/market/status
curl -sS -X POST http://127.0.0.1:8080/api/market/query \
  -H 'Content-Type: application/json' \
  -d '{"instrument_ids":["vwce.de","vwrl.as","vt","gld"],"start":"2025-01-01"}'
curl -sS 'http://127.0.0.1:8080/api/market/gold-world-proxy?currency=EUR&window_months=36'
```

Raw and adjusted price returns, vendor-adjusted index, dividend-reinvested index and EUR-adjusted returns remain distinct. The two gold/VT correlations are explicitly **ETF proxies**, not the original global-index/spot-gold definition.

## GitHub Actions static data build

A scheduled workflow now validates the repository secret **FRED_API_KEY**
through the official FRED API, fetches all mapped series, and uploads a
key-free **finance-dashboard-static-data** JSON artifact. It runs daily at
06:20 UTC and on manual dispatch. The newest complete public-source static-data build exported **42 macro/index series**, including 51 annual world listed-cap and cap/GDP observations each and 11 published global P/E and earnings-yield snapshots each, alongside the optional 24 market histories, three ECB FX feeds and two ETF proxies: [successful 42-series export](https://github.com/tpepels/finance_dashboard/actions/runs/41503489558).

See [static export architecture and secret handling](docs/STATIC_DATA.md).
This produces the data needed by a future GitHub Pages frontend; **Pages is
not yet deployed**, because the React dashboard belongs to Phase 3.

## Verification

- [Full live source acceptance — 23 non-BIS-policy series](https://github.com/tpepels/finance_dashboard/actions/runs/41459407905): includes all FRED series using the public table and the Federal Reserve's corporate equity/net-worth series, gold spot quote, BIS credit gaps, Siblis ACWI CAPE, World Bank WDI/Pink Sheet, IMF, ECB, ILO/UNSD and Shiller.
- [Three BIS policy-rate series, real Docker/PostgreSQL backfill and FastAPI query](https://github.com/tpepels/finance_dashboard/actions/runs/41449348048).
- [Short offline / PostgreSQL integration test suite](https://github.com/tpepels/finance_dashboard/actions/runs/41459407973).
- [Market static build: 24 instruments, 3 FX feeds](https://github.com/tpepels/finance_dashboard/actions/runs/41470215544).
- [Market Docker/PostgreSQL acceptance: all 24 listings](https://github.com/tpepels/finance_dashboard/actions/runs/41470443707).
- [Open Phase 2 completion tracker](https://github.com/tpepels/finance_dashboard/issues/1).

In the three-series BIS Docker test, 26,416 US, 10,130 euro-area, and 24,914 Japanese historical observations were ingested and queried. No permanent deployment has been created. All 24 market instruments and three ECB FX feeds additionally passed [full historical Docker/PostgreSQL ingestion and API validation](https://github.com/tpepels/finance_dashboard/actions/runs/41470443707). The other 29 non-BIS-policy macro/index sources have live source/fixture validation but have not been jointly production-backfilled in the same Docker run. Published revisions can be reingested without destroying the prior observed values; the application's first-seen timestamp is **not** a provider publication vintage.

## Limits

The API does not offer trade instructions, generic market-data redistribution, a React dashboard, historical true-spot gold prices, or a consistent world financial-company profit aggregate. The Siblis ACWI CAPE free API supplies sparse proprietary snapshots for personal noncommercial research; **do not publish its data to GitHub Pages without separate rights**. See [Source policy](docs/DATA_POLICY.md), [architecture](docs/ARCHITECTURE.md), and [Phase 2 details](docs/PHASE_2.md).


### Wisesheets SEC-reporting company profits (supplementary)

The new GitHub Actions secret `WISESHEETS_API_KEY` is connected and
live-verified. Wisesheets' free fundamentals service offers up to five annual
observations for SEC-reporting, US-listed issuers, **not** a complete worldwide
listed-company universe. An independent monthly pipeline enumerates SEC
filers, deduplicates by CIK, retains losses, converts non-USD profits using
ECB historical rates and compares the partial US-listed aggregate with
World Bank world GDP. Incomplete SEC filing provenance, unavailable FX
and source data quality are explicitly reported; the original
The superseded global listed-company net earnings/GDP original is retained as historical requirement provenance in [`definitions/superseded_series.json`](definitions/superseded_series.json); the active national-accounts replacement is EU27-only and separately labelled.

The first complete scan **passed** on 2026-11-02: 8,179 distinct SEC issuer CIKs in the current universe; **6,161** issuers with filing-traceable historical annual earnings. Five annual aggregate years (2021–2025) were retained, using only 150 authenticated requests. [Successful full run](https://github.com/tpepels/finance_dashboard/actions/runs/41483503450). The aggregate is available through `GET /api/earnings/sec-filers` and the static export. It is not fetched by the browser and never
contains your API key. See [Wisesheets methodology](docs/WISESHEETS.md).

## Four exact original indicators resolved (2026-11-02)

The six Phase 2 data-definition gaps have been reduced to two:

- **US Tobin's Q:** published BEA Q1 (equity market value divided by current replacement-cost net stock of produced assets), annual 1960–2024; not the unrelated Fed NCBCEPNW proxy.
- **Global labour productivity/pay:** an exact **implied** GDP-per-hour to all-labour-income-per-hour ratio derived as 100 / ILO SDG world labour-income-share percentage. The same global hours cancel. Not independently sampled hourly wages; includes imputed self-employment labour income.
- **International credit-gap composite:** 43 individual BIS national private credit/GDP gaps, GDP-weighted using previous-year nominal USD WDI GDP. Excludes euro-area aggregate to avoid double counting. Releases quarters only when countries with data cover at least 80% of world GDP. **Not an official BIS-published world gap.**
- **Gold/global equity index:** World Bank monthly mean gold vs real **MSCI ACWI NETR USD index** levels, both averaged over each month, Pearson rolling on 36 consecutive monthly returns; not the GLD/VT ETF proxy.

The two outstanding exact datasets remain historical MSCI ACWI constituent free-float weights and consolidated worldwide **listed-company earnings** with defensible multinational allocation. A current index fact-sheet or index P/E snapshot cannot reconstruct either history. See [exact gap audit](docs/ORIGINAL_GAPS.md).

Historical issuer NAV reconciliation, ticker rename continuity, and a permanent production deployment are separately tracked. A full 32-source historical PostgreSQL ingestion and read-only API smoke test passed in a disposable environment; [acceptance run](https://github.com/tpepels/finance_dashboard/actions/runs/41476599670).

### Phase 2 locked project contracts

The source-of-truth project baseline (features, component ownership, delivery acceptance and scope-change policy) is recorded in [feature contract](docs/PHASE_2_FEATURE_CONTRACT.md), [architecture contract](docs/PHASE_2_ARCHITECTURE_CONTRACT.md) and [implementation contract](docs/PHASE_2_IMPLEMENTATION_CONTRACT.md). These documents freeze the *agreed requirements*, not the code or GitHub branch permissions. [Archived exact-data sources and Yahoo/aggregate alternatives](docs/ORIGINAL_GAPS.md#source-access-assessment-yahoo-finance-and-aggregated-alternatives-2026-11-02) are separately assessed. The owner explicitly approved the [free-source contract change](docs/PHASE_2_FREE_SOURCE_REPLACEMENTS.md), superseding two unavailable original datasets and optional per-ETF completion conditions.

## Macro-first scope and four new aggregate histories (2026-11-02)

The owner's [macro-first scope amendment](docs/PHASE_2_MACRO_SCOPE_AMENDMENT.md) makes aggregate macroeconomics and structural-financial risk the product priority. Individual ETF holdings, independent issuer NAV audits and ticker-change continuity are **not required to complete macro Phase 2**. Existing market APIs remain available and were not removed.

| New world macro series | Data and method | Verified public source sample |
|---|---|---|
| `valuation.world.listed_market_cap_usd` | WDI WLD listed-domestic-company market capitalization, current USD; WFE-derived | 51 annual years (1975–2025) |
| `valuation.world.listed_market_cap_world_gdp` | 100 × WDI WLD capitalization in USD / WDI WLD nominal GDP in USD, matched annual years | 51 annual years (1975–2025); note narrower changing capital-market coverage |
| `valuation.world.global_trailing_pe` | Siblis ~3,000-company Global index normalized trailing P/E | 11 selected month-end observations: 2016–2025 Dec plus September 2026 |
| `valuation.world.global_earnings_yield` | 100 / preceding Siblis P/E; same index and date | 11 selected month-end observations |

**Source-verified complete export:** [36 mapped macro sources](https://github.com/tpepels/finance_dashboard/actions/runs/41492850778). All four are wired through the existing provider router, definitions, chart catalog, API-compatible observation storage and static export. [**All 36 mapped macro/index sources passed complete PostgreSQL ingestion and FastAPI readback**](https://github.com/tpepels/finance_dashboard/actions/runs/41494100275), including the new global aggregates. No full multi-decade Siblis source or worldwide listed-company profit measure is claimed. Do **not** multiply World Bank WFE market capitalization by Siblis index earnings yield to estimate total listed profits/GDP: these have different security universes and valuation accounting. Siblis data is proprietary and may not be redistributed on public Pages without permission.

## Free public-source replacements — owner-approved 2026-11-02

[Scope/definition contract](docs/PHASE_2_FREE_SOURCE_REPLACEMENTS.md) | [Original specifications archived](definitions/superseded_series.json) | [Dated MSCI index evidence](data/msci_acwi_published_snapshots.json).

Three **new mapped** macro sources replace two inaccessible originals without using ETF holdings or proprietary data:

- **MSCI ACWI index concentration:** eight explicitly source-dated top-ten index constituent weight totals (2019–2026). Not a complete monthly time series; no missing-month fills.
- **EU27 corporate gross operating surplus / EU GDP:** official ESA2010 annual Eurostat S11+S12 corporate sectors' gross operating surplus, divided by matched EU27 S1 GDP, both current EUR (**24 annual years**).
- **EU27 NFC gross operating surplus / NFC GVA:** independently published annual Eurostat nonfinancial-sector gross profit share (**27 annual observations**); different denominator from GDP.

[Complete **39/39 mapped macro-series** public-source static export passed](https://github.com/tpepels/finance_dashboard/actions/runs/41498656329). [Full macro PostgreSQL/API integration acceptance](https://github.com/tpepels/finance_dashboard/actions/workflows/all-macro-postgres.yml) is tested separately. OECD SDMX returned 403 in GitHub CI, so **no OECD/world corporate-series coverage** is asserted. The two original global listed-company net earnings and uninterrupted historical MSCI concentration definitions are explicitly superseded, not fraudulently claimed as reproduced. MSCI and Siblis redistribution rights must still be cleared before public dashboard deployment.

**OECD geographic coverage gate resolved (2026-11-02):** Correctly specified official **annual** OECD SDMX sector accounts are accessible without institutional access; the previous 403 came from an incorrect quarterly/format probe. [OECD38 GDP-weighted corporate gross surplus/GDP](docs/OECD_CORPORATE_SURPLUS.md) has **25 years, 2000–2024**, with separate member GDP coverage and contributor counts; a valid USD/JPY/CAD World Bank current-LCU GDP fallback is used only for the US/Japan/Canada where OECD net product-tax balances are missing. All [42/42 mapped PostgreSQL/FastAPI observations](https://github.com/tpepels/finance_dashboard/actions/runs/41503545569) and [42/42 static exports](https://github.com/tpepels/finance_dashboard/actions/runs/41503489558) passed. Eurostat EU27 indicators remain available independently. The constructed OECD reporting-country composite is not an OECD-published whole-group total and does not claim a complete 38/38 member sample in every year.

## Final OECD coverage implementation (2026-11-02)

The earlier OECD source-access blocker is resolved through the **official, free annual** `OECD.SDD.NAD,DSD_NASEC10@DF_TABLE14,1.1` endpoint. Three mapped sources are in the existing worker/PostgreSQL/FastAPI/chart/static-export pipeline: OECD38 GDP-weighted corporate operating surplus/GDP, annual eligible-member GDP coverage %, and annual eligible member count. All **25 published annual points from 2000–2024** passed full source validation. The member pool is fixed to 2026's 38 OECD members; only years above 80% covered GDP with sufficient observations are output. Official OECD S11/S12 corporate gross operating surplus remains the numerator for **all** reporting countries; USD/JPY/CAD national GDP fallback uses same-year World Bank LCU nominal GDP only where the OECD S1 product-tax balance is missing. [Methodology](docs/OECD_CORPORATE_SURPLUS.md) · [Full PostgreSQL/API PASS](https://github.com/tpepels/finance_dashboard/actions/runs/41503545569) · [Full static PASS](https://github.com/tpepels/finance_dashboard/actions/runs/41503489558). Production/public redistribution rights remain Phase 3 matters.
