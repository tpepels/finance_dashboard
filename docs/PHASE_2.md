# Phase 2 — Backend implementation and acceptance

As of 2026-11-02, the backend implements **32** macro/index source series, **24** stock/ETF histories and **three** ECB FX feeds with two derived ETF correlation proxies, while retaining **two** unresolved original financial measures without invented proxies. See [the per-source audit](DATA_COVERAGE.md). The Phase 2 issue remains open because the original historical MSCI ACWI constituent-concentration and worldwide listed-company profit-share datasets remain unavailable at the required completeness.

## Architecture

The provider-router chooses an adapter using canonical IDs from `definitions/series.json`. Provider responses must match exact series identifiers, geography, units and native observation periods.

- BIS SDMX-JSON: daily harmonized rates and quarterly private-sector credit-to-GDP gaps;
- FRED: preferred authenticated JSON API, or verified public DATE/VALUE observations HTML with extended rows, including quarterly values;
- ECB: official CSV policy-rate dataset;
- World Bank WDI: official annual indicators JSON; Pink Sheet: monthly gold workbook with USD per troy-ounce check;
- IMF DataMapper: explicitly version-limited historical global public debt;
- Shiller: public US CAPE workbook;
- Siblis: **proprietary** sparse ACWI CAPE free snapshots; no public redistribution;
- UNSD/ILO: annual world labour-share and productivity-growth series;
- Corgano: single current quoted gold spot midpoint/oz, UTC timestamp, no faux historical spot data.

## Persistence and temporal correctness

PostgreSQL stores original normalized source observations, append-only versions, ingest runs, provider request URLs and first-seen timestamps. Atomic source updates and bounded retries preserve last-known-good observations upon failures. Native periods are retained; data are not filled with invented daily values. Annual observations have period-start dates as storage keys and are still labelled annual.

An application-first-seen snapshot is not a true source publication vintage. Missing BIS NaN/null observations remain missing. Live spot quote source and per-ounce price contract are validated.

The scheduled worker shares the same Python codebase, runs separately from the FastAPI server and can filter any mapped provider by `--provider`. The HTTP API remains read-only and bound to loopback for local deployment.

## Verification

- [BIS full Docker/PostgreSQL/API acceptance](https://github.com/tpepels/finance_dashboard/actions/runs/41449348048): US 26,416; euro area 10,130; Japan 24,914 observations.
- [23 other live source checks](https://github.com/tpepels/finance_dashboard/actions/runs/41459407905), including all four FRED series without a key.
- [Fast offline/PostgreSQL tests](https://github.com/tpepels/finance_dashboard/actions/runs/41459407973).

The live macro source checks validate actual provider responses and parsers. The separate full-market PostgreSQL/API end-to-end run verified all 24 assets, three FX feeds and EUR calculation, documented in [MARKET_DATA.md](MARKET_DATA.md). A combined permanent production deployment and public GitHub Pages site have **not** occurred, and should not be claimed. Data-rights clearance is needed before any public static export.

## Markets and FX

All 24 instruments and three FX series are integrated into the scheduled worker, versioned PostgreSQL schema, read-only API, secret-protected static export and bounded live acceptance. Full source details: [MARKET_DATA.md](MARKET_DATA.md).

## Four originally missing definitions now integrated

- BEA official annual replacement-cost equity Q1 ratio.
- ILO all-labour-income/output-per-hour accounting-identity ratio.
- GDP-weighted 43-economy BIS gap composite with separate world-GDP coverage measure.
- USD World Bank monthly gold vs MSCI ACWI NETR index 36-month rolling return correlation, **not** the ETF proxy.

The latest live acceptance and complete scheduled export pass. See [exact remaining gaps](ORIGINAL_GAPS.md).

## Pending exact indicators

Worldwide **listed-company** profit share and historical MSCI ACWI free-float index top-ten constituent weights. Additional NAV/ticker continuity and all-macro PostgreSQL backfill audits remain separately outstanding. These need genuine source/licence definitions, as documented in [Data coverage](DATA_COVERAGE.md).
