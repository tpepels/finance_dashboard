# Phase 3 — comparative analytical engine: design

Status: draft for owner approval, 2026-11-08. Phase 2 is complete (36 of 36 active analyses accepted or conditional; G03 deferred). This document defines Phase 3. It builds on, and does not restate, the binding [scientific charter](../../PHASE1_SCIENTIFIC_CHARTER.md), [visualization contract](../../PHASE1_VISUALIZATION_CONTRACT.md), [analysis specifications](../../PHASE1_ANALYSIS_SPECIFICATIONS.md) and [development plan](../../DEVELOPMENT_PLAN.md).

## Intent

In the owner's words: financial media (Yahoo, the Wall Street Journal, Substack) are overwhelming and the agenda behind each number is unknown. The owner does not know which number to look at, and wants **a truth that can be trusted because it is built on rigor, not on someone wanting to sell or convince**.

The owner also wants to **discuss the numbers with an AI**. So every result must serve two readers equally: the owner looking at a chart, and an AI reading what is behind it. The chart and the conversation must never tell different stories.

Trust is earned by four properties, and the engine exists to guarantee them:

1. **Nothing hidden.** Every figure traces to the original publisher, release and transform. What is missing or limited is shown, not buried.
2. **No cherry-picking.** Indicators that answer the same question appear together, including those that disagree.
3. **Honest uncertainty.** Estimates carry ranges with their method; "the evidence does not say" is an acceptable output; a precise-looking number on thin evidence is not.
4. **No selling.** No timing signals, no buy/sell language; every analysis is framed by the decision it informs (catalogue revision 2026-11-06).

## Goals

* One engine computes every active analysis from stored, verified observations and produces one **result bundle** per analysis.
* One shared library of **named transforms** with recorded formulas replaces the transforms now duplicated across `decision_analytics.py`, `insights.py`, `research.py`, `risk_diagnostics.py`, `portfolio_risk.py` and the browser's `transform.ts`.
* **Phase 2 conditionals are tracked end to end.** Every limitation the acceptance engine records for an analysis is carried in that analysis's bundle, shown with its chart and included in its export. When a Phase 2 state changes, the affected bundles change without hand edits.
* Each bundle can be **exported** (a button per chart) and **fetched from the API**, so the owner can paste it into an AI conversation or an AI tool can read it directly.

## Non-goals

* A built-in AI chat in the dashboard. It may come later and must read the same bundles.
* Owner portfolio inputs (weights, costs, tax, withdrawal plan): the next plan slice, Phase 5 territory. The engine must accept them as declared `user_input` roles later but does not collect them now.
* Saved and duplicated custom views, the figure editor and the overview layout: Phase 4. Phase 3 supplies what those need (bundles, transforms, validity rules); Phase 4 builds the interaction.
* New data acquisition. Phase 3 uses the Phase 2 corpus as it stands.

## Anti-goals (failure even if it technically works)

* The engine writes conclusions in prose ("credit risk is rising"). It provides evidence; interpretation happens with the owner, where it can be challenged. Fixed, sourced method statements and limitation texts are not conclusions and are allowed.
* A **disagreement or agreement score** between indicators. Owner decision (2026-11-08): when rigorous indicators disagree, the engine **shows both side by side** and does not compute how far apart they are or pick a winner.
* A composite risk score, traffic light or "probability of crash" (charter: no composite without disclosed weights, sensitivity and independent evaluation; none is in scope).
* A limitation that exists in the acceptance engine but not in the bundle, or a hand-typed limitation that contradicts it.
* Any filled, interpolated, carried-forward or future value; any chart and export that show different numbers.

## The result bundle

