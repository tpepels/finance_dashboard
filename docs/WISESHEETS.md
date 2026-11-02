# Wisesheets SEC-reporting issuer earnings (Phase 2)

The repository Actions secret **WISESHEETS_API_KEY** is confirmed working.
The live endpoint accepts Bearer authentication; the free key has 5 years of
fundamentals history, 5,000 requests/month and 200 calls/minute.

**Coverage is SEC-reporting US-listed companies, including some non-US
issuers listed on US exchanges (ASML is one example). It is not global
listed-company coverage.** Consequently
`profit.global.corporate_share` remains an unresolved original definition.

## Implemented

The Wisesheets collector `src/finance_dashboard/wisesheets.py`:

- Enumerates every accessible SEC filer via paginated `/v1/companies/`
  responses and checks complete cursor traversal.
- Deduplicates share classes/ticker aliases by the stable SEC CIK.
- Fetches annual `net_income` for five years, in batches of 100 tickers
  through the official `/v1/financials/` API, retaining negative earnings.
- Accepts only rows traceable to an actual SEC filing with accession and
  filing date; reports earnings lacking that provenance as excluded.
- Converts foreign-denominated reported net income to USD using the
  average of paired daily ECB cross-rates over each fiscal year. Where
  an ECB cross-rate is unavailable, excludes the company-year and reports
  the exact missing currency and coverage count.
- Divides the USD SEC reporting-company aggregate by World Bank nominal
  world GDP `NY.GDP.MKTP.CD` for the same fiscal-end calendar year.
- Reports reporting issuer counts, verified/converted issuer counts,
  excluded currencies, omitted records, plan entitlement and snapshot date.

This is an **observed, incomplete US SEC filer profit/GDP benchmark**.
It does not estimate profits of non-US-listed issuers, private companies,
unreported financials or the missing historical delisted universe.
Some fiscal years do not coincide exactly with calendar GDP; the output
reports the assumption and must not be called a complete world profit share.

## Execution and secret management

A separate `wisesheets-refresh.yml` workflow runs monthly, on manual
dispatch and upon changes to the collector. The free-tier request budget is
capped at **800 requests per run**, and requests are rate-spaced below the
plan's 200/minute limit. It does not run on the daily macro/ETF refresh.
A bad response, incomplete pagination, or an unexpected provider identity
prevents publication.

On success, it validates and commits only the aggregated annual JSON file:

`data/wisesheets/sec_filer_profit.json`

The full SEC filer data is not stored in the repository. No key, account
details, authenticated request URL, or raw proprietary API response appears
in the aggregate. A 90-day Actions artifact backs up the current annual
aggregate.

The read-only API endpoint `GET /api/earnings/sec-filers` and the
daily static-data export read that committed snapshot. They do not call
Wisesheets on each page view or fetch the API key into the browser.

The daily static export marks the supplementary dataset as
`not_collected` before its first successful full scan, and as `stale`
if the last successful snapshot exceeds 45 days. It remains **separate**
from the original unresolved `profit.global.corporate_share` indicator.

## First complete live scan (2026-11-02)

**PASS:** 8,179 unique SEC CIKs in the accessible current-company directory, 6,161 issuers with SEC-filing-traceable annual earnings, **150 requests** against the 5,000/month free limit. Published fiscal years: **2021–2025**. Earlier isolated fiscal years (2007–2020) were excluded as too sparse to be treated as an annual SEC cross-section. The output lists currency omissions, untraceable earnings issuers and excluded invalid records for every applicable year.

[Verified complete run](https://github.com/tpepels/finance_dashboard/actions/runs/41483503450) · [Committed aggregate](https://github.com/tpepels/finance_dashboard/blob/main/data/wisesheets/sec_filer_profit.json)

The observed 8,179 unique CIKs are fewer than Wisesheets' advertised 21,577 US-listed ticker securities; ticker count and distinct SEC reporting issuers are different units of coverage. The result remains subject to current-universe survivorship bias.

## Evidence

- Source contract: https://www.wisesheets.io/api/docs
- Free plan scope: https://www.wisesheets.io/api
- Live key + AAPL/MSFT/ASML five-year data and reporting currencies:
  https://github.com/tpepels/finance_dashboard/actions/runs/41479313490
- Live USD/EUR net-income parsing, ECB FX and World Bank GDP:
  https://github.com/tpepels/finance_dashboard/actions/runs/41480398749
- Complete full-universe scan: track
  https://github.com/tpepels/finance_dashboard/actions/workflows/wisesheets-refresh.yml
