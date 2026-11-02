# Global Capital Monitor

A source-traceable financial and macroeconomic research application for global equity, labour, credit, valuation, and gold risk.

## Phased delivery

| Phase | Deliverable | Status |
|---|---|---|
| 1 — Data contracts | Validated source and chart catalog, methodology/rights flags | Complete |
| 2 — Data infrastructure | Macro feeds, 24 stock/ETF listings, ECB FX, adjusted returns, corporate actions, PostgreSQL, worker and FastAPI | **32 mapped macro/index series + 24 market + 3 FX verified; two originals unresolved** |
| 3 — Dashboard | React combined graphs, filtering and static GitHub Pages export with redistribution checks | Not started |
| 4 — Analytics | Derived economic indicators, ETF/gold portfolio and risk comparison | Not started |

The catalog now contains **34 series definitions**: 32 operational provider mappings and 2 unresolved economic measures. “Mapped” does not imply the provider has granted public redistribution rights. The 32 mapped series have been checked against live source responses, including the three BIS policy rates in a separate Docker/PostgreSQL acceptance run and all 23 other series through the source acceptance workflow.

**Phase 2 remains open** because two original indicators still lack full defensible historical source data: MSCI ACWI historical top-ten constituent concentration and worldwide listed-company profits as a percentage of GDP. The previously missing market-data layer is now fully integrated: 24 global/EU/US ETF and stock listings, three ECB FX feeds, source-adjusted closes, dividend and split history, EUR performance, and two labelled GLD/VT proxy correlations. See [market-data contracts](docs/MARKET_DATA.md) and [data coverage](docs/DATA_COVERAGE.md).

## Run locally

Requires Docker Compose, a network connection, and a PostgreSQL password.

```bash
cp .env.example .env
# Change POSTGRES_PASSWORD in .env to a long random secret
docker compose up --build -d
docker compose logs --tail=50 worker
curl http://127.0.0.1:8080/api/data-status
```

The `worker` fetches and stores every mapped macro series, all 24 registered exchange listings, and three ECB FX pairs by default, including FRED without a key via its public observations table. `FRED_API_KEY` is optional and enables the official keyed JSON interface instead. Ingestion errors preserve the last successful observations, log an ingest-run failure, and are exposed in the status API.

For a manual refresh:

```bash
docker compose exec worker python -m finance_dashboard.worker --once
# Optional: select a provider from the supported provider list
docker compose exec worker python -m finance_dashboard.worker --once --provider FRED
# Or explicitly rescan full history for older revisions
docker compose exec worker python -m finance_dashboard.worker --once --full
# Market-only backfill/refresh, including corporate actions and FX:
docker compose exec worker python -m finance_dashboard.worker --once --market-only
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

Market data API:

```bash
curl -sS http://127.0.0.1:8080/api/markets
curl -sS http://127.0.0.1:8080/api/market/status
curl -sS -X POST http://127.0.0.1:8080/api/market/query \
  -H 'Content-Type: application/json' \
  -d '{"instrument_ids":["vwce.de","vwrl.as","vt","gld"],"start":"2025-01-01"}'
