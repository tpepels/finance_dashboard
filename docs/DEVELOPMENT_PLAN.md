# Development plan — authoritative, reset to research-first Phase 1

**Decision date:** 2026-11-03. **Branch:** `main`. **State:** DEVELOPMENT PAUSED FOR PRODUCT/SCIENTIFIC REDESIGN. **Only documentation/specification work is authorized until Phase 1 approval.** All ten owner product-intent decisions are explicitly approved (2026-11-03); the full scientific content, method and design contract remains unapproved.

## Binding decision

The original Phase 1 acceptance is **reopened**. Historical Phase 2/3/4 "done", status percentages, source-sync milestones, and 0–5 workstream ordering are **not acceptance or priorities under this plan**. They are archived, not erased. The prior exact roadmap is frozen at [archive/DEVELOPMENT_PLAN_PRE_RESET_2026-11-03.md](archive/DEVELOPMENT_PLAN_PRE_RESET_2026-11-03.md). Existing code, data, release snapshots, config, backups, historical studies and tested integrations must remain intact during the pause. No implementation, data migration, cleanup or deletion is authorized by this reset. Historical data collection success remains valid evidence only, not an acceptance gate for the new research product.

**This file is the only authoritative lifecycle and phase plan.** The following are **supporting Phase 1 specification drafts, not parallel implementation roadmaps**:
- [PHASE1_SCIENTIFIC_CHARTER.md](PHASE1_SCIENTIFIC_CHARTER.md) — mission, evidence standards, methodology requirements, intended user decisions.
- [PHASE1_ANALYSIS_CATALOGUE.md](PHASE1_ANALYSIS_CATALOGUE.md) — curated 35 comparative questions and six editorial overview defaults.
- [PHASE1_ANALYSIS_SPECIFICATIONS.md](PHASE1_ANALYSIS_SPECIFICATIONS.md) — scientific specification for all 35: published variables, research sources, calculations, alternatives, comparable populations and inference limits.
- [PHASE1_VISUALIZATION_CONTRACT.md](PHASE1_VISUALIZATION_CONTRACT.md) — information architecture, independent per-graph configuration, chart grammar, annotation model and research workflow.
- [PHASE1_COHERENCE_AND_FREE_DATA_REVIEW.md](PHASE1_COHERENCE_AND_FREE_DATA_REVIEW.md) — complete critical scientific/product review of all 35 and source availability, with proposed six-story overview and four no-fee dataset discovery questions. **Review only; not an approved replacement scope.**

The earlier source and economic method files remain **inventory/technical references to the existing system**, not an approved specification of what the new application must look like or contain. Any original requirement or data source is considered for the new scope by its scientific question, not by its presence in the former code.

## Required product outcome (ideal-state first)

A locally hosted **research-driven macro-financial and political-economy workbench with long-term portfolio context**, structured around clear economic questions, **multi-indicator comparisons**, published research methods, original-source provenance and interpretive uncertainty. A restrained curated overview links to reusable, independently configurable analyses. "Country" is a **per-chart** series dimension; changing one graph never silently switches others or the whole dashboard. Each graph's indicators, geographic scope, comparative baselines, timeframe, transforms, visualization, event overlays, and saved view are independently editable. No fixed chart-per-indicator gallery. Chart types follow perceptual and statistical purpose, not arbitrary preference. Every analysis exposes scientific question, original reference, formal definition, source provenance, assumptions and limits. Prior economic crises remain correctly attributed and dated; COVID NBER recession and broader pandemic shock/recovery are distinct selectable annotations.

## Deliberately deferred until Phase 1 approved

Do **not** create a gap analysis, implementation backlog, detailed phase status or source repair plan against the new scope before the user has reviewed the **100%-ideal specification**. Do **not** resume frontend/backend coding, add indicators only because an API exists, produce design mockups that silently lock in content, or claim existing production functionality satisfies the newly revised product.

## New phases — independent responsibilities, complete acceptance

### Phase 1 — Scientific charter, complete content and product design **(OPEN, ACTIVE)**

**Research content first, UI derived from that content.** Define (a) target economic/portfolio questions and distinctions, (b) literature review with primary research and recognized methodologies, (c) fully enumerated analytical comparisons and chart defaults, (d) metadata/evidence/interpretation contracts, (e) independent per-chart controls and saved research views, (f) complete information architecture, accessibility and screen hierarchy, (g) negative requirements, editorial relevance and methodological review rubric.

