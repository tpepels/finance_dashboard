# Development plan

The authoritative roadmap. It states goals, the current state and the next slices; it is not a changelog. Implementation history up to 2026-11-06 is preserved in [archive/DEVELOPMENT_PLAN_HISTORY_2026-11.md](archive/DEVELOPMENT_PLAN_HISTORY_2026-11.md); git history records everything after.

## Goal

A locally hosted research workbench that helps a **EUR-based long-term ETF investor** make better allocation, hedging, rebalancing and savings decisions, with macro-financial and political-economy research as context. Every analysis states the decision it informs, compares several indicators, shows its sources and limits, and never fabricates data or presents timing signals.

Binding scientific scope: [Phase 1 charter](PHASE1_SCIENTIFIC_CHARTER.md) (including its 2026-11-06 revision), [analysis catalogue](PHASE1_ANALYSIS_CATALOGUE.md), [specifications](PHASE1_ANALYSIS_SPECIFICATIONS.md), [fallback matrix](PHASE1_FALLBACK_SOURCE_MATRIX.md) and [source policy](SOURCE_POLICY.md).

## Phases

| Phase | Outcome | Status |
|---|---|---|
| 1 — Scientific charter and product design | Approved question catalogue, methods, visual contract | Closed 2026-11-03; revised by the owner 2026-11-06 |
| 2 — Data, provenance and research corpus | Every active analysis reaches an evidenced end state | Active |
| 3 — Comparative analytical engine | Transforms, alignment, estimates with uncertainty | Starts with the first slice (below) |
| 4 — Interaction and visualization | Per-chart configurable views, overview, research panels | Starts with the first slice |
| 5 — Portfolio application and validation | Owner portfolio inputs, scenario and backtest validation | Later slices |

Phases describe responsibilities, not a strict sequence: work proceeds in **end-to-end slices** (data → analysis → chart) so that useful results appear early. A slice may only use analyses whose Phase 2 state is `accepted` or `conditional`.

## Phase 2 acceptance contract

Implemented in `research_acceptance.py` and validated on every run of `python -m finance_dashboard research operating`.

* **Evidence tiers.** Predictive analyses (C02, V05) need real-time evidence: ALFRED windows covering the stored history, unrevised market observations, or a cited statement that the publisher keeps no vintages (carried as a limitation). All other analyses are descriptive and use verified latest revised values, shown as a limitation.
* **Seven gates per data role:** source binding, native dimensions, stored history, independently verified original values, exact matched periods, publisher dimensions and temporal evidence.
* **End states.** A role is `accepted`, `unavailable_with_fallback` (cited unavailability plus a fallback that passes every gate) or `user_input` (owner parameters such as weights, costs or the withdrawal plan). An analysis is `accepted`, `conditional` (descoped roles or fallbacks), `deferred` (a research extension outside Phase 2 completion) or still `blocked`/`incomplete`, with its open gates named.
* **Phase 2 is complete** when every analysis is `accepted`, `conditional` or `deferred`.

## Current state (local corpus, 2026-11-06)

See the measured numbers in the latest `research operating` report; the summary below is updated at each milestone.

Measured with `research operating` after the 2026-11-06 sweeps: 247 of 268 catalogue sources have independently verified original histories.

| State | Analyses |
|---|---|
| Accepted (11) | C01, C03, C06, M01, M02, F02, F03, F05, F06, G05, P07 |
| Conditional (5) | M04, F01, P02, P04, P05 (narrowed roles, stated in the catalogue) |
| Deferred (3) | L04, G03, V03 (research extensions outside Phase 2 completion) |
| Waiting on one source (4) | P06 and V01 (Shiller CAPE original, publisher cooldown), V05 (Shiller), F04 (high-yield spread history coverage) |
| Blocked on data work (14) | C02, C05, F07, V02, L01, L02, L03, L05, L07, G01, G02, G06 (accounting check fails), P01, P03 |

16 of 34 active analyses are resolved; Phase 2 is **not** complete.

## Next slices

1. **Slice A — EUR investor portfolio context** (Phase 3/4): P06 expected-return ranges and P07 hedged versus unhedged returns, built on accepted inputs, with one configurable chart each and their method/limitation panels.
2. **Slice B — credit and valuation context:** F01–F06 (accepted or conditional) and V01, as configurable comparison charts.
3. **Phase 2 data work, by decision value:** ECB series acquisition for P02/P04/P05/P07; current ETF holdings (P01) from issuer/SEC collectors; G01 N-PORT concentration history; a sourced shock-event register (C05, P03); Fed Z.1 (F07) and DFA components (L05); OECD national accounts (L01–L03); WIID Gini (L07); ICIO accounting failure (G06).
4. **Owner inputs:** portfolio weights, rebalancing rule, costs, tax and withdrawal plan, entered through the application, not fetched.

## Working rules

* One canonical CLI (`python -m finance_dashboard`), one managed HTTP client, one acceptance engine; consolidate rather than add parallel paths.
* Preserve all databases, originals, receipts, journals and backups; take a verified backup before schema migrations or bulk acquisition.
* Run the full offline suite before each commit; verify GitHub Actions after pushing.
* Keep this plan short: update goals, state and next slices; record history in commits.
