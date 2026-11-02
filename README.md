# Global Capital Monitor

A self-hosted global financial and macroeconomic research application. The application traces original economic observations back to their sources, retaining every value it sees rather than overwriting revised history.

## Delivery phases

| Phase | Scope | Status |
|---|---|---|
| 1 — Contracts | Source catalog, methodology, chart definitions, provenance and data-quality rules | Complete |
| **2 — Backend** | BIS SDMX adapter, PostgreSQL observations/revisions, background updates, FastAPI queries and offline tests | **Expanded implementation; BIS live verified; wider source acceptance in progress** |
| 3 — Dashboard | React, ECharts, source-traceable Fed/ECB/BOJ graph, time-range controls and exports | Not started |
| 4 — Analysis | Derived macro indicators, valuation, labour/capital, concentration, portfolio and gold | Not started |

Phase 2 does not include charts or a frontend. The data worker now includes BIS (3), FRED (3), ECB (1), World Bank (8), IMF DataMapper (1), Shiller (1), and UN SDG/ILO labour share (1) official source mappings. FRED requires a personal API key; the remaining unresolved indicators are clearly blocked. Unresolved indicators are **not presented as available data**. See [coverage](docs/DATA_COVERAGE.md) for actual source availability and limits.

## Quick start (Docker Compose)

Requires Docker Compose and Internet access for the scheduled worker.

\`\`\`bash
cp .env.example .env
# Set a long random POSTGRES_PASSWORD; percent-encode URL-special characters.
docker compose up --build -d
docker compose logs --tail=30 worker
curl http://127.0.0.1:8080/api/data-status
\`\`\`

Services: \`postgres\` (private volume), one-shot \`migrate\` (Alembic), \`app\` (port 8080 on loopback only) and \`worker\` (daily refresh, initial full backfill). Worker fetches immediately at boot and every 24 hours. All historical data comes directly from the BIS SDMX API. Failed updates do not discard old observations.

\`\`\`bash
# Manual full refresh, with an existing Compose stack:
docker compose exec worker python -m finance_dashboard.worker --once --full

# Catalog and source checks:
docker compose exec app python -m finance_dashboard validate
docker compose exec app python -m finance_dashboard report

# Query three daily policy rates:
curl -sS http://127.0.0.1:8080/api/series
curl -sS http://127.0.0.1:8080/api/data-status
curl -sS -X POST http://127.0.0.1:8080/api/query \
  -H 'Content-Type: application/json' \
  -d '{"series_ids":["policy_rate.us.bis","policy_rate.ea.bis","policy_rate.jp.bis"],"start":"2025-01-01"}'
\`\`\`

The independent [live acceptance workflow](https://github.com/tpepels/finance_dashboard/actions/workflows/phase2-live.yml) passed on 2026-11-02: it fetched 26,416 US, 10,130 euro-area and 24,914 Japanese observations in a disposable PostgreSQL instance and confirmed all three through FastAPI. Historical BIS null/NaN observations are missing data, never coerced to zero. This is a verified deployed-container smoke test, not a claim that a production instance has been launched.

The query API returns decimal values as **strings** to avoid silent float rounding. A snapshot timestamp means *first observed by this app*, **not** a historical BIS release vintage. The app has no authentication and is bound to loopback; do not expose it directly to the public Internet. Place behind a secured reverse proxy if remote access is necessary.

### Local development

Requires Python 3.11+ and a running PostgreSQL server for persistent ingestion.

\`\`\`bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
python -m unittest discover -s tests -v
python -m finance_dashboard validate
export DATABASE_URL='postgresql+psycopg://capital_monitor:password@localhost/capital_monitor'
alembic upgrade head
python -m finance_dashboard.worker --once
uvicorn finance_dashboard.api:app_factory --factory --port 8080
\`\`\`

For provider documentation, compliance and known limitations see [architecture](docs/ARCHITECTURE.md), [source policy](docs/DATA_POLICY.md), [Phase 1 audit](docs/PHASE_1_AUDIT.md), and [Phase 2 implementation](docs/PHASE_2.md).

## API

- \`GET /api/health\`: database readiness
- \`GET /api/series\`: catalog, including not-yet-ingested series
- \`GET /api/series/{id}\`: canonical definition and original source
- \`GET /api/charts\`: chart definitions, **not** rendered charts
- \`POST /api/query\`: up to 12 BIS series IDs, start/end dates and optional \`snapshot_at\`
- \`GET /api/data-status\`: latest attempt, latest success and error details

API documentation: \`/docs\`. There are no public write endpoints or automatic asset recommendations.
