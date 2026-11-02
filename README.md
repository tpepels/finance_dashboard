# Global Capital Monitor

A **local-only** macroeconomic research dashboard with source-traceable observations, curated comparative charts and recorded-data interpretation. One Docker container serves the React interface and FastAPI, migrates a persistent SQLite database, and refreshes macroeconomic sources automatically. No GitHub Actions, GitHub Pages, PostgreSQL container, separate frontend container or separate worker service is required.

## Run locally

```bash
cp .env.example .env
# Set UID/GID to the owner of your persistent data directory.
# Add WISESHEETS_API_KEY to .env if you want local monthly SEC filings refresh.
docker compose up -d --build
docker compose logs --tail=80 finance-dashboard
```

Open **http://localhost:5052/** (or `http://media-server:5052/` on your LAN). The bundled React interface and all `/api/*` endpoints share the same origin. The default persistent volume is `./data-local:/data`, or set `FINANCE_DATA_DIR=/srv/finance-dashboard` in `.env`. The database is SQLite in WAL mode, backed up under that directory.

**Already using a home-server Compose with Plex/Monochrome/Vinted?** Add the [single finance-dashboard service](docs/home-server-finance-service.yml) under your existing `services:` block and clone this repo alongside the other application directories. Do not launch a separate finance Compose stack. See [home server instructions](docs/HOME_SERVER_DOCKER.md).

## What the dashboard shows

Eight deliberately ordered research chapters, followed by locally collected SEC filer earnings:

1. Monetary policy — BIS harmonized Fed/euro-area/Japan rates, same frequency and economic measure.
2. Economic growth — world and major-country annual real GDP growth.
3. Credit cycle — comparable BIS national credit-to-GDP gaps; separate world composite and data coverage.
4. Equity valuations — comparable domestic market cap/GDP, followed by separate world listed-capitalization and P/E or earnings-yield measurements.
5. Labour and corporate income — *separate* labour share and productivity-growth views; OECD and EU corporate surplus with visibly distinct denominator/coverage definitions.
6. Equity concentration — real sparse MSCI ACWI top-ten weight snapshots.
7. Gold and equities — monthly gold series and separately the published 36-month index/gold return correlation.
8. Public debt — own source series, no nonsensical overlap with daily policy rates.
9. Supplementary US SEC filer earnings — annual SEC-reporting-company profits as a share of world GDP, never relabelled as total world listed-company profits.

The first row of each chapter renders its charts **immediately**; other charts appear in an editorial two-column scroll. Expand any chart to change its range (5Y/10Y/20Y/Max/Custom), choose original/index-100/percentile display, inspect exact dates, source and ingestion runs, and export CSV, PNG, configuration or a deep link.

An **Additional source histories** picker exposes all otherwise uncategorized mapped series separately. Unrelated economic measurements cannot be overlaid solely because they share a unit or can be indexed to 100.

The Python `POST /api/chart-insight` endpoint calculates source-dated latest values, approximately one-year comparisons where adequate observations exist, and cross-country high/low spreads **only on exact common source dates**. Every chart includes its economic interpretation and explicit limitations; no interpolation, causal attribution or unsupported investment signals are generated. The chart commentary is descriptive research, not a Phase 4 risk model.

## Data and local collection

- **42 mapped canonical macro/index series** in [definitions/series.json](definitions/series.json), from BIS, FRED, World Bank, Eurostat, OECD, MSCI, IMF, ILO, ECB and other documented sources. Full historical ingestion can take time. `GET /api/data-status` reports pending, stale and failed sources; failed updates leave prior observations available.
- **Wisesheets:** set `WISESHEETS_API_KEY=...` in **your local `.env`**. One bounded full-accessible-SEC-filer collection runs on startup when no recent local snapshot exists and then at most approximately monthly. A seven-day retry cooldown prevents repeated full API scans on failure. The existing bundled snapshot (2021–2025) remains a fallback. `GET /api/earnings/sec-filers` serves the actual aggregate. See [Wisesheets methodology](docs/WISESHEETS.md).
- **FRED:** `FRED_API_KEY` is optional; authenticated access is preferred. The local public observations fallback is supported.
- **Markets:** 24 optional stock/ETF histories and ECB FX collection remain available through `FINANCE_INCLUDE_MARKETS=1` but are not part of the macro dashboard's main navigation.
- Source rights remain in catalog **metadata for provenance**. There are **no UI usage gates or rights-based restrictions in this local application**. Independent third-party source licensing terms still apply if you redistribute their observations publicly.

No API credentials are sent to the frontend. No GitHub Actions workflows or GitHub-hosted data refreshes remain in the repo.

## Develop and test locally

The Docker image uses a Node build stage and a Python runtime stage. To work on the UI with the same local API:

```bash
cd frontend
npm install
npm run dev
npm test
npm run build
```

The dev server proxies `/api` to the existing container's `127.0.0.1:8080` by default. The single-container deployment exposes port 5052 externally; use `docker compose exec finance-dashboard` for local CLI data checks if the standalone API is not also bound to 8080 on the host.

Python offline tests:

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
python -m finance_dashboard validate
```

The local Docker build is **not asserted tested on your machine**. Historical [Phase 2 data acceptance](docs/PHASE_2.md) and source definitions remain documented. [Phase 3 scope](docs/PHASE_3.md) explains the difference between descriptive interpretation and advanced Phase 4 risk calculations.

## Boundaries

- Current data observations are not genuine historical publication vintages unless a source provides them.
- OECD gross corporate operating surplus/GDP is a GDP-weighted reporting-country composite with explicit coverage, not a consolidated world listed-company profit series.
- US SEC-reporting-company earnings exclude most foreign-only listed firms and historically delisted companies.
- Sparse MSCI/Siblis source snapshots remain sparse.
- No economic data are fabricated to fill empty charts, and there is no portfolio advice, trading execution, alerts or causal model.
