# Phase 2 — locked implementation and verification contract

Status: **baseline frozen on 2026-11-02**. This records the complete delivery target, actual source paths and a source-evidenced acceptance matrix. It must not be interpreted as declaring Phase 2 complete. See [features](PHASE_2_FEATURE_CONTRACT.md) and [architecture](PHASE_2_ARCHITECTURE_CONTRACT.md).

## Implementation map

| Component | Authoritative paths | Required behaviour |
|---|---|---|
| Catalog / validation | `definitions/series.json`, `definitions/charts.json`, `src/finance_dashboard/catalog.py` | 42 active mapped definitions plus two archived, superseded originals; exact source/frequency/unit validation |
| Macro providers | `providers.py`, `bis.py`, `remaining_sources.py`, `world_credit.py`, `macro_aggregates.py`, `concentration_snapshots.py`, `eurostat_corporate.py`, `oecd_corporate.py` | Complete 42 mapped sources: previous 39 plus OECD GDP-weighted financial and nonfinancial corporate gross-surplus/GDP, independently recorded GDP coverage and member counts (25 annual years, 2000–2024) |
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
7. **Historical MSCI concentration (owner-amended, implemented):** accept only source-dated historical published top-ten aggregate weights of **MSCI ACWI 892400**, eight publicly cited snapshots in 2019–2026. Preserve index/security-share-class interpretation, exact as-of dates and per-document provenance. Sparse month-indexed observations **do not** claim an uninterrupted monthly history; missing months are not interpolated.
8. **Corporate operating surplus (owner-amended, implemented):** Eurostat annual EU27_2020 institutional sector transactions. Compute 100 × (S11+B2A3G and S12+B2A3G, gross operating surplus, CP_MEUR)/S1+B1GQ whole-economy GDP, same calendar year/current EUR. EU27 only, both listed and unlisted firms; not OECD/world net listed earnings. Separately fetch the published NFC S11 gross-profit share of **NFC gross value added** with Eurostat dataset `nasa_10_ki`, code `B2G_B3G_RAT_S11`, unit PC, never call it GDP. Validate the API dimensions, direction, units, dates and missing years.

9. **Global macro aggregates (implemented):** WDI `WLD/CM.MKT.LCAP.CD` capitalization current USD (51 annual observations, 1975–2025); derived same-year world WDI cap / world GDP * 100, 51 annual; Siblis published sparse global trailing P/E (11 snapshots: Dec 2016–2025 and Sep 2026) and 100/P-E yield, 11 corresponding snapshots. World Bank WLD market-cap/GDP derived from levels is distinct from the WDI weighted-country share; different P/E universes must **never** be mixed to claim global net earnings/GDP. Siblis redistribution restricted.

10. **Superseded source archive and container packaging:** two original unavailable definitions are stored verbatim in `definitions/superseded_series.json` with approved replacements. `data/msci_acwi_published_snapshots.json` is the canonical dated-document archive; its exact file must be copied into the production Docker image and never silently regenerated from a partial Yahoo/ETF holdings sample.

11. **OECD-member corporate gross-surplus composite (implemented and live accepted):** [full source and formula specification](OECD_CORPORATE_SURPLUS.md). Use OECD national sector accounts (S11+S12 B2G), OECD S1 GVA plus net product taxes for national GDP where reported, and only for USA/USD, JPN/JPY, CAN/CAD use source-validated same-year WDI local GDP as a denominator fallback. The weighted OECD reporting-country mean uses WDI nominal USD GDP member weights; require >=35/38 member GDP weights, >=29 complete reporting members, >=80% included GDP. Publish ratio, GDP-coverage share and count separately. 25 2000–2024 annual points were accepted in all three datasets. OECD is not the world, nor is this a published OECD aggregate.

## Definition and completion gates

