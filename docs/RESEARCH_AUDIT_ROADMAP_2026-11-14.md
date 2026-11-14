# Global Capital Monitor — research audit and development roadmap

**Baseline:** Latest inspected *deployed* diagnostic ZIP:
`finance-debug-0.2.2+cbda34bb3ad245ce-20261114T161327.zip`,
generated on 14 November 2026. Research acceptance evaluated at
`2026-11-14T16:11:25Z`. Later repository changes are not proof of a later
deployment. This document is a scope/requirements roadmap, **not a claim that
the proposed research modules have already been implemented**.

## 1. Executive findings

The application contains useful source provenance, 426 registered data
histories and 37 research questions. The current evidence is less conclusive
than a green/amber source-health lamp implies:

| Observation | Verified result in deployed ZIP | Interpretation |
| --- | ---: | --- |
| Series with retained data | 426/426 | No wholly empty registered histories; freshness and adequacy remain separate |
| Histories needing source attention | 6 | Five world WID income/wealth series through 2023, plus US EU KLEMS labour compensation through 2020 |
| Verified publisher checks with no newer observation | 4 | Monitor; do not invent missing publisher values or reclassify as download failures |
| Deferred refresh attempts with usable existing observations | 79 macro histories (77 current-data, 2 publisher-checked) | Provider cooldown/availability, not 79 missing histories; 77 appear in the limitation list as deferred refresh entries |
| Source collection failures in status | 0 | No current evidence of failed ingestion |
| Research questions evaluated | 37/37 | 24 accepted, 11 conditional, 1 incomplete (V03), 1 deferred (G03) |
| Machine-readable limitation entries | 382 | **Findings, not 382 unique defects**; 352 informational, 22 medium, 8 high |
| Method limitations | 116 | Registered assumptions/caveats; not necessarily remediable bugs |
| Original ICIO failed accounting equations | 24,869 | Full failure ledger for exported matrices; must trace which derived/accepted computations depend on each failed matrix |
| Post-ingestion coordinator in ZIP | idle, 0 batches | After deployment no in-process changes were observed yet; this does not prove ingestion hooks failed |

Among the eight high-severity audit entries are G03 and V03 acceptance
states, G03's deferred evidence, missing original-role evidence for P01/P04/P05
and V03, and the ICIO accounting issue. The research limitations inventory
includes 24 borrowed-source caveats, 123 other evidence caveats, and three
fixed-date method statements requiring review (G06, P02, P05).

### Interpretation caveat

**Accepted** means a question's currently specified original-method
scientific acceptance gates passed. It is not proof that the question captures
all economically meaningful distributions, that every source matrix in the
archive is valid, or that a detected correlation is causal. The diagnosis
must distinguish source recency, input quality, formula validity, economic
construct validity and interpretability.

## 2. Verified immediate gaps

**L01 — average pay and productivity.** The engine uses economy/sector aggregate
labour compensation and value added per hour, deflated with the same
value-added deflator, then indexes both to a common base. This supports a
*mean compensation/aggregate productivity* question. It cannot answer how the
**median wage** or bottom wage deciles have evolved. Higher executive pay can
raise the mean while the typical employee does not benefit. Add a separate
worker-distribution view; preserve existing apples-to-apples aggregate identity.

**L02 — division of company value added.** Compensation, net operating surplus,
depreciation and net production taxes are partitioned as aggregate shares of
company gross value added. Calling this chart the *typical worker's pay–profit
gap* would be incorrect. Do not replace aggregate employee compensation
in the national-accounts identity with a median wage. Link a worker-distribution
study with compatible populations, dates and deflators.

**L04 — surplus/profit estimates.** Wage variants account for self-employed
income and alternative productive-sector classifications, but do not separate
executive/managerial pay from typical labour pay. The register explicitly
states `supervisory_labour_not_separated`; any alternative treatment requires
a new explicit economic definition and the matching occupation/sector data.

**C06 — inflation and commodities.** The implemented analysis computes annual
changes in Brent crude oil, US natural gas and maize; it also displays
inflation and growth for the US, Japan and China. It does **not** estimate
inflation/asset-inflation correlations, lags, rolling relationships, price
pass-through or real investor returns. P04 is a scenario shock calculator,
not an empirical inflation/asset-correlation model.

**L07 — global inequality.** Currently compares top 1% and bottom 50% shares of
*pre-tax national income* for six geographies. Wealth concentration is
covered by separate US-centric L05 and world wealth series registered in
source coverage, but the L07 research output does not present the combined
Piketty/WID findings, the top 10%, middle 40%, distributional growth,
capital-income ratio, or a Piketty-specific evidence view.