The unit the engine produces, the chart draws from and the export contains. Contents (field names are the builder's; the content is fixed):

1. **Identity:** analysis ID, question, decision informed (from the catalogue), evidence tier (descriptive or predictive), engine and method version, computation time.
2. **Phase 2 state:** `accepted` or `conditional` and, for conditional analyses, **every** limitation from the acceptance engine (code, affected series or role, readable text), plus the acceptance evaluation time.
3. **Inputs:** each series with its role, the analysis and role under which Phase 2 accepted it (an input may be borrowed from another analysis's resolved role, carrying that role's limitations; a series accepted nowhere is refused), original publisher, source series ID and URL, geography, unit, frequency, observation dates, and the temporal evidence used (latest revised or real-time vintage).
4. **Transforms:** the ordered, named transforms applied to each input, with formula and parameters. A reader can recompute every derived value from the inputs and this list.
5. **Values:** the observed and derived series as plotted, each point with its native period. Gaps stay gaps.
6. **Estimates:** each model-based figure (category C) with its range, the method that produced the range, the sample used and the effective number of independent observations. A point value without a range says so.
7. **Comparison:** the related indicators for the same question, shown side by side; they are the roles of the analysis's `comparison_contract` in `definitions/phase2_research_corpus.json`. Agreement is not scored (anti-goals).
8. **Method limitations:** limits of the method itself (for example, P07's covered-interest-parity approximation), distinct from the Phase 2 data limitations in item 2.
9. **Citations:** method references (R-keys from the charter) for every method used.

### Analyses that lose their Phase 2 state

If an analysis's acceptance state falls back to `blocked` or `incomplete` (for example after a refresh revises stored values), its bundle still states the question and the open gates but carries no values or estimates, consistent with the plan's rule that only `accepted` or `conditional` analyses feed a slice. *Builder's call, recorded here.*

### Limitation texts

Acceptance limitations are machine codes today (for example `latest_revised_values_not_real_time`). A single register maps each code to owner-readable text. Every code the acceptance engine can emit has an entry; a test fails on an unmapped code. Method limitations live in the same register, keyed per analysis, replacing the hand-typed strings in `decision_analytics.py`.

### Conditionals register

Besides per-bundle limitations, the engine exposes one listing of all conditional analyses and their limitations (API and CLI), so the owner and the development plan can track what each conditional still lacks. The plan's "Current state" table is checked against it.

## Transforms and alignment

Implemented once in Python, named, each with a formula string recorded in the bundle. The initial set follows what the charter and specifications already require:

* calendar month-end (last observation in each month, observed date retained), dropping the incomplete current month;
* exact native-period joins of two or more series (no fill; unmatched periods are dropped and counted);
* growth rates (period-on-period, year-on-year, annualized), levels, differences, ratios with a declared denominator;
* real versus nominal with a named deflator matched to scope;
* currency translation to EUR at a named reference rate;
* index = 100 at a stated base (first visible observation; zero bases refused);
* own-history position (percentile with tied mid-ranks, deviation from own mean) with a minimum of 20 observations;
* contiguous runs and overlapping-window statistics with effective sample size.

Display normalizations the owner selects on a chart (index 100, percentile, range) are computed by the engine, not the browser, so the export always matches what is shown. *Builder's call, recorded here: this moves the work done in `frontend/src/transform.ts` to the engine.*

Predictive analyses (C02, V05, and any backtest) must use only information available at each evaluation date: the engine evaluates them against ALFRED windows or unrevised market observations, as Phase 2 accepted them.

## Uncertainty

* Model-based estimates (P06 ranges and any later estimate) give a range, its method, its sample and its effective independent observations. Overlapping windows are declared.
* Descriptive measurements show their own-history context (where in its history a value sits), not a fabricated error band.
* Where no defensible uncertainty measure exists, the bundle says so explicitly.

## Export and API

* `GET /api/analysis` lists analyses with their state; `GET /api/analysis/{id}` returns the bundle as JSON. The view parameters a chart uses (geographies, period, display normalization) are request parameters, and the response records them.
* The export button on each chart produces one text file for pasting into an AI conversation: a readable header (question, decision informed, state, limitations, method, sources, transforms) followed by the data. *Builder's call, recorded here: a single self-contained text file rather than a JSON download, because it pastes into a chat as-is; the JSON stays available from the API.*
* `/api/decision/{id}` is retired once P06, P07 and F03 run on the engine (one canonical path, per the plan's working rules).

## Build order

1. Engine skeleton: bundle, transform library, limitation register, conditionals register, `/api/analysis`.
2. Rebuild P06, P07 and F03 on the engine, with identical numbers to today's endpoints (regression check), then move the Decisions panel to the new endpoint and retire the old one.
3. Remaining analyses one **overview group** at a time, in the visualization contract's order: (1) C03/C01/C06, (2) M01/M02/M04, (3) F01/F03/F06/F07 plus F02/F04/F05, (4) V01/V03/G01 plus V02/V05, (5) L01/L02/L07/L04 plus L03/L05, (6) P02/P01/P03/P04 plus P05; then C02, C05, G02, G05, G06. Each group ships with its charts and exports (an end-to-end slice; charts reuse the existing ECharts components with each analysis's default view from the visualization contract, while configurable views wait for Phase 4) and retires the duplicated transform code it replaces.

**The pre-reset dashboard is retired during Phase 3** (owner decision, 2026-11-08). As each group moves onto the engine, its old indicator tiles (`research.py` registry and `ResearchDashboard.tsx`), the overlapping risk-diagnostics views (`risk_diagnostics.py`, `Phase4Panel.tsx`), the `insights.py` readouts and the `/api/research` and `/api/risk` endpoints they feed are removed. Views that no analysis replaces are removed with the last group rather than kept as a parallel path. Raw source inspection (the source explorer and `/api/series`) stays: it is the provenance layer, not a calculation path.

Phase 3 is complete when every active analysis produces a bundle, every chart draws from one, the duplicated transform paths are gone and the pre-reset dashboard is retired.

## Constraints

* Charter statistical rules apply unchanged: matched scope and deflators, no fill or interpolation, explicit missingness and breaks, distinct world versus reporting-country aggregates, no US NBER band presented as global.
* Plan working rules: one CLI, one HTTP client, one acceptance engine; consolidate rather than add parallel paths; full offline suite before each commit.
* Bundles never include credentials or local file paths.

## Left to the builder

Module layout, bundle schema field names, caching of acceptance results (the acceptance evaluation is expensive; the bundle states the evaluation time it used), how values are paged or trimmed for very long daily series in the export, test structure, and the order of analyses inside each group.
