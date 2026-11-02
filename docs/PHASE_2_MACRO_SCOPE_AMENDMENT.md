# Decision 2026-11-02 — Macro-first Phase 2 scope amendment

**Status:** owner-directed scope change, adopted on `main` 2026-11-02.

## Owner instruction

"Do we really need per-etf stuff for our dashboard? I'm mostly looking for macro-economics. Otherwise go ahead."

## Decision

1. The primary dashboard is a **macroeconomic and structural-financial-risk monitor**, not an ETF portfolio or market-data terminal.
2. Existing 24 instrument histories, three ECB FX market pairs, dividend/split handling and the Wisesheets SEC-filer dataset **remain implemented and accessible** as optional supplementary infrastructure. Do not delete working code, silently break the API or invest additional work in per-ETF reconciliation for Phase 2.
3. **Remove independent issuer ETF NAV/distribution reconciliation and historical ticker/venue-change continuity as Phase 2 completion gates.** They become optional market-data quality debt, not blockers for macro Phase 2. No claim of their verification is made.
4. Phase 2 core focuses on historically sound, labelled macroeconomic aggregates. The original concentration and worldwide listed-profit definitions were **subsequently and explicitly superseded by the owner** under the [2026-11-02 free-source amendment](PHASE_2_FREE_SOURCE_REPLACEMENTS.md); this document records the preceding macro-first decision and does not imply the superseded originals were reconstructed.
5. Implemented aggregate additions are:
   - `valuation.world.listed_market_cap_usd`: World Bank WDI WLD world WFE-listed domestic capitalization, current USD (51 annual years, 1975–2025 in verified source response).
   - `valuation.world.listed_market_cap_world_gdp`: the **ratio of WDI WLD USD capitalization to WDI WLD USD world GDP** for matching years (51 years); not the separately defined WDI weighted-country capitalization/GDP indicator.
   - `valuation.world.global_trailing_pe`: Siblis global equity index normalized trailing P/E, **11 free published snapshots** (2016–2025 Dec and September 2026), not the commercial 1970 monthly history.
   - `valuation.world.global_earnings_yield`: `100 / P/E` for the same 11 source snapshots; earnings are measured relative to **Siblis index capitalization**, not world GDP.
6. **No cross-universe implied earnings/GDP calculation** using World Bank all-market capitalization and Siblis selected-index P/E. The matched index capitalizations needed to infer historical Siblis earnings are not available in the free verified source. Yahoo fund holdings and SEC N-PORT historical holdings are ETF-level proxies and are outside the newly prioritized macro implementation.
7. The initial 36 operational macro/index mappings were later extended to **39 mapped** with eight published MSCI ACWI dated concentration observations and two Eurostat EU27 corporate gross-surplus measures. The two original definitions are archived in `definitions/superseded_series.json`, no longer unresolved entries in the active catalog. Siblis data require rights review before any public distribution; the current generated artifact is not a public Pages site.

## Scope consequences

| Area | Prior gate | Amended gate |
|---|---|---|
| Original macro/index data | 32 mapped, two unresolved | 36 mapped with 4 additional world aggregates, two original historical sources still unresolved |
| 24 instruments and 3 FX feeds | Required and already verified | Available optional infrastructure; no new ETF data collection required |
| Issuer NAV/dividend independent reconciliation | Blocked Phase 2 | No longer Phase 2 blocking |
| Historical ticker/venue alias audit | Blocked Phase 2 | No longer Phase 2 blocking |
| Worldwide listed profits and original MSCI concentration | Originally required | Owner subsequently **approved explicit narrower source replacements**, see [second amendment](PHASE_2_FREE_SOURCE_REPLACEMENTS.md); originals archived, not claimed |
| Dashboard deliverable | Phase 3 React/ECharts | Phase 3 remains **macro-first**, with ETF detail only if explicitly requested |

## Verification evidence

- [36-series live export including all four new aggregates](https://github.com/tpepels/finance_dashboard/actions/runs/41492850778): Siblis 11+11 source snapshots, WDI capitalization 51 years, WDI capitalization/world GDP 51 years; all 24 optional historical instruments and 3 FX sources also passed.
- [Previously verified original 32-series PostgreSQL backfill](https://github.com/tpepels/finance_dashboard/actions/runs/41476599670).
- [**Passed full 36-series live historical PostgreSQL and FastAPI acceptance**](https://github.com/tpepels/finance_dashboard/actions/runs/41494100275), including 51+51 World Bank and 11+11 Siblis observations.
- [Phase 2 tracker](https://github.com/tpepels/finance_dashboard/issues/1): the subsequent owner-approved three free public-source replacements passed [39-source PostgreSQL/API acceptance](https://github.com/tpepels/finance_dashboard/actions/runs/41499045751) and [39-source static export](https://github.com/tpepels/finance_dashboard/actions/runs/41498656329).

A frozen requirement contract only changes through an owner decision recorded here, synchronized to the [feature contract](PHASE_2_FEATURE_CONTRACT.md), [architecture contract](PHASE_2_ARCHITECTURE_CONTRACT.md) and [implementation contract](PHASE_2_IMPLEMENTATION_CONTRACT.md). This decision is the explicit record of the macro-first amendment, not a declaration of Phase 2 completion.