**WID freshness problem.** Five world WID series end in 2023 in the installed
database. The World Inequality Report 2026 publishes 2025 global indicators
(e.g., global top 10% hold 75% of personal wealth, bottom 50% hold 2%).
These facts establish an important investigation priority, **not** proof that
the exact existing WID variable/age/population source codes already publish
matching 2025 values. Inspect the original WID bulk CSV/metadata pair and
WIR methodology before importing or reconciling either series. WID parser
uses different world/national age/population variable code arrangements and
preserves observation-quality metadata.

**Research original gaps.** V03 is incomplete with `regional_trailing_pe`
and `regional_forward_pe` open. G03 is deferred because listed-parent
profit originals, issuer universe, fiscal periods, filing dates and FX roles
are missing. G01 and G02 require complete index/issuer/country originals.
P01 requires actual fund weights; P04 lacks owner currency weights,
duration and convexity; P05 lacks policy inputs, actual weights, constituent
total returns, costs, tax and withdrawal assumptions. These should not be
presented as validated owner-specific claims.

**ICIO accounting.** The 24,869 failure equations are real export evidence.
The register marks G06 accepted with a separate matrix-materiality caveat;
that cannot be treated as blanket acceptance of all archived OECD editions.
Trace hashes, editions, years and matrices used in G06, L04 and TiVA
reconstructions. Distinguish **unused historical archive failures** from
**a failed matrix contributing to an accepted result**. Do not waive residuals
with generic binary64 error bounds.

**Outdated prose.** Three fixed-date statements in G06, P02 and P05 need
source-bound verification. A time-specific method description should refer
to the actual series/reference period, not a hardcoded “currently ends” year.

## 3. Audit standard for every research question

Each question needs a structured method/quality card with:

1. **What is measured:** exact economic construct; wage mean vs median,
   wealth stock vs income flow, gross vs net, real vs nominal, total return
   vs price change, owner horizon and currency.
2. **Who and when:** population, age, employment definition, sector,
   geography, frequency, cohort, available years and revisions.
3. **Evidence:** original publisher identity, codes, latest period,
   source quality grades, hash/receipt, and derived calculation lineage.
4. **Method:** equations, deflator, aggregation, matching window,
   denominators, weighting, timing and documented sensitivity alternatives.
5. **Output and inference:** primary claim, uncertainty, distribution,
   heterogeneity, regime sensitivity and limitations. Correlation never
   implies causality.
6. **Follow-up questions:** explicit parent/child hypotheses, reason to
   ask, required data, supported alternatives and research/acceptance state.
7. **Acceptance:** integration tests with original-source fixtures,
   source-period and accounting checks, economic invariant tests,
   frontend/browser checks, and visibly withheld or conditional results
   when gates are open.

Each new question must use the **existing canonical source ingestion,
research corpus, engine, analysis bundles, frontend research navigation and
limitation inventory**, not a parallel ungoverned analytics service.

## 4. New and revised research programme

### A. L01/L02/L04 + L08 — compensation, median and minimum wage

**Core question:** Have typical workers, low-paid workers, and aggregate
labour compensation benefited equally from productivity gains? Has the
profit share shifted, and how does the within-labour distribution modify
the interpretation?

Deliver all of:

- Keep L01 aggregate per-hour *mean compensation vs productivity* with the
  value-added deflator for the sector-identical factor-share comparison.
- Add **median real earnings** and indexed median/profit/productivity
  comparisons on separately identified compatible populations and periods.
  Use CPI/HICP for workers' purchasing power as a distinct view; do not
  silently substitute it for the output deflator.
- Add P10, P50, P90 (and P99 where actually available), P90/P50,
  P50/P10, mean/median and top-end skewness, as historical curves or
  bounded source-verified snapshots when full histories are unavailable.
- Add statutory/effective **minimum wage**, minimum-to-median (Kaitz),
  low-pay incidence, and applicable sectoral coverage and legal scope.
  A statutory wage is not a population median; countries without a
  nationwide statutory floor must be represented correctly.
- Cross-country scope US and selected European economies first, with
  further countries only where original source identity/population
  compatibility is verified. Label full-time vs all workers, gross vs
  net, hourly vs weekly/monthly, self-employed coverage, and bonuses.
- Explicitly distinguish aggregate labour share of GVA (L02), relative
  employee earnings distribution (new L08), and theoretical surplus
  calculations (L04). No median is inserted into aggregate identities.
- Follow-ups: Are gains concentrated in P90–P99, or only P99+? How much
  of the mean–median gap is sector mix, occupation composition, hours,
  top-end compensation or changes in self-employment? Is a falling
  labour share associated with rising capital concentration?

