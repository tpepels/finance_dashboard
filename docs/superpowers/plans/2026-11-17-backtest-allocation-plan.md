# Backtesting and Allocation — Phased Development Plan

> **For agentic workers:** Read [AGENTS.md](../../../AGENTS.md) and [AGENT_HANDOFF.md](../../AGENT_HANDOFF.md) first. Execute phases in order unless a phase is marked parallel. Each phase ends with passing CI and an updated handoff. Production claims follow the AGENTS.md rule: deploy, collect, then verify with a post-deployment diagnostic ZIP.

**Goal:** Grow the existing Global Capital Monitor, one layer at a time, into a point-in-time backtesting and monthly allocation system for EUR index investors. It gives general market views and model portfolios, plus an optional personal layer, as specified in the [design](../specs/2026-11-17-backtest-allocation-design.md).

**Approach:** Each phase adds one architectural layer (design section 10.2), ships something usable or inspectable, and leaves the application releasable. New features stay behind the `FINANCE_ALLOCATION` flag until their acceptance gate passes.

**Tech stack:** Python 3.12, SQLAlchemy/Alembic/FastAPI, SQLite WAL, React/TypeScript/ECharts, frozen uv/npm locks, a single Docker container. New dependencies are added only in the phase that first needs them.

**Spec:** [Backtesting and allocation module — design](../specs/2026-11-17-backtest-allocation-design.md). Section numbers below (§) refer to it.

---

## 0. Starting point (verified 17 November 2026, commit `5e2d158`)

| Area | What exists now | How this plan uses it |
|---|---|---|
| Source acquisition | `ProviderRouter` → managed source policy → `SourceAcquisition`; archived originals, receipts, independent reconciliation; 623 registered series in `definitions/series.json`; source-health work recorded in the handoff | All new sources go through this path. No second collector. |
| Return histories | `research_returns.py`: French developed/emerging market and risk-free; Swinkels sovereign returns (9 countries); Doeswijk–Swinkels global multi-asset; Shiller real total return; gold; ECB FX | Starting set of bucket returns. Regions, UMD and country indices are added in D1. |
| Vintages | `vintage.py` and `alfred_acquisition.py` (ALFRED snapshots, revision windows), `philly_rtdsm.py` (RTDSM unemployment vintages), `phase2_alfred_revisions.py` | Seed rows for Tier E in the point-in-time store (D2) |
| Long history | `jst.py` (Jordà–Schularick–Taylor macrohistory; currently used for crisis starts) | Annual panel for the ML layer (D6) |
| Engine | `engine/bundle.py` `AnalysisDefinition(analysis_id, inputs, compute, artifacts, alternatives, optional_inputs)`; 37 analyses in `engine/analyses.py`; acceptance gating (`research_acceptance.py`, `engine/acceptance.py`); bundle cache, exports, limitations | A01–A06 are registered as normal engine analyses. No parallel calculation route (ARCHITECTURE.md). |
| Portfolio | P04/P05/P06/P07; `engine/analyses.py::simulate` (rebalancing rules, costs, taxes, cash flows); `owner_inputs.py`; `portfolio_holdings.py` | `simulate` is extracted into the shared backtest executor in D3, with P05 output unchanged; owner inputs and holdings feed only the personal layer (D9). |
| Recession / C02 / V05 | NBER chronology, RTDSM Sahm, Shiller CAPE, V05 calibration eras | Event labels and baseline predictors (D4, D5) |
| Jobs | `standalone.py` refresh loop; `maintenance_jobs.py` `MaintenanceAction` registry; persistent status API pattern | The monthly allocation step is added to the refresh cycle; backtest and training jobs are new `MaintenanceAction`s. |
| Storage | SQLite WAL, 6 Alembic migrations (latest `20261105_06_ingestion_evidence`) | New tables in migrations `07`–`12` |
| Dependencies | fastapi, uvicorn, sqlalchemy, psycopg, httpx, alembic, python-calamine, pypdf, numpy, rdata | Added per phase: `pyarrow` (D2), `statsmodels`, `cvxpy`, `clarabel` (D3/D5), `scikit-learn` (D5/D6), `anthropic` (D8) |
| Tests and CI | 209 Python test files (1,578 tests), 242 frontend tests, browser and release-image jobs in `.github/workflows/python-static.yml` | Every phase adds offline tests; CI never calls external APIs. |
| Governance | Charter forbids timing signals; predictive claims need category E | D0 charter amendment is a hard prerequisite |

**Open source-health work in the handoff** (G.17 refresh, BIS bounds expiring 2026-11-26, WID review 2027-07-01) continues independently and takes priority if it conflicts with this plan.

---

## 1. Layer-by-phase overview

