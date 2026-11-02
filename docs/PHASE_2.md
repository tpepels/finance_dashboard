# Phase 2 — Backend implementation and acceptance

As of 2026-11-02, the backend implements **26** operational source series and retains **six** unsupported original measurements without invented proxies. See [the per-source audit](DATA_COVERAGE.md). The Phase 2 issue remains open because the agreed full indicator scope is not yet satisfied.

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

The live source checks validate the actual provider responses and parsers. A combined 26-source production Docker backfill and public GitHub Pages deployment have **not** occurred, and should not be claimed. Data-rights clearance is needed before any public static export.

## Pending exact indicators

Tobin Q; global productivity-compensation gap; global **listed-company** profit share; licensed historical index top-ten weights; a defensible world credit gap aggregate; and gold/global equity total-return correlation. These need genuine source/licence definitions, as documented in [Data coverage](DATA_COVERAGE.md).
