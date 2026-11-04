# Phase 2 native input evidence — 2026-11-04

This is a source/evidence reference for the authoritative [development plan](DEVELOPMENT_PLAN.md), not a second implementation roadmap. The additional original histories were acquired through the existing append-only ingestion service in an isolated copy of the verified production backup. Their native source responses and acquisition receipts were preserved. The scientific acceptance count remains **0/35**.

## Missing native inputs acquired

| Source and exact series identity | Native definition | Acquired observations | Remaining comparison limits |
|---|---|---:|---|
| BLS CES via FRED `PAYEMS` | Seasonally adjusted monthly total nonfarm payroll jobs; thousands of persons | 1,053, January 1939–September 2026 | Establishment payroll jobs are not unique employed people or the civilian unemployment denominator. Multiple jobs can count separately. Original benchmark/release vintages remain open. |
| Federal Reserve H.15 via FRED `DFF` | Daily seven-day effective federal funds rate, percent | 26,423, July 1, 1954–November 2, 2026 | Broker-reported volume-weighted mean before March 1, 2016; FR 2420 transaction-based volume-weighted median thereafter. The long history has a methodological break. |
| Federal Reserve via FRED `DFEDTARL` | Daily seven-day FOMC target-range lower limit, percent | 6,533, December 16, 2008–November 4, 2026 | Policy setting, separate from realized overnight rates. No pre-target-range bound is manufactured. |
| BLS via FRED `CPIAUCSL` | Monthly seasonally adjusted CPI-U, US city average, all items; 1982–1984=100 | 956, January 1947–September 2026 | Urban consumer basket, distinct from a business-output deflator and inflation percentage. This only supplies the US price-basis comparator. |
| WDI `NY.GDP.MKTP.CD` | Annual nominal GDP in current USD, seven individual countries and separate published world aggregate | 528, 66 years per source, 1960–2025 | USA/FRA/PRT/DEU/CHN/IND/JPN are a non-overlapping but incomplete country cohort. WLD is the publisher denominator, not the cohort sum. Current-price GDP is not PPP, real growth, or investable equity weight. |
| WID `sptinc992j/p99p100` (countries), `sptincj992/p99p100` (world) | Annual top 1% pre-tax national-income fraction, equal-split adults over 20 | 541: US 117, France 115, Portugal 89, China 58, India 107, world 55 | National tails 2024, world 2023. Sparse source years remain sparse. Top 1% is nested within top 10%; these shares are not an additive partition. Independent WIID Ginis remain missing. |

These 18 additional catalog histories contain **36,034 original observations**. Nine formerly unbound required roles gain explicit native series mappings: C05 employment, M01 effective funds and target lower bound, P04 US CPI, L07 top 1% income, G02 country/world nominal GDP, G03 world nominal GDP, and G05 national nominal GDP. Their mappings do not establish complete geographic populations, synchronized releases, first publication, or whole-analysis acceptance.

Original publisher definitions: [PAYEMS](https://fred.stlouisfed.org/series/PAYEMS), [DFF](https://fred.stlouisfed.org/series/DFF), [DFEDTARL](https://fred.stlouisfed.org/series/DFEDTARL), [CPIAUCSL](https://fred.stlouisfed.org/series/CPIAUCSL), [WDI current-USD GDP](https://data.worldbank.org/indicator/NY.GDP.MKTP.CD), and [WID original bulk files](https://wid.world/data/). The effective-rate methodological change is documented by the [Federal Reserve H.15 announcements](https://www.federalreserve.gov/feeds/h15.html) and the [New York Fed calculation-method statement](https://www.newyorkfed.org/markets/opolicy/operating_policy_150708.html).

## Bounded native comparisons

Five added variants use exact native-period intersections and no filling:

- C01: monthly US industrial production / civilian unemployment, 944 matched months. Different populations and units remain explicit.
- C05: monthly US industrial production / nonfarm payroll jobs, 1,053 matched months. Quarterly GDP, shock chronology and event-baseline transforms remain separate.
- M01: effective funds / target lower / target upper, 6,531 matched days. The target-range regime starts December 16, 2008, and the effective-rate 2016 estimator break remains explicit.
- G02: seven countries / separate world current-USD GDP, 66 matched years. These inputs do not supply the missing original investable equity-country weights.
- L07: WID top 1% / top 10% / bottom 50% income in six areas, 44 matched years. This is an additional explicit variant; the prior top 10% / bottom 50% variant remains available.

The five added panels and the prior L07 panel passed independent original-value reconciliation for all 32 selected source histories in the isolated acquisition run. CPI was acquired separately because it is an original role rather than an input of these five panel contracts. DFF was subsequently fetched again after recording its publisher-documented methodology break so that the raw response proof binds the corrected canonical definition. No source values changed during that repeated DFF fetch.

This native-input increment reached 176 macro source definitions, 168 required roles and 17 native comparative variants before the subsequent consolidated integration. Current counts are recorded in the authoritative development plan and source audit. Coverage and scientific acceptance are independently evaluated; a current-source panel must not substitute for the complete original contract.

## Reproducible source and preservation checks

The existing `CapturedProvider` archives successful full FRED CSV and WDI JSON responses, strips sensitive URL parameters and binds each response to the canonical source contract. The independent selectors do not invoke the ingestion parsers. The selected WID top 1% values come from the exact raw data/metadata pairs already preserved for the other WID shares; byte-identical full re-fetches reuse the immutable bundles and append acquisition receipts.

A WID manifest records the selection made when it was acquired. A later registered percentile can be selected from the same hash-verified original CSV without modifying that historical manifest. Reuse still checks every previously recorded quality value and requires the original four share selections. The regression test verifies unchanged old manifest bytes and rejects forged old quality metadata. This avoids copying raw country histories solely because an additional percentile was registered.

`tests/fixtures/wid_top1/` contains factual original country/world excerpts, exact native metadata and the full-source SHA-256 values. Regression assertions independently pin the latest top 1% shares: US 0.2073, France 0.1182, Portugal 0.1037, China 0.1576, India 0.2307 (2024), world 0.2029 (2023). The source values remain fractions.

`tests/fixtures/phase2_native_inputs/` contains selected actual pandemic-era FRED observations, full original WDI US/world histories, retrieval/source URLs, original-file hashes and fixture hashes. A native ingestion/reconciliation/panel test verifies all nine fixture sources, preserves payroll thousands and the original CPI index, distinguishes the effective/target rates, and passes the three activity/policy panels without creating release-time evidence. Full private histories remain in the source-evidence archive.

This source increment does not resolve OECD CLI/diffusion, BoJ realized overnight rates, independent shock announcements, WIID survey concepts, index-country weights, worldwide issuer profits, or source-specific first-publication/common-release histories. Those requirements remain explicit.
