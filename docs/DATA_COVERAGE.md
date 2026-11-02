# Data coverage and blockers (Phase 2 expanded)

The source catalog has **26** indicator definitions. This document distinguishes
an implementable adapter from verified observations and legal permission to
republish data to GitHub Pages.

| Provider / category | Coverage | Reason |
|---|---|---|
| BIS central bank policy rates | 3 mapped, live verified | SDMX 1.0 decoder and historical backfill |
| FRED Fed corridor, US TIPS and Sahm Rule | 3 mapped, adapter | FRED JSON API requires FRED_API_KEY; opt-in public CSV fallback is unreliable and unverified in CI |
| ECB deposit facility | 1 mapped, adapter | Official ECB CSV format |
| World Bank real GDP and listed-cap/GDP | 8 mapped, adapter | Indicators v2 JSON API, annual source periods |
| IMF world general-government debt | 1 mapped via DataMapper, adapter | April 2026 WEO DataMapper, not October WEO; current and future projection years excluded; methodology and vintage flag explicit |
| ILO / UNSD world labour share | 1 mapped, adapter | Official UN SDG 10.4.1 `SL_EMP_GTOTL` world (M49=1), ILO-custodied; filter global reporting and all ages |
| BIS global private credit gap | Unresolved | There is no single well-defined worldwide country-comparable credit-gap series; individual geographies must be specified |
| Robert Shiller US CAPE | 1 mapped, adapter | Official Shiller workbook, dynamic link discovery, Excel header checks; redistribution rights still need review |
| MSCI/global profit/concentration | Unresolved | Complete histories and redistribution rights generally require licensed index data |
| Gold spot and correlations | Unresolved | Source licence and precise convention (fixing/spot/total return, currency) need defining |
| Productivity versus compensation | Unresolved | World aggregate with harmonized wages/output coverage not selected |
| US Tobin's Q | Unresolved | Valuation methodology and source definition not selected |

All 18 mapped entries can now enter the ingestion worker. The other 8 are
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
