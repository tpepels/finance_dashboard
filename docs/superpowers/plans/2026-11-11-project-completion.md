# Project Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the research workbench and release the same recoverable application for local use and a Linux Docker Compose server on the owner's LAN.

**Architecture:** Retain one FastAPI process serving built React/ECharts assets, a local SQLite database and original archives under `/data`. Extend the existing engine with validated figure specifications, then persist independent saved views on that installation. Preserve evidence gates and use the same runtime on both machines.

**Tech Stack:** Python 3.12, FastAPI/Pydantic, SQLAlchemy/Alembic/SQLite, React/TypeScript/ECharts, Node 24, Docker Compose, unittest, Vitest and Playwright.

**Spec:** [Development plan](../../DEVELOPMENT_PLAN.md), [visualization contract](../../PHASE1_VISUALIZATION_CONTRACT.md), [scientific charter](../../PHASE1_SCIENTIFIC_CHARTER.md). Baseline: [2026-11-11 project review](../../PROJECT_REVIEW.md). This is a proposed implementation breakdown of those requirements, not approval of a new UI design or a changed scientific method.

## Global Constraints

- Owner-confirmed target: Linux server + Docker Compose, LAN IP and port. Use the repository's single runtime service; keep native execution for development.
- Use Python 3.12 and Node 24 for the release checks; the Python package currently declares `>=3.11`.
- Preserve all observations, revisions, originals, receipts, journals and backups. No new synthetic observations, silent fills, unlabelled alternatives or bypassed acceptance gates.
- Keep `/api` requests relative to the page origin. Provider credentials remain backend-only.
- Figure selections belong to one figure. Library filters never mutate chart settings; canonical method definitions remain immutable.
- Only valid native/aligned comparisons and named engine transforms may produce plotted/exported values; unsupported choices return a reason.
- Predictive claims require real-time evidence and independent evaluation. Descriptive historical replay must disclose revisions, assumptions and sample limits.
- Separate installations own separate data directories. Never share a live SQLite database over SMB/NFS.
- Existing untracked `.claude/`, `uv.lock` and `frontend/package-lock.json` belong to the user; review lockfiles deliberately before adoption.

## Review Focus

1. Missing/revised source evidence after a refresh: withhold affected results and explain the gate; never retain a misleading accepted plot (tasks 1 and 3).
2. Empty, unwritable or moved data directories: either start with honest empty states or fail with an actionable setup error, preserving existing files (tasks 2 and 7).
3. Two browser tabs/devices editing different or identical saved views: preserve independence and reject stale overwrites (task 4).
4. Sparse/zero/negative data and unsupported units/frequencies: preserve gaps, refuse invalid log/stack/normalization options, keep export identical to the view (task 3).
5. Interrupted update/restore and loss of non-database owner state: restore a matching image/data snapshot, including portfolio inputs, policy state and saved figures (tasks 2, 4 and 7).

---

## Delivery and file boundaries

| Slice | Principal files | Result |
|---|---|---|
| Empirical readiness | `research_operating.py`, `research_acceptance.py`, `engine/acceptance.py`, existing source-specific reconciliation modules | Current corpus baseline and resolved P06 decision |
| Runtime/recovery | `Dockerfile`, `docker-compose.yml`, `.env.example`, `backup.py`, `.github/workflows/python-static.yml` | Reproducible builds, controlled startup and complete recovery |
| Figure semantics | New `engine/views.py`; existing `engine/runner.py`, `bundle.py`, `transforms.py`, `export.py`, `api.py` | Validated active view, shared by plot/method/export |
| Figure interaction/storage | New `saved_views.py`, `frontend/src/figureViews.ts`, `FigureEditor.tsx`, `SavedViews.tsx`; existing analysis shell, panels and workbench | Independent editable figures and persistent saved variants |
| Portfolio assurance | Existing `engine/analyses.py`, `owner_inputs.py`, related fixtures/tests | Independently checked calculations and limitations |
| Release verification | Browser checks under `tests/browser/`; CI and operational documentation | Verified usable local/server release |

Do not split the large `engine/analyses.py` merely for tidiness. Extract a focused component only where an actual task changes its responsibility. These slices share interfaces; implement sequentially. Native execution is a reasonable default for a later implementation session.

### Task 1: Establish the current empirical baseline and investigate P06

