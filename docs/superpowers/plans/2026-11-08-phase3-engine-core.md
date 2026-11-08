# Phase 3 engine core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the analysis engine (result bundle, named transforms, limitation register, conditionals register, `/api/analysis`) and move P06, P07 and F03 onto it with identical numbers, then retire `/api/decision` and `decision_analytics.py`.

**Architecture:** A new package `finance_dashboard/engine/` holds one module per responsibility. Each analysis is an `AnalysisDefinition` (declared inputs by role plus a pure compute function). `build_bundle` combines its result with the Phase 2 acceptance snapshot, the series catalogue and the corpus definition into one JSON bundle. Charts, the text export and the conditionals listing all read bundles.

**Tech Stack:** Python 3 (stdlib `unittest`), FastAPI, SQLAlchemy, React + TypeScript + Vitest, ECharts.

**Spec:** `docs/superpowers/specs/2026-11-08-phase3-engine-design.md`

## Global Constraints

* No filled, interpolated, carried-forward or future value; gaps stay gaps.
* The engine writes no conclusions. Fixed, sourced method and limitation texts only. No agreement or disagreement score between indicators.
* Every limitation the acceptance engine records for an analysis, and for each role whose series it uses, appears in its bundle with readable text. An unmapped code is an error, never silently dropped.
* An analysis whose Phase 2 state is not `accepted` or `conditional` gets a bundle with question and open gates but `values` and `estimates` set to `null`.
* P06, P07 and F03 produce exactly today's numbers (regression check before old code is deleted).
* Bundles never contain credentials or local file paths.
* One canonical path: `/api/decision/{id}` and `decision_analytics.py` are removed at the end; no compatibility alias.
* Full offline suite before each commit: `uv run --extra test python -m unittest discover -s tests -p 'test_*.py' -q` and `cd frontend && npm test`.

## Decisions this plan makes (builder's calls, consistent with the spec)

* **Borrowed inputs.** Today P06 calibrates with `returns.us.shiller_real_total_return` (accepted under V05), and F03 shows CN/DE/PT credit gaps (accepted under F01) and CN/PT debt service (accepted under F02). An input may come from another analysis's resolved role. The bundle then names that analysis and role and carries that role's limitations. An input in no resolved role is refused (`UnacceptedInput`).
* **Acceptance caching.** The API evaluates the corpus lazily and caches the result for `FINANCE_ACCEPTANCE_TTL_SECONDS` (default 3600). Every bundle states `phase2.evaluated_at`.
* **Transforms are added as analyses need them.** This plan registers only what P06, P07 and F03 use; later groups add theirs.

## Review Focus

1. **The acceptance evaluation is slow or fails** (missing evidence directory, corrupt original). Expected: `/api/analysis/{id}` returns 503 with a short reason, not a 500 or a bundle without limitations. Test in Task 3.
2. **A conditional analysis whose limitation has a `detail` but no `series_id`** (descoped roles, deferral). Expected: it still appears in the bundle and the conditionals listing with its detail. Test in Task 2.
3. **An input series with no observations yet** (fresh database). Expected: the bundle lists the input with `observations: 0` and the analysis's values reflect the absence (empty rows, `null` estimates), no exception. Test in Task 4.
4. **An unknown analysis ID or a deferred analysis (G03).** Expected: unknown → 404; deferred → bundle with state `deferred`, its deferral limitation, `values: null`. Test in Task 7.
5. **The current, incomplete month.** Expected: excluded from P07 month-ends exactly as today, using the request date. Test in Task 5.

---

### Task 1: Named transforms

**Files:**
- Create: `src/finance_dashboard/engine/__init__.py` (empty)
- Create: `src/finance_dashboard/engine/transforms.py`
- Test: `tests/test_engine_transforms.py`

