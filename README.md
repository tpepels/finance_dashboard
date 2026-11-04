# Global Capital Monitor

> **PHASE 1 APPROVED/CLOSED (2026-11-03) · PHASE 2 ACTIVE.** The user approved all 35 scientific questions, six connected research experiences, visualization contract and the no-fee source/fallback approach. Phase 2 covers actual source acquisition, provenance, histories and data-quality evidence. Existing local Docker data are preserved. Phase 3 analytical methods and Phase 4 interface redesign have not started.

## Current authoritative documents

- [New five-phase development plan](docs/DEVELOPMENT_PLAN.md) — **sole phase plan**; Phase 1 approved, Phase 2 source acquisition active.
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
rtk git pull --ff-only
rtk docker build -t finance-dashboard:verify .
```

The build runs all Python tests and frontend tests. Repeat Python verification in a disposable container without the media server's data mount or credentials:

```bash
rtk proxy docker run --rm --entrypoint python finance-dashboard:verify \
  -m unittest discover -s tests -p 'test_*.py'
```

Read-only Phase 2 source check, without changing the SQLite database:

```bash
docker compose exec -T finance-dashboard python scripts/phase2_source_probe.py --since 2024-01-01
```

Source-contract inventory without network access or DB mutation:

```bash
docker compose exec -T finance-dashboard python scripts/phase2_corpus_status.py
```

Run the Compose commands above from the existing `~/media-stack` project on `media-server`. Deploy a clean build there with `docker compose --progress plain build finance-dashboard` followed by `docker compose up -d --no-deps finance-dashboard`. Keep its existing `/srv/finance-dashboard:/data` mount. The repository's standalone Compose file instead uses `FINANCE_DATA_DIR`; do not start a second stack beside the existing service.

Original WID inequality files and published OECD TiVA inputs retain their raw source snapshots under `/data/source-evidence`, included in verified backups. `scripts/phase2_source_reconcile.py` checks the raw source values against the latest stored observations without writing to the database. These sources still require comparative and release-vintage validation; passing tests or storing series does not complete Phase 2.

The Phase 2 corpus now records explicit original input roles for all 35 approved questions and executable bounded comparison variants. `GET /api/research-corpus` derives their evidence from current observation versions and independently checked originals. Source availability, current-snapshot panels and full scientific acceptance are separate; Phase 2 remains incomplete.

Run `python scripts/phase2_comparative_corpus.py --store` to reconcile available originals and archive exact input/panel rows. This reads the database; `--store` writes evidence artifacts. Add `--acquire` to explicitly refresh complete histories through existing append-only ingestion first. `--only M02 L01` limits the analyses. Original responses, source contracts, native units, no-fill exclusions, hashes and temporal limits remain attached to the result.

French equity research portfolios and the pinned Swinkels sovereign-return workbook are named benchmark alternatives. Their native percent/decimal units and local currencies remain explicit. Full French outputs and large original matrices stay in private evidence; source fixtures document redistribution rights and exact original hashes.

`python -m finance_dashboard.sec_holdings_sync --recover-raw --limit 50` recovers original XML for existing verified SEC aggregates, checking their original SHA and retaining aggregate bytes. Read native facts at `/api/holdings/vt/positions?accession=0000857489-26-000275`. Named original UCITS annual PDFs/current CSVs use `finance_dashboard.ucits_holdings` and `/api/holdings/ucits/sources`; annual equity/NAV controls do not establish complete derivative or issuer mappings.

`python -m finance_dashboard.icio --package RR_WLD_2026_593.zip --readme ReadMe_ICIO_small.xlsx` verifies and archives the identified original 2022 OECD regular matrix and its source accounting diagnostics. `/api/source-evidence/icio` reports those diagnostics. The present original has accounting residuals above serialization-rounding bounds; it is preserved with a failing gate and is never silently rebalanced.

The full Python suite accepts `TEST_POSTGRES_URL` for a disposable PostgreSQL database and `TEST_ICIO_PACKAGE` for the original 55 MB replication ZIP. These four external checks are explicitly skipped when their inputs are absent, including during the ordinary Docker build. Tests never need the live production database.
