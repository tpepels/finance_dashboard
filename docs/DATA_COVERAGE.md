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

The GLD/VT fund-based correlations are **separate** from the original
unresolved world-equity-index total-return/spot-gold correlation, just as
NCBCEPNW is separate from replacement-cost Tobin's Q.

## The two remaining original indicators

| Original series ID | Missing requirement | Treatment |
|---|---|---|
| `valuation.us.tobins_q` | Exact, versioned replacement-cost asset numerator/denominator (e.g. BEA Q1/Q3 definitions) | Keep unresolved. The new `valuation.us.equity_net_worth` (FRED NCBCEPNW) is a **separately labelled proxy**, not Tobin's Q |
| `labour.world.productivity_compensation` | Comparable global hourly productivity and real labour compensation series, weighting and coverage | Keep unresolved. `labour.world.productivity_growth` supplies only global output-per-worker growth |
| `profit.global.corporate_share` | Worldwide profits **attributable to listed companies** with non-duplicated multinational geographic allocation | Keep unresolved. National-accounts total corporate profits are not listed-company profits |
| `concentration.global.top10` | Licensed historical constituent and free-float market-cap weights for a defined global equity index | Keep unresolved. Public current top-ten lists are not sufficient for historical concentration analysis |
| `credit.world.private_gdp_gap` | Economically justified global aggregate credit gap and country/denominator weights | Keep unresolved. Three **country-level BIS gaps** are implemented and comparable on a combined chart |
| `gold.world.equity_correlation` | Historical world equity **total-return** series with defined currency, price/return conventions and rights | Keep unresolved. World Bank monthly gold and live spot quote are available, but no licensed world equity return series |

These indicators are intentionally absent from chart-ready data. A chart referencing a non-mapped series stays `draft`, and the API rejects unpopulated series rather than returning fake values.

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
