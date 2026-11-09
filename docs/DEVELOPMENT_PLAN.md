# Development plan

The authoritative roadmap. It states goals, the current state and the next slices; it is not a changelog. Implementation history up to 2026-11-06 is preserved in [archive/DEVELOPMENT_PLAN_HISTORY_2026-11.md](archive/DEVELOPMENT_PLAN_HISTORY_2026-11.md); git history records everything after.

## Goal

A locally hosted research workbench that helps a **EUR-based long-term ETF investor** make better allocation, hedging, rebalancing and savings decisions, with macro-financial and political-economy research as context. Every analysis states the decision it informs, compares several indicators, shows its sources and limits, and never fabricates data or presents timing signals.

Binding scientific scope: [Phase 1 charter](PHASE1_SCIENTIFIC_CHARTER.md) (including its 2026-11-06 revision), [analysis catalogue](PHASE1_ANALYSIS_CATALOGUE.md), [specifications](PHASE1_ANALYSIS_SPECIFICATIONS.md), [fallback matrix](PHASE1_FALLBACK_SOURCE_MATRIX.md) and [source policy](SOURCE_POLICY.md).

## Phases

| Phase | Outcome | Status |
|---|---|---|
| 1 — Scientific charter and product design | Approved question catalogue, methods, visual contract | Closed 2026-11-03; revised by the owner 2026-11-06 |
| 2 — Data, provenance and research corpus | Every active analysis reaches an evidenced end state | Complete 2026-11-08 |
| 3 — Comparative analytical engine | Transforms, alignment, estimates with uncertainty | Active |
| 4 — Interaction and visualization | Per-chart configurable views, overview, research panels | Starts with the first slice |
| 5 — Portfolio application and validation | Owner portfolio inputs, scenario and backtest validation | Later slices |

Phases describe responsibilities, not a strict sequence: work proceeds in **end-to-end slices** (data → analysis → chart) so that useful results appear early. A slice may only use analyses whose Phase 2 state is `accepted` or `conditional`.

## Phase 2 acceptance contract

Implemented in `research_acceptance.py` and validated on every run of `python -m finance_dashboard research operating`.

* **Evidence tiers.** Predictive analyses (C02, V05) need real-time evidence: ALFRED windows covering the stored history, unrevised market observations, or a cited statement that the publisher keeps no vintages (carried as a limitation). All other analyses are descriptive and use verified latest revised values, shown as a limitation.
* **Seven gates per data role:** source binding, native dimensions, stored history, independently verified original values, exact matched periods, publisher dimensions and temporal evidence.
* **End states.** A role is `accepted`, `unavailable_with_fallback` (cited unavailability plus a fallback that passes every gate) or `user_input` (owner parameters such as weights, costs or the withdrawal plan). An analysis is `accepted`, `conditional` (descoped roles or fallbacks), `deferred` (a research extension outside Phase 2 completion) or still `blocked`/`incomplete`, with its open gates named.
* **Phase 2 is complete** when every analysis is `accepted`, `conditional` or `deferred`.

## Current state (local corpus, 2026-11-08)

See the measured numbers in the latest `research operating` report; the summary below is updated at each milestone.

Measured on 2026-11-08 after the V03 import: 382 of 383 catalogue sources have independently verified original histories (the remaining one, the ICE high-yield spread, has the Baa fallback).

| State | Analyses |
|---|---|
| Accepted (23) | C01, C03, C05, C06, F02, F03, F05, F06, G05, G06, L01, L02, L03, L05, L07, M01, M02, P03, P06, P07, V01, V02, V05 |
| Conditional (13) | C02 (no NBER announcement dates before 1979), F01, F04 (Baa fallback), F07, G01 and G02 (iShares MSCI ACWI ETF N-PORT positions for the unpublished ACWI weights), L04 (framework limits below), M04, P01 (fields the holdings publishers do not report), P02, P04, P05, V03 (archived factsheet coverage below) |
| Deferred (1) | G03 (free-source design researched; being bound) |

36 of 36 active analyses are resolved; none is blocked. Phase 2 is **complete**.

## Done since the revision (2026-11-06)

