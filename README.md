# Global Capital Monitor

> **Phase 1 approved (2026-11-03); Phase 2 active.** This repository contains the old running application **and** the approved replacement specifications. The deployed interface is legacy; it is not the target design. No repository reset, loss of historical data, or second runtime is authorized.

## Start here: one implementation path

- **[Authoritative development plan](docs/DEVELOPMENT_PLAN.md)** — phase gates, binding migration architecture decision (2026-11-04), acceptance and documentation policy. **Only active roadmap.**
- **[Scientific charter](docs/PHASE1_SCIENTIFIC_CHARTER.md)** and **[35-question catalogue](docs/PHASE1_ANALYSIS_CATALOGUE.md)** — the approved product scope and six connected research experiences.
- **[Scientific analysis specifications](docs/PHASE1_ANALYSIS_SPECIFICATIONS.md)** — variable definitions, calculation, comparability, alternatives and evidence requirements for all 35 questions.
- **[Visualization contract](docs/PHASE1_VISUALIZATION_CONTRACT.md)** — the target information architecture and independently configurable graph interactions, not the existing UI.
- **[Source fallback matrix](docs/PHASE1_FALLBACK_SOURCE_MATRIX.md)** and **[Phase 2 source coverage audit](docs/PHASE2_SOURCE_COVERAGE_AUDIT.md)** — approved alternatives versus observed acquisition/validation status.

### What survives the rebuild

Keep the source collectors, append-only historical observations, provenance, release vintages, storage/migrations, backups, validated calculations, local FastAPI service and useful operations. **Phase 3 consolidates analytics; Phase 4 replaces the old frontend architecture and styling**, while reusing the React/TypeScript/Vite/ECharts stack if appropriate. Full function-by-function retention is subject to the approved scientific contracts. No legacy compatibility execution paths are allowed at phase closure.

### Documentation boundaries

- **Normative:** the six linked documents above; approved Phase 1 research reviews and source-discovery reports are evidence, not additional roadmaps.
- **Current technical/operational references:** [architecture snapshot](docs/ARCHITECTURE.md), [data integrity policy](docs/DATA_POLICY.md), [server setup](docs/SERVER_SOURCE_SETUP.md), [Docker deployment](docs/HOME_SERVER_DOCKER.md) and [OECD surplus method](docs/OECD_CORPORATE_SURPLUS.md). Some record the pre-redesign implementation and must not be mistaken for target architecture.
- **Historical only:** [docs/archive/](docs/archive/) contains superseded contracts, source decisions and former phase plans. Redirect-only files were removed; link directly to the archive. Git history preserves earlier versions. Do not create new phase roadmaps or duplicate status diaries.

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
