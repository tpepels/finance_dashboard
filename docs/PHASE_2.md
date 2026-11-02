# Phase 2 — Backend implementation and acceptance

As of 2026-11-02, the macro backend implements **39 mapped** series, 24 optional market instruments and three optional ECB FX sources. The owner's [second free-source amendment](PHASE_2_FREE_SOURCE_REPLACEMENTS.md) superseded two inaccessible original definitions with eight public source-dated MSCI ACWI index concentration snapshots and two official Eurostat EU27 corporate gross-surplus measures. Original requirements remain archived and cannot be described as fulfilled exactly. [39-series live PostgreSQL/API acceptance](https://github.com/tpepels/finance_dashboard/actions/runs/41499045751) and [static export](https://github.com/tpepels/finance_dashboard/actions/runs/41498656329) passed.

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

The live macro source checks validate actual provider responses and parsers. The separate full-market PostgreSQL/API end-to-end run verified all 24 assets, three FX feeds and EUR calculation, documented in [MARKET_DATA.md](MARKET_DATA.md). A full **temporary** PostgreSQL backfill for all 32 mapped macro/index sources has passed ([acceptance run](https://github.com/tpepels/finance_dashboard/actions/runs/41476599670)). A **permanent** production deployment and public GitHub Pages site have **not** occurred, and should not be claimed. Data-rights clearance is needed before any public static export.

## Markets and FX

All 24 instruments and three FX series are integrated into the scheduled worker, versioned PostgreSQL schema, read-only API, secret-protected static export and bounded live acceptance. Full source details: [MARKET_DATA.md](MARKET_DATA.md).

## Four originally missing definitions now integrated

- BEA official annual replacement-cost equity Q1 ratio.
- ILO all-labour-income/output-per-hour accounting-identity ratio.
- GDP-weighted 43-economy BIS gap composite with separate world-GDP coverage measure.
- USD World Bank monthly gold vs MSCI ACWI NETR index 36-month rolling return correlation, **not** the ETF proxy.

The latest live acceptance and complete scheduled export pass. See [exact remaining gaps](ORIGINAL_GAPS.md).

## Pending exact indicators

The **original** worldwide listed-company net-profit share and continuous monthly MSCI ACWI free-float constituent history were infeasible without licensed data. The owner approved [narrower free-source substitutes](PHASE_2_FREE_SOURCE_REPLACEMENTS.md) and the original definitions were preserved in [the archive](../definitions/superseded_series.json). The substitutes are **EU27** corporation gross surplus/GDP and **sparse actual MSCI ACWI index top-ten snapshots**, not proofs of worldwide listed profits or complete monthly concentration. Optional NAV reconciliation and ticker/venue continuity remain outside Phase 2. See [locked feature contract](PHASE_2_FEATURE_CONTRACT.md), [architecture contract](PHASE_2_ARCHITECTURE_CONTRACT.md), [implementation contract](PHASE_2_IMPLEMENTATION_CONTRACT.md) and [Data coverage](DATA_COVERAGE.md).

## Macro-first 2026-11-02 implementation extension

The owner-prioritized [macro-first scope amendment](PHASE_2_MACRO_SCOPE_AMENDMENT.md) adds four global market valuation series without per-ETF holdings: WDI WLD annual listed capitalisation in USD and its ratio to WDI world GDP (51 years each), and Siblis world aggregate trailing P/E plus earnings yield on **11 public, sparse** observations each. The [36-macro complete static export passed](https://github.com/tpepels/finance_dashboard/actions/runs/41492850778). [All 36-series historical PostgreSQL ingestion and live API readback passed](https://github.com/tpepels/finance_dashboard/actions/runs/41494100275). Those two original unavailable requirements were subsequently superseded by explicit owner approval, rather than declared sourced. [Live 39/39 backend ingestion, API and static integration passed](https://github.com/tpepels/finance_dashboard/actions/runs/41499045751). Siblis and WDI universes are not interchangeable for implied worldwide earnings.

## Final amended Phase 2 macro source acceptance — 2026-11-02

Owner-approved [historical MSCI/Eurostat substitutes](PHASE_2_FREE_SOURCE_REPLACEMENTS.md) were integrated into the same provider router, canonical definitions, charts, PostgreSQL worker, FastAPI, and static JSON export. **39/39 mapped series accepted**, with 8 source-cited MSCI ACWI index top-ten weight markers, 24 years of official EU27 corporate gross operating surplus/GDP, 27 years of independently published EU27 NFC gross profit/GVA. [Live PostgreSQL/FastAPI acceptance](https://github.com/tpepels/finance_dashboard/actions/runs/41499045751) and [static source export](https://github.com/tpepels/finance_dashboard/actions/runs/41498656329) both passed. The two original historical source requirements are archived, not silently relabelled. Geographic scope limitation: OECD SDMX was blocked (HTTP 403) and the live corporate indicator is EU27-only, not world/OECD. Phase 3 frontend, production deployment and public data redistribution clearance remain separate work.