```
Phase:     D0   D1   D2   D3   D4   D5   D6   D7   D8   D9   D10
L8 UI       ·    ·    ·    ■    ·    ■    ■    ■    ■    ■    ■
L7 Engine   ·    ·    ·    ■    ·    ■    ■    ■    ■    ■    ■
L6 Eval     ·    ·    ·    ■    ·    ■    ■    ■    ■    ·    ■
L5 Decision ·    ·    ·    ■    ·    ■    ·    ·    ·    ■    ·
L4 Synth    ·    ·    ·    □    ·    ■    ·    ·    ·    ·    ·
L3 Models   ·    ·    ·    ·    ·    ■    ■    ·    ■    ·    ·
L2 Features ·    ·    ·    ·    ■    ·    ·    ·    ·    ·    ·
L1 PIT      ·    ·    ■    ·    ·    ·    ·    ·    ·    ·    ·
L0 Sources  ·    ■    ·    ·    ·    ·    ·    ·    ·    ·    ·
Governance  ■    ·    ·    ·    ·    ·    ·    ■    ·    ·    ■
■ = built or extended   □ = minimal version (risk model only)
```

| Phase | Name | Adds | First user-visible result | Size |
|---|---|---|---|---|
| **D0** | Governance and scaffolding | Charter amendment, catalogue domain A, flag, package skeleton, contracts | Nothing visible; design approved | S |
| **D1** | Data foundation | New sources (returns, predictors, text) | New series on the Data page | L |
| **D2** | Point-in-time store and bucket returns | L1 | Bucket return histories in Source Explorer | M |
| **D3** | Reference portfolios and baseline backtests | L5–L8 with a minimal risk model; shared executor | **Model portfolios at reference weights and baseline backtests (first release behind the flag)** | L |
| **D4** | Feature store and targets | L2 | Feature/target inspector (diagnostics) | M |
| **D5** | Econometric forecasts, synthesis and optimiser | L3 econometric, L4, outlook | **Market outlook and tilted model portfolios, labelled "research view"; live forward log starts** | L |
| **D6** | Machine-learning layer | L3 ML, registry, model cards | ML models in the scorecard and model cards | L |
| **D7** | Pre-registration freeze and holdout | Governance gate | **"Validated" labels where earned** | M |
| **D8** | Claude ensemble member and explainer (can start after D5, in parallel with D6/D7) | L3 LLM, memo | Monthly memo; Claude scored on forward log | M |
| **D9** | Personal layer and alerts | A05 | Gap analysis, contribution routing and alerts on recorded holdings | M |
| **D10** | Release, operations and recurring review | Hardening, docs, production verification | Flag removed; monthly operation | M |

Dependency graph:

```
D0 ─► D1 ─► D2 ─► D3 ─► D4 ─► D5 ─┬─► D6 ─► D7 ─┬─► D9 ─► D10
                                  └─► D8 ───────┘
```

D9 needs only D5 to function, but it is released after D7 so personal recommendations carry validation labels. D8's evidence accrues with calendar time, so it should start as soon as D5 is deployed.

---

## 2. Global constraints (every phase)

- Never relax source acceptance, fabricate observations, splice sources or silently substitute a different economic concept (DATA_POLICY, charter).
- All acquisition goes through the managed transport, immutable evidence and durable publisher budget.
- Every model reads data only through `pit.as_of()`. Purging is enforced in `backtest.training_window()`.
- The backtest and live runs share code. No backtest-only computation path.
- Keep existing API fields, question hash links, exports and P01–P07 results unchanged. P05 output must be byte-identical after the executor extraction.
- No paid data or services. API keys live only in the environment and are excluded from logs, diagnostics ZIPs and backups.
- No publisher originals, production diagnostics, credentials or private holdings in git.
- Each phase updates `docs/AGENT_HANDOFF.md` (status, verified commit, open evidence) and, where behaviour changes, README, ARCHITECTURE and RUNNING.
- Definition of done per phase: tests for the new behaviour, full offline suite and frontend tests green in CI, handoff updated. Phases that change ingestion or production output also need a post-deployment ZIP that verifies the new state.

---

## Phase D0 — Governance and scaffolding

**Goal:** Approve the scientific basis and create an empty, flagged skeleton so that later phases add code to a stable structure.

**Files:** `docs/PHASE1_SCIENTIFIC_CHARTER.md`, `docs/PHASE1_ANALYSIS_CATALOGUE.md`, `docs/DEVELOPMENT_PLAN.md`, `definitions/allocation_references.json`, `definitions/allocation_preregistration.json` (skeleton), `src/finance_dashboard/allocation/__init__.py`, `allocation/contracts.py`, `allocation/flags.py`, `tests/test_allocation_contracts.py`.

- [x] Owner approves the charter amendment (§1). Record it in the charter revision log with the date and exact wording.
- [x] Owner settles the open points (§13): reference ladder (5 rungs), default backtest view (gross: no costs, no tax), compute (server, low priority). Broker fees and example funds remain open for D3/D9.
- [x] Add catalogue domain **A — Allocation** with A01–A06 entries in the required research-record form (question, decision informed, evidence tier, limits).
- [x] Link this plan from `DEVELOPMENT_PLAN.md` as a separate track that does not change existing acceptance thresholds.
- [x] Create `allocation/` with `contracts.py` (`FeatureSnapshot`, `ForecastDistribution`, `Forecaster`, `Posterior`, `ReferencePortfolio`, `Allocation`, `Provenance`; §10.3) and `flags.py` (`FINANCE_ALLOCATION=0` by default; API routes return 404 and UI entries are hidden while it is off).
- [x] `allocation_references.json`: market anchor and R1–R5 rules with caps, TE and bands (§3), validated by `finance_dashboard validate`.
- [x] Tests: contract dataclasses are immutable and serialisable; references validate (weights sum to 1, caps consistent); the flag hides routes.

