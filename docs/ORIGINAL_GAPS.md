# Phase 2 — exact remaining data contracts (2026-11-02)

The original financial requirements include six difficult derived or licensed
indicators. Four are now mapped with explicit economic definitions; **two
cannot yet be called implemented**, because the required historical underlying
observations are not publicly retrievable at complete coverage.

## Implemented original definitions

| Original series | Source | Meaning and scope |
|---|---|---|
| `valuation.us.tobins_q` | Official BEA 2026 Table E Q1 | Annual US nonfinancial-company equity market capitalization divided by current replacement cost of produced corporate assets, 1960–2024 |
| `labour.world.productivity_compensation` | Official ILO/UNSD global SDG 10.4.1 | **Accounting-implied** ratio of GDP/hour to all-labour-income/hour, 100 ÷ world labour share %. Not independently measured hourly employee wages. Includes imputed self-employed income |
| `credit.world.private_gdp_gap` | BIS 43 national private credit gaps + WDI nominal USD GDP | Prior-year-GDP-weighted average of national HP credit gaps, excluding overlapping euro-area aggregate, only >=80% covered-world-GDP quarters. **Not official BIS world gap** |
| `gold.world.equity_correlation` | World Bank nominal monthly gold USD + MSCI ACWI 892400 NETR USD | Monthly mean index and gold levels → monthly arithmetic returns → trailing 36-month Pearson correlation. Genuine equity **index** net-total-return; no ETF substitution |

Supporting, separately mapped original data: `equity.world.msci_acwi_netr_usd`
and `credit.world.private_gdp_gap_coverage`.

Successful verification of the complete mapped sources, with 32 real series,
24 registered investment instruments and three ECB currency sources:
- Live sources: https://github.com/tpepels/finance_dashboard/actions/runs/41474846685
- Complete scheduled static export: https://github.com/tpepels/finance_dashboard/actions/runs/41474846662
- Short backend/PostgreSQL CI: https://github.com/tpepels/finance_dashboard/actions/runs/41474846646

## Remaining original definition A: historical MSCI ACWI top-ten weight

**Required input:** historical security-level, free-float-adjusted constituent
weights for MSCI ACWI index code **892400**, ideally every month end, over
a meaningful multi-decade period. Grouping must specify whether two
share classes of one company count as distinct index securities or one
economic company. The existing requested definition is **top ten index
constituents**, so count index securities separately and preserve issuer IDs
so alternative company aggregation can be compared.

**Exact calculation at each index composition date:**
sort all included constituents by actual index weight at that date; sum ten
largest float-adjusted constituent weights; record calendar date, number
of constituents, total reported index weight, observation-vintage/source
identifiers, and methodology. Do not recompute old weights from today's
constituents, and do not derive them from individual US ticker prices alone.