| Gate | State as of baseline | Evidence / outstanding requirement |
|---|---|---|
| Original 32/32 mapped macro + derived series | **PASS** | [complete original macro PostgreSQL ingestion and API](https://github.com/tpepels/finance_dashboard/actions/runs/41476599670) |
| 4 new macro aggregates, real public provider responses/static export | **PASS** | [36-series source-validated static export](https://github.com/tpepels/finance_dashboard/actions/runs/41492850778) |
| 36-series macro PostgreSQL ingestion and API | **PASS** | [All 36 mapped sources full historical ingestion and API readback](https://github.com/tpepels/finance_dashboard/actions/runs/41494100275) |
| Optional 24/24 market histories + 3/3 ECB FX | **PASS — nonblocking** | [real market PostgreSQL/API](https://github.com/tpepels/finance_dashboard/actions/runs/41470443707) |
| Combined mapped static artifact | **PASS** | [36-series macro export plus optional markets](https://github.com/tpepels/finance_dashboard/actions/runs/41492850778) |
| Wisesheets SEC-filer supplementary history | **PASS — limited universe** | [full documented 2021–2025 scan](https://github.com/tpepels/finance_dashboard/actions/runs/41483503450) |
| MSCI published top-ten concentration replacement | **PASS — 8 documented live source snapshots, storage/API/static** | Eight actual MSCI ACWI 892400 top-ten historical snapshots with source archive and no fabricated monthly observations. Original archived. |
| Eurostat EU27 S11+S12 gross surplus/GDP + S11 GVA profit-share | **PASS — 24 + 27 real annual records, storage/API/static** | Official Eurostat EU27_2020 corporate sectors, matched current EUR GDP, NFC gross-profit-share publication. This does not measure OECD/global listed net earnings. Original archived. |
| OECD geographic coverage of corporate surplus | **PASS — OECD38 GDP-weighted reporting aggregate** | Official OECD annual corporate source with WDI GDP weights and restricted local-currency GDP fallback for USA/JPN/CAN; 25 eligible years with >=80% of OECD-member GDP and explicit participation/count. [42-series full live acceptance](https://github.com/tpepels/finance_dashboard/actions/runs/41503545569). |
| Historical instrument ticker/exchange continuity | **NONBLOCKING optional debt** | Already implemented instrument history remains; further per-ETF work removed from macro phase by owner |
| Independent issuer NAV and distributions | **NONBLOCKING optional debt** | No claim of independent issuer audit; owner explicitly removed this Phase 2 condition |
| Full amended Phase 2 macro regression | **PASS — 42/42 mapped, zero unresolved** | [42-source historical PostgreSQL/API](https://github.com/tpepels/finance_dashboard/actions/runs/41503545569), [42-source live static export](https://github.com/tpepels/finance_dashboard/actions/runs/41503489558), and offline tests. |

Tests must include complete source registries; no tests that pass on a hand-picked subset count as phase completion. Integrate the three owner-approved replacement measures in *the existing* registry, persistence model, API and static export, including failure/staleness/rights semantics. Do not mark a definition `mapped` before live source evidence.

## Completion workflow

1. Obtain and verify a complete source with identity, historical dates, economic scope, entitlements and use rights. If no exact source is available, keep original open and add a separately named proxy with explicit owner approval.
2. Add catalog definition/rights metadata and source adapter; implement data-normalization, calculation and revision tracking; migrate schema if needed.
3. Integrate and validate API and static export; use the same calculation service, not duplicated browser formulas.
4. Run bounded unit/property tests for all variations and short real-source/PostgreSQL acceptance; do not block on long CI. Store links/results in issue #1.
5. Record the macro-first owner amendment and remove ETF NAV/ticker audits from mandatory completion; optional market data remains operational.
6. Close issue #1 when all **42 owner-amended active source contracts** have passed full ingestion/API/static acceptance, and archive the original inaccessible definitions with the explicit differences in meaning and geography. Do not claim exact worldwide profits or a full monthly concentration series.

## Contract-change policy

Feature identity, sources, formula scope, universe, outputs and quality gates cannot be reduced or substituted by implementing only a representative subset. A proposed scope change must be approved by the owner and recorded in issue #1, with synchronized edits to the feature and architecture contracts. **A written design freeze is not technical enforcement of repository branch protection.** [Owner-approved macro-first change](PHASE_2_MACRO_SCOPE_AMENDMENT.md) and [owner-approved free-source substitutions](PHASE_2_FREE_SOURCE_REPLACEMENTS.md) supersede the ETF-level and original impossible-history gates, without suppressing original definitions archived under `definitions/superseded_series.json`.