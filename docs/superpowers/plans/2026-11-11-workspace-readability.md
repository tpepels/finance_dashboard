# Workspace Readability Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans with dispatching-parallel-agents for independent backend/UI work and a fresh integrated reviewer.

**Goal:** Make question navigation faster and present research through a clear, accessible hierarchy.
**Architecture:** Retain canonical Python analyses and hash routes; optimize measured backend reads, scope frontend requests and redesign the existing workspace.
**Tech Stack:** Python/FastAPI/SQLite, React/TypeScript/ECharts, pinned Docker image.
**Spec:** [Workspace readability design](../specs/2026-11-11-workspace-readability-design.md).

## Global constraints
No fabricated observations, weaker acceptance, persistent private browser cache, new framework or loss of drafts/history/exports. Current private holdings revision 2 and original evidence remain preserved. Near-black dark surfaces, clear text/series contrast, comfortable/compact density, 390px support and reduced motion.

## Review focus
Changed inputs cannot reuse stale calculations; dates and configured views cannot collide in caches; switching questions during requests cannot display the previous result; mobile navigation must preserve focus and public hashes; density/theme changes cannot reset owner/saved-figure drafts.

### Task 1: Measure and optimize backend reads
**Files:** `src/finance_dashboard/api.py`, owning engine/data/guard helpers, focused API/engine tests as measurement requires.
**Interfaces:** Existing GET analysis, configured views, capabilities and export remain compatible.
- [ ] Measure live cold/repeated request and profile expensive boundaries; retain private reports.
- [ ] Reproduce measured redundant work with tests. Implement bounded reuse or query improvements with current evidence guards, assessment/date/owner identity and mutation-safe outputs.
- [ ] Verify invalidation, concurrent/error paths and unchanged analytical output; record before/after timing.

### Task 2: Scope and stabilize frontend loading
**Files:** `frontend/src/analysisShell.tsx`, `frontend/src/analysisShell.test.tsx`.
**Interfaces:** Preserve `useBundles(ids, dataVersion)` and `load`, use existing ResearchSelection context.
- [ ] Reproduce whole-topic reads for a selected question and repeated successful reads during pending retries.
- [ ] Fetch only the selected question when applicable, isolate retries, preserve loading/refresh safety and ignore obsolete route responses.
- [ ] Verify selected/topic/overview requests, refresh and rapid route transitions.

### Task 3: Implement visual hierarchy
**Files:** `App.tsx`, `Overview.tsx`, `Workbench.tsx`, `styles.css`, `chartKit.ts`, related frontend tests. Task 2 owns analysisShell.
**Interfaces:** Existing public hash routes, semantic headings, appearance preferences and portfolio/saved contexts.
- [ ] Build the full scrollable default dashboard across all topics, optional navigation menu on every screen size, clear drilldowns and comfortable/compact control.
- [ ] Apply coherent near-black tokens and distinctive chart palettes; retain light mode, text labels and redundant series cues.
- [ ] Split secondary UI imports if safe; verify route/focus/draft preservation, responsiveness and build output.

### Task 4: Integrate, review and deploy
- [ ] Fresh independent review of cache correctness, UI accessibility and loading regressions; resolve findings.
- [ ] Run full Python/frontend/build and meaningful browser checks; visually inspect desktop/mobile in both themes and benchmark populated data.
- [ ] Build pinned image, verify it, adopt reviewed source into original workspace, deploy both installations with rollback retained and no private state replacement.
- [ ] Check actual LAN/local flows and holdings integrity, update runbook/release evidence and record remaining real limits.
