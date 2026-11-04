# Global Capital Monitor

> **PHASE 1 APPROVED/CLOSED (2026-11-03) · PHASE 2 ACTIVE.** The user approved all 35 scientific questions, six connected research experiences, visualization contract and the no-fee source/fallback approach. Phase 2 covers actual source acquisition, provenance, histories and data-quality evidence. Existing local Docker data are preserved. Phase 3 analytical methods and Phase 4 interface redesign have not started.

## Current authoritative documents

- [New five-phase development plan](docs/DEVELOPMENT_PLAN.md) — **sole phase plan**; research-first Phase 1 active, later scope acceptance reset.
- [Phase 1 scientific charter](docs/PHASE1_SCIENTIFIC_CHARTER.md) — ten approved product-intent decisions, seven research domains, 28 scientific/authoritative methodological references and source-validation rules.
- [Phase 1 analysis catalogue](docs/PHASE1_ANALYSIS_CATALOGUE.md) — 35 owner-approved first-class questions and the six connected research experiences.
- [35 scientific analysis specifications](docs/PHASE1_ANALYSIS_SPECIFICATIONS.md) — variables, original methodology, reproducible formulas, alternatives, validity, interpretation and 49 scholarly/statistical references.
- [Phase 1 visualization contract](docs/PHASE1_VISUALIZATION_CONTRACT.md) — complete per-graph geography/series/chart type/method, saved research views, accessibility, monitoring and independent recession/shock/recovery overlays.
- [Approved critical Phase 1 coherence/free-source review](docs/PHASE1_COHERENCE_AND_FREE_DATA_REVIEW.md) — binding six-story editorial structure, five reclassifications, five new scientific questions and no-fee source rule.
- [Historical no-fee source discoveries](docs/PHASE1_FREE_DATA_SOURCE_DISCOVERY.md) — academic return histories and original government, fund and company filings.
- [Accessibility-first follow-up research](docs/PHASE1_ACCESSIBILITY_FIRST_DATA_SEARCH.md) — publicly documented MSCI NETR JSON, historical iShares AJAX holdings, global company web/MCP access, Bloomberg LEGATRUU source identifiers, with actual download verification still open.
- [Preselected fallbacks for the four unresolved historical data targets](docs/PHASE1_FALLBACK_SOURCE_MATRIX.md) — verified alternative historical files, official lower-frequency sources, scientific labels and precise fallback triggers.
- [Pre-redesign roadmap archive](docs/archive/DEVELOPMENT_PLAN_PRE_RESET_2026-11-03.md) — prior operational fixes/empirical evidence; historical only.

## Existing implementation (preserved, not the approved product)

The previous application includes a single Docker service, stored 53 macro/24 market/3 FX histories, previous 46 indicator views, two UI sync actions, verified local backups, SEC source records and ALFRED original vintage imports. The Nov 3 18:14 sync completed with 0 missing requested historical vintages and 0 recent source issues. These facts document the preserved implementation, **not** the scientific/design completeness of the newly proposed application.

The following existing operational documentation remains available for running or safely servicing the current installation: [server setup](docs/SERVER_SOURCE_SETUP.md), [source indicator inventory](docs/INDICATOR_ACCEPTANCE_MATRIX.md), [original research methods](docs/ECONOMIC_RESEARCH_METHODS.md), [historical research/source contracts](docs/PHASE_4_RESEARCH_SOURCES.md). They are references to existing code and historic decisions, not competing product requirements.

## Phase 2 — Docker-only verification

The single Compose service is `finance-dashboard`. The image now includes the full `scripts/` directory, original Fed reference evidence, existing tests and Phase 2 additions. **Build runs the existing acceptance tests and the new Phase 2 tests before it can complete.** A failed build means no tested new image was produced, so do not infer a successful deployment.

```bash
cd ~/Projects/finance_dashboard
git pull --ff-only
docker compose build finance-dashboard
docker compose up -d finance-dashboard
docker compose ps
docker compose exec -T finance-dashboard python -m finance_dashboard validate
```

Run **all** Python tests in the container (the build runs only a selected set):

```bash
docker compose exec -T finance-dashboard python -m unittest discover -s tests -p 'test_*.py'
```

Read-only Phase 2 source check, without changing the SQLite database:

```bash
docker compose exec -T finance-dashboard python scripts/phase2_source_probe.py --since 2024-01-01
```

Source-contract inventory without network access or DB mutation:

```bash
docker compose exec -T finance-dashboard python scripts/phase2_corpus_status.py
```

The configured `FINANCE_DATA_DIR` path is mounted at `/data`; builds and container recreation must **not** clear it. `FRED_API_KEY` and other source configuration remain supplied by Compose. The source probe reports missing, rejected, or unavailable source samples rather than making up values. The new original-index and BIS integrations still require real-source verification; passing tests alone is not source coverage.