Sources to validate: BLS CPS median weekly earnings, OECD
`DSD_EARNINGS@DEC_I` decile ratios and `DSD_EARNINGS@MIN2AVE`
minimum-to-median, Eurostat Structure of Earnings Survey. Prefer actual
publisher median levels when available; **decile ratios alone cannot
reconstruct absolute median wages**. Different source universes/years
must remain separate. Use latest released original metadata and revision
dates, not hardcoded annual assumptions.

**Done when:** matched-period comparisons, native distributions, footnotes,
revisions, all missing-data scenarios and source quality/coverage gates are
implemented, original-source tests and cross-country economic checks pass,
and L01/L02/L04 UI descriptions have been revised to prevent misinterpretation.

### B. C06 + new asset-inflation question — inflation transmission

**Core question:** How and when do consumer-price inflation, housing
inflation, equity/bond prices, gold, commodity prices and real returns
move together?

Data groups: headline and core CPI/HICP, PPI if approved,
housing price indices (BIS selected series), local equity **total
returns and price indices separately**, sovereign yields/bond
returns, gold and approved source-verified commodity benchmarks
(energy, metals, agriculture). Add commodity-wide index only when
a genuine published basket is available; never treat Brent alone as
the whole commodity market.

Outputs:

- Time-aligned year-on-year price changes, nominal and CPI-deflated
  **real asset price changes**, and separately defined total returns.
  Use EUR and USD currency views with coherent FX and currency labels.
- Contemporaneous Pearson **and** rank correlations, scatter plots and
  rolling 3/5/10-year correlations with observation counts and intervals.
- Lead/lag cross-correlations (e.g., ±12 months for monthly sources,
  ±8 quarters for quarterly) with a prespecified lag convention and
  no forward-looking alignment.
- Regime comparison (stable inflation, 1970s where verified,
  inflation shock 2021–2023, disinflation) with coverage-matched periods,
  dates, sample sizes and uncertainty.
- Robustness: level-vs-change warnings, overlapping-return problems,
  frequency harmonisation, recession/rate/liquidity controls, outlier
  sensitivity, structural breaks, nonstationarity and multiple-testing
  caveats. Do not claim causal pass-through from correlation alone.
- An optional explicit pass-through model can test whether commodity
  shocks predict **subsequent** CPI/PPI, and whether the association
  changes by country and inflation regime. State it as an observational
  model, with stability checks and a no-causality disclaimer.
- Follow-ups: Do commodities lead CPI? Are house prices more closely
  tied to credit expansion and rates? Is gold a hedge to realised CPI
  or to inflation shocks? Are nominal equity gains driven by real
  earnings, discount-rate changes or currency? Do responses differ
  for a EUR investor?

Use existing C06 and P02/P04/V01/M02 data roles when compatible; keep
modelled stress tests distinct from actual historical estimates.

**Done when:** the new analysis is registered, its source-specific
provenance and missing-history logic are complete, original inputs
and monthly/quarterly joins are regression-tested, and all charts
expose sample/period, FX, units, error ranges and caveats.

### C. L07/L05 + new Piketty/WID research workspace

Use a **Piketty — inequality, capital and distribution** section in the
current Labour/Profits/Inequality research topic, with a concise dashboard
summary and links to full figures. Reuse the WID original CSV/metadata
pipeline and acceptance mechanism; do not create an alternative WID
downloader that bypasses source policy.

The five primary research findings and their proposed figures:

1. **Wealth is more concentrated than income:** historical shares
   top 1%, top 10%, middle 40%, bottom 50% for *both* pre-tax income
   and net personal wealth, with the same population concept and
   matched year. Provide T10/B50 and T1/B50, with denominator safety
   for very small or negative bottom wealth.
2. **Long-run distribution of growth:** growth incidence by percentiles
   (P0–10 … P99.9–100 when publisher-provided) with explicit
   periods such as 1980–latest, country/region, purchasing-power
   convention, revisions and population scope.
3. **Capital/wealth-to-income ratio:** private, public and national
   wealth-to-national-income ratios, comparing countries through
   long histories. Distinguish capital stock valuation from productive
   physical capital and avoid equating every increase with new saving.
4. **Capital income, labour income and r–g:** separate shares of
   national income and an **explicitly defined, sourced** estimate of
   the rate of return on capital versus real economic growth.
   A stock index return or a sovereign yield is not by itself
   Piketty's net return on aggregate wealth. If a commensurable
   return series cannot be certified, show the components and
   mark r–g **not empirically validated**, not a fabricated number.
