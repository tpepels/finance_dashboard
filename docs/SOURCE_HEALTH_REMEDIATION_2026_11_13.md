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

## Follow-up — targeted resolution of the remaining 24 (13 Nov 2026)

The earlier 24-issue count is the **pre-follow-up baseline**, not an
immutable live count. This follow-up explicitly rechecks five publication
bounds and fixes missing acquisition orchestration, yielding **19 expected
actionable series** on the same 2026-11-13 data snapshot. These are
source-health classifications, not fabricated data acquisitions.

**Five publisher-window checks**

- Two Shiller monthly components, earnings and dividends, have no
  nonmissing observations beyond June 2026 in the published historical
  series checked on 13 November. July–September share-price and CAPE
  updates are *not* dividend or earnings updates. They now use a
  per-series verified 2026-06 cutoff expiring on **8 December 2026**;
  sources: Robert Shiller data documentation, Finance Toolkit monthly
  source extract, and independent Shiller earnings release reporting.
- The BIS selected real residential price indexes for **Germany and
  Portugal** already have exact 2026-Q2 native observations in the stored
  history; BIS October 29 selected release includes 2026-Q2. The BIS
  **US commercial** exact source `Q.US.0.A.0.2.6.0` explicitly
  lists 2026-Q2 as its last period. These three bounds expire on
  **26 November 2026**, the next publisher update. Check against the
  *exact source key* after expiry; nominal and residential indices are
  not substitutes for the registered real/commercial series.

**Actual collection orchestration repair**

The previous ordinary `Sync current` runs attempted the whole macro
catalogue. Healthy sources could consume publisher request quotas
before the stale series were reached. The new canonical operation
`repair_source_health` is exposed inside the unified Data & Sync UI:

1. Read the full current source-coverage census and select only
   actionable macro issues (missing/stale/failed), excluding in-cadence
   but policy-deferred healthy histories.
2. For affected MSCI regional P/E histories, attempt the *existing*
   Wayback original-PDF collector, restricted to affected regional
   indexes. Archive captures remain CDX-digest-verified and conflicts
   remain blocked. No parallel MSCI scraper or ungoverned HTTP path.
   Allow cancellation between requests.
3. Reattempt the selected canonical source adapters through the same
   managed publisher-rate and immutable original-evidence pipeline.
   In particular, rerun the failed Swinkels source even if its pinned
   2022 original is historically complete; do not silently hide the
   operational error.
4. Recompute source coverage after refresh and report selected sources,
   resolved issues, unresolved canonical IDs, publisher refusals and
   whether MSCI acquisition succeeded.
5. Retain the original source-health audit CSV with every attempt and
   classification. A failed or deferred request is never a success.

There is an equivalent single-process, macro-only CLI operation:

```sh
docker compose exec -T finance-dashboard python -m finance_dashboard.worker \
  --once --macro-only --health-repair
```

The option is also available for source-constrained schedules; ordinary
scheduled refresh now skips complete, named pinned editions until they
actually need checking, while explicit/manual runs can still force
revalidation.

**Remaining expected 19** after deploying the preceding bounds, *if
no publisher acquisition has yet succeeded*: 5 WID world distribution
histories; 2 OECD NFC net fixed assets; 2 OECD CLI trend-restored
(histories require actual GDP-dependent source content); 1 EUKLEMS
US labour compensation; 1 ECB euro-area HICP; 6 MSCI
EAFE/Europe/Japan trailing or forward P/E; 1 live gold XAU/USD
spot; and 1 failed Swinkels original-access attempt.
These are not all scientifically equivalent or automatically
repairable. In particular, source-access refusals, absent WID 2024–25
cells, source edition mismatches and unavailable MSCI capture months
remain explicit unresolved issues when the managed collector cannot
obtain verified originals.

**Acceptance:** all four mandatory GitHub workflows must pass on the
final repository commit. Offline tests exercise source-age bounds and
expiry, selected source IDs, no quota spent on deferred-but-current
histories, failed pinned-source retry, MSCI originals preceding
reingestion, truthful before/after counters, UI initiation and
cancel-safe acquisition. These tests do not constitute a successful
run on the owner's private database; only the resulting server audit
can certify the live 19→N count.

### Additional confirmed resolution: discontinued ECB HICP edition

