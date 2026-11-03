# Global Capital Monitor

Local economic research dashboard: one page, one existing Docker service, SQLite source history and transparent economic comparisons. The application distinguishes original source measurements, calculated relationships, explicitly scoped proxies and missing evidence.

**Routine operation uses just two buttons** under **Data & sync**:

- **Sync current data** — refresh all registered macro series (including PWT countries), 24 market instruments, three ECB FX histories and quota-aware Wisesheets earnings. Verify a local backup afterward.
- **Sync history** — request complete registered macro and market/FX histories, resume genuine dated ALFRED releases, collect original verified SEC holdings (bounded to 50 filings per fund), then verify a local backup. Missing sources and licensing gaps remain explicitly reported.

One job runs at a time, with visible progress and an option to cancel. The 80-source table, raw source dates/failure codes and full CSV audit are behind **Source diagnostics**. A separate **Developer logs** disclosure inside Source diagnostics provides the last 400 structured server events, recent job outcomes and current source issues, with Copy report and Download .txt controls. The journal is bounded and stored in the existing /data/maintenance directory; raw provider responses, headers, request URLs and API keys are not collected. No series IDs, batch sizes or provider options are needed in normal use. The only routine shell operation is deploying an updated application image.

## Current development status

**The single authoritative status/implementation roadmap is [Development plan](docs/DEVELOPMENT_PLAN.md).** It maps the original four phases to five ordered source/research work packages, includes open critiques and blockers, and specifies acceptance checks. Legacy phase plans have been archived as historical evidence and are not active instructions.

As of 2026-11-03, 53 macro source definitions, 24 market instruments, three ECB FX currencies and 46 research views are implemented in the repository. Local import completeness and scientifically exact historical research are **not** certified. The latest supplied Docker build stopped at a frontend test (43 passing, one failing); a code correction was committed subsequently but has not yet been observed passing in a Docker build.

## Deploy on the existing media server

Follow [Server source setup](docs/SERVER_SOURCE_SETUP.md) to preserve the **existing** `/srv/finance-dashboard:/data` mount, credentials and original source records. A GitHub Actions secret does not configure this server's `.env`. Do not replace your current Compose project or delete the database/backups.

```bash
cd ~/media-stack
git -C finance_dashboard pull --ff-only
docker compose config --quiet
docker compose build finance-dashboard &&
docker compose up -d --no-deps finance-dashboard
```

Open `http://media-server:5052/`. Source readiness: `/api/source-coverage` (53 macro, 24 market and 3 ECB FX rows); original observation coverage: `/api/data-status`; operational backup and credential booleans: `/api/operations`. The current service is designed for a private LAN or authenticated reverse proxy, **not** the public internet.

## Reference documentation

- [Development plan](docs/DEVELOPMENT_PLAN.md) — only active sequence, blockers, original phase mapping and empirical acceptance.
- [Complete source configuration and data-preserving import](docs/SERVER_SOURCE_SETUP.md) — environment, FRED/ALFRED, SEC N-PORT, Wisesheets, OECD, backup.
- [46-indicator source/definition matrix](docs/INDICATOR_ACCEPTANCE_MATRIX.md) — original research indicators and exact/alternative definition.
- [Scientific methodology](docs/ECONOMIC_RESEARCH_METHODS.md) and [historical-source contracts](docs/PHASE_4_RESEARCH_SOURCES.md) — analysis, provenance and source-level limitations.
- [Architecture](docs/ARCHITECTURE.md) and [data policy](docs/DATA_POLICY.md) — one-container boundaries and responsible source use.
- [Historical plans](docs/archive/) — frozen superseded specifications, not implementation instructions.

**Acceptance policy:** Committed code, passing simulated tests, live source ingestion, independent source verification and predictive validation are different states. Source substitutions are never silently treated as original exact measures.