**Exit gate:** charter amendment recorded; CI green; no behaviour change with the flag off.

**Status (17 November 2026):** code-complete on branch `claude/allocation-d0`. Contracts in `allocation/contracts.py`, flag in `allocation/flags.py` (`FINANCE_ALLOCATION`, wired in Compose and `.env.example`), references and pre-registration skeleton validated by `finance_dashboard validate` (`allocation/references.py`), tests in `tests/test_allocation_d0.py`. The growth mix is measured market weights from D2; the defensive mix is provisional and labelled so.

---

## Phase D1 — Data foundation (L0)

**Goal:** Acquire every new free source the design needs, with originals and reconciliation, in three waves so that each wave can be deployed and verified.

**Files:** new provider modules (`french_regions.py`, `aqr_factors.py`, `bundesbank_curve.py`, `ecb_curves.py`, `fed_ebp.py`, `ec_esi.py`, `spf.py`, `nareit.py`, `cboe_vix.py`, `cb_statements.py`), `definitions/series.json`, `definitions/source_policies.json`, provider registry entries, minimal original fixtures under `tests/fixtures/`, reconciliation verifiers, `docs/SOURCE_POLICY.md`.

**Wave D1a — returns inputs** (needed by D2/D3):
- [ ] French data library:
  - [x] Europe, Japan and Asia Pacific ex Japan market/risk-free/total (1990-07+) and WML momentum for developed, Europe, Japan, Asia Pacific ex Japan (1990-11+) and emerging (1990-01+): 14 series. The French parser and the independent verifier are now table-driven; archive members are matched exactly (momentum archives use `*_MOM_Factor.csv` inside `*_Mom_Factor_CSV.zip`). Full originals downloaded 2026-11-17 parse identically in both (435/431/441 months to 2026-09, no missing values). Tests: `tests/test_allocation_d1a_french.py`.
  - [x] US CRSP files `F-F_Research_Data_Factors` (market, RF, total, SMB, HML from 1926-07) and `F-F_Momentum_Factor` (Mom from 1927-01), plus developed SMB/HML from the existing archive: 8 series. Datasets declare their vintage database (Bloomberg or CRSP) and missing statement; -99.99 and -999 are missing everywhere. The RF series records the publisher's Ibbotson → ICE BofA T-bill change at 2024-06. Full originals parse identically in parser and verifier (1,203 and 1,197 months).
  - [x] Profitability (RMW, for the quality bucket) from the US (1963-07+) and developed (1990-07+) five-factor files; their SMB is not registered a second time because it is constructed differently from the three-factor SMB.
  - [x] International country portfolios (`F-F_International_Countries.zip`) through a new `FRENCH_COUNTRIES` provider (`french_countries.py`, independent reader `_french_countries`): for 20 countries the monthly market return in USD and local currency (1975-01+, Austria 1987, Ireland 1991, to 2025-12) and the annual B/M, E/P and dividend yield (ratio x 100, 1975–2025), universe "All 4 Data Items Not Reqd": 100 series. Malaysia (ends 2001) is not registered. One archive download per batch under the existing French policy. Tests: `tests/test_allocation_d1a_french_countries.py`.
- [ ] Bundesbank:
  - [x] Month-end par yields on listed Federal securities for 1, 2, 3, 5, 7, 15, 20 and 30 years (with the existing 10-year series), from the same `BBSIS` family and provider: 650 months from 1972-09 for 1–7 years, 485 from 1986-06 for 15/20 years, 322 from 2000-01 for 30 years, no gaps. **Design change:** par yields replace Svensson parameters as the bond-bucket input. Swinkels' par-bond formula already reproduces his published German returns from the 10-year par yield, so every maturity can use the same tested method without re-deriving yields from curve parameters. Tests: `tests/test_allocation_d1a_bundesbank.py`.
  - [ ] Inflation-indexed (linker) real yields: `BBSIS` uses data structure `BBK_SEIS`, whose dimension order matches the nominal key and whose `BBK_SEIS_INTEREST_TYPE` codelist has `I` (inflation-linked). Exact keys with `I` in that position (5y, 10y, monthly and daily) return 404, and the API rejects open-maturity queries and the availability endpoint. Still open: try the `BBSEI` dataflow or the Bundesbank's published series list.
  - [x] Pre-1999 cash: guessed `BBIG1` money-market keys returned 404, so the OECD immediate rate (`IRSTCI01DEM156N`) and 3-month interbank rate (`IR3TIB01DEM156N`) for Germany, monthly from 1960-01, are registered through the existing FRED provider as labelled German proxies.
  - [x] DEM/USD 1971-01 to 2001-12 (FRED `EXGEUS`, monthly average; the month-average vs month-end mismatch is recorded in its notes). Tests: `tests/test_allocation_d1a_fred.py`.
