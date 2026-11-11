# Research and Presentation Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for coordinator-owned tasks and superpowers:dispatching-parallel-agents for the independent source, presentation and G03 tasks. Verify the combined branch with a fresh reviewer before release.

**Goal:** Complete the research explanations, repair dependable source collection, and make all 37 questions usable in a concise local/LAN dashboard.

**Architecture:** Extend existing acceptance, source transport, bundle summaries and React panels. Preserve canonical computations, originals, source policy and single-container deployment.

**Tech stack:** Python 3.12, SQLAlchemy/FastAPI, React/TypeScript/ECharts, frozen uv/npm dependencies, Docker Compose.

**Spec:** [Research and presentation design](../specs/2026-11-11-research-presentation-design.md).

## Global constraints

- Never relax acceptance, fabricate observations or silently substitute a different economic concept.
- All acquisition uses the existing managed transport, immutable evidence and durable publisher budget.
- Existing local/server stores and previous image/data pairs remain recoverable; stage new evidence first.
- Use the existing isolated completion worktree; preserve the original workspace's prior changes and `.claude` directory.
- Keep existing API fields compatible, existing question hash links and exact-view exports.
- No new paid service, framework, public hosting, shared SQLite network writer or synthetic source history.

## Review focus

- A latest date from one country must not falsely date another country's finding.
- Empty, withheld, owner-example and bounded-alternative results must not appear fully verified.
- Cached publisher bytes must retain truthful receipts and permit later revisions; partial multi-file data must not be accepted.
- Direct links, browser back/forward and keyboard navigation must open the correct research question on narrow screens.
- A deferred refresh and current observations must remain distinguishable; last refresh is not a publication vintage.

### Task 1: Correct research interpretation and current scope

**Files:** `engine/analyses.py` G03 only, `frontend/src/GlobalPanel.tsx` G03 only, `definitions/limitations.json`, `definitions/phase2_research_corpus.json`, focused G03 tests and `docs/RESEARCH_COMPLETION.md`.

**Interfaces:** Preserve the G03 values/bundle structure and deferred-original gate. Correct names, formulas and disclosures consistently across bundle, chart and export.

- [ ] Reproduce the cap/P-E interpretation with an independent fixture; assert a proxy cannot be labelled realized consolidated listed-company profits.
- [ ] Use the official MSCI methodology to state normalization/free-float and denominator-coverage limits. Correct current conditional descriptions from real archived evidence; do not remove scientific limits just to improve counts.
- [ ] Document every conditional/deferred question's usable answer, verified source coverage and remaining boundary, with primary references.
- [ ] Run owning engine/API/frontend tests and record the evidence.

### Task 2: Repair source windows and common-original collection

**Files:** owning OECD adapter, `providers.py`, `source_capture.py`, relevant native acquisition/managed-client boundaries and source tests. No changes to publisher budgets or ingestion validation.

**Interfaces:** Keep `ProviderRouter.fetch(series_id, start)` and `IngestionService.refresh(...)` compatible. Each successful series retains a truthful immutable acquisition receipt.

- [ ] Run failing exact-date annual flow/stock tests and real temporary-ledger G17/FDIC sequential-fetch tests.
- [ ] Trim OECD rows to the exact requested date after year-rounded retrieval. Reuse identical immutable responses inside the batch with evidence capture intact; a fresh router can see revisions.
- [ ] Reproduce WID's CSV/metadata starvation and provide bounded completion/resumption through the canonical boundary, with no partial success or request-budget bypass.
- [ ] Verify missing/denied/unavailable sources retain their evidence and actionable failure states; run source/policy/architecture suites.

### Task 3: Deliver findings and research/source status

**Files:** `engine/summaries.py`, new `research_status.py`, `engine/runner.py`/`api.py` integration, `source_coverage.py`, summary/status/coverage/API tests.

**Interfaces:** Retain `summarize(analysis_id: str, values: dict | None) -> list[str]`. Add `research_status(snapshot, document) -> dict` exposed as `GET /api/research-status`: `evaluated_at`, `counts`, `questions`, with existing catalogue fields plus `phase2` limitations/open gates and role dispositions. Extend source rows with independent `observation_state`, `refresh_state`, `research_questions` and readable `next_action` while preserving existing fields.

