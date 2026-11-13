# Source-health remediation — 13 November 2026

## Scope, definition and evidence

The 13 November user-supplied original full source audit from
`0.2.0+f21b2f39427f8b7e` contains **426 registered sources** and
**110 attention states**: 80 `refresh_deferred_with_data`, 28 `stale`,
one `collection_failed`, one `refresh_failed_with_data`. It has 397
of 398 macro histories, 25/25 market histories and 3/3 FX histories.

This is **not a census of 110 missing series or invalid values**.
Seventy-three deferred series retain observations inside the then-configured
source-lag thresholds. Source-coverage code now treats those as
`available` while preserving `refresh_state=deferred`, last error,
attempt timestamps and every original observation in the complete source
audit. Seven deferred histories are genuinely old and remain attention
items.

The initial 37 issues needing substantive evaluation were reduced to 33 by
country-specific World Bank Gini publication-year verification (four
original histories already reach the published latest survey years).
This release additionally verifies **nine exact existing histories**:

| Series | Locally stored through | Evidence establishing that bound | Recheck / nature |
| --- | --- | --- | --- |
| property.jp.real_residential.bis | 2025-Q4 | BIS WS_SPP, Q.JP.R.628 exact series page | 26 November 2026 |
| property.world.real_residential.bis | 2026-Q1 | BIS WS_SPP, Q.XW.R.628 exact series page | 26 November 2026 |
| property.us.real_residential.bis | 2026-Q2 | BIS WS_SPP, Q.US.R.628 exact series page | 26 November 2026 |
| property.ea.real_residential.bis | 2026-Q2 | BIS WS_SPP, Q.XM.R.628 exact series page | 26 November 2026 |
| activity.us.industrial_production_diffusion_1m | 2026-08 | Fed G.17 October 16 diffusion original `diff_sa.txt` | 17 November 2026 |
| activity.us.industrial_production_diffusion_3m | 2026-08 | The same independent 3-month block | 17 November 2026 |
| activity.us.industrial_production_diffusion_6m | 2026-08 | The same independent 6-month block | 17 November 2026 |
| stress.us.high_yield_oas_fred_archive | 2025-11-03 | Exact retained FRED Wayback capture `20251104204105` with CDX/receipt proof | Fixed historical artifact; not a live series |
| returns.doeswijk_swinkels.global_multiasset.usd.nominal | 2022-12 | SHA-256-pinned author workbook GMP JIMF | Fixed 1970-2022 research edition; not current market |

A publisher-date boundary does **not** certify immutable receipt identity,
original vintage dissemination, absence of revisions, representativeness
or the macro-research analyses. The original acquisition and append-only
source history are unchanged. No tolerated numeric error, inferred value or
source series is introduced. All source-specific publication bounds require
actual last local observations at least as new as the source-specific date.
BIS/Fed bounds expire on the **scheduled next release**, and warnings
return if an end date has not been reverified. The two explicitly immutable
research artifacts remain completed for those exact fixed original versions.

BIS selected residential: https://data.bis.org/topics/RPP/
BIS series pages: `https://data.bis.org/topics/RPP/BIS%2CWS_SPP%2C1.0/Q.<AREA>.R.628`.
Official BIS calendar: https://data.bis.org/release-calendar
Fed original: https://www.federalreserve.gov/Releases/G17/Current/ipdisk/diff_sa.txt
Fed calendar: https://www.federalreserve.gov/releases/G17/
FRED pinned local method: `src/finance_dashboard/fred_wayback.py`.
GMP pinned local method: `src/finance_dashboard/global_market_returns.py`.

## Operational gold-collector repair

The stored historical `gold.usd.spot` run reported only the generic
`provider_failed`, which is **insufficient** to determine whether
the problem was publisher access, malformed JSON, stale source clock,
currency identity or transport failure. The published Gold API live
XAU/USD endpoint still documents the expected exact
`symbol=XAU`, `name=Gold`, `currency=USD`, `exchangeRate=1`,
`price`, and UTC `updatedAt` fields. No replacement provider or
economic-series splice was authorized.