**Files:** inspect `src/finance_dashboard/research_operating.py`, `research_acceptance.py`, `source_reconciliation.py`, `engine/acceptance.py`, `definitions/phase2_research_corpus.json`; update `docs/DEVELOPMENT_PLAN.md` and a private run report. Modify a provider/definition only after identifying the failed gate.

**Interfaces:** consume existing `research operating` and `/api/analysis` reports; produce an image/revision-stamped per-analysis state report and a named resolution for P06's `global_earnings_yield` role. Do not add another acceptance engine.

- [ ] Record the release revision, image ID and selected data/evidence paths. Preserve a verified recovery copy before any mutation.
- [ ] Run release-code `research operating` **without `--acquire`**, explicitly selecting the existing database, evidence, vintage and holdings paths. Store output outside original evidence. Example inside the container: `python -m finance_dashboard research operating --output /data/review-2026-11-11.json --details`. Choose a new filename for each assessment; inspect exit status and gates rather than assuming success.
- [ ] Compare this fresh report with the running-image baseline: 23 accepted, 12 conditional, G03 deferred and P06 incomplete. Identify P06's source binding, actual original hash, native dimensions, stored periods and exact verification failure.
- [ ] If the failure is a software regression, add a fixture-based regression test in the owning source/reconciliation test module; run it to prove failure before fixing only that cause. If evidence is genuinely absent, obtain it through existing bounded acquisition with backup/publisher policy, or record an owner-approved deferral/alternative. Never change a threshold just to make P06 pass.
- [ ] Verify that P06 either has accepted/conditional verified values with all limitations, or remains visibly withheld under the explicit approved scope decision. Re-run the relevant source and `test_engine_acceptance.py`/`test_engine_api.py` tests, then update the roadmap from the fresh report.

**Gate:** The release's real corpus state is known; no unresolved role is silently counted as complete. Historical Phase 2 closure remains identified as historical.

### Task 2: Make builds, startup and recovery reproducible

**Files:** modify `Dockerfile`, `docker-compose.yml`, `.env.example`, `docs/home-server-finance-service.yml`, `.dockerignore`, `src/finance_dashboard/backup.py`, `.github/workflows/python-static.yml`, `docs/RUNNING.md`; review/adopt `uv.lock` and `frontend/package-lock.json`. Extend `tests/test_backup.py`, `test_standalone.py`, `test_source_policy.py` and `test_cli_consolidation.py` as appropriate.

**Interfaces:** retain service `finance-dashboard`, container port 8080, default host port 5052, `/data` mount and one worker. Keep `backup_local(...) -> dict` and `verify_manifest(Path) -> dict` compatible with historical manifests; add versioned optional application-state metadata rather than invalidating old bundles.

- [ ] Add recovery tests proving that saved owner inputs and durable publisher cooldown/budget state survive restoring a backup to a different directory. Test a ledger with committed WAL changes; a raw copy of its live main file is insufficient. Reject tampered owner-state components and continue verifying existing-format manifests.
- [ ] Implement versioned backup coverage for `FINANCE_OWNER_INPUTS` and the source-policy SQLite ledger using consistent SQLite backup semantics. Record hashes and archive membership; do not archive secrets. Preserve old bundle verification. Route backup/verification through the canonical CLI and update runbook commands together, rather than adding a parallel CLI.
- [ ] Review the existing lockfiles, reconcile them with package metadata, and commit the selected locks. Build the frontend with `npm ci`; install Python from the reviewed frozen lock without silently resolving new versions. Include needed lockfiles in Docker copy/cache stages.
- [ ] Parameterize auto-refresh, Wisesheets refresh and refresh interval in Compose, preserving defaults `1`, `1` and `86400`. Default SEC collection to `0` consistently with `.env.example` until fund identity/contact is configured. Align the existing-stack snippet with source-policy/BEA settings from standalone Compose.
- [ ] Test a new, writable bind directory under a non-1000 UID/GID, an existing populated directory, and an unwritable directory. A startup failure must not erase existing state. Verify that `FINANCE_AUTO_REFRESH=0` prevents publisher work and document that automatic backups share that thread.
- [ ] Add frontend test/build plus isolated image-startup checks to CI. Run Python tests independently of the build. Update stale `.dockerignore` comments that claim Docker runs the full Python suite.
- [ ] Run full Python tests, locked frontend tests/build, `docker compose config --quiet`, a fresh image build and isolated startup/recreation/backup verification. Use separate storage/ports/name; do not restart the research installation for testing.

