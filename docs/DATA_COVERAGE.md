# Phase 2 — source coverage, provenance and blockers

Verified 2026-11-02. **34 canonical macroeconomic/index series total: 32 mapped and live-source verified; two original economic definitions unresolved.** Separately, **24 exchange-listed stock/ETF instruments and three ECB FX source series** are fully implemented in the market registry.

An operational adapter can fetch and parse real source data into PostgreSQL; it is not an assertion that the provider grants public redistribution rights or that every derived comparison is methodologically valid.

| Source / provider | Series | Verification | Important limitation |
|---|---:|---|---|
| BIS policy rates | 3 | Live backfill + Docker/PostgreSQL/API | Harmonized policy instruments may change historically |
| BIS credit gaps | 3 | Live SDMX country checks | US, euro area and Japan, private nonfinancial credit gap **CG_DTYPE=C**; no world aggregate |
| FRED | 4 | Live no-key observations HTML + keyed JSON contract tests | Fed upper target, real 10Y yield, Sahm Rule and nonfinancial corporate equities/net worth; raw-data rights review |
| ECB | 1 | Live CSV | ECB deposit facility, distinct from BIS harmonized rate |
| World Bank WDI | 8 | Live six real GDP growth areas + US/Japan domestic listed-cap/GDP | Annual, incomplete country coverage, revised values |
| IMF DataMapper | 1 | Live | WEO DataMapper world public debt; not Oct 2026 WEO. Excludes current/future calendar years; earlier years may still be estimates |
| Shiller US CAPE | 1 | Live Excel workbook | US-only; dynamic workbook, reproduction rights review |
| Siblis ACWI CAPE | 1 | Live free API | **Sparse nine historical snapshots, proprietary**; public chart/data redistribution requires licence |
| ILO-custodied UN SDG | 2 | Live world labour share + real output/worker growth | Productivity growth differs from compensation growth |
| World Bank Pink Sheet | 1 | Live Excel workbook | Monthly average USD/oz, **not daily spot** |
| Gold spot quote | 1 | Live Corgano XAU/USD quote | One current indicative spot midpoint/oz; historical API provides futures, not spot |

All mapped source IDs are referenced from `definitions/series.json`. The relevant open-source calculations and provider validation functions are in `src/finance_dashboard/providers.py` and `src/finance_dashboard/bis.py`.

## Stock, ETF and foreign-exchange coverage

**Implemented and end-to-end verified:** 24 exchange-listed assets (six European
UCITS ETFs, 16 US ETFs/stocks, two EU stocks), three ECB USD/GBP/CHF FX
reference series, raw/adjusted close and volume history, distributions,
splits (including non-trading-day ex-dates), EUR total-return calculations
and 36-month USD/EUR GLD-versus-VT investable-ETF proxy correlations.

