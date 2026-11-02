# Data coverage and blockers (Phase 2 expanded)

The source catalog has **27** indicator definitions (26 original + 1 separately named World Bank monthly-gold measure): **23 mapped** (including 3 additional country-level BIS credit gaps), 3 FRED credential-gated; **7 original series unresolved**. This document distinguishes
an implementable adapter from verified observations and legal permission to
republish data to GitHub Pages.

| Provider / category | Coverage | Reason |
|---|---|---|
| BIS quarterly country credit gaps | 3 mapped | Q.US/Q.XM/Q.JP: CG_DTYPE=C, private nonfinancial borrowers and all lenders; no fabricated global aggregate |
| BIS central bank policy rates | 3 mapped, live verified | SDMX 1.0 decoder and historical backfill in PostgreSQL |
| FRED Fed corridor, US TIPS and Sahm Rule | 3 mapped, **credential-gated** | FRED JSON API requires FRED_API_KEY; opt-in public CSV fallback is unreliable and unverified in CI |
| ECB deposit facility | 1 mapped, adapter | Official ECB CSV format |
| World Bank real GDP and listed-cap/GDP | 8 mapped, live verified | Indicators v2 JSON API, all 6 GDP geographies plus both capitalization ratios verified |
| IMF world general-government debt | 1 mapped, live verified | April 2026 WEO DataMapper, not October WEO; current and future calendar years excluded |
| Siblis global ACWI CAPE | 1 mapped, live endpoint verified | Sparse proprietary free-tier snapshot series, noncommercial use. Public GitHub Pages redistribution **not permitted without separate licence**; no interpolated history |
| ILO / UNSD world labour share | 1 mapped, live verified | Official UN SDG 10.4.1 `SL_EMP_GTOTL` world (M49=1), ILO-custodied; filter global reporting and all ages |
| BIS global private credit gap | Unresolved | There is no single well-defined worldwide country-comparable credit-gap series; individual geographies must be specified |
| Robert Shiller US CAPE | 1 mapped, live verified | Official Shiller workbook, dynamic link discovery, Excel header checks; redistribution rights still need review |
| MSCI/global profit/concentration | Unresolved | Complete histories and redistribution rights generally require licensed index data |
| World Bank monthly gold price | 1 mapped, live verified | Pink Sheet monthly average USD/troy oz since 1960; openly licensed CC BY 4.0 with attribution. Daily spot and total returns remain separate unresolved series |
| Productivity versus compensation | Unresolved | World aggregate with harmonized wages/output coverage not selected |
| US Tobin's Q | Unresolved | Valuation methodology and source definition not selected |

All 20 mapped entries can now enter the ingestion worker. The other 7 are; one additional monthly gold average source has been introduced separately
**blocked source specifications**, never silently substituted with a US series or
an invented global aggregate.

## Evidence / API contracts

- BIS: https://stats.bis.org/api-doc/v2/
- FRED REST: https://fred.stlouisfed.org/docs/api/fred/series_observations.html
- FRED public CSV: https://fred.stlouisfed.org/help/data/downloading/using-the-download-data-link/
- ECB CSV: https://data.ecb.europa.eu/help/api/data-examples
- World Bank V2: https://datahelpdesk.worldbank.org/knowledgebase/articles/898581-api-basic-call-structures
- IMF WEO portal: https://data.imf.org/datasets/WEO
- ILO labour income datasets: https://ilostat.ilo.org/data/

## Export warning

A successful fetch does **not** establish permission to redistribute the raw
data in a public static GitHub Pages deployment. Store provider rights with
the series; complete rights reviews before enabling public JSON export.

## Current verification (2026-11-02)

- Offline contracts and PostgreSQL integration: [GitHub Actions](https://github.com/tpepels/finance_dashboard/actions/runs/41453185646).
- All **13 mapped non-FRED/non-BIS** series: [live acceptance](https://github.com/tpepels/finance_dashboard/actions/runs/41453185610).
- All **3 BIS** rates plus full PostgreSQL ingestion/API: [Docker acceptance](https://github.com/tpepels/finance_dashboard/actions/runs/41449348048).
- **3 FRED** sources have parser/transport tests but no verified authenticated production call because no FRED_API_KEY was supplied.
- 8 other original indicator definitions remain unresolved. The original `gold.usd.spot` remains unresolved: monthly-average gold has a separate canonical series ID.

## Global CAPE licensing

The free Siblis ACWI CAPE API is authenticated-free but proprietary. Provider permits non-commercial personal research; public-site reproduction of complete datasets or API-powered charts requires a separate redistribution agreement. The original series ID now maps to a genuine ACWI CAPE dataset, but no public Pages export is authorized. Source: https://siblisresearch.com/data-licensing/.
