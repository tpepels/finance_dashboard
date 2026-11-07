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

## Current state (local corpus, 2026-11-07)

See the measured numbers in the latest `research operating` report; the summary below is updated at each milestone.

Measured on 2026-11-07 after the L03 sweep: 336 of 349 catalogue sources have independently verified original histories.

| State | Analyses |
|---|---|
| Accepted (22) | C01, C03, C05, C06, F02, F03, F05, F06, G05, G06, L02, L03, L05, L07, M01, M02, P03, P06, P07, V01, V02, V05 |
| Conditional (11) | C02 (no NBER announcement dates before 1979), F01, F04 (Baa fallback), F07, G01 and G02 (iShares MSCI ACWI ETF N-PORT positions for the unpublished ACWI weights), M04, P01 (fields the holdings publishers do not report), P02, P04, P05 |
| Deferred (3) | L04, G03, V03 (research extensions outside Phase 2 completion) |
| Blocked (1) | L01 (industry-matched inputs; EU KLEMS 2025 identified) |

33 of 34 active analyses are resolved; Phase 2 is **not** complete.

## Done since the revision (2026-11-06)

* **Slice A:** Decisions panel with P06 expected-return ranges and P07 hedged versus unhedged EUR returns (`/api/decision/{P06,P07}`).
* **Slice B (first card):** F03 credit gaps against the BIS 2/10 pp guide and debt service against each economy's own history.
* **Free alternative sources:**
  * Eurostat ECOICOP v2 HICP replaces the discontinued ECB index.
  * Moody's Baa−Treasury spread is the cited fallback for the ICE high-yield spread, which FRED now keeps for three years only.
  * Internet Archive captures of MSCI's official ACWI factsheet supply concentration history.
  * DFA wealth-group balance sheets (L05) and Z.1 broker-dealer equity and finance-company balance sheets (F07) come from FRED.
  * The World Bank PIP survey Gini replaces WIID for L07.
  * A curated, sourced shock-event register serves C05/P03.
* **Corrected strictness:** TiVA identity check uses a 0.01 pp materiality bound (G06).
* **Infrastructure:** OECD Table 14 non-financial corporate accounts provider for L02/L03, awaiting the country coverage check.
* **Acquisition and verification fixes (2026-11-07):**
  * Providers whose descriptive URL differs from the request host declare a `request_origin`, so OECD and MSCI requests are paced by the right publisher policy.
  * The two-request Shiller download fits its pacing, so it is no longer deferred in every sweep.
  * Sweeps and the app's refresh loop take turns on short waits instead of recording a publisher stop.
  * Archived scheduled refreshes certify periods they append (ECB and MSCI windowed captures included); a refresh that revises stored values still needs a full snapshot.
  * Declared fallbacks are corpus inputs with their own exact-join panel (F04).
  * A survey gap at a window start is recorded as a publisher absence, not a late start (L07).
  * SEC N-PORT holdings: 12 quarterly filings each for VT, BND and the iShares MSCI ACWI ETF, discovered through each fund's EDGAR series feed.
* **G06:** the owner downloaded OECD's 2025 regular ICIO archives (the automated route is a Cloudflare challenge); all 28 years 1995-2022 are pinned, audited and stored, 2016-2022 matching independent replicas byte for byte. Identities hold within 0.1% of each node's gross output in every year (worst 0.089%); residuals above rounding are retained, not rebalanced.
* **L03:** net fixed assets of non-financial corporations (OECD Table 9B, N11N) for all eight countries.
* **C02:** USREC ALFRED windows back to 1854; NBER chronology and committee announcements collected and gated on each announcement's dateline or header.
* **G02:** country weights from the same ACWI ETF N-PORT positions as G01.
* **Holdings acceptance (G01, P01):** holdings roles declare a fund contract and are judged on each fund's latest original snapshot: accounting control, cited per-source field reviews ([holdings_sources.json](../definitions/holdings_sources.json)) and value-weighted coverage of required fields (95%). Publisher absences (sector in N-PORT and Vanguard reports; identifiers in the iShares CSV and Vanguard reports) are per-fund limitations.

## Next slices

1. **L01 via EU KLEMS & INTANProd 2025:** value added (VA_CP), its price index (VA_PI), hours of persons engaged (H_EMP) and labour compensation including self-employed (LAB) on one matched scope, 1995-2021, all eight countries. Files are served through Dropbox content hosts that the exact-host policy registry cannot name yet.
2. **Slice B continued:** V01 valuation context, plus configurable comparison charts for F01–F06.
3. **Owner inputs:** portfolio weights, rebalancing rule, costs, tax and withdrawal plan, entered through the application, not fetched.

## Working rules

* One canonical CLI (`python -m finance_dashboard`), one managed HTTP client, one acceptance engine; consolidate rather than add parallel paths.
* Preserve all databases, originals, receipts, journals and backups; take a verified backup before schema migrations or bulk acquisition.
* Run the full offline suite before each commit; verify GitHub Actions after pushing.
* Keep this plan short: update goals, state and next slices; record history in commits.