**Gate:** A clean checkout builds from fixed dependencies, offline smoke startup is selectable through `.env`, and a verified recovery bundle includes all existing application state. CI checks the release path.

### Task 3: Add validated figure specifications to the engine and exports

**Files:** create `src/finance_dashboard/engine/views.py` and `tests/test_engine_views.py`; modify `engine/runner.py`, `bundle.py`, `transforms.py`, `export.py`, relevant definitions in `analyses.py`, `api.py`, `tests/test_engine_api.py` and `tests/test_engine_transforms.py`.

**Interfaces (proposed):**

- `FigureView`: versioned validated schema with `figure_id`, selected `roles`, `geographies`, `start`, `end`, `currency`, `transform`, `frequency`, `encoding`, `scale`, `events` and optional `benchmark`. Each field has explicit per-figure capabilities/defaults; omission restores the default, never a global preference.
- `figure_capabilities(analysis_id: str) -> dict`: stable figure IDs, defaults, permitted choices and reasons for unavailable choices, exposed at `GET /api/analysis/{id}/views/capabilities`.
- `validate_view(analysis_id: str, raw: dict) -> FigureView`: refuse unknown figure/roles/geographies, incompatible units/frequencies, invalid ranges and invalid encodings. Keep canonical analysis IDs unchanged.
- Existing JSON/export routes accept the same optional URL-encoded JSON `view` query parameter alongside `today`. No view parameter preserves today's defaults. Store the normalized specification in bundle `view`; apply data transformations only in Python.

- [ ] Test: unknown geography or `start > end` returns 422; logarithmic scale with nonpositive data is refused; nonadditive ratios cannot be stacked; sparse months remain absent; a valid C01 Germany-only figure does not change a separately requested C03 result. Every rejection contains a readable reason.
- [ ] Test that JSON and text export given the same view carry identical geography, period, transform parameters, values and limitations. Tests must include a source whose acceptance becomes incomplete after a revision: no values may escape through view configuration or export.
- [ ] Implement the schema and capabilities registry using existing method definitions. First support C01 as a vertical slice, then cover every figure in the visualization contract. Preserve native frequency when valid downsampling is unavailable; do not fabricate support for arbitrary currencies or transforms.
- [ ] Implement engine filtering/alignment/normalization and connect both routes to one normalized view path. Keep lookback needed for growth calculations outside the visible start date, but export its dependency/provenance. Keep missingness and uncertainty disclosures.
- [ ] Test event semantics: March–April 2020 US NBER contraction, distinct COVID shock/recovery layers, explicit US context on non-US figures, independent visibility per figure. Legends and axis semantics remain display metadata; derived values stay server-computed.
- [ ] Run the new view/API tests and existing engine tests, then the full offline suite. Record supported/unsupported capabilities so the editor can explain them without duplicating scientific rules.

**Gate:** Each figure has an explicit valid specification; its chart, methods and export can consume the same computed view without changing other figures.

### Task 4: Build the independent editor and persistent saved figures

**Files:** create `src/finance_dashboard/saved_views.py`, `tests/test_saved_views.py`, `frontend/src/figureViews.ts`, `FigureEditor.tsx`, `FigureEditor.test.tsx`, `SavedViews.tsx`, `SavedViews.test.tsx`; modify `api.py`, `backup.py`, `frontend/src/analysisShell.tsx`, `TimePanel.tsx`, `Workbench.tsx`, the eight existing analysis panels, associated tests and styles.

**Interfaces (proposed):**

- Persist versioned records at `FINANCE_SAVED_VIEWS` (default `/data/saved-views.json`) with `id`, `name`, `analysis_id`, `figure_id`, validated `spec`, `method_version` and integer `revision`.
- `GET /api/saved-views` lists records; `POST` creates; `PUT /api/saved-views/{id}` requires the expected revision; stale updates return 409. An unreadable/corrupt store returns an actionable error and is not overwritten with an empty file.
- Frontend `FigureEditor` consumes server capabilities and emits only the edited figure's specification. Saved variants receive unique view IDs; canonical defaults are not writable.

