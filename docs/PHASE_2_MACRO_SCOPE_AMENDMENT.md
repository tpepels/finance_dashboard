# Decision 2026-11-02 — Macro-first Phase 2 scope amendment

**Status:** owner-directed scope change, adopted on `main` 2026-11-02.

## Owner instruction

"Do we really need per-etf stuff for our dashboard? I'm mostly looking for macro-economics. Otherwise go ahead."

## Decision

1. The primary dashboard is a **macroeconomic and structural-financial-risk monitor**, not an ETF portfolio or market-data terminal.
2. Existing 24 instrument histories, three ECB FX market pairs, dividend/split handling and the Wisesheets SEC-filer dataset **remain implemented and accessible** as optional supplementary infrastructure. Do not delete working code, silently break the API or invest additional work in per-ETF reconciliation for Phase 2.
3. **Remove independent issuer ETF NAV/distribution reconciliation and historical ticker/venue-change continuity as Phase 2 completion gates.** They become optional market-data quality debt, not blockers for macro Phase 2. No claim of their verification is made.
4. Phase 2 core focuses on complete global macro datasets and historically sound aggregate equity-market measures. Concentration and worldwide listed profits remain the two original outstanding exact definitions, and **are not waived or silently replaced** by Wisesheets, ETF holdings or mismatched-market-cap/P-E calculations. Implement and label available official aggregates separately while seeking adequate history.
5. Implemented aggregate additions are:
   - `valuation.world.listed_market_cap_usd`: World Bank WDI WLD world WFE-listed domestic capitalization, current USD (51 annual years, 1975–2025 in verified source response).
   - `valuation.world.listed_market_cap_world_gdp`: the **ratio of WDI WLD USD capitalization to WDI WLD USD world GDP** for matching years (51 years); not the separately defined WDI weighted-country capitalization/GDP indicator.
   - `valuation.world.global_trailing_pe`: Siblis global equity index normalized trailing P/E, **11 free published snapshots** (2016–2025 Dec and September 2026), not the commercial 1970 monthly history.
   - `valuation.world.global_earnings_yield`: `100 / P/E` for the same 11 source snapshots; earnings are measured relative to **Siblis index capitalization**, not world GDP.
6. **No cross-universe implied earnings/GDP calculation** using World Bank all-market capitalization and Siblis selected-index P/E. The matched index capitalizations needed to infer historical Siblis earnings are not available in the free verified source. Yahoo fund holdings and SEC N-PORT historical holdings are ETF-level proxies and are outside the newly prioritized macro implementation.
7. The 36 operational macro/index mappings and their charts remain sourced by Python adapters, PostgreSQL/worker/FastAPI and scheduled static export. The remaining 2 original indicators are catalogued as unresolved. Siblis data require rights review before any public distribution; the current generated artifact is not a public Pages site.

## Scope consequences

| Area | Prior gate | Amended gate |
|---|---|---|
| Original macro/index data | 32 mapped, two unresolved | 36 mapped with 4 additional world aggregates, two original historical sources still unresolved |
| 24 instruments and 3 FX feeds | Required and already verified | Available optional infrastructure; no new ETF data collection required |
| Issuer NAV/dividend independent reconciliation | Blocked Phase 2 | No longer Phase 2 blocking |
| Historical ticker/venue alias audit | Blocked Phase 2 | No longer Phase 2 blocking |
| Worldwide listed profits and original MSCI concentration | Required | Still required as exact historical definitions, unless the owner approves a later explicit scope replacement |
| Dashboard deliverable | Phase 3 React/ECharts | Phase 3 remains **macro-first**, with ETF detail only if explicitly requested |

## Verification evidence

- [36-series live export including all four new aggregates](https://github.com/tpepels/finance_dashboard/actions/runs/41492850778): Siblis 11+11 source snapshots, WDI capitalization 51 years, WDI capitalization/world GDP 51 years; all 24 optional historical instruments and 3 FX sources also passed.
- [Previously verified 32-series PostgreSQL full backfill](https://github.com/tpepels/finance_dashboard/actions/runs/41476599670).
- [Phase 2 tracker](https://github.com/tpepels/finance_dashboard/issues/1): new complete full macro PostgreSQL acceptance should include all 36 series before declaring this extension end-to-end accepted.

A frozen requirement contract only changes through an owner decision recorded here, synchronized to the [feature contract](PHASE_2_FEATURE_CONTRACT.md), [architecture contract](PHASE_2_ARCHITECTURE_CONTRACT.md) and [implementation contract](PHASE_2_IMPLEMENTATION_CONTRACT.md). This decision is the explicit record of the macro-first amendment, not a declaration of Phase 2 completion.
