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

* **Phase 3 group 1, growth and inflation (2026-11-09):** C01, C03 and C06 run on the engine and appear in a Growth & inflation panel: an OECD business-cycle clock with a selectable 12-month trail, a growth strip placing each region's latest year within its last decade, and a growth-against-inflation map beside 12-month commodity price changes, each with zoomable histories and small multiples underneath. The six pre-reset growth tiles are retired. IMF WEO series carry historical estimates only (forecast years are excluded at ingestion), so no forecasts are drawn.

* **Phase 3 group 2, rates and currencies (2026-11-09):** M01, M02 and M04 run on the engine in a Rates & currencies panel: a rate ladder (each central bank now against a year ago, the Fed target range, the euro's rate gaps), the US 10-year yield split into real yield and breakeven now and a year ago, and the euro's 12-month moves beside its rate gaps, with step-line rate histories, yield histories and per-currency small multiples. Six more pre-reset tiles retired (34 remain).

* **Phase 3 group 3, credit and stress (2026-11-09):** F01, F02, F04, F05, F06 and F07 run on the engine in a Credit & stress panel: credit to GDP against its BIS trend, debt service five years ago against now, stress gauges within their own history with the OFR index split into its published parts, debt by sector stacked as % of GDP with US bank equity, real house and commercial property prices within their own history, and US nonbank leverage and repo funding. Seven more pre-reset tiles retired (27 remain).

* **Phase 3 group 4, valuation (2026-11-09):** V01, V02, V03 and V05 run on the engine in a Valuation panel: US valuation gauges within their own history (CAPE, P/E, dividend yield, excess CAPE yield), BEA Q ratios beside CAPE, trailing and forward P/E per MSCI region from archived factsheets (sparse months drawn as dots, never bridged), and a grid of how well starting valuation ranked later 5, 10 and 15-year real returns per era with effective independent samples. Three more pre-reset tiles retired (24 remain).

* **Phase 3 groups 5–7, world, labour and portfolio (2026-11-09):** G05 and G06 (World), L01, L02, L03, L05 and L07 (Labour & inequality), P02 and P03 (Portfolio) run on the engine; all pre-reset tiles are retired.

* **Archive-based analyses (2026-11-09):** the engine also reads named archives besides stored series (`engine/artifacts.py`): SEC N-PORT filings, the iShares UCITS holdings file and the Rotta & Kumar framework originals. A missing archive gives an empty result, never a broken page. G01 (the ten largest issuers in the ACWI ETF beside MSCI's published top 10), G02 (index weight against share of world GDP), L04 (the spread of surplus-value and profit rates across two sector classifications and three wage measures) and P01 (where the owned funds invest, and their largest holdings).

* **Owner inputs (2026-11-09):** a Your portfolio form (mix, euro share and hedging, bond duration, rebalancing rule, trading costs, contributions and withdrawals) stored locally in `FINANCE_OWNER_INPUTS` (default `/data/owner-inputs.json`) through `/api/owner-inputs`; invalid inputs are refused with a reason. Until saved, a labelled example portfolio is used and every result says so. P04 shows first-order shock effects on the mix; P05 replays the mix in euros under never, calendar and threshold rebalancing with trading costs.

* **Cleanup (2026-11-09):** `/api/research`, `/api/research/{id}`, `/api/risk` and `/api/risk/{scope}` and their modules (`research.py`, `risk_diagnostics.py`) are removed, with the stylesheet rules only the old dashboard used. `insights.py` stays for the source explorer's chart readouts.

* **Last corpus questions (2026-11-09):** every corpus analysis now has an engine definition. C02 places the first yield-curve inversion, the Sahm trigger and the NBER announcement on one timeline around each recession since 1970, with signals not followed by a recession listed apart (no agreement score). C05 shows, per recession, how deep industrial production, payrolls and real GDP fell and how many months each took to regain its pre-recession peak, with curated shock events as context. G03 is defined but stays withheld while Phase 2 defers it; its section explains what is missing, and its two non-equivalent alternatives appear once Phase 2 accepts them. P05 models tax on realised gains (cost basis per asset) or a yearly tax on value.

* **G03 and L04 (2026-11-09):** the engine computes from alternatives Phase 2 itself verified when the original method is unresolved, and labels the result (`basis: verified_alternatives`); G03 shows the EU27 and OECD corporate profit measures that way. The WIOD 2016 world input-output tables are archived (`python -m finance_dashboard.wiod_io`, pinned to DataverseNL's SHA-1) and the authors' input-origin ratio is recomputed: all 2,580 published WIOT values (645 country-years) match. Their total value is basic-price output plus the product-taxes row, which counts those taxes twice; it is reproduced as published and recorded. L04 shows the full method and value added only side by side.

* **Gap sources, first three (2026-11-10):**
  * Euro bonds: new Bundesbank provider for the month-end 10-year par yield (`bond.de.bund_10y_par_yield_month_end`, 1972-09 onward), the input Swinkels names; his formula on it reproduces all 603 of his German returns to 3e-16. Accepted in Phase 2 as a P05 role; the engine's `par_bond_return` transform rebuilds the return, and P05 uses it for euro or hedged bonds (replay now 2001-2026).
  * G03: MSCI ACWI index market cap is read from the archived factsheets (58 months, 2015-2026, no conflicts) and joins the trailing P/E as a third Phase 2-verified alternative; cap / P/E is the constituents' aggregate trailing earnings ($4.8 trillion to September 2026, 3.0-3.4% of world GDP at year ends).
  * F04: FRED's full high-yield spread download (1996-12-31 to 2025-11-03) is archived from the Internet Archive (`python -m finance_dashboard.fred_wayback`, pinned by CDX digest). It agrees with FRED's current three years on all 522 shared days; reconciliation counts days that rolled out of FRED as verified by the identical archived value, and F04 is now accepted. The Baa stand-in is retired.

* **Gap sources, next three (2026-11-10):**
  * C02: the Philadelphia Fed's unemployment vintages (collected from the original BLS releases, `python -m finance_dashboard.philly_rtdsm`) recompute the Sahm rule at each of 244 quarterly vintages since 1965; FRED's real-time Sahm values agree at two decimals in 242. The two differences (April and July 2026) are listed on the page and in the export.
  * Owner-supplied Phase 2 roles are accepted when their supplying store holds valid values: your saved portfolio inputs (never the example) for P04 and P05, and the curated shock register for C05 and P03, each with a limitation saying where the values come from. Saving inputs re-evaluates Phase 2 in the background. C05 and P03 have no open gates; with saved inputs P04 keeps only convexity and P05 only constituent returns and benchmark weights.

* **L04 extension (2026-11-10):** EU KLEMS & INTANProd Release 2025 all-country files (national, growth and capital accounts) are archived (`python -m finance_dashboard.euklems_marxian`) and the SEA formulas applied to 1995-2021 for the eight non-Chinese L04 countries. Each WIOD industry maps to one EU KLEMS leaf; the finest published cover is used per country, and an industry spanning both sides (M; E under Tsoulfidis & Paitaridis; M-N in Japan) is counted once each way. Over 2000-2014 the rate of surplus value differs from WIOD by -0.05 to +0.08 (United States -0.14 to -0.10). L04 offers it as a third method beside WIOD.

## Next slices

1. **L04 input-output correction after 2014:** needs the OECD ICIO 2025 tables (1995-2022). The OECD site refuses automated downloads (HTTP 403 challenge), so the owner downloads them; the reader then follows `wiod_io`.
2. **Sources found for the known gaps** (each to be pinned, read and taken through Phase 2):
   * More shock dates beyond the curated register: Jordà-Schularick-Taylor Macrohistory R6 crisis dates (18 economies, 1870-2020).

## Working rules

* One canonical CLI (`python -m finance_dashboard`), one managed HTTP client, one acceptance engine; consolidate rather than add parallel paths.
* Preserve all databases, originals, receipts, journals and backups; take a verified backup before schema migrations or bulk acquisition.
* Run the full offline suite before each commit; verify GitHub Actions after pushing.
* Keep this plan short: update goals, state and next slices; record history in commits.
