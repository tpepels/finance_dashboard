# Phase 1 visualization and interaction contract — approved intent, detailed design for review

**Status: ten product choices, revised six-story editorial flow and 35-question no-fee-source direction APPROVED on 2026-11-03; final detailed UI/science acceptance remains OPEN.** [Authoritative plan](DEVELOPMENT_PLAN.md). Design and scientific analysis remain intertwined; UI is derived from research questions and data comparison validity.

## Approved editorial reading flow (2026-11-03); detailed design acceptance remains open

The user **approved** the [critical scientific/UX review](PHASE1_COHERENCE_AND_FREE_DATA_REVIEW.md). Its required reading sequence is question → primary comparative measurement → supporting/contradicting evidence → methodology/alternatives → relevant portfolio implications. The six connected research experiences are binding, replacing six unrelated cards. No global country mode. All required datasets must be legally usable at no cost; unavailable originals are clearly labelled rather than substituted under the original name.

## Information architecture

**Primary navigation:** (1) **Overview** — 6–8 curated, editorially chosen multi-measure research analyses with evidence summaries; (2) **Research workbench** — searchable catalogue of the approved questions, save, duplicate and compare chart variants; (3) **Portfolio** — optional actual holdings/fund exposure analysis, stress and diversification; (4) **Research & data** — source/method registry and research transparency, expandable background sync/admin diagnostics. Domain chips/filters narrow *which analyses are listed*, never change their graphs silently.

No persistent, globally applied **country mode**. A country/region selection is owned by each chart spec. Global pinned annotations, if ever provided, require an explicit "apply to selection" action, never implicit changes.

## Analysis interaction contract

Every analysis comprises: meaningful **question title**; visual comparison with enough axes and source dates; **two-sentence observed-evidence summary** with date, measurement and honest qualification; independent, visible **Configure**, **Method**, **Sources** actions; visible clear dataset limitations; historical comparison event controls; optional view variants and saving. Analysis page/expanded panel includes alternative studies, formulas, weights/deflators/vintages, failure conditions, source quality and chart-specific data table.

### Per-graph configuration (first-class)

- independently select indicators/roles, one or multiple named countries/regions, currency, sample period, transformation, frequency (only when supportable), chart encoding, axes, legends, historic events, ranges, reference baseline, saved view identity;
- **default settings** follow publication/research question; user can restore defaults and duplicate a view without changing canonical definitions;
- limit mathematically invalid combinations: cannot directly mix GDP percentage, index units, percentage points and currency levels on one unlabelled shared axis; prefer aligned small multiples over unexplained dual axes;
- treat level, year-over-year change, contribution, index=100, rolling correlation, difference and ratio as named, reproducible transforms with matched observation/availability dates and documented formula;
- chart type selection includes **line**, **step-line where appropriate**, **bars/dots for cross-sectional snapshots**, **stacked bars/areas only for additive contributions**, **scatter for matched observations**, **heatmap for comparable two-dimensional panels**, **aligned small multiples**; disallow unsupported types with an explanation;
- maintain stable visual identity for units/concepts/countries *within* a comparison while using accessible colors, line patterns, readable axes, legends and annotations. Avoid repeating the same color to imply identical concepts in unrelated contexts;
- explicit data density, missingness and sparse last-point indicators. Never connect across unknown long periods, fabricate smooth curves or hide missing months;
- month/quarter/year tick labels and dynamic scaling must retain meaningful magnitude; user-selectable log scale only for strictly positive meaningful data, declared clearly.

## Time, event and COVID annotations

- **Official recession** per named jurisdiction/source; for US NBER February 2020 peak–April 2020 trough, shade **March and April**; other countries' official cycle dates require their own authorities. Recession overlays on world/Europe/Japan charts require explicit **US context** label; never imply a global NBER recession.
- **Shock episode** is a separately scoped and cited factual historical interval (COVID pandemic economic disruption, dot-com equity drawdown, financial-crisis conditions, inflation shock). Editor may choose predefined official or research-method intervals; show citations and event scope.
- **Recovery** must be data-defined (e.g. first regained pre-February-2020 real employment or output), labelled series-specific, not a stretched recession band.
- Per-graph independent overlay visibility and editable reference; no forced COVID two-month-looking story when the user selected the longer pandemic shock overlay.

## Visual/editorial hierarchy