- [ ] Add independent fixtures for each question family; verify own-date, units, empty/withheld handling and no probability/causality claims.
- [ ] Implement concise findings across the 37-question catalogue where computed values exist; correct existing summary date/concept errors. Deferred originals retain an explicit no-answer explanation plus named alternatives.
- [ ] Add snapshot-derived research status with current role dispositions and limitation text. Test loading/reassessment paths and unknown/missing roles without leaking raw errors or original bodies.
- [ ] Test and implement independent collection/freshness axes and engine-source question mapping, including current-but-deferred and stale-but-successful sources.
- [ ] Run full Python suite and catalogue validation.

### Task 4: Focus the presentation and make evidence readable

**Files:** `App.tsx`, `Overview.tsx`, `Workbench.tsx`, `analysisShell.tsx`, responsive/chart styles and owning frontend/browser tests; avoid G03-specific edits owned by task 1.

**Interfaces:** Consume existing bundles' `summary` and `/api/research-status`. Source details consume compatible extended coverage. All `#q-ID` links and topic anchors must still navigate correctly; saved figures remain independent.

- [ ] Add behavior tests for selected topic/question, back/forward/deep links, loading/retry, research-state filtering and preserved saved figures.
- [ ] Implement a concise overview and focused research workspace, accessible navigation, h1/main/skip link, loading states and short question findings with expandable evidence.
- [ ] Repair narrow graphic label cropping and numeric/table readability; preserve source dates, units, missingness and exact export. Respect reduced motion and ensure theme/data controls are reachable.
- [ ] Run all frontend tests/build, then real desktop/390px light/dark/keyboard navigation through all questions and saved-view/error flows. Inspect screenshots and console output.

### Task 5: Acquire, reassess and release the verified improvement

**Files:** operating/deployment records, `README.md`, roadmap, runbook and release verification. Separate staged data and release source/image, no original corpus overwrite.

- [ ] Restore the existing verified full recovery bundle into a new disk-backed working directory. Apply a bounded canonical acquisition/reconciliation plan using existing configured source access; preserve every original and journal actual failures/deferments.
- [ ] Compare source coverage and full research assessment before/after. Correct any regression before release, and report actual unresolved evidence instead of promised coverage.
- [ ] Complete independent code review, full Python/frontend/build/browser checks and isolated image/recovery verification after final changes.
- [ ] Adopt reviewed files into the original workspace; deploy the same pinned image to local and server services with retained previous image/data and verified recovery copy. Change only finance service configuration.
- [ ] Verify live LAN health, question findings, exact exports, saves and new navigation. Finalize operator documentation and measured research/source outcomes.

## Execution rulings

The owner explicitly asked to finish this work, continuing the established application and deployment scope; implementation proceeds without an additional design-approval stop. Presentation defaults to concise pending optional steering. Original-method G03 completion cannot be invented from cap/P-E or national corporate accounts; deliver a correct bounded answer and a visible evidence boundary. Missing personal inputs remain the owner's labelled example. No host reboot or hosted CI run is claimed.

## Owner holdings addendum

During execution the owner confirmed the concise presentation, supplied two lists of real positions and explicitly requested combining them. Add a typed, private `portfolio-holdings.json` store and `GET/PUT /api/portfolio-holdings`, with revisions, strict validation, exact-ISIN grouping, Decimal money totals, nullable dates/cash flows and separate account controls. Include this state in verified backup/restore and bind it to acceptance invalidation. Expose the computed snapshot in P01 and an editable/importable frontend table. Keep the existing model scenario store separate so importing actual holdings cannot mislabel an ACWI/sovereign/gold replay as the owner's actual returns.

Independent synthetic tests must cover invalid saves, corrupt-state preservation, concurrent stale writes, aggregation without guessing share classes, precious metals distinct from gold, API/model independence and full recovery. Actual positions are seeded only in private staged data after the owner's combination instruction; no private values enter source or image. An unknown valuation date, cash flows, unreported cash and unresolved share classes remain explicit. Root owns API/backup/P01/owner-supply integration; a dedicated store implementer owns the new typed module and tests; the presentation implementer owns the UI.