- [ ] Add store/API tests: atomic save/reload, invalid specs refused, corrupt file preserved, stale writes rejected, two independently edited views retained. Add backup restore coverage for saved figures before shipping persistence.
- [ ] Add UI tests: configure a rates figure while a labour figure retains its selections; duplicate a view, rename it and reset the duplicate without changing the original; workbench region filters leave both untouched. Reload restores each record independently.
- [ ] Present a concrete editor layout based on existing styles for owner review before implementing its new visual interaction. Include keyboard/narrow-screen examples, disabled-option explanations, save/duplicate/reset and explicit chart-link controls.
- [ ] Implement the focused store/API and editor using task 3's capabilities/validation. Shared currency/time preferences must never silently mutate unrelated figures. Saved state belongs to the server installation, so another browser on that server can load it.
- [ ] Wire methods, sources, data table and export to the selected view. Add compare mode for independent saved variants; only synchronize viewport/events after an explicit link action. Flag outdated `method_version` records and revalidate before use.
- [ ] Run saved-store/API and frontend tests, then a browser flow that saves two different figures, reloads and opens a second tab. Verify both figures and exports; include save failure and 409 conflict recovery.

**Gate:** Configure/save/duplicate/compare/reset works per figure, survives browser/container replacement and backup restore, and never alters canonical defaults or another view implicitly.

### Task 5: Independently validate portfolio calculations

**Files:** extend `tests/test_engine_owner.py`, `test_engine_portfolio.py`, `test_owner_inputs.py`, `test_engine_p06.py`, `test_engine_p07.py`, `test_return_source_reconciliation.py`; modify owning functions in `engine/analyses.py` and `owner_inputs.py` only if evidence identifies a defect. Record validation in a new `docs/PORTFOLIO_VALIDATION.md`.

**Interfaces:** retain existing owner-input schema and `/api/owner-inputs`; P04/P05/P06/P07 produce their existing bundles plus required disclosures. Do not add a new simulation engine or silently use the example as saved owner evidence.

- [ ] Establish independent hand-calculated examples: 60/40 assets with +10%/−10% returns produce 102 from 100 before costs/cash flows; a 20% equity-only fall contributes −12 percentage points at 60% weight; duration 7 and a +1 pp yield shock give first-order −7% bond value, explicitly excluding convexity.
- [ ] Add cost-basis/tax/cash-flow examples with a documented transaction order, calendar/threshold/never rebalancing, zero costs, nonzero costs, withdrawals exhausting capital and missing months. Expected values come from separate arithmetic, not calls to production helpers. Reject NaN/infinity and malformed owner fields without replacing saved data.
- [ ] Reconcile replay returns and FX with selected verified source histories/benchmark alternatives. Disclose par-bond reconstruction, hedge approximations, sampled years, fee/tax treatment and gaps. Historical hindsight must not be described as predictive validation.
- [ ] For any predictive interpretation, evaluate genuine as-known-then inputs, independent/nonoverlapping samples and uncertainty, or retain the descriptive framing. No synthetic extension of histories.
- [ ] Run focused portfolio/reconciliation tests and full offline tests. Review P04/P05/P06/P07 graphics, inputs, limitations and exact-view exports with the owner; record remaining limits explicitly.

**Gate:** Portfolio calculations have independent numerical evidence and understandable limits; no unverified advice, timing signal or unsupported simulated precision is introduced.

### Task 6: Verify integrated behaviour, accessibility and performance

**Files:** extend frontend integration tests and relevant components; add reproducible browser checks under `tests/browser/` and a documented invocation in `docs/RUNNING.md`; update CI. Use a small deterministic seeded corpus in isolated storage, not the research database.

**Interfaces:** browser checks consume existing APIs and saved-view interfaces. Preserve `/api` same-origin access, acceptance `Retry-After` behaviour and visible missingness.

- [ ] Add end-to-end flows for empty install, populated overview/workbench, all panels, figure editor/compare, portfolio save, source/method disclosures and exact-view export. Simulate acceptance loading, failed evaluation and lost connection; verify usable explanations and recovery without reload loops.
- [ ] Verify desktop and 390 px mobile widths, keyboard-only navigation, visible focus, chart data-table alternative, long legends, light/dark contrast and positive/negative/zero/missing/outlier plots. Inspect screenshots; a passing DOM test alone does not establish legibility.
- [ ] Measure initial bundle size, duplicate bundle requests and engine latency with a populated corpus. Reuse identical in-flight read requests and lazy-load offscreen panels where this reduces work without stale results; preserve invalidation after owner saves/source updates. Record before/after results rather than just raising the chunk-warning threshold.
- [ ] Add a favicon or remove its request; confirm no unexpected console errors. Acceptance 503 loading responses remain explicitly distinguished from runtime exceptions.
- [ ] Run complete Python/frontend/build/browser checks once after the final changes; record all optional skips. Obtain owner acceptance of the remaining named graphics and editor.

