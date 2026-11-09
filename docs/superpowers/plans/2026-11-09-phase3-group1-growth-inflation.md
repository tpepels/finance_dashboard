# Phase 3 group 1 (C01, C03, C06) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Move C01, C03 and C06 onto the engine and draw them in the visual language (cycle clock, growth strip, stagflation map with commodity bars), retiring the six old growth tiles.

**Spec:** `docs/superpowers/specs/2026-11-08-phase3-engine-design.md`, `docs/superpowers/specs/2026-11-09-phase3-visual-language.md`; owner-approved pictures 2026-11-09 (chat).

## Global Constraints

* Engine computes every value; the browser only draws. Each derived value names a registered transform.
* No fill, no interpolation; exact period joins; gaps stay gaps.
* IMF WEO series in the store already exclude current-year and projection years (catalogue notes); captions say so instead of drawing forecasts.
* Colour follows the entity; aggregates (World, G7, G20) are drawn in neutral ink; at most 8 hues; scatter-like forms show at most three coloured series, others neutral with direct labels.
* Readability gate: every graphic rendered with real data and checked for overlap before the task is done (memory: visual-dashboard-for-humans).

## Review Focus

1. An economy whose CLI stops before the others (e.g. trend-restored series end 2026-05): its clock dot is dated by its own last month and the dot says so.
2. A year where one cohort member has no growth value: that year has no dispersion value (never an SD over fewer members).
3. A commodity with a missing month: no 12-month change for the months that need it.
4. A country with growth but no inflation for a year: no stagflation point for that year.
5. Analyses with fewer than two observations: hero graphics render an explicit empty state, not a crash.

---

### Task 1: Transforms and C01 definition (engine)
Files: `src/finance_dashboard/engine/transforms.py`, `engine/analyses.py`, `definitions/limitations.json` (method texts), tests `tests/test_engine_c01.py`.
- `cycle_position`: CLI − 100 and its 1-month change; phase = expansion (≥100, rising), slowdown (≥100, falling), contraction (<100, falling), recovery (<100, rising).
- `log_change`: 100·ln(x[t]/x[t−k]) with k months (IP k=12, GDP quarterly k=1 quarter).
- C01 values: `clock` per CLI series (last 13 monthly positions, phase, as_of), `history` per CLI series, `us_activity` (IP 12-month log change, GDP q/q log change, unemployment level), `diffusion` (1m/3m/6m lines).
- [ ] tests first (phase quadrants, gap breaks the trail, stale series keeps own as_of), implement, full engine tests, commit.

### Task 2: C03 and C06 definitions (engine)
Files: same modules, tests `tests/test_engine_c03_c06.py`.
- `own_range_window`: min/max over the last n annual observations; `cross_section_sd`: population SD across a fixed cohort for years where every member is observed.
- C03 values: `strip` per series (latest, year, 10-year min/max), `history`, `dispersion` (cohort US, EU, CN, IN, JP).
- `year_on_year_change` monthly for Brent, gas, maize; C06 values: `commodities` (latest 12-month change, as_of, history of changes), `map` per country (growth, inflation pairs on exactly matched years), `inflation` and `growth` histories.
- [ ] tests first (incomplete cohort year has no SD; commodity gap; unmatched year), implement, commit.

### Task 3: Hero graphics (frontend)
Files: `frontend/src/heroes.tsx`, tests `frontend/src/heroes.test.tsx`; `chartKit.ts` entity map (IN, GB, EU; aggregates neutral).
- `CycleClock`: four labelled quadrants; one neutral dot per economy with a direct label; selecting an economy highlights it and shows its 12-month trail.
- `GrowthStrip`: one row per region, decade range bar, latest dot, value label.
- `StagflationMap`: growth (x) × inflation (y), labelled quadrant "high inflation, low growth", one coloured dot per country (≤3) with a trail through recent years.
- `ChangeBars`: diverging bars around zero for commodity 12-month changes.
- [ ] tests first (roles/aria names, quadrant labels, empty states), implement, commit.

### Task 4: Growth & inflation panel; retire old tiles
Files: `frontend/src/GrowthPanel.tsx` (+test), `App.tsx`, `src/finance_dashboard/research.py` (remove global_growth, us_growth, ea_growth, jp_growth, compare_growth, compare_growth_differential) and their tests.
- [ ] tests first, implement, render with real data and fix readability, full suites, update plan docs, commit.
