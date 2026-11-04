# Global Capital Monitor

> **Phase 1 approved (2026-11-03); Phase 2 active.** This repository contains the old running application **and** the approved replacement specifications. The existing interface is legacy; it is not the target design. No repository reset, loss of historical data, or second runtime is authorized.

**Environment:** Development/research only; no separate production deployment or production database. Existing historical observations, source evidence and backups must still be preserved.

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

## Phase 2 — Local and Docker verification

The offline registry inventory can run directly from a checkout, without a configured database and without the optional original-artifact parser being imported:

```sh
PYTHONPATH=src python scripts/phase2_corpus_status.py
```

The full application and original-source parsers **do** require the dependencies declared in `pyproject.toml` (including `python-calamine`). On a local Python installation, activate a project virtual environment and install the declared package rather than installing individual dependencies globally:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
```

Do not confuse this offline registry report with the database/source-reconciliation acceptance run.

The default offline inventory is deliberately short. Use `--details` for per-analysis mapping counts or `--json` for structured output. **It does not claim that all 35 analyses are blocked**: empirical readiness requires reading original evidence and stored observations.

To ingest and independently reconcile the seven newly integrated native publisher families (59 mapped series) **against an already existing SQLite research database**, use the existing Phase 2 comparative-corpus runner in targeted-source mode. Replace both explicit paths with real local paths; the command rejects nonexistent or invalid SQLite files and missing evidence directories before any write:

```sh
PYTHONPATH=src python scripts/phase2_comparative_corpus.py \
  --database-url "sqlite+pysqlite:////absolute/path/to/existing-research.sqlite3" \
  --source-evidence-dir "/absolute/path/to/existing-source-evidence" \
  --new-sources --acquire > phase2-native-acquisition.json
```

`--source-ids activity.us.oecd_cli bank.us.fdic_total_assets` can replace `--new-sources` to operate on an explicit subset. Without `--acquire`, the same command only reconciles existing original responses against the stored database. A passing targeted run proves current source-value consistency for that subset, **not** observation first-publication timing, complete structured-source evidence or 35-analysis certification. The original corpus evaluation remains the canonical path for analysis-level readiness; there is no new ingest engine.



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

The canonical schema derives source references from original roles, native comparison variants and explicit context inputs. API and CLI share one evaluation transaction, so concurrent revisions cannot mix older reconciliation with newer coverage. Individual question requests inspect only their own sources and relevant artifacts. Holdings and regional profit summaries disclose partial availability without satisfying original worldwide roles.

Run `python scripts/phase2_comparative_corpus.py --store` to reconcile available originals and archive exact input/panel rows. This reads the database; `--store` writes evidence artifacts. Add `--acquire` to explicitly refresh complete histories through existing append-only ingestion first. `--only M02 L01` limits the analyses; `--required-inputs` includes every original/context input and role diagnostics. `--holdings-dir` or `FINANCE_HOLDINGS_DIR` explicitly selects the existing holdings archive. Original responses, source contracts, native units, no-fill exclusions, hashes and temporal limits remain attached to the result.

French equity research portfolios and the pinned Swinkels sovereign-return workbook are named benchmark alternatives. Their native percent/decimal units and local currencies remain explicit. Full French outputs and large original matrices stay in private evidence; source fixtures document redistribution rights and exact original hashes.

The Doeswijk–Swinkels USD nominal global **multiasset** research-portfolio return uses the same canonical ingestion and independent reconciliation. It is not an equity or bond benchmark. Native CVM issuer filings retain fiscal periods, filing revisions, BRL scales and source discrepancies without creating a worldwide profit aggregate.

`python -m finance_dashboard.sec_holdings_sync --recover-raw --limit 50` recovers original XML for existing verified SEC aggregates, checking their original SHA and retaining aggregate bytes. Read native facts at `/api/holdings/vt/positions?accession=0000857489-26-000275`. Named original UCITS annual PDFs/current CSVs use `finance_dashboard.ucits_holdings` and `/api/holdings/ucits/sources`; annual equity/NAV controls do not establish complete derivative or issuer mappings.

`python -m finance_dashboard.icio --package RR_WLD_2026_593.zip --readme ReadMe_ICIO_small.xlsx` verifies and archives the identified original 2022 OECD regular matrix and its source accounting diagnostics. `/api/source-evidence/icio` reports those diagnostics. The present original has accounting residuals above serialization-rounding bounds; it is preserved with a failing gate and is never silently rebalanced.

The full Python suite accepts `TEST_POSTGRES_URL` for a disposable PostgreSQL database, `TEST_ICIO_PACKAGE` for the original 55 MB replication ZIP, `TEST_GLOBAL_MARKET_PACKAGE` for the original global-return workbook and `TEST_CVM_PACKAGE` for the original annual ZIP. External checks are explicitly skipped when their inputs are absent, including during the ordinary Docker build. Tests never need the live production database.