**Access reality:** MSCI's [Index Constituents API](https://developer.msci.com/apis/index-api)
and [Index Deep History](https://dataexplorer.msci.com/ui/products/DM_Index_Deep_History)
offer historical constituent datasets, but require entitled access. Public
MSCI live factsheets expose today's top ten, but not enough past dates to
reconstruct complete history. Their April 2026 ACWI factsheet publishes
24.62% top-ten weight; September 2026 publishes 25.40%. These are
**isolated, source-dated snapshots**, not a historical monthly dataset.
Neither current figures nor non-MSCI ETF provider holdings justify marking
`concentration.global.top10` as mapped.

**Implementation gate:** an MSCI entitled API user/token or a complete
monthly historical constituent-weight file with source date and index code.
The user has offered to create **free** keys; no free historical MSCI
constituent entitlement has been verified. If such a file is obtained,
implement provider import, monthly historical revision tracking, validation
of sum of weights and top-ten selection, and full-history static export.

## Remaining original definition B: listed-company global profit share

**Required numerator:** global consolidated **listed-company profits**,
preferably trailing 12-month net income attributable to ordinary shareholders,
with a defined treatment of loss-making companies, multiple equity classes,
cross-listed companies, fiscal-year alignment, currency and inflation,
profits of financial firms, and parent/subsidiary double counting.
A worldwide listed-company dataset needs explicit universe/country coverage.

**Required denominator:** World Bank `NY.GDP.MKTP.CD` global annual
GDP in current USD, aligned to the profit observation window.

**Exact formula:** global total listed-company trailing earnings converted
to USD / world nominal GDP for the same period × 100. Negative profits must
not silently disappear or be converted to positive values. The platform
should report investable market-cap share/universe size and the coverage
of reported earnings in each time window.

**Wisesheets assessment (2026-11-02):** The user's free
`WISESHEETS_API_KEY` is working. The official Wisesheets API currently
advertises 21,577 **US stocks**, based on US SEC EDGAR/XBRL, with five
years of free annual fundamentals. It includes SEC-reporting foreign issuers
with US listings (e.g., ASML), and non-USD reported currencies.
This is not a complete world-listed issuer universe, so even a successful
all-filer Wisesheets scan must remain a separately named partial numerator.
The implemented [SEC-filer source collector](WISESHEETS.md) reports coverage,
SEC CIK deduplication, verified SEC filing provenance, omitted records,
currency conversions and world GDP comparisons. It does not close this
original worldwide definition.

**Why current public sources are insufficient:** MSCI ACWI provides
market cap and aggregate index P/E and covers approximately 85% of global
investable equity, not all listed companies; its aggregate valuation
methodology can exclude negative/unavailable earnings in some ratios.
The shortcut *index market capitalization ÷ index P/E ÷ world GDP*
is an **index-implied earnings proxy**, not comprehensive consolidated
worldwide listed-company net profits, and the publicly visible aggregate
index P/E is only a current snapshot rather than a reproducible complete
history. The WFE publishes exchange market-capitalisation statistics, but
not a sufficiently defined consolidated global listed-company net-income
history via its open statistics portal.

**Implementation gate:** a documented historical global listed-company
financial-statements source with complete profits and share-class/issuer
mapping, and a defensible policy for accounting/domicile and multinational
geography. Source access, not a FRED key, is missing.

## Further implementation/acceptance debt

Independent issuer NAV/dividend reconciliation and historical ticker-change identity continuity remain unverified **optional market-data audits**, no longer macro Phase 2 gates. The combined live PostgreSQL backfill of all 32 mapped macro/index series **passed** on 2026-11-02.
The backend has verified all 24 investment instruments against live PostgreSQL ingestion and all 32 mapped macro/index sources against live PostgreSQL ingestion, live API readback, and static export. [All-macro full-historical PostgreSQL acceptance](https://github.com/tpepels/finance_dashboard/actions/runs/41476599670), [market PostgreSQL acceptance](https://github.com/tpepels/finance_dashboard/actions/runs/41470443707).

**Do not close Phase 2** until both original outstanding historical datasets and the macro acceptance tests have been implemented and verified, unless the owner approves an explicit change to the two original definitions. Do not claim a
premium dataset can be accessed merely by assuming usage permission.


## Source-access assessment: Yahoo Finance and aggregated alternatives (2026-11-02)

The original two indicators remain **unmapped**. These concrete sources offer partial or point-in-time historical evidence and are not authorized substitutes for their exact definitions:

| Route | Verifiable public coverage | Use / limitation |
|---|---|---|
| MSCI Index Constituents API / Index Deep History | Historical MSCI index securities for entitled subscribers | **Exact route** to `concentration.global.top10`; index 892400 and float-adjusted weights must be verified. Requires entitlement. [API](https://developer.msci.com/apis/index-api), [history](https://dataexplorer.msci.com/ui/products/DM_Index_Deep_History) |
| Official MSCI ACWI factsheets/profile | Source-dated top-ten totals and index capitalization/valuation; 24.62% April 2026, 25.40% September 2026 | Exact index *snapshots*, **not a complete monthly history**. [MSCI ACWI](https://www.msci.com/indexes/index/892400/msci-acwi-index) |
| SEC N-PORT | Public fund portfolio holdings data Oct 2019–Sep 2026, quarterly dataset releases | A reconstructible *ACWI fund holdings* history from iShares fund records; **ETF proxy only**. Filter the correct fund series/registrant and observation date. [SEC datasets](https://www.sec.gov/data-research/sec-markets-data/form-n-port-data-sets) |
| iShares holdings | Downloadable current/historical-as-of holdings selected by fund site | Reconcile with SEC N-PORT; benchmark weights may differ. [Fund source](https://www.ishares.com/us/products/239600/ishares-msci-acwi-imi-etf) |
| Yahoo Finance | Current `ACWI` ETF top-ten holdings (retrieved snapshot: ~25.30%) and instrument financial/price histories | Useful third-party ETF cross-check; no verified complete historical MSCI security weights or world-listed issuer master. ETF P/E and index P/E cannot be used interchangeably. [Yahoo holdings](https://ca.finance.yahoo.com/quote/ACWI/holdings/) |
| MSCI ACWI valuation | Sep 30 2026 index cap **USD 102.69T**, index P/E **21.35**, implying about **USD 4.81T** trailing earnings if this P/E is interpreted as cap/aggregate earnings | **Index-implied earnings proxy**, not all worldwide listed-company net income. Publish provider P/E methodology, exclusions and reference date; no unsupported assumption of exact net-profit accounting. [MSCI ACWI](https://www.msci.com/indexes/index/892400/msci-acwi-index) |
| Siblis global-market P/E | Public global aggregate P/E for year-ends 2016–2025 plus Sep 2026; fuller historical data commercial | Source provides *aggregate* index cap/normalized net income methodology rather than an average P/E, but P/E alone is not an absolute profit series without **same-universe, same-date capitalization**. Full series and reuse rights require provider terms. [Global index P/E](https://siblisresearch.com/data/global-markets-pe/), [API](https://siblisresearch.com/financial-data-api/), [licensing](https://siblisresearch.com/data-licensing/) |
| Existing Wisesheets supplementary | 8,179 current SEC CIKs; 6,161 traceable financial filers; 2021–2025 | Useful measured SEC-listed partial universe, not global or survivorship-free. [Collector](WISESHEETS.md) |

**Implementation decision:** retain exact `concentration.global.top10` and `profit.global.corporate_share` as unresolved until their required source histories pass the contracts. New approaches can be implemented as separately labelled `proxy.*` or supplementary series after a source/rights review; no implicit replacement is approved. Do not combine one provider's index cap with another provider's P/E unless constituent universe, date and valuation methodology have been independently reconciled. If the owner elects to change the original scope, record an explicit change to the [locked feature contract](PHASE_2_FEATURE_CONTRACT.md) and [implementation contract](PHASE_2_IMPLEMENTATION_CONTRACT.md).

## Macro-first aggregate histories added without ETF holdings (2026-11-02)

The owner deprioritized per-ETF analysis. Four **separately named** global macro measures were implemented and source-validated in the [36-series live static export](https://github.com/tpepels/finance_dashboard/actions/runs/41492850778): World Bank WDI WLD listed domestic market capitalization in USD (51 years), a same-calendar-year capitalization / WLD GDP ratio (51 years), Siblis global-index aggregate trailing P/E (11 published snapshots, 2016–2026), and the same-index reciprocal earnings yield (11 snapshots). Source code: [macro_aggregates.py](../src/finance_dashboard/macro_aggregates.py). An Alembic numeric-precision migration stores large USD world totals.

The World Bank WLD ratio is calculated from its WLD USD capitalization and WLD world GDP values; it differs from the WDI published *country-weighted* market capitalization/GDP aggregate. Index earnings yield is relative to **Siblis's index market cap**, not world GDP. The sources have different corporate universes; cross-multiplying them does **not** yield worldwide consolidated net profits.

Under the [recorded macro-first scope amendment](PHASE_2_MACRO_SCOPE_AMENDMENT.md), individual issuer NAV reconciliation and historical ticker continuity are optional market-data debt, **not blockers** to macro Phase 2. The original `profit.global.corporate_share` and `concentration.global.top10` historical contracts remain unresolved.
