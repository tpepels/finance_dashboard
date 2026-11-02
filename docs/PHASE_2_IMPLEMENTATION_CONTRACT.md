# Phase 2 — locked implementation and verification contract

Status: **baseline frozen on 2026-11-02**. This records the complete delivery target, actual source paths and a source-evidenced acceptance matrix. It must not be interpreted as declaring Phase 2 complete. See [features](PHASE_2_FEATURE_CONTRACT.md) and [architecture](PHASE_2_ARCHITECTURE_CONTRACT.md).

## Implementation map

| Component | Authoritative paths | Required behaviour |
|---|---|---|
| Catalog / validation | `definitions/series.json`, `definitions/charts.json`, `src/finance_dashboard/catalog.py` | 38 definitions (34 original + 4 new global macro), 36 mapped and 2 original unresolved; source/frequency/unit validation |
| Macro providers | `providers.py`, `bis.py`, `remaining_sources.py`, `world_credit.py`, `macro_aggregates.py` | Complete 36 live mapped sources: original 32 plus WDI world capitalization, matched world cap/GDP ratio, Siblis world trailing P/E and same-universe earnings yield |
| Optional market registry / ingestion | `definitions/instruments.json`, `market.py`, `market_service.py` | Retain all 24 implemented listings, raw/adjusted prices, dividends, splits, proper historical ex-dates and exchange/currency checks |
| Optional market analytics / export | `market_analytics.py`, `market_export.py` | Four distinct return conventions, ECB USD/GBP/CHF FX conversion, explicitly labelled GLD/VT 36m proxies |
| Persistence | `database.py`, `service.py`, `migrations/` | Append-only versioned records, ingestion runs, transactions, date/type fidelity, previous successful values on failure |
| Query API | `api.py` | Read-only `/api/series`, `/api/charts`, `/api/query`, `/api/data-status`, market routes, `/api/earnings/sec-filers` |
| Scheduled and static data | `worker.py`, `static_export.py`, `.github/workflows/static-data.yml` | all mapped data; complete fail-closed JSON artifact, no secrets |
| Wisesheets supplementary | `wisesheets.py`, `.github/workflows/wisesheets-refresh.yml`, `data/wisesheets/sec_filer_profit.json` | monthly, quota-bound full accessible SEC-filer scan, strict provenance/FX/fiscal-year checks and coverage |
| Original worldwide profits | **not implemented** | Source adapter + normalized worldwide issuer master + full historical net profits + GDP + reconciliation |
| Original historical concentration | **not implemented** | MSCI entitled constituent source or equivalent validated source file + historical free-float weights + top-ten sum |

## Frozen algorithm and data contracts

1. **BEA Q1:** replacement-cost published BEA annual corporate valuation. No Fed equity/net-worth substitution.
2. **ILO productivity/compensation:** `100 / world labour income share (%)`, explicitly accounting-implied including self-employment, not independent wage growth.
3. **World credit:** 43 BIS national credit gaps `C`, excluding aggregate `XM`; previous-calendar-year nominal USD World Bank GDP weights; publish only periods with at least 80% world-GDP coverage; publish companion actual coverage.
4. **Gold/index:** matched monthly *mean levels* of World Bank USD/oz gold and MSCI ACWI code 892400 NETR USD; monthly arithmetic returns; 36 complete consecutive returns; Pearson correlation. GLD/VT ETF last-session monthly vendor-adjusted returns are *different* named series.
5. **Market returns:** raw price index, vendor-adjusted index, cash dividend reinvestment with splits, and ECB-converted EUR-adjusted index each start at 100 on the eligible first observation. Do not present raw returns as total return; do not misapply foreign-per-EUR FX.
6. **Wisesheets:** deduplicate SEC CIKs, collect `net_income` with real filing dates/accessions, preserve negative values, reject invalid/untraceable/future records, convert each reporting fiscal year's currency to USD with audited ECB rates, divide only by corresponding World Bank nominal world GDP, expose exclusions, survivorship limitations, freshness and issuer counts. Validated scan: 8,179 CIKs, 6,161 verified financial issuers, 2021–2025, 150 requests.
7. **Historical MSCI concentration (outstanding):** at each composition date, sum ten largest *actual MSCI security weights* after source total-weight validation; preserve security/share-class identities, dates and revision provenance. Monthly multi-year history is required. No present-day-membership backtest.
8. **Worldwide listed profits (outstanding):** annual or consistent TTM consolidated net income attributable to ordinary shareholders, including losses, unique issuer and global geography, fiscal alignment, USD conversion and current USD world GDP. Track missing-data coverage, delistings, cross-listed shares and consolidated parent/subsidiary eliminations. An MSCI or Siblis earnings estimate derived from an index P/E is allowed *only as a separately named proxy*, with compatible same-date index cap/P-E and explicit provider method.