- [ ] ECB Data Portal:
  - [x] Euro area AAA **par yields** for 1, 2, 3, 5, 7, 10, 15, 20 and 30 years (business daily from 2004-09-06, 5,676 observations each, no gaps), €STR (`EST.B.EU000A2X2A25.WT`, from 2019-10-01; its unit column is `UNIT_MEASURE` "PC") and EONIA monthly average (`FM.M.U2.EUR.4F.MM.EONIA.HSTA`, 1994-01 to 2021-12; the daily key does not exist). 11 series through the existing ECB provider with approved dimensions in `_ECB_SERIES`. EONIA values before 1999-01 precede the euro and EONIA itself, so they are registered as published but flagged as unusable for euro cash until documented. Tests: `tests/test_allocation_d1a_ecb.py`.
  - [x] All-issuer (all ratings) par yields for 2, 5, 10 and 30 years (`G_N_C`, daily from 2004-09-06): the all-issuer minus AAA spread is the euro sovereign credit predictor.
  - [x] Moody's Aaa and Baa yields (FRED `AAA`, `BAA`, monthly from 1919) for the IG credit model.
  - [ ] Euro corporate bond yields/spreads: ICE BofA series on FRED now carry only three years (from 2023-11) and cannot support a backtest; no free long euro corporate series is known. The IG bucket uses the Moody's model until one is found.
- [ ] Nareit All Equity REITs TR (category D proxy). **Blocked for automated collection:** the files linked from reit.com (`/sites/default/files/returns/MonthlyHistoricalReturns.xls`, `MonthlyReturns.xls`) serve a JavaScript "Client Challenge" page to scripted requests. The challenge is not bypassed. Owner options: download the workbook manually and import it through the existing manual-original upload, or use a REIT ETF price history (shorter, from 2000+) as a labelled proxy.
- [x] AQR datasets via a new `AQR_FACTORS` provider (`aqr.py`, adapter, independent reader `_aqr` in `captured_sources.py`, policy `aqr-data-sets`): QMJ US (1957-07+) and global (1989-07+), BAB US (1930-12+) and global (1987-02+), and from the Century of Factor Premia file the commodities market, carry and momentum, equity-index value and momentum, and fixed-income carry (1926-07+). Decimal excess returns, fully revised at every AQR update. Each workbook is fetched once per collection batch. **Design change:** the AQR commodities market excess return (futures, with roll) replaces the World Bank Pink Sheet spot proxy for the COMMODITY bucket. Tests: `tests/test_allocation_d1a_aqr.py`.

**Wave D1b — predictors:**
- [x] Fed excess bond premium and GZ spread (1973-01+) through a new `FED_EBP` provider; the Board's recession-probability column is a forecast and is not registered. Tests: `tests/test_allocation_d1b_ebp.py`.
- [x] VIX: already registered (`stress.us.vix`, FRED `VIXCLS`).
- [x] ECB SPF longer-term expectations for HICP inflation, real GDP growth and unemployment (quarterly rounds from 1999-Q1) via the ECB provider. The rolling-horizon SPF series (P9M, P21M) are dated by target quarter, which ingestion rightly rejects as future periods; they need point-in-time handling in D2 before registration.
- [x] Philadelphia Fed SPF median inflation expectations (`Inflation.xlsx`): GDP price 1 year (1970-Q2+), CPI 1 year (1981-Q3+) and CPI 10 years (1991-Q4+) through a new `PHILLY_SPF` provider. The separate mean-level workbooks return a script page to scripted requests and are not used. Tests: `tests/test_allocation_d1b_philly_spf.py`.
- [x] EC Economic Sentiment Indicator via Eurostat `ei_bssi_m_r2` for the euro area (EA21 composition, 1980-01+; EA20 ended 2025-12), Germany and Portugal through a new `EUROSTAT_SENTIMENT` provider. Tests: `tests/test_allocation_d1b_sentiment.py`.
- [ ] Wu–Xia shadow rates; OECD MEI original-release/revisions data for CLI vintages; BIS REER; OECD PPP.
- [ ] Euro-area OECD CLI: the OECD has no `EA20`, `EA19`, `EA` or `EZ` series in `DF_CLI`; use the registered German and French CLIs or the EC sentiment indicator instead.
- [x] FRED coverage: Moody's Aaa/Baa, DGS2/DGS3MO/DGS10, T10Y3M, DFII10 and DEM/USD are registered. [ ] Extend `vintage.py` targets for FRED predictors with revisions (D2).

**Wave D1c — text:**
- [ ] FOMC statements and minutes; ECB monetary policy statements and press conferences. Store as dated originals with publication timestamps (`cb_statements.py`). Text is stored as evidence, not as series observations.

**For every source:**
- [ ] Register source identity, policy budget, attribution and licence note.
- [ ] Add a minimal original sample fixture with source identity. Full publisher files are not committed.
- [ ] Add a parser test and an independent reconciliation verifier; missing values stay missing.
- [ ] Record the publication calendar used later for lags (D2).

**Exit gate per wave:** CI green; deployed; a post-collection ZIP shows the new series `available`, or a correctly labelled limitation; handoff updated with counts.

---