- Landing screen explains **what matters, what changed and how strong the evidence is**, not "80 feeds/46 cards" or oversized alerts.
- Large readable comparative plots; whitespace, small meaningful legends, muted event gray, and real-data exemplars for the whole analysis. UI priority: research answer > comparison > caveat > metadata > developer logs.
- Admin/sync remains accessible but is not part of normal reading surface. Keep historical two-button operations as an implementation inventory, not yet an immutable future layout decision.
- Desktop-first, fully responsive and keyboard accessible; light/dark palettes designed from shared tokens, not automatic patches; axis contrast, accessible color differentiation and tested legibility.
- Scientific reading affordances: expand/collapse method without shifting entire page unexpectedly; source references, version/date available inline; selected series/toggles are reflected in the method/explanation and share/export representation.
- Avoid unvalidated traffic-light risk badges, fabricated confidence or news-like editorial claims. Evidence summary should identify contrary signals when supported.

## Scientific visualization basis

- Cleveland and McGill (1984) on quantitative graphical perception: [original paper](https://faculty.washington.edu/aragon/classes/hcde511/s12/readings/cleveland84.pdf). Prefer positions and comparable scales for quantitative differences; bar length encodes magnitude for categorical comparisons; continuous lines for time evolution.
- OECD/JRC (2008) composite methodology: [handbook](https://www.oecd.org/content/dam/oecd/en/publications/reports/2008/08/handbook-on-constructing-composite-indicators-methodology-and-user-guide_g1gh9301/9789264043466-en.pdf). Explicitly disclose weights, normalization, uncertain rankings; never hide arbitrary composite choices in colors.
- NBER original dating: https://www.nber.org/research/business-cycle-dating.
- ALFRED original release availability: https://fred.stlouisfed.org/docs/api/fred/realtime_period.html.

## Fully specified analytical interaction model

**The unit of navigation is a scientific question; the unit of interaction is an independently configurable figure.** The overview is a small editorial selection of questions, and the workbench exposes the entire approved catalogue of approximately 35 analyses. Region filters for the *library* narrow displayed search results only. They must never mutate already-visible charts.

### Default overview and research workbench

The approved overview contains **six connected research experiences**: (1) global growth/inflation/commodities (C03/C01/C06), (2) policy/discount-rate transmission (M01/M02/M04), (3) debt/property/funding fragility (F01/F03/F06/F07), (4) valuation/concentration (V01/V03/G01 where free sources exist), (5) labour/capital/inequality (L01/L02/L07/L04), and (6) portfolio resilience (P02/P01/P03/P04). Each contains an editorially chosen primary comparison with related smaller subfigures, not a single data-source tile. Each shows question, chart, short evidence paragraph, contrasting evidence when available, period/scope and inline **Configure / Method / Sources / More** actions. Unknown or unverified claims must not be replaced by decorative generated copy.

Research workbench allows:
1. Find a question by topic, economic theory, indicator, region, source or analytical use; compare alternative method records, not just source-series names.
2. Open, duplicate and configure an independent view of any approved analysis, while preserving the immutable curated reference definition.
3. Select one or multiple geographies *inside that figure only*. Add/remove series only when they pass the method's explicit variable roles and comparable sampling constraints.
4. Save and rename custom views with selected variables/geographies/transforms/periods/chart type/events; restore publication-based default independently of any other saved view.
5. Inspect original observed values, source availability dates, revision versions, assumptions, sensitivity and reproducible formula; export the exact view specification with accompanying data/source citation and limitations.
6. Coordinate viewports across *explicitly linked* charts for visual comparisons, without imposing a single global time range or country switch on unrelated research.

### Figure scientific contract (conceptual)

A saved figure definition includes stable question ID; view ID and default-method version; series identities and economic roles; named countries/regions and compatible comparison universe; exact original source and requested publication-vintage interpretation; transformation and unit dimensions; frequency and alignment; time window; chart encoding; per-axis semantics; missingness handling; event-overlay definitions and scope; visibility order and styling; chosen contrast/benchmark; source citation and method version; owner edits with a restore operation.

This describes the desired **behavior and scientific semantics**, not a proposed database schema or implementation architecture. Two figures must be independently changed, independently saved and independently reset; another chart's country selection never changes unless the owner explicitly commands a multi-chart update.

### Graph-type policy and explicit overrides

| Analytical task | Primary default | Allowed alternative | Invalid/misleading combination |
|---|---|---|---|
| Historical level or rate | **Line**; stepped only for piecewise-constant policy series | Dot timeline for sparse releases | Bars for each crowded daily/weekly observation without categorical purpose |
| Same-definition country comparisons | **Multi-line** (small set); aligned small multiples (many countries) | Heatmap of country×date equal-unit cells | Mixed country units on a shared unlabelled axis |
| Different but jointly informative units | **Aligned small multiples** with synchronized time | Matched dated scatter if asking about association | Unexplained dual-y axis or false additive stacked area |
| Explicit country/sector snapshot | **Dot or bar** with zero and comparability checks | Ranked table | Joined line connecting unrelated categories |
| Additive budget, portfolio or value-added components | **Stacked bars/areas** only if components really sum to the whole and sign handling is defined | Small multiples | Stacking nonadditive ratios, independently normalized series, or opposite economic scopes |
| Two-variable association | **Scatter**, with sample size and fitted model optional | Dated line panels | Trend-line regression portrayed as causal or significant without assumptions |
| Correlations, long country/sector matrix | **Heatmap** or rolling-comparison lines | Bubble only if dimensions and size meaning are justified | Color scale hiding zero/direction or unsupported statistical precision |
| Drawdown and recovery | **Underwater line** + indexed wealth | Event table | Incorrect “recession” band stretched to drawdown duration |

The figure editor must show **why a graph type is unavailable** for that question rather than silently producing an illogical bar chart. It should preserve defaults when switching compatible types, avoid implying interpolation across sparse historical periods and label normalization bases.

### Time and event semantics for every chart

- The time axis distinguishes monthly **observation reference periods**, actual public-release availability and the date a later revision entered the research record. Users may compare "what we know now" and "what was known then", explicitly.
- In the NBER convention the **February 2020 peak** is followed by **March–April 2020** contraction; show these two months only as US recession shading. Separate `COVID disruption` and `recovery of real output/employment` layers use their own explicitly sourced event start/end or a named pre-shock threshold. NBER dates must not be extended just to make the chart look better.
- Country-specific research may have different official recession dating institutions or no accepted official chronology; never paint US NBER as global recession.
- For a graph with yearly values, the period classification must be honest: do not invent monthly precision or treat a dated event overlay as creating observed monthly evidence.
- All annotations are optional and **per graph**; synchronized comparative charts may share annotations only by explicit owner link. Preserve official grey recession fill, distinct nonrecession shock color/pattern, and series-dependent recovery line.
- Multiple periods (2001 technology decline, 2007–09 financial crisis, 2020 pandemic) are separate historically grounded overlays; named events may overlap without implying economic causation.

### Method, results and uncertainty presentation

When opening **Method**, show: precise analytical question; reference(s) and identified studied population/horizon; what the source actually measures; original series IDs and URLs; current units/frequency, observation vs release vs latest revision; all arithmetic and statistical transforms; denominator and aggregation rules; comparison validity and missing data; competing explanations; historical forecasting skill *if independently tested*; and links to the reproducible values behind the active figure. The panel updates to reflect the **current chosen graph variant**, not only the curated default.

A figure's **Evidence summary** has four parts at appropriate depth: observed comparison and date → agreement/disagreement → published contextual interpretation → material uncertainty/alternative hypothesis. No made-up source data or unjustified numerical threshold. The chart is still legible when the methods panel is closed.

### Monitoring and privacy interaction

Monitoring defaults to quiet: observed, source-verifiable material changes and incomplete/late releases, with optional periodic research digest. A change is not an automatically calibrated "red risk" notification. The optional holdings workflow can use manually entered holdings or explicit private import with separate permissions; the overview never assumes personal access. Administrative source sync, logs and developer diagnostics stay subordinate to research reading.

### UI accessibility and full-coverage acceptance

- Responsive desktop and mobile composition; neither a compressed multi-column graph nor a hidden chart-type selector counts as mobile support. Tables have accessible narrow-screen alternative and horizontal-scroll affordance.
- Light/dark modes use one shared semantic typographic/color contract, with readable contrast and both line-color **and** line-pattern differentiation. Legends, labels, pointer targets and keyboard focus are inspected, not assumed.
- Scatter/heatmap/bar/line and small-multiple geometry tested on positive, negative, zero, missing and outlier values, mixed frequencies, very long dates and many geographical series.
- Navigation, chart editor, export, methodology, source inspection, saved-view restore and the independent-country property are covered in design walkthroughs before a code comparison is permitted.
- The ideal experience can explain empty/unavailable data without replacing research with API status or a spinner.

## Phase 1 acceptance examples (normative)

1. Workbench can *describe* a chart comparing Fed/ECB/BoJ rates without changing a separate labour-income comparison's country selections; saved settings preserve this independence.
2. Comparing credit gap with DSR selects two synchronized, separately labelled line panels, not an unexplained common scale.
3. The same research question can generate a by-country multi-line or a matched-period scatter only when statistics permit.
4. COVID NBER recession and separately defined pandemic output shock/recovery are independently selectable, labelled and sourced.
5. A ratio's method explanation tells the reader exact numerator, denominator, geography, units, original source, missingness and publication vintage.
6. A sparse yearly dataset never masquerades as continuously observed monthly data.
7. The overview never becomes an unordered collection of all available single-indicator plots.
8. Every original user-requested broad topic can be found as a substantive analysis or is explicitly excluded by an approved scope decision.

These examples are intended product behavior, not coded or tested capabilities. Avoid any new implementation gap analysis until owner approval of Phase 1.