- [Actual 24-instrument historical static data build](https://github.com/tpepels/finance_dashboard/actions/runs/41470215544)
- [Actual full 24-instrument PostgreSQL/FX/API ingestion acceptance](https://github.com/tpepels/finance_dashboard/actions/runs/41470443707)
- [Source registry, methodology and caveats](MARKET_DATA.md)

The GLD/VT fund-based correlations are **separate ETF proxies**. The original gold/global-equity correlation has since been implemented with real MSCI ACWI NETR USD index values and World Bank monthly gold. Likewise, BEA replacement-cost Tobin's Q is now implemented and distinguished from Fed NCBCEPNW.

## The two remaining original indicators (updated 2026-11-02)

| Original series ID | Missing requirement | Treatment |
|---|---|---|
| `profit.global.corporate_share` | Comprehensive worldwide consolidated listed-company net profits, including losses, cross-listing deduplication, multinational allocation, currency alignment and matching world GDP | **Unresolved.** The Wisesheets current SEC-filer aggregate is separately named and incomplete. MSCI cap/P-E implied earnings is an index-universe proxy, not a complete global net-income sum. |
| `concentration.global.top10` | Historical monthly MSCI ACWI index 892400 security-level free-float constituent weights | **Unresolved.** MSCI contemporary factsheets and SEC/ACWI ETF holdings proxies cannot replace the historical index-constituent series. |

The other four original gaps are now implemented: official BEA Q1 replacement-cost Tobin's Q, ILO accounting-implied world output/labour-income hourly ratio, a documented weighted 43-country BIS private credit/GDP-gap composite with coverage, and a 36-month World Bank gold/MSCI ACWI NETR USD index correlation. See [locked feature contract](PHASE_2_FEATURE_CONTRACT.md) and [source history](ORIGINAL_GAPS.md).

The two unresolved indicators must remain absent from chart-ready observations. A chart referencing a non-mapped series stays `draft`, and the API rejects unpopulated series rather than returning fake values.

## Provider verification

- [29 non-BIS policy sources live](https://github.com/tpepels/finance_dashboard/actions/runs/41459407905).
- [3 BIS policy rates, full PostgreSQL/API integration](https://github.com/tpepels/finance_dashboard/actions/runs/41449348048).
- [Offline and PostgreSQL tests](https://github.com/tpepels/finance_dashboard/actions/runs/41459407973).

FRED's public observation HTML renders up to the first 1,000 observations in an HTML table and later observations in `#extra-rows` records. The parser reads both, and fails closed on malformed rows. Its key-based JSON API remains preferred for long-term stability.

The BIS credit-gap parser selects dimensional code `C` (actual minus trend) independently of positional ordering of `A` (actual) or `B` (trend). True historical publication vintages cannot be inferred from when the app downloaded the data.

## Publishing to GitHub Pages

Public Github Pages requires **series-by-series attribution and redistribution permission**; a public API or free data query does not in itself grant that permission. For example the free Siblis data cannot simply be committed to public JSON/CSV for distribution. Gold spot quote and some FRED/index data also carry usage rights. The exporter must filter or omit restricted sources and report them explicitly.

Sources:

- BIS policy and credit SDMX: https://stats.bis.org/api-doc/v2/
- FRED official API: https://fred.stlouisfed.org/docs/api/fred/
- FRED financial accounts ratio: https://fred.stlouisfed.org/series/NCBCEPNW
- World Bank: https://datahelpdesk.worldbank.org/knowledgebase/articles/898581-api-basic-call-structures
- IMF: https://www.imf.org/external/datamapper/api/v2/GGXWDG_NGDP
- UN SDG: https://unstats.un.org/SDGAPI/v1/sdg/Series/SL_EMP_GTOTL/GeoArea/1/DataSlice
- Shiller: https://shillerdata.com/
- Siblis free API: https://siblisresearch.supabase.co/functions/v1/free-data-api/v1/ACWI/cape
- Siblis licence: https://siblisresearch.com/data-licensing/

### Recent additional live acceptance

[Full mapped-source check: 29 non-BIS policy sources](https://github.com/tpepels/finance_dashboard/actions/runs/41474846685), [complete 32-series static export](https://github.com/tpepels/finance_dashboard/actions/runs/41474846662), [short PostgreSQL/pytest suite](https://github.com/tpepels/finance_dashboard/actions/runs/41474846646).

### Full PostgreSQL macro/index acceptance

All 32 mapped macro/index sources completed a combined real-data historical PostgreSQL backfill, with API readback for BEA Q1, ILO hourly ratio identity, 43-country BIS credit gap and coverage, MSCI ACWI NETR and monthly gold/index correlation: [live acceptance](https://github.com/tpepels/finance_dashboard/actions/runs/41476599670). Only the two exact original source-dataset gaps remain unresolved.

### US SEC-reporting earnings supplementary source

The free Wisesheets key was tested live against AAPL, MSFT and ASML:
five annual net-income records per company, including EUR and USD filing
units, with SEC provenance. See [WISESHEETS.md](WISESHEETS.md).
The monthly complete SEC-filer aggregation is **supplementary**;
it is not a replacement for `profit.global.corporate_share` or a
historically unbiased worldwide listed-company universe.

**Wisesheets full source scan verified (2026-11-02):** 8,179 unique SEC issuers, 6,161 issuers with verified SEC-filing annual financials, 5 reporting years (2021–2025), 150 API requests. Separate `profit.us_sec_filers.world_gdp_share` aggregate committed in [data/wisesheets/sec_filer_profit.json](https://github.com/tpepels/finance_dashboard/blob/main/data/wisesheets/sec_filer_profit.json) and documented [here](WISESHEETS.md). It is SEC-reporting listed coverage, not all global listed companies.