curl -sS 'http://127.0.0.1:8080/api/market/gold-world-proxy?currency=EUR&window_months=36'
```

Raw and adjusted price returns, vendor-adjusted index, dividend-reinvested index and EUR-adjusted returns remain distinct. The two gold/VT correlations are explicitly **ETF proxies**, not the original global-index/spot-gold definition.

## GitHub Actions static data build

A scheduled workflow now validates the repository secret **FRED_API_KEY**
through the official FRED API, fetches all mapped series, and uploads a
key-free **finance-dashboard-static-data** JSON artifact. It runs daily at
06:20 UTC and on manual dispatch. The expanded build successfully exported **32 macro/index series + 24 ETF/stock histories + three ECB FX feeds + two ETF proxy correlations**: [successful full-market static build](https://github.com/tpepels/finance_dashboard/actions/runs/41470215544).

See [static export architecture and secret handling](docs/STATIC_DATA.md).
This produces the data needed by a future GitHub Pages frontend; **Pages is
not yet deployed**, because the React dashboard belongs to Phase 3.

## Verification

- [Full live source acceptance — 23 non-BIS-policy series](https://github.com/tpepels/finance_dashboard/actions/runs/41459407905): includes all FRED series using the public table and the Federal Reserve's corporate equity/net-worth series, gold spot quote, BIS credit gaps, Siblis ACWI CAPE, World Bank WDI/Pink Sheet, IMF, ECB, ILO/UNSD and Shiller.
- [Three BIS policy-rate series, real Docker/PostgreSQL backfill and FastAPI query](https://github.com/tpepels/finance_dashboard/actions/runs/41449348048).
- [Short offline / PostgreSQL integration test suite](https://github.com/tpepels/finance_dashboard/actions/runs/41459407973).
- [Market static build: 24 instruments, 3 FX feeds](https://github.com/tpepels/finance_dashboard/actions/runs/41470215544).
- [Market Docker/PostgreSQL acceptance: all 24 listings](https://github.com/tpepels/finance_dashboard/actions/runs/41470443707).
- [Open Phase 2 completion tracker](https://github.com/tpepels/finance_dashboard/issues/1).

In the three-series BIS Docker test, 26,416 US, 10,130 euro-area, and 24,914 Japanese historical observations were ingested and queried. No permanent deployment has been created. All 24 market instruments and three ECB FX feeds additionally passed [full historical Docker/PostgreSQL ingestion and API validation](https://github.com/tpepels/finance_dashboard/actions/runs/41470443707). The other 29 non-BIS-policy macro/index sources have live source/fixture validation but have not been jointly production-backfilled in the same Docker run. Published revisions can be reingested without destroying the prior observed values; the application's first-seen timestamp is **not** a provider publication vintage.

## Limits

The API does not offer trade instructions, generic market-data redistribution, a React dashboard, historical true-spot gold prices, or a consistent world financial-company profit aggregate. The Siblis ACWI CAPE free API supplies sparse proprietary snapshots for personal noncommercial research; **do not publish its data to GitHub Pages without separate rights**. See [Source policy](docs/DATA_POLICY.md), [architecture](docs/ARCHITECTURE.md), and [Phase 2 details](docs/PHASE_2.md).


## Four exact original indicators resolved (2026-11-02)

The six Phase 2 data-definition gaps have been reduced to two:

- **US Tobin's Q:** published BEA Q1 (equity market value divided by current replacement-cost net stock of produced assets), annual 1960–2024; not the unrelated Fed NCBCEPNW proxy.
- **Global labour productivity/pay:** an exact **implied** GDP-per-hour to all-labour-income-per-hour ratio derived as 100 / ILO SDG world labour-income-share percentage. The same global hours cancel. Not independently sampled hourly wages; includes imputed self-employment labour income.
- **International credit-gap composite:** 43 individual BIS national private credit/GDP gaps, GDP-weighted using previous-year nominal USD WDI GDP. Excludes euro-area aggregate to avoid double counting. Releases quarters only when countries with data cover at least 80% of world GDP. **Not an official BIS-published world gap.**
- **Gold/global equity index:** World Bank monthly mean gold vs real **MSCI ACWI NETR USD index** levels, both averaged over each month, Pearson rolling on 36 consecutive monthly returns; not the GLD/VT ETF proxy.

The two outstanding exact datasets are historical MSCI ACWI constituent free-float weights and consolidated worldwide **listed-company earnings** with defensible multinational allocation. A current index fact-sheet or index P/E snapshot cannot reconstruct either history. See [exact gap audit](docs/ORIGINAL_GAPS.md).

Historical issuer NAV reconciliation, ticker rename continuity, and a combined 32-source PostgreSQL production backfill are also separately tracked as remaining Phase 2 acceptance criteria.
