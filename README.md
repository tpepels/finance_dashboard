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
PYTHONPATH=src python -m finance_dashboard research corpus
```

The full application and original-source parsers **do** require the dependencies declared in `pyproject.toml` (including `python-calamine`). On a local Python installation, activate a project virtual environment and install the declared package rather than installing individual dependencies globally:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
```

Do not confuse this offline registry report with the database/source-reconciliation acceptance run.

The default offline inventory is deliberately short. Use `--details` for per-analysis mapping counts or `--json` for structured output.

For OECD STAN 2025, the first Portugal full-history acquisition returned
publisher **HTTP 500**, and no STAN originals were archived. The original
adapter also wrongly expected `TRANSACTION` and `VALUATION` CSV fields,
rather than the STAN-native `MEASURE` and `PRICE_BASE` dimensions.
The current parser uses the native publisher field identities, and acquisition
still refuses to invent or accept missing historical observations.

Before attempting the large historical request again, run the single
read-only, narrowly bounded publisher diagnostic:

```sh
docker compose exec -T finance-dashboard \
  python -m finance_dashboard stan acquire \
  --evidence-dir /data/source-evidence \
  --countries PRT --since 1970-01-01 \
  --diagnose --probe-year 2020
```

The diagnostic issues at most eight one-year queries: a publisher-documented
B1G value-added key for total activity with and without the CSV format query
parameter, an all-industry B1G key, four other proposed input-measure keys,
and the complete candidate group restricted to total activity. It reports
HTTP status, safe failure categories and SHA-256 of accepted source CSVs,
without exposing publisher HTML errors, creating source bindings, modifying
SQLite or archiving unverified inputs. Publisher backpressure (429/503)
stops further requests.

After the **2026-11-05 live diagnostic**, four original measures were
retrievable for Portugal in 2020: B1G, D1, P51C, D29X39. The candidate B2N
returned **HTTP 404 for PRT/_T/2020** (which is not proof of absence across
industries/years); the final combined query returned **HTTP 429**. OECD
documents a limit of **60 data downloads per hour** and discourages
unnecessary repeated requests; VPN traffic may also be restricted:
<https://www.oecd.org/en/data/insights/data-explainers/2024/11/Api-best-practices-and-recommendations.html>.

The standard `--acquire` operation now requests the **four verified
Portugal candidate codes** in a single multi-industry, historical query per
country. It never fills missing B2N data and never claims a complete labour,
income or capital accounting matrix. Original responses, full requested
measure selections, request keys and source identities are archived under
separate native-measure scopes. Receipt verification re-hashes each original
response and re-parses the same native dimensions. Previously validated
same-scope archives are reused without another OECD request.

From the development machine, after the publisher rate limit has cleared:

```sh
docker compose exec -T finance-dashboard \
  python -m finance_dashboard stan acquire \
  --evidence-dir /data/source-evidence \
  --countries PRT --since 1970-01-01 --acquire
```

To request a different selection explicitly use `--measures B1G D1 B2N P51C D29X39`,
without pretending the unsupported B2N 2020 selection is an original
operating-surplus source. A 429 or 503 ends the batch and marks unrequested
countries as deferred. No automatic retry loop or artificial imputation is
permitted. Successfully verified partial archives remain readable and all
missing candidate measures, observed years, native observation status flags
and the unavailable scientific-role bindings are exposed. Do not rerun the
eight-request `--diagnose` sequence; retain the 2026-11-05 probe results.
A full history is not certified merely because `--since 1970` was
requested; it must be verified from actual source periods and native dimensions.

Use `PYTHONPATH=src python -m finance_dashboard research corpus --candidates` to see the original dataset investigations for L01–L03. These are unverified publisher candidates; no empty source bindings are filled and no analysis is certified by the candidate list. After a native acquisition, summarize the saved JSON report without copying its full contents:

```sh
cat phase2-native-report.json | docker compose exec -T finance-dashboard \
  python -m finance_dashboard research corpus --run-report -
```

Run this pipe on the media-server host from `~/media-stack`, where the acquisition JSON was saved. No second copy in `/data` is required. Add `--details` for per-analysis gap rows or `--json` for machine-readable, credential-free diagnostics. This command does not reopen the database or rehash the original evidence, and reports incomplete source acquisition as a nonzero exit status.
 **It does not claim that all 35 analyses are blocked**: empirical readiness requires reading original evidence and stored observations.

To acquire and independently reconcile the seven newly integrated publisher families
(**59 mapped series**) and produce the empirical 35-analysis gap report, run this
**inside the existing development/research container** after updating its code.
It uses the established SQLite and evidence paths; this is not a production operation.
It requires the full declared Python dependencies, including `python-calamine`.

```sh
python -m finance_dashboard research compare \
  --database-url sqlite+pysqlite:////data/finance.sqlite3 \
  --source-evidence-dir /data/source-evidence \
  --backup-dir /data/backups/phase2-acquisition \
  --vintage-dir /data/vintages \
  --holdings-dir /data/holdings \
  --new-sources --acquire --assess-all --store \
  > /data/phase2-native-report.json
```

