# Global Capital Monitor

A source-traceable financial and macroeconomic research application for global equity, labour, credit, valuation, and gold risk.

## Phased delivery

| Phase | Deliverable | Status |
|---|---|---|
| 1 — Data contracts | Validated source and chart catalog, methodology/rights flags | Complete |
| 2 — Data infrastructure | Multiple source adapters, real observations, PostgreSQL revision history, scheduled worker and FastAPI | **26 mapped and live-source verified; 6 original definitions unresolved** |
| 3 — Dashboard | React combined graphs, filtering and static GitHub Pages export with redistribution checks | Not started |
| 4 — Analytics | Derived economic indicators, ETF/gold portfolio and risk comparison | Not started |

The catalog now contains **32 series definitions**: 26 operational provider mappings and 6 unresolved economic measures. “Mapped” does not imply the provider has granted public redistribution rights. The 26 mapped series have been checked against live source responses, including the three BIS policy rates in a separate Docker/PostgreSQL acceptance run and all 23 other series through the source acceptance workflow.

**The original full-scope Phase 2 issue remains open** because six metrics cannot yet be presented from defensible worldwide datasets. See [Data coverage](docs/DATA_COVERAGE.md).

## Run locally

Requires Docker Compose, a network connection, and a PostgreSQL password.

```bash
cp .env.example .env
# Change POSTGRES_PASSWORD in .env to a long random secret
docker compose up --build -d
docker compose logs --tail=50 worker
curl http://127.0.0.1:8080/api/data-status
```

The `worker` fetches and stores every mapped series by default, including FRED without a key via its public observations table. `FRED_API_KEY` is optional and enables the official keyed JSON interface instead. Ingestion errors preserve the last successful observations, log an ingest-run failure, and are exposed in the status API.

For a manual refresh:

```bash
docker compose exec worker python -m finance_dashboard.worker --once
# Optional: select a provider from the supported provider list
docker compose exec worker python -m finance_dashboard.worker --once --provider FRED
# Or explicitly rescan full history for older revisions
docker compose exec worker python -m finance_dashboard.worker --once --full
```

Queries are read-only; the API is bound to local loopback by default.

```bash
curl -sS http://127.0.0.1:8080/api/series
curl -sS http://127.0.0.1:8080/api/charts
curl -sS -X POST http://127.0.0.1:8080/api/query \
  -H 'Content-Type: application/json' \
  -d '{"series_ids":["policy_rate.us.bis","policy_rate.ea.bis","policy_rate.jp.bis"],"start":"2025-01-01"}'
```

Other API routes: `GET /api/health`, `GET /api/series/{id}`, `GET /api/data-status`. OpenAPI at `/docs`.

## GitHub Actions static data build

A scheduled workflow now validates the repository secret **FRED_API_KEY**
through the official FRED API, fetches all mapped series, and uploads a
key-free **finance-dashboard-static-data** JSON artifact. It runs daily at
06:20 UTC and on manual dispatch. The first full build successfully exported
all 26 mapped series: [successful run](https://github.com/tpepels/finance_dashboard/actions/runs/41464962331).

See [static export architecture and secret handling](docs/STATIC_DATA.md).
This produces the data needed by a future GitHub Pages frontend; **Pages is
not yet deployed**, because the React dashboard belongs to Phase 3.

## Verification

- [Full live source acceptance — 23 non-BIS-policy series](https://github.com/tpepels/finance_dashboard/actions/runs/41459407905): includes all FRED series using the public table and the Federal Reserve's corporate equity/net-worth series, gold spot quote, BIS credit gaps, Siblis ACWI CAPE, World Bank WDI/Pink Sheet, IMF, ECB, ILO/UNSD and Shiller.
- [Three BIS policy-rate series, real Docker/PostgreSQL backfill and FastAPI query](https://github.com/tpepels/finance_dashboard/actions/runs/41449348048).
- [Short offline / PostgreSQL integration test suite](https://github.com/tpepels/finance_dashboard/actions/runs/41459407973).
- [Open Phase 2 completion tracker](https://github.com/tpepels/finance_dashboard/issues/1).

In the three-series BIS Docker test, 26,416 US, 10,130 euro-area, and 24,914 Japanese historical observations were ingested and queried. No permanent deployment has been created. The other 23 mapped sources passed live fetch/validation, not a combined production full-history backfill. Published revisions can be reingested without destroying the prior observed values; the application's first-seen timestamp is **not** a provider publication vintage.

## Limits

The API does not offer trade instructions, generic market-data redistribution, a React dashboard, historical true-spot gold prices, or a consistent world financial-company profit aggregate. The Siblis ACWI CAPE free API supplies sparse proprietary snapshots for personal noncommercial research; **do not publish its data to GitHub Pages without separate rights**. See [Source policy](docs/DATA_POLICY.md), [architecture](docs/ARCHITECTURE.md), and [Phase 2 details](docs/PHASE_2.md).