9. **Global macro aggregates (implemented):** WDI `WLD/CM.MKT.LCAP.CD` capitalization current USD (51 annual observations, 1975–2025); derived same-year world WDI cap / world GDP * 100, 51 annual; Siblis published sparse global trailing P/E (11 snapshots: Dec 2016–2025 and Sep 2026) and 100/P-E yield, 11 corresponding snapshots. World Bank WLD market-cap/GDP derived from levels is distinct from the WDI weighted-country share; different P/E universes must **never** be mixed to claim global net earnings/GDP. Siblis redistribution restricted.

## Definition and completion gates

| Gate | State as of baseline | Evidence / outstanding requirement |
|---|---|---|
| Original 32/32 mapped macro + derived series | **PASS** | [complete original macro PostgreSQL ingestion and API](https://github.com/tpepels/finance_dashboard/actions/runs/41476599670) |
| 4 new macro aggregates, real public provider responses/static export | **PASS** | [36-series source-validated static export](https://github.com/tpepels/finance_dashboard/actions/runs/41492850778) |
| 36-series macro PostgreSQL ingestion and API | **OPEN pending fresh full acceptance** | Entire new mapped catalogue plus original series, not 32-only smoke test |
| Optional 24/24 market histories + 3/3 ECB FX | **PASS — nonblocking** | [real market PostgreSQL/API](https://github.com/tpepels/finance_dashboard/actions/runs/41470443707) |
| Combined mapped static artifact | **PASS** | [36-series macro export plus optional markets](https://github.com/tpepels/finance_dashboard/actions/runs/41492850778) |
| Wisesheets SEC-filer supplementary history | **PASS — limited universe** | [full documented 2021–2025 scan](https://github.com/tpepels/finance_dashboard/actions/runs/41483503450) |
| `concentration.global.top10` | **OPEN** | Historical original MSCI security-weight dataset, complete import, calculation, provenance and API/static tests |
| `profit.global.corporate_share` | **OPEN** | Worldwide historical consolidated issuer earnings, consistent GDP formula, missing/delisted-issuer audit and API/static tests |
| Historical instrument ticker/exchange continuity | **NONBLOCKING optional debt** | Already implemented instrument history remains; further per-ETF work removed from macro phase by owner |
| Independent issuer NAV and distributions | **NONBLOCKING optional debt** | No claim of independent issuer audit; owner explicitly removed this Phase 2 condition |
| Full Phase 2 macro regression | **OPEN** | 36 mapped macro series including 4 new sources, supplementary provenance and unresolved exact historical definitions in acceptance report |

Tests must include complete source registries; no tests that pass on a hand-picked subset count as phase completion. Integrate both new original measures in *the existing* registry, persistence model, API and static export, including failure/staleness/rights semantics. Do not mark a definition `mapped` before live source evidence.

## Completion workflow

1. Obtain and verify a complete source with identity, historical dates, economic scope, entitlements and use rights. If no exact source is available, keep original open and add a separately named proxy with explicit owner approval.
2. Add catalog definition/rights metadata and source adapter; implement data-normalization, calculation and revision tracking; migrate schema if needed.
3. Integrate and validate API and static export; use the same calculation service, not duplicated browser formulas.
4. Run bounded unit/property tests for all variations and short real-source/PostgreSQL acceptance; do not block on long CI. Store links/results in issue #1.
5. Record the macro-first owner amendment and remove ETF NAV/ticker audits from mandatory completion; optional market data remains operational.
6. Close issue #1 only after all original and integration gates pass or the owner explicitly approves a change to the frozen contract.

## Contract-change policy

Feature identity, sources, formula scope, universe, outputs and quality gates cannot be reduced or substituted by implementing only a representative subset. A proposed scope change must be approved by the owner and recorded in issue #1, with synchronized edits to the feature and architecture contracts. **A written design freeze is not technical enforcement of repository branch protection.** [Owner-approved macro-first change](PHASE_2_MACRO_SCOPE_AMENDMENT.md) supersedes the previous ETF-level acceptance gates.