5. **Composition of wealth and inheritance:** housing vs financial/
   business wealth and inherited vs earned wealth **only for
   countries and dates with matching original definitions**;
   show “not available” otherwise. Top-tail ownership should
   distinguish household vs adult/individual definitions.

Each finding gets: Piketty's **hypothesis/theoretical context**,
latest empirically supported measurements, historical test,
counterevidence/method limitations, source-quality and revision
badges, country/geography selection, and a link to primary sources.
These are evidence-driven panels, not static book quotations.

**2026 published reference:** World Inequality Report 2026's 2025
global snapshot reports 53% income and 75% net personal wealth for
the top 10%; 8% income and 2% wealth for the bottom 50%.
Treat these as a **dated report reference** until the corresponding
variable, units, population and source versions are reconciled with
the canonical WID source. The current ZIP's five world WID histories
stop in 2023. Never append a report figure to a different
WID time series solely to make it look current.

Piketty himself cautions that r > g is one important force but neither
a deterministic law nor the sole/primary explanation of wealth
inequality. The application must present distributional history,
institutional differences, tax and inheritance effects, and uncertainty.

**Update contract:** Periodically check the publisher's exact WID bulk
pair/report original; validate variable/unit/age/population definitions,
content hashes and observation quality; append verified vintages only.
Every accepted new observation triggers the existing post-commit
availability/acceptance/figure refresh pipeline. Dated report
snapshots must retain their vintage and coexist with updated live
series without silently overriding them.

**Done when:** all five modules have genuine accepted data or
explicit withheld states, automatic refresh is integrated,
the 2025 report reference is method-reconciled or distinctly dated,
historical regressions and original-quality badges are tested,
and desktop/mobile browser acceptance passes.

### D. Follow-up question network

Extend existing `phase2_research_corpus.json` metadata and research UI with
a navigable, reproducible **question → evidence → findings → follow-up**
graph. Each child question stores ID, parent(s), reason/hypothesis,
required series and concept mapping, method, data adequacy, owner
priority, run/acceptance state, uncertainty and source citations.

Examples: L01 → median labour income → decile composition → income
capitalisation; C06 → commodity/CPI lead–lag → earnings/profit squeeze
→ bond/equity repricing; L07 → share concentration → wealth-to-income
ratio → top-tail growth and r–g; G06 → source exposure → imported
inflation → sector profit/price effect.

No speculative automatically generated statement is presented as an
observed fact. A proposed follow-up becomes a measured finding only
after source and analytical gates pass. No duplicated manual list in a
parallel UI or hidden non-versioned prompts.

**Done when:** every implemented child is fully integrated and
cross-linked, missing-data/withheld cases work, graph and lineage
are versioned, and keyboard/mobile/automated regression tests pass.

## 5. Prioritized engineering phases

### Phase 0 — accuracy/integrity of existing claims (P0)

- Preserve the deployed ZIP baseline and create a current diagnostic
  snapshot after deployment (the current ZIP is **0.2.2**, not the
  latest repository revision).
- Trace all 24,869 ICIO accounting failures to hashes/editions,
  annual matrices and G06/L04 consumers; classify used/unused and
  prevent accepted results from depending on failed source accounts
  without an explicit accepted original reconciliation.
- Address V03's two blocking valuation roles; otherwise keep the
  incomplete research result visibly withheld.
- Keep G03 deferred unless complete original listed-parent profits,
  issuer mapping, FX and filing timestamps exist; never substitute an
  index-earnings proxy for global consolidated profits.
- Check WID 2025 publication and why the exact world series still
  end in 2023; audit metadata and data quality, not only HTTP success.
- Bind the three hardcoded period statements to actual source metadata.
- Reconcile the 11 conditional research questions with remaining
  unaccepted roles; no conditional result silently promoted.

**Gate:** source-to-calculation lineage report, no unexplained reused
bad matrices, all open gates explicit, original-data and display
regression tests green, new debug ZIP demonstrates measured changes.

### Phase 1 — wage and distribution research (P1)

Implement and integrate the **entire L01/L02/L04/L08 scope** defined
above: median wage, deciles, minimum wage, comparisons, methodological
distinctions, validated originals, UI and acceptance tests.

**Gate:** no mixed denominators, no silently imputed medians, no
mean/median conflation, and demonstrable workers-at-P10/P50/P90
historical comparisons where evidence exists.

### Phase 2 — consumer vs asset/commodity inflation (P1)

Implement and integrate the **entire C06/asset-inflation scope**:
approved original source histories, relative/real/nominal asset
measurements, multi-frequency alignment, rolling/lagged statistics,
uncertainty, explanatory controls, frontend and tests.