**Required deliverables:** approved [scientific charter](PHASE1_SCIENTIFIC_CHARTER.md), approved [analysis catalogue](PHASE1_ANALYSIS_CATALOGUE.md), approved [visualization contract](PHASE1_VISUALIZATION_CONTRACT.md), a source-backed research reference register and the ten **approved** user scope decisions incorporated into these artifacts. No arbitrary indicator counts or source-driven UI.

**Acceptance gate:** user approves the entire intended 100%-ideal product and evidence framework, including representative comparative analysis definitions, research references, global-versus-national scope, per-graph authoring semantics, interpretive boundaries, default overview composition and explicit exclusions. Each catalogue analysis has primary question, expected paired/multiple measures, scientific motivation, default plot, comparison-validity test and interpretive limitation. No gap analysis in Phase 1.

### Phase 2 — Reproducible data sources, provenance and research corpus **(NOT STARTED UNDER NEW CONTRACT)**

Implement scientifically exact source definitions, viable worldwide/regional coverage, quality validation, original observations and release vintages, legal usage rights, licensed/primary data identification, import and provenance, revisions/gaps, reconciliations, controlled source operation and durable recovery. Confirm both data fidelity and the resulting comparative research universe (including blocked estimates). **Acceptance:** reproducible end-to-end data corpus for all approved required analyses, with transparent unavailable/conditional data and no fabricated value.

### Phase 3 — Comparative analytical and methodological engine **(NOT STARTED UNDER NEW CONTRACT)**

Implement unit-consistent alignment, transform algebra, temporal/vintage constraints, research alternatives, independent horizon-specific backtesting where approved, equation and uncertainty contracts, comparative graph definitions, provenance-aware narrative evidence and reproducible exports. **Acceptance:** every approved analytical question is answered by correctly implemented and validated multi-series methods; no ungrounded "risk score" or leakage.

### Phase 4 — Unified interaction, visualization and editorial product **(NOT STARTED UNDER NEW CONTRACT)**

Build the entire agreed overview, research workbench, independent graphs/country scopes, validated per-graph chart types, saved and resettable view definitions, research-method panels, sources, portfolio navigation, admin/ops separation, graceful missingness, historical annotation model, keyboard/accessibility and visual polish on responsive light/dark screens. **Acceptance:** complete designed workflows and visual review of real data across states/devices; no global country mode or mismatched chart semantics.

### Phase 5 — Portfolio applications, empirical validation and scientific acceptance **(NOT STARTED UNDER NEW CONTRACT)**

Implement full approved portfolio exposure/scenario research (FX/costs/tax constraints where applicable), empirically validate estimates and any forecasts using primary historical as-of inputs, horizons, temporal/event holdouts, uncertainty, transparent benchmarks and replication, and run expert/owner usability acceptance. **Acceptance:** reproducible scientific, analytical and UX end-to-end evidence for the approved product; no pretend crash probability.

Phases define **outcomes**, not token commits. Each future phase includes full tests, integration, source proof and documentation. A phase may be labelled complete only after its entire approved scope is finished, not a representative subset. Work on `main`, no legacy compatibility paths, and no GitHub Actions unless separately approved.

## Phase 1 decision protocol

The assistant owns technical and scientific proposals, evidence review and rigorous defaults; the user decides only **product intent, audience and presentation tradeoffs**. **Completed on 2026-11-03:** all ten user decisions adopted as recommended, without overrides; see [charter](PHASE1_SCIENTIFIC_CHARTER.md). Next, the assistant completes exact literature-grounded methods and 35 candidate analyses, refines the scientific UI contract, and presents the **entire ideal-state specification for explicit acceptance**. Do not conduct implementation gap analysis or change application code before that full Phase 1 approval. Only after approval compare current implementation and data against that target.

## Evidence and methodological standards

