# Current architecture

Reviewed **2026-11-11**. [Development plan](DEVELOPMENT_PLAN.md) is the sole roadmap; [project review](PROJECT_REVIEW.md) records measured evidence and gaps; [RUNNING.md](RUNNING.md) covers operation.

## Runtime and persistence

One container, built from the root `Dockerfile`, serves the built React/TypeScript/ECharts frontend and FastAPI API. Node is used only in the frontend build stage. `start.sh` validates the catalogue, runs Alembic migrations and starts one Uvicorn worker on `0.0.0.0:8080`.

The standalone Compose service maps port 5052 by default and bind-mounts `FINANCE_DATA_DIR` at `/data`. This works on the local computer and a Linux LAN server. Each installation owns a local-disk SQLite WAL database and independent original archives. There is no separate frontend runtime, PostgreSQL service, Redis or scheduler container. PostgreSQL remains an optional integration-test target.

`FINANCE_BIND_HOST` controls host publication: `127.0.0.1` for this host, a LAN IP or `0.0.0.0` for network access. API calls use the page's `/api` origin. The app has no authentication and is intended for trusted-network access.

## Responsibility boundaries

| Component | Responsibility |
|---|---|
| `definitions/` and `catalog.py` | 398 mapped source definitions, 37 research questions, 21 original source-chart definitions and registered market instruments; counts measured on review date |
| `providers.py`, provider registry/adapters and source modules | Fetch/parse original native publisher observations through shared HTTP/publisher policy; never invent missing values |
| `database.py` and `migrations/` | Append-only observation/market/FX versions, ingestion runs and evidence references in SQLite WAL |
| `source_capture.py`, reconciliation modules and archive readers | Preserve source responses/receipts and independently compare originals with stored values |
| `source_policy*` | Shared publisher request budgets, cooldowns, operator attestations and durable rate ledger |
| `research_acceptance.py`, `research_runtime.py` | One evidence acceptance model for source roles and research questions |
| `engine/` | Compute result bundles with accepted inputs, named transforms/formulas, values/estimates, limitations and export; 37 engine definitions |
| `api.py` | Same-origin data, analyses, portfolio inputs, source evidence and operations; expensive acceptance evaluated in a cached background job |
| `standalone.py`, `worker.py` | One in-process refresh thread, macro/optional market collection, optional Wisesheets/vintage/holdings tasks and daily backup |
| Frontend panels, `Overview`, `Workbench` | Read engine bundles; overview and searchable catalogue lead to eight analysis panels |
| `analysisShell.tsx`, `TimePanel.tsx`, chart helpers | Methods, sources, limitations, AI export, charts and zoom presets; independently configurable saved figures are still planned |
| `owner_inputs.py` | Validate/atomically save portfolio inputs at `/data/owner-inputs.json`; clearly identify the example until owner values are saved |
| `backup.py` | Consistent online SQLite copy, selected evidence/earnings archives, hashes, integrity checks and bounded retention |

## Evidence and calculation contracts

Native reference periods, application ingestion/revision times and original public-release availability are distinct. Genuine ALFRED/release archives are integrated where accepted; an application's first-seen timestamp never substitutes for historical publication evidence.

The analytical engine gates original-method output on research acceptance. Explicit verified alternatives can be shown under their own labels while the original remains deferred. An incomplete analysis can therefore correctly have no values on an otherwise healthy installation. Acceptance can regress after revisions or evidence changes; historical closure is not permanent certification.

National-account surplus, listed net income and Marxian surplus-value measures retain separate conceptual populations and denominators. Missing periods stay missing. No unsupported crash probability, synthetic risk score or implicit timing signal is produced.

Portfolio P04/P05 use owner allocations, shock assumptions and historical replay. Rebalancing rules, contributions/withdrawals, trading costs and tax modes are implemented; historical coverage, par-bond reconstruction and currency/hedging approximations remain explicit. Their independent release validation is outstanding.

The source explorer is the provenance/inspection layer. Pre-engine research, risk, insight, market comparison, vintage backtest and Marxian-accounting routes were retired; do not restore them as parallel calculation paths.

## Operational limits

- Service health (`/api/health`) checks database connectivity, not empirical corpus completeness. Acceptance loading can return 503 with `Retry-After` while the UI retries.
- Automatic backups run after the refresh cycle, not as a pre-migration startup backup. Disable automatic refresh and its automatic backup cycle is also disabled.
- Current backups omit the portfolio-input file and source-policy ledger. Until task 2 expands recovery coverage, transfer/recover a complete stopped data tree. Scheduled bundles alone are not complete application-state recovery.
- Backups on the same disk do not protect against disk loss; retain an independent complete copy.
- Some Compose scheduler flags are hardcoded; use the runbook's override procedure for an offline smoke test.
- Dependency locks exist untracked in the reviewed workspace, but Docker does not yet use them. Reproducible-build adoption is planned.

## Verification

`.github/workflows/python-static.yml` runs Python syntax/selected Ruff checks, the full offline suite and supported CLI checks. Docker build runs frontend tests/build, Python syntax and catalogue validation. The full Python suite is separate from image build. Frontend/browser/container/recovery CI coverage remains in the completion plan.

The 2026-11-11 review checked full Python/frontend tests, a frontend build, cached-layer image build, fresh non-root Compose startup/persistence, host LAN-interface health and native startup. Actual destination-server and second-device verification remain required.
