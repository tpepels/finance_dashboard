# Scheduled static-data pipeline for GitHub Pages

The backend generates source-traceable JSON from **every mapped catalog series** (currently 36 macro/index sources) without a permanent FastAPI or PostgreSQL instance.

## FRED authentication

The repository Actions secret must be named **FRED_API_KEY** under Settings → Secrets and variables → Actions.

The workflow **.github/workflows/static-data.yml** injects it only into the server-side Python steps. The FRED probe tests all four mapped FRED series through the authenticated official observations API. A missing or invalid key fails the workflow instead of quietly using the public HTML fallback.

Never place the key in a Vite environment variable, browser fetch URL, frontend bundle, published JSON file, or committed .env file.

## Refresh

The workflow runs at 06:20 UTC each day, can be run manually, and is triggered by relevant code/catalog changes. It:

1. Runs offline security/format tests.
2. Tests the private FRED key against the official API.
3. Fetches all mapped macro sources, all 24 ETF/stock listings, and the three ECB FX series concurrently, and calculates the two clearly labelled ETF proxy correlations.
4. Generates index.json, charts.json, one series/<canonical-id>.json for each mapped macro series, markets/index.json, markets/<listing-id>.json, fx/<ISO-currency>.json and two gold/VT ETF proxy files.
5. Uploads the complete data as the **finance-dashboard-static-data** Actions artifact.

A failed macro, market, or FX source fails the entire job; no partial artifact is published. Two unresolved indicator definitions remain explicitly flagged in the manifest. Observations and decimal values preserve native frequencies and source attribution; no invented values are added.

The manifest uses an allowlist of catalog metadata. Secrets, raw authenticated URLs, headers, arbitrary API response bodies and exception strings are never written into the artifact. Full-history refreshes produce latest-known values but cannot reconstruct genuine historical release vintages.

## GitHub Pages

**The current workflow produces a downloadable Actions artifact, not a live Pages website.** The React UI and combined charts are scheduled for Phase 3. Their build can then consume the generated JSON and deploy to Pages. The secret stays in the Python/Actions job.

Pages publication is generally public; treating a project as personal-use does not make the generated website private.

## Local validation

Install the package and run the short offline test suite:

    python -m unittest discover -s tests -v

Generate static datasets manually:

    python -m finance_dashboard.static_export --output-dir build/static-data

Without FRED_API_KEY the existing local adapter uses FRED's public data tables, but the GitHub Actions workflow intentionally requires the configured secret.

See **docs/DATA_COVERAGE.md** for the exact source catalog and remaining methodology gaps.

## Market coverage

The 24 instrument and three currency feeds are documented in [MARKET_DATA.md](MARKET_DATA.md). Both raw and corporate-action-adjusted histories, exchange venue identity, ETF share-class currency, EUR conversion and two labelled ETF proxy correlations are included in the generated artifact. The first successful full-market run is [Actions run 41470215544](https://github.com/tpepels/finance_dashboard/actions/runs/41470215544). The separate [live PostgreSQL/API acceptance](https://github.com/tpepels/finance_dashboard/actions/runs/41470443707) verified all 24 instruments and the three currencies end to end.

### Exact new index/valuation inputs

The exported macro catalog now includes official BEA Q1 (replacement-cost Tobin Q), MSCI ACWI NETR USD index levels, a 36-month monthly-average gold/index return correlation, the ILO world GDP/labour-income hourly ratio identity and a 43-economy GDP-weighted BIS credit-gap composite with a separate world-GDP coverage series. The original historical MSCI top-ten constituent concentration and world listed-company earnings/GDP remain unresolved and explicitly listed in the JSON manifest. Four world valuation macro sources are now mapped and exported: 51 WDI world capitalization USD observations, 51 matched WDI capitalization/world-GDP ratios, and 11 public Siblis global-index trailing P/E plus 11 same-universe earnings-yield snapshots. The [complete 36-series static export passed](https://github.com/tpepels/finance_dashboard/actions/runs/41492850778). Siblis remains proprietary and must not automatically be published to Pages.

### Wisesheets supplementary earnings

The nightly macro+ETF build never makes 20,000+ Wisesheets company API
requests. A separate monthly Wisesheets Actions workflow uses the
`WISESHEETS_API_KEY` secret, caps monthly requests, writes an audited
annual aggregate, and stores it in `data/wisesheets/sec_filer_profit.json`.
If present, that snapshot is included as
`supplementary/sec_filer_profit.json` and listed in
`index.json.supplementary_sources` with its real freshness status.
Before the first verified complete scan, its status is `not_collected`.
It is never mislabelled as the original global listed-company profits.
See [WISESHEETS.md](WISESHEETS.md).