* **Slice A:** Decisions panel with P06 expected-return ranges and P07 hedged versus unhedged EUR returns (now served as engine bundles from `/api/analysis/{P06,P07}`).
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
* **L01:** value added (VA_CP), its price index (VA_PI), hours of persons engaged (H_EMP) and labour compensation including self-employed (LAB) from the EU KLEMS & INTANProd 2025 total-economy workbooks for all eight countries, on one matched scope. The publisher's Dropbox shares are fetched from the fixed host `dl.dropboxusercontent.com`, so no wildcard policy was needed. All 32 series are verified against an independent reader and L01 is accepted.

* **L04:** Rotta & Kumar (2024) productive-sector framework. Their Zenodo deposit (Table A1 classification and 43-country 2000-2014 panel) and the Tsoulfidis & Paitaridis (2017) alternative classification are fetched and pinned; the WIOD 2016 Socio-Economic Accounts are an owner copy pinned to DataverseNL's SHA-1, since its robots.txt disallows automated clients. The authors' panel is recomputed from the SEA under Table A1 for all 645 country-years: 32,100 levels and 16,665 published ratios match exactly. L04 is conditional: no supervisory-labour split outside the US, no published turnover or circulating capital, surplus gross of depreciation, and the input-origin ratio is the authors' published value until the WIOD input-output tables are imported.

* **V03:** trailing and forward P/E (MSCI Fundamental Data Methodology, I/B/E/S EPS12F) and composition for MSCI ACWI, World, EM, USA, Europe, Japan and EAFE, read from 588 raw Internet Archive captures of MSCI's own factsheets, each checked against the CDX SHA-1 and dated by the document's own as-of month. Values two factsheets print differently are a recorded conflict and stay absent. V03 is conditional: monthly coverage is sparse outside World, ACWI and EM, histories start 2012-2017, and only the top countries are printed.

* **Phase 3 engine core (2026-11-08):** design in [superpowers/specs/2026-11-08-phase3-engine-design.md](superpowers/specs/2026-11-08-phase3-engine-design.md). One engine (`finance_dashboard/engine/`) computes each analysis into a result bundle: inputs with the analysis and role under which Phase 2 accepted them (borrowed inputs carry the accepting role's limitations), named transforms with formulas, values, estimates with ranges, Phase 2 and method limitations in plain language ([limitations.json](../definitions/limitations.json)), citations. P06, P07 and F03 run on it with numbers identical to the retired `/api/decision` endpoints; each Decisions card shows its limitations and an "Export for AI" text file. `/api/conditionals` and `research conditionals` list the 13 conditional analyses.

* **Visual language (2026-11-09):** [design](superpowers/specs/2026-11-09-phase3-visual-language.md). The Decisions panel answers each question with a graphic instead of tables: a real-return ruler (P06), a risk–return map (P07) and own-history thermometers (F03), with zoomable history charts underneath. Every time chart shades all NBER US recessions since 1854 from the stored indicator (`/api/recessions`), naming the dot-com, 2008 and COVID episodes; charts zoom by wheel, pinch, slider or 5Y/10Y/20Y/All presets, read every series under a crosshair, and link across small multiples. One validated eight-colour palette per theme; the bundled Atkinson Hyperlegible Next typeface.

## Next slices

1. **Phase 3, overview group by group:** move the remaining analyses onto the engine in the design's build order, starting with C03/C01/C06, and retire the pre-reset dashboard pieces each group replaces. V01 and F01–F06 arrive in their groups.
2. **Owner inputs:** portfolio weights, rebalancing rule, costs, tax and withdrawal plan, entered through the application, not fetched.
3. **L04 extensions:** recompute the input-origin ratio from the WIOD 2016 input-output tables (`WIOTS_in_EXCEL.zip`, owner download from DataverseNL); extend 1995-2021 with EU KLEMS industry workbooks (capital accounts K_GFCF) and OECD ICIO 2025, reconciling vintages over the 2000-2014 overlap.

## Working rules

* One canonical CLI (`python -m finance_dashboard`), one managed HTTP client, one acceptance engine; consolidate rather than add parallel paths.
* Preserve all databases, originals, receipts, journals and backups; take a verified backup before schema migrations or bulk acquisition.
* Run the full offline suite before each commit; verify GitHub Actions after pushing.
* Keep this plan short: update goals, state and next slices; record history in commits.