## Phase D2 — Point-in-time store and bucket returns (L1)

**Goal:** One vintaged store that every later layer reads, and monthly EUR return histories for all 21 buckets (§3, §4.3).

**Files:** `migrations/versions/20261xxx_07_allocation_pit.py` (`pit_observation`, `bucket_return`), `allocation/pit.py`, `allocation/buckets.py`, `definitions/publication_lags.json`, `definitions/allocation_buckets.json`, `definitions/allocation_instruments.json`, `allocation/jobs.py` (PIT ingestion step), tests `test_allocation_pit.py`, `test_allocation_buckets.py`, `test_allocation_import_boundary.py`.

- [ ] Migration 07: `pit_observation` (series_id, period, value, known_from, known_to, tier, vintage_source, evidence_ref) and `bucket_return` (bucket, month, local, EUR, hedged, cash, tier, recipe hash). Indexes on (series_id, known_from).
- [ ] PIT ingestion: Tier E rows from ALFRED snapshots, RTDSM, OECD MEI revisions and naturally unrevised series (markets, surveys). Tier R rows from verified latest values plus `publication_lags.json` (each lag cites its release calendar and includes a safety margin).
- [ ] `as_of(series_id, t, tier)` and `snapshot(t, tier)`. Add an **import-boundary test** that fails if any module under `allocation/models`, `allocation/ml` or `allocation/features` imports the raw observation tables.
- [ ] Bucket recipes (`buckets.py`):
  - Svensson par-bond reconstruction for any maturity, extending the existing P05 Bund method.
  - Linker real par bond plus HICP carry.
  - FX conversion, using DEM at 1.95583 before 1999 (labelled).
  - Hedged returns with interest differential and hedge cost.
  - Long-only factor proxies, credit spread-duration models, commodity spot plus collateral.
  - Each recipe is labelled with its evidence category (A–D).
- [ ] Instrument mapping file: bucket → example UCITS, US-listed and index-fund implementations (data only).
- [ ] Add bucket returns to Source Explorer as derived series, with recipe, category and limitations.
- [ ] Add dependency `pyarrow` if feature caching is started here; otherwise defer to D4.

**Tests:**
- A value with `known_from > t` is never returned.
- A hand-built vintage fixture reproduces the ALFRED first-release value.
- Par-bond return matches a hand calculation within 1e-10.
- FX and hedge arithmetic match independent fixtures.
- Bucket return totals reconcile to source series where a direct comparison exists (French US market, Swinkels).

**Exit gate:** CI green; deployed; ZIP shows bucket returns for all 21 buckets with expected start dates and labelled categories.

---

## Phase D3 — Reference portfolios and baseline backtests (L5–L8, minimal L4)

**Goal:** The first usable release behind the flag: general **model portfolios R1–R5 at reference weights**, and a backtest workspace comparing them with the baselines. No forecasts yet. This proves the evaluation machinery before any model can be judged by it.

**Files:** `allocation/executor.py` (extracted from `engine/analyses.py::simulate`), `allocation/references.py`, `allocation/models/risk.py` (EWMA + Ledoit–Wolf), `allocation/backtest.py`, `allocation/metrics.py`, `allocation/preregistration.py`, `migrations/.../08_allocation_backtest.py` (`backtest_run`, `backtest_trial_log`), engine A02 (reference mode) and A03 (baselines), `maintenance_jobs.py` (`run_allocation_backtest` action), `api.py` routes, frontend `ModelPortfolios.tsx`, `BacktestWorkspace.tsx`, tests.

- [ ] **Extract** `simulate` into `allocation/executor.py` (rebalancing rules, costs, taxes, cash flows). P05 calls the shared executor. A regression test asserts P05 bundles are identical before and after.
- [ ] Reference portfolios: market anchor from FTSE/French regional weights and the ECB maturity profile; R1–R5 from the growth/defensive split; the "simple version" constraint set.
- [ ] Minimal risk model (EWMA + Ledoit–Wolf, §6.1) for ex-ante risk and TE display.
- [ ] Backtest harness (§5.1): decision-date loop, `training_window(t)` with purging, execution at t+1, costs and tax modes, Tier E/R runs, caching by spec hash.
- [ ] Baselines (§5.3): each reference portfolio, 1/N, EUR 60/40, risk parity.
- [ ] Metrics (§5.4): CAGR, volatility, Sharpe, Sortino, maximum drawdown, Ulcer, time under water, certainty-equivalent return, TE, IR, turnover, cost and tax drag; stationary block bootstrap; deflated Sharpe ratio; trial log.
- [ ] Engine A02 in reference mode (weights, ranges = none, expected risk) and A03 (baseline backtests per rung and tier). Bundles carry provenance.
- [ ] API: `GET /api/allocation/model-portfolios`, `GET/POST /api/allocation/backtests` (POST needs the action marker and runs as a maintenance job).
- [ ] UI: model-portfolio table with example funds; backtest workspace with equity/drawdown curves, metric table, tier and cost toggles.
- [ ] Add dependency `statsmodels` (HAC, bootstrap helpers if used).

