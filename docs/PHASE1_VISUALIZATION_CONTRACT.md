# Phase 1 visualization and interaction contract — proposed ideal state

**Status: DRAFT.** User intent and research approval pending. [Authoritative plan](DEVELOPMENT_PLAN.md). Design and scientific analysis remain intertwined; UI is derived from research questions and data comparison validity.

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