The collector now maps all controlled parser failures to dedicated **safe,
redacted** codes. A non-JSON HTTP 200 response is
`gold_spot_invalid_response`; wrong source identity and currency,
conversion, timestamp, quote age, window and price each receive a precise
code. HTTP refusal/transport errors retain their existing typed categories.
No raw API response, URL tokens or provider error body is persisted.
These changes **do not imply the actual production request succeeded**.

Run exactly one canonical refresh on the private deployment (no source-policy
workaround or parallel raw HTTP client):

```sh
cd ~/media-stack
git -C finance_dashboard pull --ff-only origin main
docker compose up -d --no-deps --build --wait finance-dashboard
docker compose exec -T finance-dashboard python -m finance_dashboard.worker --once --macro-only --series gold.usd.spot
```

Then download a new versioned source-audit CSV to read the precise
`last_failure_code`. This could still fail because of network, upstream
response, policy deferral or actual source changes. No successful collection
was performed against the owner's private database from GitHub CI.

## Remaining expected actionable issues (24, *after* deploying this code)

The count assumes the input data remain the same as the supplied audit and
the as-of time is within all fixed verification windows. It is **not a
reported post-deployment server observation**.

| Family | Attention | Next real remediation |
| --- | ---: | --- |
| WID.world worldwide income/wealth distribution | 5 | Recheck latest native WID country `WO` file + metadata under 360-second spacing; retain original hash/vintage and revisions. Do not substitute UNU-WIDER's distinct WIID methodology |
| OECD NFC net fixed assets for Spain and Portugal | 2 | Recheck native OECD S11 `N11N` 2024/2025 source keys and observation metadata after publisher cooldown |
| OECD US/JP CLI trend-restored | 2 | Verify native `TR` series; unlike `AA`, trend restoration requires GDP reference trend and may legitimately lag; never use `AA` as replacement |
| US EUKLEMS labour compensation | 1 | Source file shows only 2020 vs documented 2025 edition through 2021; inspect source `LAB` published year and whether the missing 2021 cell is truly available |
| Euro area ECB HICP index | 1 | Ingest 2026 source periods with exact ECB key; 2025-12 is significantly behind the actual published inflation observations |
| BIS residential DE/PT, commercial US | 3 | Reconcile exact source keys/last official per-key dates; local DE/PT already have 2026-Q2 while some indexed publisher pages lag, so do not infer publisher identity from another value/nominal index |
| MSCI EAFE/Europe/Japan trailing and forward P/E | 6 | Acquire newer original PDF releases with the existing Wayback CDX+SHA-1 workflow; verify as-of dates and source conflicts; no interpolation across missing months |
| Shiller earnings/dividends | 2 | Determine last *nonmissing* original author cell: later price or CAPE months do not establish available future earnings/dividends |
| Gold XAU/USD live snapshot | 1 | Attempt canonical endpoint and diagnose typed cause; only admit exact valid live USD quote |
| Swinkels AUD original v6 | 1 | Diagnose source-policy-denied attempted refresh; pinned v6 local history remains intact, but a failed operational attempt must remain visible |

The remaining 24 are not all provably retrievable; source-specific
publisher publication and operator network access are independent gates.
No original data were removed, changed or invented to improve the count.
No cross-provider identity has been substituted.

## Acceptance

- `tests/test_source_coverage.py` checks publisher-period completeness,
  expiration, strict per-ID bounds and incomplete-history negative cases.
- `tests/test_source_failure_codes.py` checks safe detailed gold failures
  including currency mismatch, nonfinite/future/stale timestamps, and
  credential redaction via fixed-vocabulary codes.
- `frontend/src/SourceCoveragePanel.test.tsx` ensures the operational
  deferred-attempt filter remains visible after in-cadence deferrals are
  excluded from the actionable count.
- Four CI jobs (Python, frontend, browser, release image) must pass at the
  final main revision. No end-to-end production re-ingestion is asserted
  by CI.