**Tests:**
- Metric unit tests against published or hand-computed examples (Sharpe, DSR worked example, bootstrap reproducibility with a fixed seed).
- Baseline results equal hand-calculated fixtures on a 36-month synthetic return panel (test harness data only).
- A backtest repeated with the same spec and data produces identical output and reuses cache.
- Flag off hides everything.

**Exit gate:** CI green; deployed with the flag on locally and on the server; ZIP shows A02/A03 bundles; owner reviews the reference ladder in the UI.

---

## Phase D4 — Feature store and targets (L2)

**Goal:** Reproducible, point-in-time feature matrices and target labels for every decision date and tier (§4.2, §11.3).

**Files:** `migrations/.../09_allocation_features.py` (`feature_snapshot` metadata), `allocation/features/{build,transforms,targets,text_tone}.py`, `definitions/allocation_predictors.json`, Parquet cache under `/data/allocation/features/`, diagnostics view, tests.

- [ ] Transforms: level, 3- and 12-month change, own-history percentile, expanding z-score, ECY, term spreads, credit spread minus expected loss, real yields, carry, 12-1 momentum, SMA gap, realised volatility.
- [ ] Entity-relative transforms for panels (countries, regions) without entity identifiers as features.
- [ ] Targets: 12-month excess log returns; event labels (drawdown > 15%, EA/US recession start using announcement-date logic from C02/NBER and the CEPR chronology, equities underperforming bonds). Labels are attached only when the target window has ended by the snapshot date.
- [ ] Central-bank tone indices using published dictionaries (Apel & Blix Grimaldi; Loughran–McDonald). Store per statement and per month.
- [ ] `snapshot(t, tier)` writes Parquet keyed by `snapshot_hash`; rebuilds must be byte-identical.
- [ ] Diagnostics view: feature coverage per date, missingness, tier mix.

**Tests:**
- Rebuilding a snapshot is byte-identical.
- No target is attached before its window ends.
- A recession announced after its start date is not visible at the start date.
- Tone scoring matches hand-scored fixture statements.

**Exit gate:** CI green; snapshot coverage report in the handoff (feature × first available date × tier).

---

## Phase D5 — Econometric forecasts, synthesis and optimiser (L3, L4, L5)

**Goal:** Turn reference portfolios into recommended portfolios and publish the general market outlook. Everything is labelled **"research view"** until D7. Start the live forward log immediately, because forward evidence accrues only with time.

**Files:** `allocation/models/{equilibrium,building_blocks,predictive,trend,regime}.py`, `allocation/calibrate.py`, `allocation/combine.py`, `allocation/optimise.py`, `migrations/.../10_allocation_forecasts.py` (`model_forecast`, `posterior`, `allocation`, `forecast_log` with an insert-only trigger), engine A01 and A04, A02 in recommendation mode, monthly step in `standalone.py`/`worker.py`, `MarketOutlook.tsx`, `ForecastScorecard.tsx`, tests.

- [ ] Forecasters M1–M6 (§6.2) implementing `Forecaster`: equilibrium prior from the market anchor; valuation/yield building blocks; univariate predictive regressions with Campbell–Thompson restrictions and Rapach–Strauss–Zhou combination; trend; recession probit and regime classifier (plus the Markov-switching alternative); volatility scaling.
- [ ] Event calibration (isotonic or Platt on expanding windows), PIT histograms, reliability.
- [ ] Combination by discounted log score shrunk to equal weights; Ω from out-of-sample MSFE; Black–Litterman posterior (§6.4).
- [ ] Optimiser (§6.5) with `cvxpy` + `clarabel`: one posterior, one run per reference portfolio; resampled weights and 10–90% ranges; partial adjustment; fallback to the reference portfolio on infeasibility.
- [ ] General signals (§6.6): outlook changes, rebalancing climate, model-portfolio changes.
- [ ] Engine A01 (outlook table and "where to put new money"), A02 in recommendation mode, A04 (scorecard: out-of-sample R², Clark–West, CRPS, Brier, view hit rates).
- [ ] Monthly job on the 3rd business day after month-end, after the refresh. Writes `forecast_log` entries labelled "research".
- [ ] Development-period backtests of the full pipeline per rung and tier, recorded in the trial log.
- [ ] Add dependencies `cvxpy`, `clarabel`, and `scikit-learn` (for isotonic calibration).

**Tests:**
- Each forecaster has a deterministic fixture test.
- BL posterior equals the closed-form result on a 3-asset example.
- With all Ω infinite, the posterior equals the prior and the optimiser returns the reference portfolio.
- Optimiser property tests: constraints hold for random valid inputs, and infeasible inputs fall back to the reference.
- `forecast_log` rejects updates and deletes.
- The live run and the backtest at the same t produce identical forecasts.

**Exit gate:** CI green; deployed; first live month recorded in `forecast_log`; ZIP shows A01/A02/A04 bundles labelled "research view"; development-period report written to `docs/`.

---

## Phase D6 — Machine-learning layer (L3 ML)

**Goal:** Add the ML forecasters, registry and model cards defined in §11. They earn weight only through the same combination.