**Interfaces:**
- Produces:
  - `TRANSFORMS: dict[str, str]`, mapping name → formula, with exactly these names: `month_end`, `complete_months`, `contiguous_tail`, `monthly_return`, `return_summary`, `own_history`, `index_100`, `overlapping_window_percentiles`.
  - `applied(name: str, **params) -> dict` returns `{"name", "formula", "params"}`; raises `KeyError` for an unregistered name.
  - `month_end(points) -> dict[(y, m), (date, float)]`, `complete_months(ends, today: date) -> dict`, `contiguous_tail(months) -> list[(y, m)]`, `previous_month(key)`, `return_summary(returns: list[float]) -> dict` (today's `summary`), `own_history(points) -> dict | None`. Semantics are identical to `decision_analytics.py`: move the bodies, don't rewrite them.
  - `index_100(returns: list[tuple[str, float]]) -> list[tuple[str, float]]`: cumulative level starting at 100 × (1 + first return), matching the frontend `wealth()` it replaces.
  - `percentile(sorted_values: list[float], q: float) -> float | None`: P06's linear interpolation.

- [ ] **Step 1: Write the failing tests.** Move the four month-end, contiguity and own-history assertions from `tests/test_decision_analytics.py` into `tests/test_engine_transforms.py`, importing from `finance_dashboard.engine.transforms`. Add:

```python
def test_index_100_compounds_without_inventing_months(self):
    self.assertEqual(index_100([("2026-01", 0.1), ("2026-02", -0.5)]),
                     [("2026-01", 110.0), ("2026-02", 55.0)])

def test_every_transform_has_a_formula_and_unknown_names_fail(self):
    self.assertTrue(all(TRANSFORMS[name].strip() for name in TRANSFORMS))
    self.assertEqual(applied("month_end")["formula"], TRANSFORMS["month_end"])
    with self.assertRaises(KeyError):
        applied("interpolate")
```

- [ ] **Step 2: Run** `uv run --extra test python -m unittest tests.test_engine_transforms -v`. Expected: FAIL, `ModuleNotFoundError: finance_dashboard.engine`.
- [ ] **Step 3: Implement `engine/transforms.py`.** Write the formula strings in plain notation, for example `month_end`: "last observation in each calendar month; observed date retained". Leave `decision_analytics.py` in place for now; Task 5 switches its imports.
- [ ] **Step 4: Run the test again.** Expected: PASS.
- [ ] **Step 5: Commit:** "Engine transforms: named, with recorded formulas".

### Task 2: Limitation register

**Files:**
- Create: `definitions/limitations.json`
- Create: `src/finance_dashboard/engine/limitations.py`
- Test: `tests/test_engine_limitations.py`

**Interfaces:**
- Produces:
  - `definitions/limitations.json` has the shape `{"phase2": {code: text}, "method": {"P06": {key: text}, "P07": {...}, "F03": {...}}}`.
  - `class UnmappedLimitation(KeyError)`.
  - `describe(item: dict) -> dict` returns `item` plus `"text"`; raises `UnmappedLimitation(code)`.
  - `method_limitations(analysis_id: str) -> list[dict]` returns `[{"code", "text"}]` in file order.

- [ ] **Step 1: Write the failing tests.**

```python
ACCEPTANCE_MODULES = ["research_acceptance.py", "holdings_acceptance.py", "chronology_acceptance.py",
                      "marxian_acceptance.py", "regional_valuation_acceptance.py",
                      "comparative_corpus.py", "research_readiness.py"]

def test_every_code_literal_in_acceptance_modules_has_text(self):
    codes = {m for f in ACCEPTANCE_MODULES
             for m in re.findall(r'"code":\s*"([a-z0-9_]+)"', (SRC / f).read_text())}
    self.assertGreaterEqual(len(codes), 28)
    self.assertEqual(sorted(codes - set(load_register()["phase2"])), [])

def test_detail_only_limitation_is_described(self):
    item = {"code": "role_descoped_by_phase1_revision", "role": "x", "detail": "no free source"}
    self.assertEqual(describe(item)["detail"], "no free source")
    self.assertTrue(describe(item)["text"])

def test_unmapped_code_raises(self):
    with self.assertRaises(UnmappedLimitation):
        describe({"code": "not_a_code"})

def test_method_limitations_replace_hand_typed_strings(self):
    self.assertEqual(len(method_limitations("P07")), 3)
    self.assertEqual(len(method_limitations("P06")), 3)
    self.assertEqual(len(method_limitations("F03")), 3)
```

- [ ] **Step 2: Run** `uv run --extra test python -m unittest tests.test_engine_limitations -v`. Expected: FAIL.
- [ ] **Step 3: Write `definitions/limitations.json`.** Write one owner-readable sentence for each of the 28 Phase 2 codes listed by `grep -ohE '"code": *"[a-z0-9_]+"' src/finance_dashboard/*.py | sort -u`. Each sentence says what the limit means for reading the result, for example `latest_revised_values_not_real_time`: "Values are the publisher's latest revised figures, not what was known at the time." The `method` entries are today's limitation strings from `decision_analytics.py`, verbatim, under short keys.
- [ ] **Step 4: Implement `engine/limitations.py`.** Load the register once with `catalog.DEFAULT_ROOT`, which honours `FINANCE_DASHBOARD_ROOT`.
- [ ] **Step 5: Run the test again.** Expected: PASS. **Commit:** "Limitation register with readable text for every acceptance code".

### Task 3: Acceptance snapshot

**Files:**
- Create: `src/finance_dashboard/engine/acceptance.py`
- Test: `tests/test_engine_acceptance.py`

**Interfaces:**
- Consumes: `describe` (Task 2).
- Produces:
  - `@dataclass(frozen=True) class AcceptanceSnapshot: evaluated_at: datetime; analyses: dict[str, dict]`, keyed by analysis ID; each value is the public report's `acceptance` dict.
  - `snapshot_from_report(public_report: dict, evaluated_at: datetime) -> AcceptanceSnapshot`.
  - `analysis_phase2(snapshot, analysis_id) -> dict` returns `{"state", "evaluated_at": iso, "limitations": [described], "open_gates": [role names from blocking_roles]}`.
  - `class UnacceptedInput(ValueError)`.
  - `input_provenance(snapshot, analysis_id, series_id) -> dict` returns `{"accepted_under": {"analysis_id", "role"}, "limitations": [described]}`. Prefer a resolved role of `analysis_id` itself; otherwise the first resolved role of another `accepted` or `conditional` analysis (in sorted analysis-ID order) whose `series_ids` contain the series. Raise `UnacceptedInput` if none.
  - `class AcceptanceUnavailable(RuntimeError)`.
  - `class AcceptanceCache: __init__(self, loader: Callable[[], AcceptanceSnapshot], ttl_seconds: float, clock=time.monotonic)` with `get() -> AcceptanceSnapshot`. It wraps any loader exception in `AcceptanceUnavailable` and keeps no failed result.

- [ ] **Step 1: Write the failing tests.** Use a synthetic `public_report` with three analyses:
  - `P06`: conditional, with a role `us_cape` that has one limitation;
  - `V05`: accepted, with a role `matched_equity_total_return` on `returns.us.shiller_real_total_return` that has a `latest_revised_values_not_real_time` limitation;
  - `G03`: deferred.

  Assert:
  - `input_provenance(snap, "P06", "returns.us.shiller_real_total_return")["accepted_under"] == {"analysis_id": "V05", "role": "matched_equity_total_return"}`, and its limitations carry text;
  - `input_provenance(snap, "P06", "unknown.series")` raises `UnacceptedInput`;
  - `analysis_phase2(snap, "G03")["state"] == "deferred"`;
  - with a fake clock, `AcceptanceCache` calls the loader once within the TTL and again after it;
  - a loader that raises `OSError` makes `get()` raise `AcceptanceUnavailable`, and the next `get()` retries the loader.
- [ ] **Step 2: Run** `uv run --extra test python -m unittest tests.test_engine_acceptance -v`. Expected: FAIL.
- [ ] **Step 3: Implement `engine/acceptance.py`.**
- [ ] **Step 4: Run the test again.** Expected: PASS. **Commit:** "Acceptance snapshot: per-input provenance and cached evaluation".

### Task 4: Bundle builder

**Files:**
- Create: `src/finance_dashboard/engine/bundle.py`
- Test: `tests/test_engine_bundle.py`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces:
  - `@dataclass(frozen=True) class Computed: values: dict; estimates: dict | None; transforms: list[dict]; comparison: list[str]`. `transforms` comes from `applied(...)` with an `applied_to` param naming roles; `comparison` names the roles shown side by side.
  - `@dataclass(frozen=True) class AnalysisDefinition: analysis_id: str; inputs: dict[str, str]; compute: Callable[[dict[str, list[tuple[date, float]]], dict], Computed]`. `inputs` maps role to series ID; for multi-area inputs the role key is `"<role>:<AREA>"`, for example `"credit_gap:PT"`. `compute(points_by_role, view)` receives `view` (for example `{"today": date}`) and returns `Computed`.
  - `ENGINE_VERSION = "1"`.
  - `build_bundle(definition, *, points: dict[str, list[tuple[date, float]]], snapshot: AcceptanceSnapshot, corpus_analysis: dict, catalog_series: dict[str, dict], view: dict, computed_at: datetime) -> dict` with these top-level keys, exactly: `analysis_id, question, decision_informed, evidence_tier, engine_version, computed_at, phase2, inputs, transforms, values, estimates, comparison, method_limitations, citations, view`.
  - Each `inputs[]` entry is `{role, series_id, name, publisher, source_key, source_url, geography, unit, frequency, first, last, observations, accepted_under, limitations}`. `publisher` is the catalogue `provider`. `question` is the corpus `title`. `citations` are the corpus `primary_method_sources` resolved against `original_sources` (`id, label, url`), passed in through `corpus_analysis["method_sources"]`.
  - When `phase2.state` is not `accepted` or `conditional`, `compute` is not called and `values`, `estimates` and `comparison` are `None`.

- [ ] **Step 1: Write the failing tests.**
  - With a toy definition whose compute returns the input count, check that the keys equal the set above.
  - Check that a borrowed input carries `accepted_under` for the other analysis.
  - Feed an input with `[]` points: expect `observations == 0` and `first`/`last` set to `None`, with no exception.
  - A deferred analysis: expect `values is None` and a compute that would raise if called.
  - Assert `"/home" not in json.dumps(bundle)` and `"api_key" not in json.dumps(bundle).lower()`.
- [ ] **Step 2: Run** `uv run --extra test python -m unittest tests.test_engine_bundle -v`. Expected: FAIL.
- [ ] **Step 3: Implement `engine/bundle.py`.** Compute per-input `limitations` from `input_provenance`. Analysis-level `phase2` comes from `analysis_phase2`. `method_limitations` comes from Task 2.
- [ ] **Step 4: Run the test again.** Expected: PASS. **Commit:** "Result bundle: one self-describing record per analysis".

### Task 5: P07 on the engine

**Files:**
- Create: `src/finance_dashboard/engine/analyses.py`
- Modify: `src/finance_dashboard/decision_analytics.py` (import the transforms from `engine.transforms` instead of defining them)
- Test: `tests/test_engine_p07.py`

**Interfaces:**
- Consumes: Tasks 1 and 4.
- Produces: `P07: AnalysisDefinition` with inputs equal to today's `P07_INPUTS` and `values = {"rows": [...same rows as today...], "nominal": {...}, "real_eur": {...}, "real_period": ..., "wealth": {"nominal": {"eur_unhedged": [[month, level]], "eur_hedged": [...]}, "real": {...}}}`, where wealth uses `index_100` over the same rows the frontend `wealth()` used; `estimates = None`; `comparison = ["eur_unhedged", "eur_hedged"]`. Also `DEFINITIONS: dict[str, AnalysisDefinition]` (P07 now; P06 and F03 are added in Task 6).

- [ ] **Step 1: Write the failing tests.**
  - Move the P07 tests from `tests/test_decision_analytics.py` to call `P07.compute(...)`, with the same assertions.
  - Add a regression test: seed an in-memory database with the 5 series (24 months, including one gap), then assert `P07.compute(points, {"today": date(2026, 11, 6)}).values` without `wealth` equals `decision_analytics.load_p07(session, date(2026, 11, 6))` without `inputs` and `limitations`.
  - Add `wealth["real"]` equality with the frontend fixture `[['2026-01', 100]]` case from `DecisionPanel.test.tsx`.
  - Add a test that the incomplete current month is excluded (Review Focus 5).
- [ ] **Step 2: Run** `uv run --extra test python -m unittest tests.test_engine_p07 -v`. Expected: FAIL.
- [ ] **Step 3: Implement the P07 definition.** Move `p07_hedging` into `engine/analyses.py`. `decision_analytics.load_p07` stays as the regression oracle until Task 8.
- [ ] **Step 4: Run the test again.** Expected: PASS. **Commit:** "P07 runs on the engine with identical numbers".

### Task 6: P06 and F03 on the engine

**Files:**
- Modify: `src/finance_dashboard/engine/analyses.py`
- Test: `tests/test_engine_p06_f03.py`

**Interfaces:**
- Consumes: Tasks 1, 4 and 5 (`DEFINITIONS`).
- Produces:
  - `P06` with today's `P06_INPUTS`. `values` holds the latest bonds, inflation and world snapshot. `estimates = {"equity_us": {...today's equity_us...}}`, including `calibration_windows` and `effective_independent_windows`. `comparison = ["equity_us", "equity_world_snapshot", "bonds"]`.
  - `F03` with inputs `credit_gap:<AREA>` and `private_dsr:<AREA>` for today's areas. `values = {"rows": ..., "guide": ...}`, `estimates = None`, `comparison = ["credit_gap", "private_dsr"]`.

- [ ] **Step 1: Write the failing tests.** Move the P06 and F03 tests from `tests/test_decision_analytics.py`. Add regression tests against `decision_analytics.load_p06` and `load_f03` over a seeded database, the same way as Task 5.
- [ ] **Step 2: Run** `uv run --extra test python -m unittest tests.test_engine_p06_f03 -v`. Expected: FAIL.
- [ ] **Step 3: Implement both definitions.** Move `p06_expected_returns`, `f03_credit` and the guide constants.
- [ ] **Step 4: Run the test again.** Expected: PASS. **Commit:** "P06 and F03 run on the engine with identical numbers".

### Task 7: API, export and conditionals command

**Files:**
- Create: `src/finance_dashboard/engine/runner.py`
- Create: `src/finance_dashboard/engine/export.py`
- Create: `src/finance_dashboard/engine/conditionals_cli.py`
- Modify: `src/finance_dashboard/api.py` (new routes; an `AcceptanceCache` built inside `create_app` from `current_corpus_report`)
- Modify: `src/finance_dashboard/command_registry.py` (add `"research conditionals"`)
- Test: `tests/test_engine_api.py`, `tests/test_engine_export.py`

**Interfaces:**
- Consumes: Tasks 3–6.
- Produces:
  - `analysis_bundle(session, analysis_id, *, snapshot, corpus_document, catalog_series, view) -> dict`. It loads the points of the definition's inputs through `finance_dashboard.service.current_observations`. An analysis without a definition gets a bundle with `values: None` and the state from the snapshot.
  - `export_text(bundle: dict) -> str` produces, in this order:
    1. a header with the question, decision informed, state, Phase 2 limitations, method limitations, inputs with publisher and URL, and transforms with formulas;
    2. a line `--- data (JSON) ---`;
    3. `json.dumps({"values": ..., "estimates": ...}, indent=1)`.
  - `conditionals(snapshot) -> list[dict]` returns `[{"analysis_id", "state": "conditional", "limitations": [described]}]`.
  - Routes:
    - `GET /api/analysis` lists `[{analysis_id, question, state, has_engine}]`;
    - `GET /api/analysis/{id}` returns the bundle, accepts the query param `today` (ISO date, for tests) and returns 404 for an unknown ID;
    - `GET /api/analysis/{id}/export` returns `text/plain` with `Content-Disposition: attachment; filename="<id>-<computed date>.txt"`;
    - `GET /api/conditionals` returns the conditionals listing;
    - any of these returns 503 `{"detail": "Phase 2 acceptance evaluation unavailable"}` on `AcceptanceUnavailable`.
  - CLI `python -m finance_dashboard research conditionals --database-url URL --evidence-dir D --vintage-dir V --holdings-dir H` prints the listing as JSON. It exits 1 if any limitation code is unmapped, naming the code.

- [ ] **Step 1: Write the failing tests.** Follow the `tests/test_research_corpus_api.py` setup: in-memory SQLite, `create_app(engine)`, and `AcceptanceCache` loader patched with a synthetic snapshot.
  - `/api/analysis/P07` → 200, with `phase2.limitations` non-empty for a conditional fixture.
  - `/api/analysis/XYZ` → 404.
  - `/api/analysis/G03` → `values` null and state `deferred`.
  - A loader that raises gives 503.
  - The export contains `--- data (JSON) ---` and every limitation text in the bundle.
  - The CLI's main function, with a snapshot containing `{"code": "not_a_code"}`, returns exit code 1.
- [ ] **Step 2: Run** `uv run --extra test python -m unittest tests.test_engine_api tests.test_engine_export -v`. Expected: FAIL.
- [ ] **Step 3: Implement the service, export, CLI and routes.** Add the new command to `docs/COMMANDS.md`.
- [ ] **Step 4: Run the test again.** Expected: PASS.
- [ ] **Step 5: Run the command on the live corpus and check it against the plan's conditional list.** Run `uv run python -m finance_dashboard research conditionals --database-url sqlite:///data-local/finance.sqlite3 --evidence-dir data-local/source-evidence --vintage-dir data-local/vintages --holdings-dir data-local/holdings`. Expected: exit 0, listing the 13 conditional analyses in `docs/DEVELOPMENT_PLAN.md`. Add text for any unmapped code it names to the register.
- [ ] **Step 6: Commit:** "Analysis API, AI export and conditionals listing".