The command fails before any ingestion if the SQLite file is absent, invalid, or
does not contain the research tables, or if the evidence directory is missing.
It writes an unpruned, independently verified **before** backup, acquires complete
publisher histories through the existing append-only ingestion and SHA-256 original-response
capture, then writes a verified **after** backup. It independently reconciles all 59
histories and evaluates the 35 analyses using the single canonical research engine.
ALFRED information-available-as-of snapshots and original fund holdings are
evaluated from their explicitly selected archives without treating either as
evidence of observation first publication. Missing archives remain missing.
The output identifies failed acquisitions, mismatching source histories and the
remaining original-method, publisher-dimension and release-vintage barriers.
A success exit code for 59 sources **does not certify** the research analyses.

Use `--source-ids activity.us.oecd_cli bank.us.fdic_total_assets` instead of
`--new-sources` for a restricted publisher acquisition. Omitting `--acquire`
performs read-only reconciliation; `--assess-all` additionally evaluates the
full historical data and original structured artifacts. The original evidence
bundles and separate verified backups remain under `/data`; copy recovery
bundles off the same physical disk for independent disaster recovery.

The single Compose service is `finance-dashboard`. The image includes the application package, original Fed reference evidence, and offline test fixtures. Docker build validates syntax, catalog and frontend tests; the full Python offline integration suite runs in CI, not at Docker build time. Operational commands use `python -m finance_dashboard`.

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
docker compose exec -T finance-dashboard python -m finance_dashboard sources probe --since 2024-01-01
```

Source-contract inventory without network access or DB mutation:

```bash
docker compose exec -T finance-dashboard python -m finance_dashboard research corpus
```

Run the Compose commands above from the existing `~/media-stack` project on `media-server`. Deploy a clean build there with `docker compose --progress plain build finance-dashboard` followed by `docker compose up -d --no-deps finance-dashboard`. Keep its existing `/srv/finance-dashboard:/data` mount. The repository's standalone Compose file instead uses `FINANCE_DATA_DIR`; do not start a second stack beside the existing service.

Original WID inequality files and published OECD TiVA inputs retain their raw source snapshots under `/data/source-evidence`, included in verified backups. `python -m finance_dashboard sources reconcile` checks the raw source values against the latest stored observations without writing to the database. These sources still require comparative and release-vintage validation; passing tests or storing series does not complete Phase 2.

The Phase 2 corpus now records explicit original input roles for all 35 approved questions and executable bounded comparison variants. `GET /api/research-corpus` derives their evidence from current observation versions and independently checked originals. Source availability, current-snapshot panels and full scientific acceptance are separate; Phase 2 remains incomplete.

The canonical schema derives source references from original roles, native comparison variants and explicit context inputs. API and CLI share one evaluation transaction, so concurrent revisions cannot mix older reconciliation with newer coverage. Individual question requests inspect only their own sources and relevant artifacts. Holdings and regional profit summaries disclose partial availability without satisfying original worldwide roles.

Run `python -m finance_dashboard research compare --store` to reconcile available originals and archive exact input/panel rows. This reads the database; `--store` writes evidence artifacts. Add `--acquire` to explicitly refresh complete histories through existing append-only ingestion first. `--only M02 L01` limits the analyses; `--required-inputs` includes every original/context input and role diagnostics. `--holdings-dir` or `FINANCE_HOLDINGS_DIR` explicitly selects the existing holdings archive. Original responses, source contracts, native units, no-fill exclusions, hashes and temporal limits remain attached to the result.

French equity research portfolios and the pinned Swinkels sovereign-return workbook are named benchmark alternatives. Their native percent/decimal units and local currencies remain explicit. Full French outputs and large original matrices stay in private evidence; source fixtures document redistribution rights and exact original hashes.

The Doeswijk–Swinkels USD nominal global **multiasset** research-portfolio return uses the same canonical ingestion and independent reconciliation. It is not an equity or bond benchmark. Native CVM issuer filings retain fiscal periods, filing revisions, BRL scales and source discrepancies without creating a worldwide profit aggregate.

`python -m finance_dashboard.sec_holdings_sync --recover-raw --limit 50` recovers original XML for existing verified SEC aggregates, checking their original SHA and retaining aggregate bytes. Read native facts at `/api/holdings/vt/positions?accession=0000857489-26-000275`. Named original UCITS annual PDFs/current CSVs use `finance_dashboard.ucits_holdings` and `/api/holdings/ucits/sources`; annual equity/NAV controls do not establish complete derivative or issuer mappings.

`python -m finance_dashboard.icio --package RR_WLD_2026_593.zip --readme ReadMe_ICIO_small.xlsx` verifies and archives the identified original 2022 OECD regular matrix and its source accounting diagnostics. `/api/source-evidence/icio` reports those diagnostics. The present original has accounting residuals above serialization-rounding bounds; it is preserved with a failing gate and is never silently rebalanced.

The full Python suite accepts `TEST_POSTGRES_URL` for a disposable PostgreSQL database, `TEST_ICIO_PACKAGE` for the original 55 MB replication ZIP, `TEST_GLOBAL_MARKET_PACKAGE` for the original global-return workbook and `TEST_CVM_PACKAGE` for the original annual ZIP. External checks are explicitly skipped when their inputs are absent, including during the ordinary Docker build. Tests never need the development research database.