**Files:** `allocation/ml/{datasets,cv,estimators,conformal,stacking,explain,drift,registry}.py`, `migrations/.../11_allocation_ml.py` (`model_registry`, `model_artifact`), `definitions/ml_models.json`, hyperparameter spaces in `allocation_preregistration.json`, artifact store `/data/allocation/models/`, engine A06, `ModelCards.tsx`, `MaintenanceAction` `run_allocation_training`, tests.

- [ ] Panel datasets: equity family (French country indices plus regions), bond family (Swinkels plus curve buckets), and the JST annual panel for Tier R pre-training. Overlap and entity weights (§11.2).
- [ ] Purged, embargoed, nested walk-forward CV with pre-registered grids; every configuration logged to the trial log.
- [ ] M8 elastic net with sign constraints; M9 shallow gradient boosting with monotonic constraints, quantile loss and shrinkage towards M8; M10 bagged forests on block bootstraps; M11 L1 logistic/multinomial and Gaussian HMM with state matching.
- [ ] Adaptive conformal intervals; the variance passed to BL comes from the conformal width.
- [ ] Optional stacking variant (NNLS, shrunk), evaluated only as a variant.
- [ ] Registry and artifact store: artifacts are loaded only if their SHA-256 matches the registry; artifacts are excluded from backups but their hashes are kept.
- [ ] Model cards (A06): permutation importance, partial dependence and ICE, constraints, skill, coverage, weight history, PSI drift.
- [ ] Lifecycle: research → registered (gate §11.9) → holdout (D7) → monitoring → retirement.
- [ ] Refit cadence: linear monthly, trees yearly, re-tuning every 36 months; respect the compute budget (§10.8) and the owner's decision on where training runs.

**Tests:**
- A planted future-dated feature yields no inner-CV gain (leakage test).
- Fixed-seed fixture fits are reproducible.
- Monotonic constraints hold on a grid.
- A tampered artifact is refused.
- Conformal coverage on exchangeable simulated data (harness only) is within tolerance.
- The registration gate rejects a model that only matches the baseline.

**Exit gate:** CI green; development-period comparison report (ML vs econometric combination) in `docs/`; registration decisions recorded; deployed; ZIP shows the registry and A06.

---

## Phase D7 — Pre-registration freeze and holdout evaluation

**Goal:** Turn research views into validated recommendations where, and only where, they are earned (§5.2, §5.4).

**Files:** `definitions/allocation_preregistration.json` (frozen), `docs/ALLOCATION_HOLDOUT_REPORT.md`, `allocation/preregistration.py` (lock), engine acceptance wiring for A01/A02/A04, tests.

- [ ] Freeze the specification: features, models, hyperparameter spaces, combination, optimiser settings, references, costs. Commit it with its SHA-256 in the commit message.
- [ ] Lock: the holdout period (2010-01 to the latest complete target) can be evaluated only once per spec hash. Re-runs return the stored result.
- [ ] Run the holdout for all registered econometric and ML models, per rung and tier. Compute the gate metrics (CE improvement and bootstrap bound, deflated Sharpe with the full trial count, drawdown limit, calibration).
- [ ] Wire the gate into acceptance. A01/A02 views and tilts become "validated" or stay "research view / neutral" per bucket and per rung. A failed model's weight is zero in live runs.
- [ ] Publish the holdout report, including failures and the trial count.

**Tests:**
- A second holdout evaluation of the same spec hash is refused.
- A changed spec requires a new pre-registration entry.
- Acceptance labels follow gate results on fixture metrics.

**Exit gate:** owner reviews the holdout report; deployed; ZIP shows validation labels consistent with the report.

---

## Phase D8 — Claude ensemble member and explainer (parallel track after D5)

**Goal:** Add Claude as a scored forecaster and as the explainer (§8), without letting it influence allocations before it has earned post-cutoff skill.

**Files:** `allocation/llm_client.py`, `allocation/llm_pack.py`, `allocation/models/llm.py`, `definitions/llm_models.json` (model IDs, training cutoffs, prices), `migrations/.../12_allocation_llm.py` (`llm_forecast`, `llm_budget_ledger`), settings UI, `docs/SOURCE_POLICY.md` (api.anthropic.com budget), recorded response fixtures, tests.

- [ ] Add dependency `anthropic`. Read the key from `ANTHROPIC_API_KEY` in `.env` (documented in `.env.example` and RUNNING). Exclude it from logs, ZIPs and backups.
- [ ] Input pack: cached stable prefix plus a point-in-time as-of block and dated central-bank text. No tools, no portfolio data.
- [ ] Structured output schema and validator; adaptive thinking; configurable effort and K samples with per-field median; refusal and fallback handling; failures become missing forecasts.
- [ ] Budget: `count_tokens` estimate before each run, accrual from `usage`, hard monthly cap, graceful disable without a key.
- [ ] Zones per model: contaminated (diagnostics only, opt-in), post-cutoff replay via Message Batches, live forward. Memorisation probe.
- [ ] Combination: Claude weight is zero until 24 scored post-cutoff months, then capped (default 25%).
- [ ] Explainer memo for layers 1–2 (and the optional personal paragraph), with a numeric cross-check against the bundle and a charter lint list; blocked memos fall back to the plain summary.