### Task 8: Decisions panel on bundles; retire the old path

**Files:**
- Modify: `frontend/src/DecisionPanel.tsx`, `frontend/src/DecisionPanel.test.tsx`
- Modify: `src/finance_dashboard/api.py` (remove `/api/decision/{analysis_id}`)
- Delete: `src/finance_dashboard/decision_analytics.py`, `tests/test_decision_analytics.py` (their tests now live in Tasks 1, 5 and 6; replace the regression oracles there with frozen expected values captured from the oracle before deletion)
- Modify: `docs/DEVELOPMENT_PLAN.md` (Done and Next slices), `docs/ARCHITECTURE.md` only where it names `decision_analytics.py`

**Interfaces:**
- Consumes: the bundle JSON from Task 7.
- Produces: `DecisionPanel` fetches `/api/analysis/{id}`. It reads `values` and `estimates` as the old payloads did, draws P07 wealth from `values.wealth` (the `wealth()` function is deleted), shows `phase2.limitations[].text` and `method_limitations[].text` under each card, and has an "Export for AI" link to `/api/analysis/{id}/export` on each card.

- [ ] **Step 1: Freeze the regression oracles.** In `tests/test_engine_p07.py` and `tests/test_engine_p06_f03.py`, replace the calls to `decision_analytics.load_*` with the literal expected values they produced on the seeded fixtures.
- [ ] **Step 2: Update `DecisionPanel.test.tsx` to bundle-shaped fixtures and run it.** Assertions:
  - the ranges text `-4.0% to 8.3%` still renders;
  - a Phase 2 limitation text renders;
  - an "Export for AI" link with `href="/api/analysis/P06/export"` exists;
  - fetch URLs start with `/api/analysis/`.

  Run `cd frontend && npm test -- DecisionPanel`. Expected: FAIL.
- [ ] **Step 3: Implement the panel changes.** Remove the route, the module and its old test.
- [ ] **Step 4: Run the full suites.**
  - `uv run --extra test python -m unittest discover -s tests -p 'test_*.py' -q`: expected `OK`.
  - `cd frontend && npm test && npm run build`: expected pass.
  - `grep -rn "api/decision\|decision_analytics" src frontend/src tests`: expected no matches.
- [ ] **Step 5: Update the plan docs and commit:** "Decisions panel reads engine bundles; /api/decision retired".
