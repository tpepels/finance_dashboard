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

Independent issuer NAV/dividend reconciliation, historical ticker-change
identity continuity, and a single combined live PostgreSQL macro backfill
across the 32 mapped series remain outside what has already been proven.
The backend already verified all 24 investment instruments against live
PostgreSQL ingestion and every mapped macro/index series against live
provider responses and static export.

**Do not close Phase 2** until both original outstanding datasets and these
agreed integration checks have been implemented and verified. Do not claim a
premium dataset can be accessed merely by assuming usage permission.