**Tests (all offline):**
- Recorded responses parse; an invalid schema becomes missing.
- The budget cap stops calls.
- The pack contains no data with `known_from > t` and no holdings.
- The weight is zero before 24 post-cutoff months.
- A memo containing a number not in the bundle is blocked.

**Exit gate:** CI green; deployed with a key configured by the owner; ZIP shows `llm_forecast` entries, the spend ledger and the memo for the live month.

---

## Phase D9 — Personal layer and alerts (L5 personal, A05)

**Goal:** Apply the general posterior to the owner's own policy and recorded holdings (§7.3, §6.6), without changing layers 1–2.

**Files:** `allocation/alerts.py`, owner policy section in `owner_inputs.py` (schema extension with migration of the existing file format), engine A05, `PersonalAllocation.tsx`, backup manifest update, tests.

- [ ] Owner policy: choose a rung or edit weights; it is stored with the existing atomic, revisioned owner-input mechanism.
- [ ] Gap analysis vs recorded holdings from `portfolio_holdings.py`, including ISIN → bucket mapping and unmapped-holding warnings.
- [ ] Alerts: band rule, CE gain vs cost and tax, contribution routing first, defer rules during stress (only if the drawdown model is validated), policy review.
- [ ] Trade list in whole ETF shares with cost and estimated Portuguese tax. Nothing is executed.
- [ ] Without a policy or holdings, A05 returns an explicit "not configured" state.
- [ ] Backtest the alert rules against calendar rebalancing using the shared executor.

**Tests:**
- Without holdings, A05 is "not configured" and layers 1–2 are unchanged.
- Alerts fire on fixture drifts.
- Contributions are routed before sales.
- Holdings are never sent to Claude except as weights in the optional memo paragraph.
- Recovery restores the owner policy.

**Exit gate:** CI green; deployed; owner verifies the personal view against their real holdings; ZIP (with private values redacted as usual) shows A05 state.

---

## Phase D10 — Release, operations and recurring review

**Goal:** Remove the flag, document the module, verify production, and set the recurring operating rhythm.

- [ ] Documentation: README section, ARCHITECTURE (allocation layers), RUNNING (jobs, compute, key), DATA_POLICY (PIT tiers), limitation texts in `definitions/limitations.json`.
- [ ] Browser tests for all panels (desktop/mobile, light/dark, keyboard); performance check that Data Collection status remains fast while a backtest runs.
- [ ] Remove the `FINANCE_ALLOCATION` flag (default on). Release via `deploy.sh`; verify the release identity and a post-deployment ZIP.
- [ ] Recovery drill including allocation tables, registry and `forecast_log`; artifacts rebuild and match their hashes.
- [ ] Handoff: final verified commit, deployed release, open evidence.

**Recurring operations (after D10):**

| Cadence | Task |
|---|---|
| Monthly (automatic) | Refresh → PIT ingestion → features → forecasts → posterior → outlook, rungs, personal → memo → `forecast_log` |
| Monthly (owner) | Read the outlook and alerts; act or not |
| Quarterly | Review drift flags, conformal coverage and Claude spend; check source health for allocation inputs |
| Yearly | Tree-model refits; scorecard review of the forward log; reference-ladder review |
| Every 36 months | Hyperparameter re-tuning (same pre-registered spaces) |
| On model changes | New pre-registration entry; evaluation only on the forward log (the holdout is spent) |
| On new Claude model | New zone boundaries; weight restarts at zero |

---

## 3. Risk register

| Risk | Effect | Mitigation | Phase |
|---|---|---|---|
| Charter amendment not approved | No predictive allocation | D3 still delivers reference portfolios and baseline backtests, which are descriptive and charter-compatible | D0 |
| A free source changes terms or disappears | Bucket or predictor history breaks | Source policy ledger; category D labels; buckets without history become unavailable rather than proxied silently | D1 |
| Too little Tier E history | Weak headline evidence | Tier R reported with its bias estimate; live forward log from D5 | D2, D5 |
| No model passes the holdout gate | Recommendations stay at reference weights | Accepted outcome; the reference ladder is still useful and honest | D7 |
| Overfitting through repeated research | Inflated results | Trial log, deflated Sharpe, single-use holdout, forward-log-only evaluation afterwards | D3–D7 |
| Backtest compute too heavy for the server | Slow jobs, contention | Caching by spec and refit point, annual tree refits, run training locally if the owner chooses | D3, D6 |
| P05 regression during executor extraction | Existing results change | Byte-identical regression test before merging | D3 |
| Claude cost or availability | Missing forecasts | Hard cap, graceful disable, missing forecasts never imputed | D8 |
| Conflicting source-health work | Delays | Source-health tasks in the handoff take priority | All |

---

## 4. Tracking

Each phase is tracked in `docs/AGENT_HANDOFF.md` under a new heading **"Allocation module progress"**, which records the phase, its status (not started / in progress / code-complete / production-verified), the verified commit, the deployed release and the still-open evidence. A phase is **code-complete** with tests and green CI. It is **production-verified** only with a post-deployment ZIP that shows the expected state.
