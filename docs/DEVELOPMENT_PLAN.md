# Development plan

The sole current roadmap, reviewed **2026-11-11**. Detailed tasks are in the [completion implementation plan](superpowers/plans/2026-11-11-project-completion.md) and [research/presentation plan](superpowers/plans/2026-11-11-research-presentation.md); current evidence is in [research release verification](RESEARCH_RELEASE_VERIFICATION.md). The [initial project review](PROJECT_REVIEW.md) records the starting state. Earlier milestones remain in git history and [the archived history](archive/DEVELOPMENT_PLAN_HISTORY_2026-11.md).

## Goal and deployment target

A private workbench that helps a **EUR-based long-term ETF investor** assess allocation, hedging, rebalancing and savings decisions. Each question compares evidence, identifies sources and limits, and avoids fabricated data or timing recommendations.

Run the same React/FastAPI/SQLite image locally and on an owner-managed **Linux server with Docker Compose, accessed by LAN IP and port** (owner confirmed 2026-11-11). Keep one API process, one scheduled refresh thread and one persistent `/data` directory per installation. Each installation owns its database; local/server writers must not share SQLite over a network filesystem.

Scientific scope remains governed by the [charter](PHASE1_SCIENTIFIC_CHARTER.md), [catalogue](PHASE1_ANALYSIS_CATALOGUE.md), [specifications](PHASE1_ANALYSIS_SPECIFICATIONS.md), [fallback matrix](PHASE1_FALLBACK_SOURCE_MATRIX.md), [visualization contract](PHASE1_VISUALIZATION_CONTRACT.md) and [source policy](SOURCE_POLICY.md). This plan does not change acceptance thresholds.

## Current state

| Area | State |
|---|---|
| Catalogue and engine | 398 mapped source definitions; 37 questions and 37 engine definitions |
| Research acceptance | Fresh release-code assessment: 24 accepted, 12 conditional, one deferred (G03); no incomplete analysis |
| P06 | Accepted after independently checking its latest page and archived rolled-off September observation |
| Analytical engine | Phase 3 implementation complete; empirical acceptance varies by installation and refresh |
| Interaction | Concise overview, all-question findings, focused workspace with expandable research detail, independent configurable/saved figures and preserved source/question deep links |
| Portfolio | Separate actual holdings snapshot with account/ISIN weights and recovery; model scenarios retain independent inputs and explicit replay limitations |
| Runtime | Same pinned image deployed locally and on media-server; fresh/non-root startup, recreation, verified restore and actual LAN access checked |
| Verification | Updated Python suite: 1,215 tests OK with 10 optional skips; frontend: 149 passing; TypeScript/Vite and expanded browser flows verified |

The live local and server containers use the same verified release image. Each has completed a fresh full-corpus assessment with the states above. A clean installation intentionally has no equivalent research history; each later collection can change acceptance.

## Completion order

| Priority | Deliverable | Completion gate |
|---|---|---|
| 1 | Establish empirical baseline and resolve P06 | Fresh report from release code; verified P06 evidence or an explicitly approved deferral/alternative |
| 2 | Reproducible runtime and complete recovery | Committed dependency locks, configurable startup flags, CI frontend/container checks; portfolio inputs and policy state survive restore |
| 3 | Validated figure-view API | Geography, dates and supported transforms validated by engine; plot, methods and export describe the same view |
| 4 | Independent editor and saved views | Configure, duplicate, rename, save, compare and reset one figure without mutating another; views survive recovery |
| 5 | Independent portfolio validation | Hand-calculated cost/tax/cash-flow examples and benchmark reconciliation; no invented history or unsupported predictive claim |
| 6 | Integrated usability and performance | Empty/populated browser tests, mobile/keyboard/light/dark review, robust loading/error states and reduced unnecessary chart loading |
| 7 | LAN-server release and recovery drill | Second device reaches server; corpus, owner inputs and views survive replacement/restore; previous image and recovery bundle retained |

Steps 3–4 finish configurable figures. Step 5 closes Phase 5 validation rather than rebuilding existing portfolio features. Owner review covers C02, C05, G01–G03, L04, P01, P04, P05, portfolio form, overview, workbench and editor. Explicit research limitations may remain; completion does not mean every source exists.

## Definition of complete

- Each question has a current evidenced end state; deferred methods are explained without presenting unaccepted original-method values.
- Required configuration, saved-view independence, methods and exact-view exports work together.
- Portfolio calculations pass independent examples and disclose coverage and assumptions.
- Automated checks pass; optional original-artifact/PostgreSQL omissions are recorded.
- Empty and populated installations run locally and on the Linux LAN server; service health and scientific readiness remain distinct.
- Data transfer, verified backups, restore, updates and image rollback are exercised; owner review is recorded.

## Working rules

- One canonical research CLI, one managed HTTP client, one acceptance engine; extend established paths.
- Preserve observations, originals, receipts, journals and backups. Take a verified recovery copy before migrations or acquisition.
- Investigate evidence gates; do not bypass acceptance to repair a blank chart.
- Run full offline tests before code commits and verify CI after pushing. Implementation commits are on `codex/project-completion`; no push was requested and no remote CI execution is claimed.
- Use [RUNNING.md](RUNNING.md) for operation; keep reviews distinct from the roadmap and scientific contracts.

## First implementation outcome — 2026-11-11

Priorities 1–7 are implemented and verified within the recorded operating limits. P06 is accepted after independently checking the rolled-off September original; both live corpora have 24 accepted, 12 conditional and one documented deferred question. Independent figures/saved variants, exact exports, complete defined application-state recovery, frozen builds, portfolio validation and integrated mobile/browser checks are implemented.

An independent review found and reproduced stale acceptance authorizing new revisions, sparse derived lines, incompatible FX axes and ineffective structured-result date bounds. Regression tests now cover those failures and the corrected behaviour. See [release verification](RELEASE_VERIFICATION.md).

The owner chose the verified local corpus for `media-server`, retaining the divergent previous server store intact. The first release used image `finance-dashboard:release-d0c7f37`; its image/data pair remains available for rollback. Its operating evidence is retained in the historical release verification.

## Research and presentation outcome — 2026-11-11

The follow-up request is implemented: concise findings for all 37 questions, expandable research detail, independent observation-age and collection states, repaired source collection and an actual portfolio snapshot separate from model scenarios. The owner confirmed combining the supplied accounts. Unknown dates, cash flows, complete portfolio scope and two unconfirmed share classes remain explicit. All conditional/deferred research boundaries are documented in [research completion](RESEARCH_COMPLETION.md); no acceptance threshold was relaxed.

Both hosts now run `finance-dashboard:release-84230be`, at **http://localhost:5052/** and **http://192.168.1.200:5052/**. The exact image, test evidence, new data directories, sealed recovery copy and rollback scripts are recorded in [current release verification](RESEARCH_RELEASE_VERIFICATION.md). The previous local data, previous server release and divergent original server corpus remain intact. Formal owner visual acceptance remains a user review of the delivered application. Only the finance service was recreated; unrelated services and the shared host were preserved.