The nominally stale `prices.ea.hicp_index` (ECB source
`ICP.M.U2.N.000000.4.INX`, **2015=100**) officially ends
**December 2025**. The 2026 rebasing also changed the euro-area
composition. The user's source audit ALREADY records the separate,
registered new `prices.ea.hicp_index_2025`
(Eurostat source `prc_hicp_minr/M.I25.TOTAL.EA`, **2025=100**)
through **October 2026**, state `available`. The old exact
edition is now publisher-complete; no old/new index levels are ever
spliced or given false common units. The new Eurostat original remains
independent. Source: https://data.ecb.europa.eu/data/datasets/ICP/ICP.M.U2.N.000000.4.INX
and https://data.ecb.europa.eu/data/concepts/hicp .

This reduces the remaining expected actionable issues from 19 to
**18**, assuming an unchanged November 13 database and publication
windows. The actual post-deployment number must be read from a fresh
source audit. The remaining 18 are: five WID world histories,
two OECD non-financial-corporation net fixed assets, two OECD CLI
trend-restored, one EUKLEMS US labour-compensation, six MSCI regional
P/E histories, one gold spot collection, and one failed Swinkels
retrieval. All 18 have an explicit canonical repair attempt via
`repair_source_health`, but successful new publisher acquisition
cannot be claimed without executing it on the owner's host.


### Follow-up forensic improvements: verified original snapshots and resumable MSCI

Original audit release `0.2.0+f21b2f39427f8b7e` includes exact
source-evidence records (2026-11-13). Four additional old observation
histories have **recent successful complete original publisher snapshots**:

| Source | Original last observation | Verified retrieved full snapshot | Recorded immutable evidence |
| --- | --- | --- | --- |
| US OECD CLI, trend restored | 2026-05 | 2026-11-11 | Full original response, hash/receipt |
| JP OECD CLI, trend restored | 2026-05 | 2026-11-11 | Full original response, hash/receipt |
| ES OECD S11 net fixed assets | 2023 | 2026-11-07 | Full original response, hash/receipt |
| PT OECD S11 net fixed assets | 2023 | 2026-11-07 | Full original response, hash/receipt |

OECD's official CLI methodology explains why the trend-restored
series can lag the monthly headline: it requires GDP-reference trend
estimates, which only become available with quarterly national-account
observations. These four originals were checked *within the previous
14 days*, and their exact registered queries returned no later source
observations. The special `source_checked_no_newer_data` state is
**only** authorized while their successful full original response
with SHA-256 bundle digest and original receipt is recent. It expires
after 14 days without an equally valid refreshed full-original check
and reverts to an actionable warning. Current observation dates remain
old (`observation_state=stale`), and the audit does **not** claim
a fixed new published edition or make up 2024/2025 corporate balances.

The source-audit CSV now exports separately:
`observation_state`, `freshness_basis`,
`source_checked_through_utc`, `evidence_scope`,
`evidence_receipt_recorded`, and `evidence_bundle_digest`.
For missing receipts or partial source windows, or after expiration,
the alert persists. WID world (2023) and EUKLEMS US compensation
(2020) are excluded: publisher releases imply newer potential
reference years, so they still need real original-source checks.

This classifies the old four publisher-lag warnings as **recently
checked without newer published observations**, yielding **14**
expected actionable sources on the Nov 13 database, not 18.
That is not four newly collected years and is not a claim the research
inputs are uniformly contemporaneous. To see the actual live number,
deploy and run an updated data audit.

The six MSCI valuation histories have a separate genuine data gap.
The previous Wayback collector re-fetched all legacy URL listings on
every run, then tried ancient archived captures first, exhausting the
registered Internet Archive request limit before reaching current
regional P/E. The source-health collector now:

- reads and re-verifies previously stored, SHA-256-bundled CDX listings,
  checking original URL/query identity before reuse;
- prioritizes never-queried URLs, uses time-limited existing listings,
  resumes after `PolicyDeferred`/publisher refusals instead of
  discarding completed collection progress;
- filters captures earlier than the month following the existing
  oldest target's last observation and prioritizes recent captures;
- records excluded old captures separately, never miscounts them as
  already stored, and retains and verifies each fetched original PDF
  with its Internet Archive CDX digest.

Existing full-history archival acquisition is unchanged: only the
health-repair invocation opts into the recent-date filter. Tests cover
quota resumption, tampered saved CDX listings, recent-first selection,
and no old unneeded capture downloads.

**Remaining actual publication/acquisition problems** (14):
WID world 5; MSCI regional trailing/forward P/E 6;
EUKLEMS US imputed-self-employed LAB 1; indicative Gold API XAU/USD 1;
Swinkels original source policy access failure 1. There are still
no live new source bytes in the supplied forensic ZIP, and no connection
to the owner's private Docker DB in this ChatGPT session.
The public WID 2025/2026 methodology documents *newer world
distribution estimates*, so its five 2023 histories cannot
be declared current by extending lag thresholds.