**Gate:** The integrated product is usable on both screen sizes with expected failure states and a documented performance baseline.

### Task 7: Release on the LAN server and rehearse recovery

**Files:** finalize `docs/RUNNING.md`, `HOME_SERVER_DOCKER.md`, `SERVER_SOURCE_SETUP.md`, `ARCHITECTURE.md`, `README.md` and the roadmap. At plan creation the target was unspecified; the owner subsequently supplied `media-server` and selected the verified local corpus with the previous server data preserved.

**Interfaces:** same release image/revision and schema on both hosts; local storage paths/UID/GID/keys differ through server configuration only. Retain previous image plus its verified matching data snapshot.

- [ ] Run an isolated clean-checkout build on Linux with the reviewed locks; verify no secrets/private archives enter the image context. Start with a fresh directory and with a restored populated copy under the destination UID/GID.
- [ ] Perform the runbook's stopped-tree transfer or the now-complete verified recovery-bundle procedure. Compare file hashes, database integrity/schema, source counts, originals/receipts, acceptance states, owner settings, policy cooldowns and saved figures before enabling collection.
- [ ] On the server, verify localhost health; then use a **second LAN device** to load the UI, health, a populated analysis, a saved figure and an export. Inspect only non-secret configuration; leave the app inside the trusted network.
- [ ] Recreate the container and reboot the server; confirm restart policy and persisted state. Exercise one controlled update and restore drill in an isolated copy, including schema/image mismatch handling and an interrupted transfer. Do not test destructive recovery against the sole research copy.
- [ ] Take a complete verified recovery bundle off the server's physical disk. Record exact release revision/image, environment requirements, tested recovery steps, optional verification omissions and owner acceptance. Update current roadmap status only from that evidence.

**Gate:** Local and actual remote use both work, the complete state is independently recoverable, and all definition-of-complete items are satisfied or explicitly approved as deferred research scope.

## Plan self-review

At the planning checkpoint, the tasks covered the roadmap's seven priorities and the visualization contract's independent views, supported encodings, event semantics, methods/sources/tables and exact exports. Runtime and saved-view state share backup requirements; task 4 extends task 2 rather than creating another backup system. The task checklists above preserve the original proposed steps; the execution record below gives measured outcomes and explicit verification limits.

## Execution record — 2026-11-11

Tasks 1–7 implemented. Evidence: 1,166 Python tests OK (10 optional skips), 129 locked frontend tests, TypeScript/production build, 14 real Chromium flows, non-root fresh/populated container startup and verified recovery/restore. Both live installations run the same pinned image and report 24 accepted, 12 conditional and one deferred analysis, with none incomplete. The server is reachable over the LAN from the development computer. Complete recovery copies are verified on separate hosts, and the previous server image/data remain intact. Exact image identity, operating paths and rollback are in [release verification](../../RELEASE_VERIFICATION.md).

| Task | Execution outcome |
|---|---|
| 1 | Read-only full-corpus assessment; P06 regression reproduced and fixed using the archived original |
| 2 | Frozen builds, selectable scheduling, versioned application-state recovery and CI jobs; isolated UID/recreation/restore checks pass |
| 3 | Server-validated independent views and exact exports; current evidence and source versions gate all output |
| 4 | Durable atomic saved figures, conflict recovery, independent compare/reset and backup coverage; browser flows pass |
| 5 | Independent portfolio arithmetic and gap/input corrections; model limitations remain visible |
| 6 | Desktop/mobile/keyboard/light/dark, error recovery and performance improvements verified |
| 7 | Local and media-server deployment, complete restored corpus, LAN checks, retained old image/data and verified off-server recovery copy |

Rulings: keep curated reference graphics and expose scientifically compatible independent variants; cadence-unknown derived outputs are dots/tables; complex structured results reject unsupported date bounds. Bind acceptance to exact current observation versions and original filesystem identities, rehashing after any change. The owner explicitly chose the verified local corpus for the server while preserving the previous server corpus separately. No host reboot is performed on the shared media server; container replacement/restart policy is the scoped reliability check. Formal owner visual approval remains a review of the delivered app and is not claimed by automated tests. No code push or hosted CI execution was requested. Original-method research deferral G03 remains explicit; no missing source history was invented.
