# Scheduled static-data pipeline for GitHub Pages

The backend generates source-traceable JSON from **every mapped catalog series** (currently **42 macro/index sources**) without a permanent FastAPI or PostgreSQL instance.

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

The exported macro catalog now includes official BEA Q1 (replacement-cost Tobin Q), MSCI ACWI NETR USD index levels, a 36-month monthly-average gold/index return correlation, the ILO world GDP/labour-income hourly ratio identity and a 43-economy GDP-weighted BIS credit-gap composite with a separate world-GDP coverage series. The original complete historical monthly MSCI top-ten index-weight history and worldwide listed-company earnings/GDP are **superseded and archived**, not claimed as mapped. The user-approved sources provide sparse **MSCI ACWI index** concentration snapshots and **EU27** corporate gross surplus percentages, not the unavailable original economic definitions; see [amendment](PHASE_2_FREE_SOURCE_REPLACEMENTS.md). Four world valuation macro sources are now mapped and exported: 51 WDI world capitalization USD observations, 51 matched WDI capitalization/world-GDP ratios, and 11 public Siblis global-index trailing P/E plus 11 same-universe earnings-yield snapshots. The [complete **39-series** static export passed](https://github.com/tpepels/finance_dashboard/actions/runs/41498656329), including eight dated MSCI ACWI index concentration points, 24 matched annual EU27 corporate surplus/GDP points and 27 Eurostat NFC/GVA profit-share points. Siblis remains proprietary and must not automatically be published to Pages.

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

### Final macro scope amendment and static export 2026-11-02

The [approved free-public-source replacement](PHASE_2_FREE_SOURCE_REPLACEMENTS.md) provides the following **three** mapped additional datasets, included in the passing [39/39-series static export](https://github.com/tpepels/finance_dashboard/actions/runs/41498656329): `concentration.global.msci_acwi_published_top10` (8 documented **sparse** index snapshots with exact dates/URL archive); `profit.eu27.corporate_operating_surplus_gdp` (24 annual 2002–2025 matched EU27 nominal corporate gross surplus/GDP readings); and `profit.eu27.nonfinancial_gross_surplus_value_added` (27 official NFC gross profit/GVA year readings). Neither original unavailable world-listed net-earnings series nor a fabricated monthly MSCI history is published as though observed. An export without required mapped data fails atomically. Publication rights for MSCI and Siblis remain subject to review. [39-source PostgreSQL/API integration passed](https://github.com/tpepels/finance_dashboard/actions/runs/41499045751).

## OECD source expansion — 42/42 live static export accepted

[Complete 42-series source and 24 optional market static build](https://github.com/tpepels/finance_dashboard/actions/runs/41503489558) includes three separate official-OECD-sourced data-layer outputs: 25 years (2000–2024) of **GDP-weighted 38-current-member OECD reporting-country corporate gross-surplus/GDP**, 25 corresponding annual GDP coverage percentages (>=80%), and 25 participating-member counts (>=29). Country GDP denominators come from same-year OECD GVA + product taxes, with a narrowly matched World Bank current-local-currency GDP fallback for USA/JPN/CAN when OECD tax components are absent; WDI current USD GDP provides weights. Original EU27 and all 39 previous series remain. This does not license public reproduction of restricted MSCI/Siblis material. [42-series PostgreSQL/FastAPI verification](https://github.com/tpepels/finance_dashboard/actions/runs/41503545569) and [methodology](OECD_CORPORATE_SURPLUS.md).