- Each required research analysis is question-led; default is a justified **comparison**, not a series tile.
- Literature distinguishes correlation, mechanism, association, early-warning indicators and validated prediction.
- Published series, reproducible transforms, model-based estimates and proxies remain different types of evidence.
- Different geographies, price deflators, economic sectors, source vintages, index universes and percentages cannot be silently mixed.
- No filled/interpolated "global" aggregates unless a transparent published aggregate method specifically justifies them.
- Recession chronology is a sourced classification; shocks and recovery intervals have separate definitions and toggles.
- Each analysis retains units, frequency, measurement window, publication/availability date, revision vintage, source identity, licensing and comparison warnings.
- Peer-reviewed methodology is preferred for scientific interpretation; official statistical documentation is authoritative for definitions; conflicting research must be disclosed. An official indicator is not proof of predictive effectiveness.
- No overarching numeric risk index without predeclared valid construction, sensitivity and independent evaluation.

## Historical evidence (preserved, not active acceptance)

The November 3 18:14 UTC diagnostics reported **80/80 sources with saved observations, 0 active issues, completed current/history sync, 0 missing requested ALFRED vintages within 580 prepublication exclusions, and VT/BND 28/29 verified matching SEC filings**. This demonstrates historic ingestion operations, not product/methodological success. Prior original phase progress, source obstacles, provider repairs, URLs, tested scripts and caveats are preserved in the archived roadmap and current data/source reference documents.

## Approved decisions — Phase 1 research continuation, 2026-11-03

All ten product defaults were accepted: global comparative macro-financial research for long-term ETF decisions; informed reader with scholarly methods; medium/structural horizons; US/Europe/Japan and other comparable geographies; first-class political economy; about six overview analyses and 35 research-library analyses; independent per-graph custom views; concise evidence/uncertainty; optional holdings and non-prescriptive stress analysis; quiet monitoring. The scientific charter now documents original-source methods for BIS national credit gaps and DSRs, OECD productivity/pay matching, BEA Q variants, Marxian industry-accounting research, portfolio diversification and NBER/COVID dates.

**Status distinction:** owner **product intent accepted**; Phase 1 **scientific specification open**; no approval of existing content, code or data. The catalogue and visualization contract are normative research/design documents, not observed implementation. No production code, ingestion change, data edit or migration in this phase.

## Phase 1 visualization-specification continuation (2026-11-03)

The [visualization contract](PHASE1_VISUALIZATION_CONTRACT.md) now specifies the full research navigation, six default comparative analyses, **per-figure** geography/indicator/type/method/event/view state, strict chart-type compatibility, historical event/recession distinction, versioned methodology panel, accessible figure grammar, quiet monitoring and 8 normatively testable walkthrough examples. These are **ideal-state design obligations, not already implemented functionality**. The owner has approved the product intentions; the complete visualization acceptance review remains part of the open Phase 1 gate.

## Expert-led Phase 1 analysis specifications — 2026-11-03

The scientific [PHASE1_ANALYSIS_SPECIFICATIONS.md](PHASE1_ANALYSIS_SPECIFICATIONS.md) now contains **35/35 individual question contracts** and **42 original scholarly/statistical source links**. Each has original/source-defined variables, methodological basis, reproducible calculation, meaningful alternatives, comparison-validity constraints, interpretation boundary and default graph. The six editorial analyses are included. Source IDs are verified when available; proposed worldwide measurements without a single public publisher series retain explicit intended universes and may not be silently replaced by narrower data.

This completes the requested **first-pass analysis-specification writing task**, but it does **not** close Phase 1, establish actual source licensing or validate research models. The complete ideal scientific UI/content specification still requires final expert review and explicit owner approval. Application code, sync systems and implementation-gap analysis remain paused.

## Critical product/scientific review (2026-11-03)

Completed the ideal-product coherence review in [PHASE1_COHERENCE_AND_FREE_DATA_REVIEW.md](PHASE1_COHERENCE_AND_FREE_DATA_REVIEW.md). The user requires **only free/no-fee data**; publicly visible MSCI and issuer factsheets cannot be treated as free historical original file feeds without rights and history proof. All 35 existing questions are critiqued, a six-story **research-flow** overview is proposed, five redundant headline topics can become submethods, five undercovered scientific topics are proposed (inflation/commodities, property, nonbank/funding risk, world inequality, global supply chain), and four narrow original-source search problems remain. **This is an expert recommendation, not a feature-gap analysis or a change to the ten approved product decisions.** The original catalogue/specifications and current implementation are preserved. Scientific Phase 1 acceptance remains open.