**Gate:** zero synthetic observations, stationarity/lookahead checks,
all plotted correlations report exact n/period/source/units/FX,
and stress scenarios remain clearly distinct from empirical results.

### Phase 3 — Piketty research with automatic data updates (P1)

Implement and integrate all five Piketty findings, WID publisher
vintage/quality handling, WIR snapshot reconciliation, acceptance and
frontend. Reuse existing L07/L05/WID infrastructure.

**Gate:** every displayed statistic traces to source identity, unit,
population, period and vintage; r–g only when its economic definition
is supported; automatic publisher ingestion refreshes the displays
without any manual button.

### Phase 4 — question-driven research navigation (P2)

Implement and integrate a parent/child question graph for all 37
existing questions and the approved new questions; add per-question
method/quality/distribution cards and research uncertainty/lifecycle
states across existing views.

**Gate:** exact question/series traceability, typed scope and expected
next questions, no duplicated manual catalog, complete navigation
and browser tests.

### Phase 5 — remaining deferred/conditional originals (P2/P3)

Complete G01/G02/P01/P04/P05 evidence only with actual user/public
source data and original-method verification. G03 remains separately
deferred until its full original source universe is supportable; do
not fake completion. Resolve long-standing source historical
comparison issues and update all 37 current question quality cards.

**Gate:** zero unlabelled proxy claims; all accepted computations
have verified original evidence; deferred questions are explicitly
declared and limited where source rights, data or methodologies
prevent completion.

## 6. Required acceptance tests across every phase

- **Data:** original source receipts, publisher policy/spacing,
  content hash, revisions, observation-quality metadata, expected
  frequency, duplicate/undefined/missing dates and numeric bounds.
- **Economics:** factor-share accounting identity, denomination,
  stock/flow boundaries, percentiles, weighted aggregation,
  real/nominal deflation, purchasing power, country definitions,
  publication/capture vs observation dates.
- **Research:** methods reproduce source samples within justified
  error bounds; robustness and uncertainty; never promote stale,
  unverified or inconsistent originals as accepted.
- **Automation:** initial load, automatic post-commit ingestion,
  replay/restart, no new source, publisher defer, partial failure,
  changed series in mid-calculation, no manual re-import required.
- **Presentation:** current snapshot dates, all five Piketty modules,
  wage distributions, rolling/lag correlations, source/action links,
  question lineage, missing-value warnings, mobile accessibility.
- **Release:** CI Python+frontend+browser+release image green and
  a numbered deployment via `deploy.sh`. Inspect a fresh debug ZIP
  from the running build; passing test fixtures alone cannot
  certify installed publisher observations.

## Primary research sources

- World Inequality Report 2026: https://wid.world/document/world-inequality-report-2026/
- WIR 2026 methodology/data archive: https://wir2026.wid.world/methodology/
- WID data: https://wid.world/data/
- WID quality and provenance: https://wid.world/methodology/
- Piketty's clarification on r–g:
  https://www.aeaweb.org/articles?id=10.1257%2Fjep.29.1.67
- OECD earnings dispersion `DSD_EARNINGS@DEC_I`:
  https://data-explorer.oecd.org/vis?df%5Bid%5D=DSD_EARNINGS%40DEC_I
- OECD minimum/median `DSD_EARNINGS@MIN2AVE`:
  https://data-explorer.oecd.org/
- Eurostat Structure of Earnings Survey:
  https://ec.europa.eu/eurostat/cache/metadata/en/earn_ses_main_esms.htm
- US BLS median earnings:
  https://www.bls.gov/cps/earnings-faqs.htm
- BIS selected property prices:
  https://data.bis.org/topics/RPP
- OECD employment dataset: https://www.oecd.org/en/data/datasets/oecd-employment-database.html

## 7. Baseline acceptance table (37 questions)

| Status | Questions |
| --- | --- |
| Accepted (24) | C01, C03, C05, C06, M01, M02, F02, F03, F04, F05, F06, V01, V02, V05, L01, L02, L03, L05, L07, G05, G06, P03, P06, P07 |
| Conditional (11) | C02, M04, F01, F07, L04, G01, G02, P01, P02, P04, P05 |
| Incomplete (1) | V03 |
| Deferred (1) | G03 |

**Future status naming:** Distinguish `accepted_with_method_caveats`
from `accepted_without_known_evidence_gaps`, and keep
`conditional`, `incomplete`, and `deferred` as distinct research
states. This is an explanatory recommendation; do not rewrite
the existing acceptance state machine until the meaning and
compatibility of every consumer are verified.
