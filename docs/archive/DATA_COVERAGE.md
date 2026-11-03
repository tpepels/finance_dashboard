# Phase 2 — source coverage, provenance and blockers

Verified 2026-11-02. **42 active mapped macroeconomic/index series and no unresolved active definitions.** The two original inaccessible historic requirements are preserved in [the superseded archive](../definitions/superseded_series.json); the new public-source replacements have different scopes and do not reproduce the originals. Separately, **24 exchange-listed stock/ETF instruments and three ECB FX source series** are fully implemented in the market registry.

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

## New macro-first global equity aggregates (2026-11-02)

| Provider and scope | Canonical series | Verified input history | Rights / coverage caveat |
|---|---|---|---|
| World Bank WDI WLD, WFE-sourced | `valuation.world.listed_market_cap_usd` | 51 years, 1975–2025 | WDI CC BY 4.0, varying exchange/geographic coverage; current USD, not profits |
| WDI WLD market cap + WLD GDP, both USD | `valuation.world.listed_market_cap_world_gdp` | 51 matched years | True WLD cap/WLD GDP ratio, **not** the separate WDI weighted national capitalization/GDP series |
| Siblis public global valuation year ends | `valuation.world.global_trailing_pe` | 11 sparse dates, 2016–2025 Dec and Sep 2026 | Normalized aggregate 3,000-company index P/E, proprietary; no redistributed public website without permission |
| Same Siblis observations | `valuation.world.global_earnings_yield` | 11 sparse dates | 100/P-E in percent of **index** market capitalization; not global net income/GDP |

[Successful 36-series static source validation](https://github.com/tpepels/finance_dashboard/actions/runs/41492850778). All 36 mapped macro/index series, including the four new aggregates, **passed full real historical PostgreSQL ingestion and API readback**: [acceptance run](https://github.com/tpepels/finance_dashboard/actions/runs/41494100275). [Macro-first amendment](PHASE_2_MACRO_SCOPE_AMENDMENT.md). **No cross-universe WDI capitalization × Siblis earnings-yield fabrication.**

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

## Free-source replacements and retained superseded requirements (2026-11-02)

The owner approved the [source-definition change](PHASE_2_FREE_SOURCE_REPLACEMENTS.md); the inaccessible original `profit.global.corporate_share` and `concentration.global.top10` are **archived**, not mapped active series. The now 42-series active catalog has **zero unresolved** source mappings.

| Mapped macro measure | Verified official/public source | Coverage / principal limitation |
|---|---|---|
| `concentration.global.msci_acwi_published_top10` | Public dated MSCI ACWI 892400 factsheets and published research with index top-ten constituent weights | 8 sparse documented snapshots, 2019–2026; no fabricated 2022 or other missing months; MSCI rights review |
| `profit.eu27.corporate_operating_surplus_gdp` | Official Eurostat `nasa_10_nf_tr` S11 B2A3G + S12 B2A3G / S1 B1GQ | 24 matched annual 2002–2025 points, EU27 **only**, includes unlisted corporations, gross operating surplus not accounting net profits |
| `profit.eu27.nonfinancial_gross_surplus_value_added` | Official Eurostat `nasa_10_ki` S11 `B2G_B3G_RAT_S11` | 27 annual observations; NFC surplus / NFC gross **value added**, NOT GDP |

The initial **quarterly** OECD request was invalid/blocked (403), so Eurostat EU27 was used temporarily. A corrected official **annual OECD** SDMX request now supplies the separate verified OECD38 GDP-weighted 25-year series; EU27 remains its own regional dataset. [Source contract](OECD_CORPORATE_SURPLUS.md). None of these observations claims full worldwide listed-company net profits or a complete monthly historical MSCI universe. Both retired contracts are preserved with original source metadata in [`definitions/superseded_series.json`](../definitions/superseded_series.json).

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

All 32 mapped macro/index sources completed a combined real-data historical PostgreSQL backfill, with API readback for BEA Q1, ILO hourly ratio identity, 43-country BIS credit gap and coverage, MSCI ACWI NETR and monthly gold/index correlation: [live acceptance](https://github.com/tpepels/finance_dashboard/actions/runs/41476599670). Those original definitions have been explicitly superseded under the owner's approved amendment; they were not independently reconstructed.

### US SEC-reporting earnings supplementary source

The free Wisesheets key was tested live against AAPL, MSFT and ASML:
five annual net-income records per company, including EUR and USD filing
units, with SEC provenance. See [WISESHEETS.md](WISESHEETS.md).
The monthly complete SEC-filer aggregation is **supplementary**;
it is not a reconstruction of the superseded `profit.global.corporate_share` or a
historically unbiased worldwide listed-company universe.

**Wisesheets full source scan verified (2026-11-02):** 8,179 unique SEC issuers, 6,161 issuers with verified SEC-filing annual financials, 5 reporting years (2021–2025), 150 API requests. Separate `profit.us_sec_filers.world_gdp_share` aggregate committed in [data/wisesheets/sec_filer_profit.json](https://github.com/tpepels/finance_dashboard/blob/main/data/wisesheets/sec_filer_profit.json) and documented [here](WISESHEETS.md). It is SEC-reporting listed coverage, not all global listed companies.

### 39-series source validation

[**Full static export passed: 39 series + 24 optional markets**](https://github.com/tpepels/finance_dashboard/actions/runs/41498656329): eight MSCI published historical index concentration markers, 24 EU27 S11+S12/GDP observations and 27 NFC GVA profit-share observations. Source-named active definition coverage 39/39 with no unresolved IDs; source provenance/rights stay attached. See [second owner-approved amendment](PHASE_2_FREE_SOURCE_REPLACEMENTS.md).

## OECD corporate gross operating surplus — geographic gap resolved 2026-11-02

| Canonical mapped series | Live accepted history | Definition |
|---|---|---|
| `profit.oecd38.corporate_gross_surplus_gdp` | 25 years, **2000–2024** | GDP-weighted reporting OECD38-member (fixed 2026 set) national corporate S11+S12 B2G gross-surplus share of GDP |
| `profit.oecd38.corporate_gross_surplus_gdp_coverage` | 25 years | Annual share of known OECD-member nominal USD GDP included, **>=80%** |
| `profit.oecd38.corporate_gross_surplus_member_count` | 25 years | Countries with valid GDP weights and complete numerator/denominator, **>=29**; WDI GDP weights for >=35/38 members |

Official source: OECD [annual national institutional-sector accounts](https://sdmx.oecd.org/public/rest/dataflow/OECD.SDD.NAD/DSD_NASEC10@DF_TABLE14/1.1?references=all), not the failed quarterly probe. For country/year GDP denominator, use OECD GVA + net product taxes; restricted fallback to matching same-year World Bank nominal **local-currency** GDP only for USA/USD, JPN/JPY and CAN/CAD when OECD product taxes unavailable. GDP weights are WDI annual nominal USD. **Not an official OECD group aggregate or worldwide listed-company net earnings.** [42/42 PostgreSQL+FastAPI PASS](https://github.com/tpepels/finance_dashboard/actions/runs/41503545569), [42/42 complete static PASS](https://github.com/tpepels/finance_dashboard/actions/runs/41503489558). [Detailed methodology](OECD_CORPORATE_SURPLUS.md).
