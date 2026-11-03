# Development plan — sole authoritative implementation roadmap

**Updated:** 2026-11-03. **Scope:** Global Capital Monitor, a single-page local-only economic research dashboard and one existing Docker service. **Branch:** `main`. The original source definitions, saved observations and historical evidence must never be silently replaced, cleared, or declared complete from source-code coverage alone.

**Binding operation policy:** The user-facing source management flow has exactly **two primary actions**: **Sync current data** and **Sync history**. Current sync refreshes all registered macro series, all market/FX sources and quota-aware earnings, then creates a verified local backup. History sync refetches full available macro/market/FX histories, resumes ALFRED original release snapshots and checks original verified SEC filings (currently capped at 50 filings per fund), then creates a verified local backup. Keep the detailed 80-source audit, failure information and CSV export under a collapsed **Source diagnostics** disclosure. Every routine source import, source repair, publication-vintage backfill, SEC holdings collection, earnings refresh, verification check, data-coverage inspection, and backup creation must be executable from the **single-page UI**, with readable status, progress, errors and retries. The terminal is for developer builds/recovery only, never the required way to operate data sources. UI actions must be bounded, source-ID validated, idempotent/resumable, credential-safe, and preserve original data. Do not regress this requirement in any phase. New research pipelines (including UCITS and OECD) must have UI workflows in the same increment as their backend collectors.

**This is the only active development plan.** Historical phase contracts and changed decisions are retained as non-operative snapshots in `docs/archive/`. Technical documents such as `SERVER_SOURCE_SETUP.md`, `INDICATOR_ACCEPTANCE_MATRIX.md`, `PHASE_4_RESEARCH_SOURCES.md` and the scientific methodological references specify *how* the work is done; they do not define competing priorities or acceptance gates. If a historical note disagrees with this file, this file governs. No requirements are dropped by archival.

### 2026-11-03 15:45 UTC diagnostic and source repair

The latest user export reports 80/80 registered sources with stored observations and one latest failure: `valuation.us.cape` (`shiller_workbook_invalid`, last stored April 2026). The previous complete history run reports ALFRED 964 missing with HTTP 400 (`fred_bad_request`), SEC VT 28 and BND 29 filings found or reused but still partial, markets complete and backup complete. The 15:41 history job was still running at export. The 80/80 count establishes saved coverage only, not continuous monthly or original point-in-time completeness.

**Committed corrective implementation; Docker runtime not yet verified:** the Shiller adapter now reads split worksheet headers, distinguishes ordinary CAPE from total-return CAPE, uses a unified Excel reader for XLS/XLSX, rejects non-workbook bytes and out-of-range/truncated history, and preserves parser-specific failure codes instead of blanket-catching the `ProviderError(ValueError)`. The ALFRED backfill queries the original first revision date for each source from FRED `series/vintagedates`, excludes prepublication month-end dates without fabricating observations, and reports the number excluded separately from genuine outstanding requests. The HTML developer export presents this count and safe source/HTTP failure codes. This is an acceptance implementation, not proof that the production providers now respond correctly.

**Next gate:** pull/build `main`, run `Sync current data` and `Sync history` in the browser, then export completed Developer logs. Verify that Shiller imports historical CAPE from 1881 onward without invented months; verify the original FRED vintage availability bounds and a positive number of real ALFRED snapshots downloaded; verify fund filing coverage rather than equating counts with full history. Any HTTP failure, continuity gap or original-source mismatch remains open. No persisted observations or snapshots are removed by this change.

### 2026-11-03 16:25 UTC build failure — acceptance remains blocked

The Docker frontend stage succeeded and the Python test runner reached `tests/test_maintenance.py`. Two ALFRED integration tests failed after introducing `first_available_vintages`: their mocks covered `probe_access` and `backfill_batch` but omitted the new external vintage-bound query. The mocked batch results also lacked mandatory `prepublication_excluded`. Production code was not exercised by those fixtures. The `tests/test_vintage.py` prepublication regression additionally contained an undefined `root` reference outside the temporary-directory lifetime. Tests now mock the new lookup, assert the bounds are passed to the backfill, provide the full batch contract, and verify excluded dates while the directory exists. This corrects test scaffolding without weakening provider validation. A full Docker rebuild and runtime import remain unverified.

## Latest empirical acceptance evidence — user sync + 80-source CSV, 2026-11-03

The user reports the Docker build and both sync actions work. The exported CSV contains exactly **80 registered source rows**: 53 macro, 24 market and 3 FX, **all with saved periods**. This demonstrates ingestion coverage, **not** complete observation sequences or independently validated definitions. Sync history reported macro and market success, while genuine ALFRED was blocked (**964 missing; zero newly downloaded**) and SEC returned partial for two verified funds. The verified local backup stage succeeded according to the user's sync result; off-server replication and restore rehearsal remain unverified.

Seven status issues appear in the supplied CSV snapshot, while the later UI summary reports six, so the temporal state differs: five BIS Q1-2026 credit-gap flags, one Shiller monthly CAPE warning, and one CHF FX last-attempt failure `source_invalid` despite retained rates through 2026-11-02. Do not erase the CSV CHF evidence based solely on the UI counter.

**Remedies committed on main after this empirical result:**
- Recession zones restored to quiet dark-gray backgrounds in both themes; no red shading/borders.
- BIS September 14 2026 official Q1 publication recognized as current **only until December 7 2026**, the announced next release; stale status returns after expiry unless new original observations and release evidence arrive.
- ALFRED partial result now reports the safe actual preflight FRED denial reason and HTTP code rather than the opaque `provider_blocked` catch-all. Request a user rerun of **Sync history** after deployment to distinguish bad key from network/rate-limiting/API request issues. Never echo the key, query URL or provider error body.
- SEC partial result now exposes per-fund VT/BND status, recorded filing count, checked candidates, safe HTTP status and whether older candidate filings remain unexamined. The 50-filing ceiling still prevents a full-history claim.
- Shiller CAPE 291 observations between 1881–2026 and 1,450 internal calendar gaps are inconsistent with a monthly source. A conservative completeness guard now **rejects** severely truncated source workbooks before recording them as successful imports, retaining previously recorded values. This is a protective check, not a full restoration: inspect original Shiller workbook, monthly date parsing and latest CAPE source availability before closing the gap.
- Existing research UI now directs users to **Data & sync → Sync history**, not an obsolete CLI command.

**Current next gate:** rebuild the updated `main` image, confirm graph shading and source-status UI, sync current/history, inspect actual ALFRED denied reason and each SEC fund's result, then audit/fix the genuine Shiller monthly sequence, CHF refresh and rights/source-history gaps. An in-volume verified backup is **not** an independent off-host copy.

**Latest Docker build feedback (2026-11-03, 15:01):** the frontend gate passed 62 of 63 tests and stopped on the Developer logs copy test, where a preinstalled `navigator.clipboard.writeText` mock was replaced by `userEvent.setup()`. The UI itself displayed "Diagnostic report copied". Commit `c94b09a` removes the invalid mock assumption and asserts against the actual simulated clipboard contents (including a filtered-out event). The Docker image was **not built or deployed** after this failure, and no Python acceptance tests were reached. The next gate is a fresh complete Docker build, then manual Copy report/Download .txt verification in the running browser and checks of redacted ALFRED/SEC failure details.

### Developer support logs — implementation added, awaiting runtime verification

Open **Data & sync → Source diagnostics → Developer logs** to see a hidden, auto-refreshing server diagnostic timeline. It reads **/api/developer-log**, which combines a bounded 400-event, local `/data/maintenance/diagnostics.jsonl` journal, up to eight redacted sync job summaries and current source-coverage issues. Logging is structured/field-whitelisted, with no raw exception strings, provider bodies, headers, credentials or request URLs. The panel supports event-level filtering, manual refresh, copy and text download; exports always include full content regardless of the display filter.

Capture scheduled refresh stage failures and manual current/history sync starts, stage outcomes, source-level failures and terminal statuses. The normal dashboard remains uncluttered. Acceptance requires Docker frontend/Python test gates, a real browser run in light and dark, a complete diagnostic report after a source failure, and verification that copied text has no credentials. This is developer-only visibility, not a public observability service or a replacement for off-device archival.

### Diagnostic analysis — 2026-11-03 15:09 UTC user report (after logging build)

A captured in-progress report shows **80/80 registered histories stored**, **15 warnings** (ten FRED labour/PWT source-validation failures, Shiller CAPE and equity-net-worth validation, two ECB FX, gold/world equity transport, etc.). Count 15 is a snapshot of latest attempts, not 15 lost datasets. Exact raw report is supplied in the user conversation. The 15:09:02 `sync_history` was **waiting** behind a `scheduled_refresh` started 15:08:34; earlier two history jobs were partial, ALFRED `provider_blocked` with 964 missing vintages and SEC fund histories blocked, with stored filing counts. Neither provider rights nor source-specific failure causes are established by that report alone. FRED’s published PWT 11.0 observations legitimately terminate in 2023, but new `source_invalid` errors on refresh remain genuine failures.

**Committed remediation (new image not yet independently built):**
- Manual browser sync raises a cooperative scheduling priority flag. The scheduled refresh exits between provider requests, stops later stages, records `interrupted`, and releases its single collector lock before the manual sync acquires it. Preserve existing data and job serialization; test both manual queue signalling and preemptible scheduled refresh.
- Distinguish fixed, secret-safe source failure codes for malformed FRED JSON/HTML, empty FRED data, invalid/future/duplicate periods, source-window mismatch, source-mapping mismatch, incomplete Shiller, and ECB schema/identity/empty/value problems. Do not log free-form errors or request URL. Retain `source_invalid` only for unclassified validation failures.
- Developer report now identifies the actual FRED collection mode (`authenticated_api`, `public_table` or `public_csv`) and safe FRED API key presence/format-valid flags, SEC contact-presence flag and whether background refresh is enabled. Never return secret values.

**Acceptance:** rebuild Docker, run both manual sync actions, then share the final Developer logs after job completion. Verify the pending-vs-scheduled priority, which FRED mode is active, new source-specific codes, ALFRED HTTP denial code, SEC per-fund HTTP/reason codes, and whether failing sources now actually refresh. Do not mark source ingestion or historical acquisition complete until original observations independently verified.

### Latest acceptance report — 2026-11-03 15:25 UTC

User-provided developer export has **80/80 stored histories and one latest failed source**, `valuation.us.cape` with last native April 2026. This is **not** a cleanly validated monthly Shiller history. A manual history operation at 15:24 interrupted the scheduled refresh and started at 15:24:35, confirming that cooperative priority works in the deployed image. The earlier 15:09 job ended partial at 15:23:19: ALFRED `fred_bad_request` and 964 missing source-month vintages, SEC VT 28 found/cached records (partial), BND 21 found/cached records and HTTP 503 (blocked), macro one failure (Shiller) and market/FX complete. A following scheduled refresh produced `source_window_invalid` across the FRED PWT/BLS/valuation subset, whereas full manual refresh had imported those histories successfully. These are observation-window processing failures, not proof of data-source disappearance.

**New corrections committed after the 15:25 export; build and live outcomes pending:**

- Apply deterministic local requested-date filtering to every FRED adapter transport (authenticated JSON, public CSV/table), while retaining strict source-window validation in the ingestion service. A mock provider reproducing older rows verifies that only in-window data are ingested and a full import preserves all original dated observations.
- Expand Shiller failure taxonomy to distinguish official link discovery, unapproved host, workbook corruption, missing CAPE headers, empty/incomplete monthly history and no values in the requested period. Keep the canonical workbook and last-good records; no invented monthly CAPE readings.
- For ALFRED HTTP 400, classify only known parameter-family denials (historical realtime dates, observation window, series ID, limit) into fixed safe codes. Record **the first rejected source ID/as-of date and HTTP status** under `Sync results` and the Developer logs export. This identifies the actual failing original source request rather than guessing that the key is bad, or marking an unavailable pre-publication vintage as an observed no-data month. The 964 month/source combinations remain open until an authenticated successful response or accepted original provider absence evidence is obtained.
- SEC HTTP 502/503/504 fetches now use at most three requests (two bounded delays) on submissions, original filing index and XML retrieval. 400/401/403/429 continue to stop without retry storms. This is a transient error recovery; VT/BND lifetime coverage and source rights remain unverified.
- Added regression tests to the existing Docker Python and frontend suites and corrected test fixture imports.

**Acceptance gate:** after rebuilding `main`, run **Sync current data** and **Sync history**, inspect the latest Shiller failure category and whether FRED source-window failures recur, inspect the first actual ALFRED failed source/date/code, verify whether SEC 503 clears, and audit original stored data. Any source gaps and valid original publication-vintage rights remain blocking, not automatically accepted.

## Current verified baseline

| Evidence | Status at audit | What it proves | What it does not prove |
|---|---|---|---|
| 53 canonical macro source mappings | User's 80-row export confirms stored periods for all 53 | Live saved macro observations exist | Complete, independently source-audited histories or all current publication periods |
| 24 market instruments and 3 ECB FX currencies | User's audit shows stored history for all 27 | Real observation periods preserved | Exact corporate-action/price audit and successful CHF latest refresh |
| 46 curated economic indicator views | Implemented in `src/finance_dashboard/research.py` and frontend | Definitions and relationships present | Original exact empirical definition or completed production data |
| Source coverage, browser maintenance and targeted PWT refresh | Committed to `main`; `Data & sync` UI provides per-source/bulk imports, ALFRED/SEC checks and collections, earnings and verified local backup | Data maintenance can be scheduled via safe same-origin API and a durable serialized job queue | Successful rebuilt container, historical/source imports and full visual inspection |
| One-page light/dark UI and revised charts | Implemented in source | Chart-first hierarchy, disclosures, visible recession bands, dated sparse series | Human-reviewed dark/light desktop and mobile layouts |
| Two-button UI Docker build (2026-11-03) | **53 frontend tests passed, 1 test failed**: the collapsed-results test used an ambiguous text query; image build and container replacement stopped | All other frontend tests passed, but Python tests and production sync were not exercised in that build | Fixed test assertion and verified rebuild |
| Build and source-status corrections | The unused TypeScript test parameter was fixed on `main`; FRED annual ISO handling remains implemented; PWT 11.0 is recognized as officially ending in 2023; downloadable complete source audit added | Code-level fixes and regression tests committed | Successful next Docker build, live 80-source audit and real PWT import |
| ALFRED 2000–2026 | Last shared 180-request batch: 0 new; initial key-only check passed | Prior historical backfill blocked and FRED key likely accepted | Revised historical-as-of `--check` and backfill success |
| Original SEC N-PORT VT/BND | Last shared attempt: 0 XML imports; official index discovery code improved since | Source identification and parser exist | Actual 1/12 filing imports, holdings accuracy or broader fund coverage |
| OECD industry input–output and capital-stock research | Input contract and scenario calculations exist | Implementation can reject unsupported claims | Original audited IOT input, net stock and genuinely validated Marxian estimates |
| Forecast probabilities | Source-gated backtest code exists | Model/evaluation pipeline described | Credible out-of-time calibrated prediction or causal identification |

**Never report percent complete from mapped series or test counts.** Use separate gates: source registered → imported source observations → independently source-audited → research definition accepted → model externally validated.

## Historical phases: current honest acceptance

| Original phase | Status | Unclosed acceptance requirement |
|---|---|---|
| **Phase 1 — feasibility, contracts and source audit** | Baseline complete, decisions archived | Continue honoring exact source identity, geography, rights and unit caveats |
| **Phase 2 — native source collection and persistent backend** | Engineering implemented; **empirical acceptance open** | 53 macro, 24 markets, 3 FX source-by-source census, repair failures, source dates/provenance, data preservation, exact replacements vs originals |
| **Phase 3 — usable research dashboard** | UI implemented; **acceptance open** | Successful Docker build, human visual inspection on light/dark desktop/mobile; stable typography/layout, visible graphs, source/status caveats, no developer wording and one page |
| **Phase 4 — risk, economic relationships and historical research** | Partially implemented; **acceptance open** | Complete original publication/filing histories, exact research definitions, source-gated Marxian calculations, independently validated models and costs/uncertainty |

The five agreed implementation workstreams below are **cross-phase work packages**, not new phases or a substitute for acceptance of original Phases 2–4. Work package 1 closes the remaining Phase 2 data gate and Phase 3 coverage UI; 2–5 close Phase 4 empirical gates, with the economic-relationship acceptance originating in Phase 3.

## Single ordered implementation route

### 0. Stabilize deployment and preserve existing data — immediate prerequisite

**Status:** the previously deployed version worked. The first build of the two-button UI failed with **53/54 frontend tests passing** and one ambiguous Testing Library assertion in `DataOperations.test.tsx`; the assertion now inspects the `details.open` state. Code review also identified and corrected that the backup verifier rejected valid `maintenance/` evidence; a regression test now includes that archive member. The next image build, Python tests, live source behavior, backup verification and responsive visual review remain open. Do not claim the new UI is deployed until it has been built and inspected.

**Do:**
1. Run a full local Docker build, including frontend tests, Python source-coverage/provider tests, maintenance API tests and PWT annual ISO date tests. Fix *actual* failures; do not weaken real source/date assertions.
2. Confirm the running image is new and its mounted `/data` path still points to the existing `/srv/finance-dashboard`. Keep the existing database, ALFRED snapshots, SEC N-PORT XML-derived records, Wisesheets snapshot, original OECD extracts and backups.
3. Check the actual browser at mobile/desktop widths in light/dark, including texts, legend, scatter/bar geometry and the US-only NBER recession explanation. Only primary and secondary information should be visible initially.
4. Confirm safe, verifiable independent/off-server backup of the database **and all source evidence**, with a restore drill and no credentials in output.

**Gate:** clean Docker tests/build + running service + verified original data retention + real two-theme/two-width UI inspection. Until then no phase is "done."

### 1. Repair source coverage (original Phase 2, with Phase 3 source-status UI)

**Status:** implementation code committed; real local census and PWT import **not accepted**. The source audit distinguishes genuinely old annual history from complete published PWT 11.0 history ending in 2023; absent histories and those ending in 2022 remain incomplete. The version-specific exception must be reviewed when a new PWT contract is adopted. The dashboard now offers a complete safe CSV export of all 80 source statuses, including first/last observation dates, stored revisions, calendar gaps, source release bounds and failure categories.

**Complete scope:** 53 canonical macro series, 24 market instruments, 3 ECB FX currencies. Audit each for mapping, collector switch, provider availability, observation count, first/latest source date, latest attempt and fixed safe failure code. Separate a deliberately sparse annual source from missing data; check gaps, duplicates, unit stability, temporal availability and source revisions. Count cached valid data even after failed refreshes.

**First fixes:** use the dashboard's **Data & sync → Sync current data** action to fetch the mapped original FRED annual source fractions, including Germany, France and Italy PWT histories (`LABSHPDEA156NRUG`, `LABSHPFRA156NRUG`, `LABSHPITA156NRUG`). The dashboard handles fractional-to-percent presentation without modifying original stored values. Run one current sync, inspect all 53/24/3 rows under the collapsed **Source diagnostics** view; the server endpoints remain available for automated regression tests, not required manual commands. Verify every original date and provider result.

**Gate:** all 80 registered source contracts have an evidence-backed state and correct source date; the three PWT series have independently checked nonempty history; any other absent/failed feed has a named blocker and owner action. No source is silently excluded.

### 2. Complete historical acquisition (original Phase 2 provenance and Phase 4 vintage/holding foundations)

**Status:** importer/validator implemented; empirical acquisition open.

**ALFRED:** **Data & sync → Sync history** performs the historical-as-of access check (realtime_start=end), then resumes bounded 2000–2026 T10Y3M, SAHMREALTIME and USREC month-end snapshots; audit HTTP statuses, input vintage availability, cache and random original-source spot checks. Keep no-data months explicit, not interpolated. Historical as-of prediction labels require actual information availability, not later-revised ex-post labels.

**SEC:** **Sync history** imports verified original VT/BND XML filings (currently a 50-filing-per-fund bounded scan) with verified CIK/series and SHA, inspect filing coverage and issuer-country residuals. Add all user-requested US ETFs only with independently verified mappings; obtain separate primary, dated holdings/position disclosure sources for Irish/European UCITS. Distinguish legal fund domicile, issuer incorporation, revenue exposure and portfolio allocation; never infer one from another.

**Gate:** complete checked vintage inventory and documented SEC/UCITS original-file coverage, point-in-time eligibility and source provenance; no missing historical record treated as observed.

### 3. Finish original economic comparisons (Phase 3 economics; Phase 4 exactness)

**Status:** proxies/calculations implemented, exact empirical gates open.

- **World labour productivity vs compensation:** independently source hours-worked, value-added deflator, pay including self-employment treatment and aligned sector/country coverage (ILO, OECD, Eurostat). The labour share inverse identity is **not** the original requested global hourly pay gap.
- **Replacement-cost US Tobin Q:** independently reconcile BEA Q1 numerator/denominator, produced-assets scope, market value versus debt, intangibles and sector boundaries against original release documents.
- **Global credit gap:** source nonfinancial private credit levels and matched GDP from BIS country/area accounts; construct a researcher-defined aggregate and consistent one-sided trend, deduplicate country/area scope. A GDP-weighted national-gap mean is not a global stock-based gap.
- **Gold/world equity correlation:** verify original World Bank Gold and genuine MSCI ACWI NETR index returns, FX currency and month matching; independently recompute rolling Pearson coefficients. GLD/VT ETF correlation remains a separate transparent proxy.

**Gate:** every exact indicator has original numerator/denominator, geography, dates, units and source verification; otherwise it stays labeled proxy/blocked. No artificial continuity or renamed substitutions.

### 4. Resolve worldwide securities history (Phase 4 exact global ownership/profit evidence)

**Status:** honest public alternatives implemented; exact data missing.

**MSCI concentration:** acquire properly licensed original ACWI constituent/free-float history at required frequency, deduplicate share classes, check weight totals and independently reproduce published top-ten reference dates. Existing eight factsheet snapshots remain dated evidence, not a continuous invented history.

**World listed net profit:** obtain authorized comprehensive global issuer consolidated net earnings/filings, company-family and fiscal year crosswalk, multi-currency conversion, controlled multinational deduplication and listed/unlisted scope, paired to world GDP. Wisesheets US SEC filers and OECD38 gross corporate operating surplus remain valid *different* measures.

**Gate:** documented reuse rights, original complete series, global universe and issuer coverage, reconciled historical source values. If source licenses are unavailable, report the blocker and exact acquisition decision, not a false "complete."

### 5. Complete Marxian accounting and historical model validation (Phase 4)

**Status:** OECD normalized-data contract, sensitivity engine and source-gated logistic backtesting implemented, **not** empirically accepted.

**OECD:** acquire/audit raw official IOT archives, implement reproducible source-ZIP-to-normalized-row extraction and hashes; reconcile industry compensation, depreciation, gross/net operating surplus and sector GVA. Obtain harmonized *net productive capital stock* by matched industry/year, distinguish productive/unproductive sector assumptions, imputed self-employment and capital turnover; implement sensitivity and uncertainty. Report national-account analogues separately from unobservable direct Marxian value magnitudes.

**Prediction:** with genuine historical ALFRED vintages, pre-register time horizons and non-leaking features/labels, use embargoed expanding walk-forward, event-block uncertainty, baseline models, independent temporal holdouts, Brier/AUC/calibration checks. No unsupported live crisis probability. Keep portfolio scenarios cost-, FX-, tax- and fee-aware with validated adjusted prices.

**Gate:** all recorded industry identities reconcile, original data/source rights reproduced, profit rates only when valid matched capital values exist, predictive performance demonstrated out of time and all caveats attached.

## Currently unresolved critiques and corresponding remedies

| Critique | Where addressed |
|---|---|
| Source completeness counted as source registration rather than evidence | Package 1: all 80 original-date source statuses, independent source sample verification |
| Sparse charts and recession shading can mislead across geographies | Prerequisite 0: validate real screenshot/render at multiple breakpoints; use date-correct bars, show US-only NBER convention and allow context disclosure |
| Long text, dark-mode visual jumps and overly nested hierarchy | Prerequisite 0: one page / one heading, reserved card geometry, closed methodology until requested, desktop/mobile light/dark acceptance |
| No automated off-host data archival or tested restore | Prerequisite 0: durable off-device copies of SQLite+Wisesheets+ALFRED+SEC+OECD, hash verification, restore rehearsal |
| Read-only status does not guarantee alerting or reconciliation | Package 1: add missed-run/state transitions and gap/duplication checks; investigate source-specific thresholds |
| Real-time provenance inconsistent across external providers | Packages 1–3: store source published/available dates separately from observation period and ingestion date; no as-of leakage |
| LAN dashboard has no authentication | Prerequisite 0: LAN-only firewall or authenticated reverse proxy, no Internet port forwarding, secrets only inside server env |
| Provider licenses and unofficial market API use are not proven reusable | Packages 1/4: track terms and data rights; obtain licensed original sources as needed |
| Global equity index, country-credit and national-account aggregates do not share an economic universe | Packages 3–5: explicit universe/weights/coverage metadata, independent denominator comparisons |
| Predictive/causal claims lack independent validation | Package 5: as-of, blocked-event, forward holdouts, calibration, sensitivity and pre-registration |

## Blockers and how to remove them

| Blocker | Resolution or research direction | Proof needed |
|---|---|---|
| New two-button sync interface is not yet build- or server-verified | Build the latest `main`, verify all frontend/Python tests and try both one-click sync jobs with existing mounted data | Both jobs complete or report precise partial blockers, source observations retained and verified backup created |
| PWT or other mapped source histories may be empty/stale/failed | Use **Sync current data**; inspect the collapsed **Source diagnostics** audit for failures and independently verify source-period samples | Real observations, correct source dates and no CLI dependence |
| Prior ALFRED as-of import failed; FRED key alone does not prove historical vintage access | Use **Sync history**, which checks historical availability and resumes bounded historical batches; inspect its partial/blocked result | Every required historical source date accounted for |
| VT/BND original N-PORT collector previously found zero matching documents | Test official SEC index access with real User-Agent and XML mapping, 1/12 staged import, verify fund series | Original XML-derived holdings and hashes |
| UCITS historical positions not represented by US SEC sources | Research official European fund annual/quarterly portfolio holdings, documents or licensed provider with dated positions | Original UCITS holdings with availability dates |
| MSCI ACWI continuous constituent history may require a paid license | Approach MSCI / licensed index data vendors, evaluate research-use rights | Rights-cleared monthly weights and audit |
| Global issuer consolidated earnings not in public national-accounts data | Research broad issuer filings / licensed global financial statements with parent-company deduplication | Reconciled global listed issuer sample and world GDP |
| International compensation/hours and productive capital stock not harmonized | Audit OECD/ILO/Eurostat coverage and raw national accounts; build explicit crosswalk and sector constraints | Verified same-year/country/industry numerator and denominator |
| Too few independent recession events for strong prediction | Extend trustworthy vintage history, assess sample/event count, restrict conclusions and validate external periods | Defensible event-independent out-of-time results |

## Documentation ownership and lifecycle

- **Only roadmap:** `docs/DEVELOPMENT_PLAN.md` (this file). Work status and changing decisions are updated **here**. Never create another `PHASE_*PLAN`, `MISSING_*PLAN`, parallel acceptance list or new phase contract.
- **Operational manual:** `docs/SERVER_SOURCE_SETUP.md`. **Economic contracts:** `docs/ECONOMIC_RESEARCH_METHODS.md`, `docs/INDICATOR_ACCEPTANCE_MATRIX.md`, `docs/PHASE_4_RESEARCH_SOURCES.md`, source definitions and code. These are references, not competing task lists.
- **Historical files:** `docs/archive/` contains superseded full documents; original filenames in `docs/` remain short redirects to this roadmap and to archived evidence. Archive contents are frozen, not active requirements. All original user-approved requirements are accounted for above.
- **Rule:** Any change to exact definitions, accepted substitutes, sources, or acceptance criteria updates this file and the corresponding source contract together in the same commit. No "done" without source/binary/runtime proof.

## Reviewed public source leads — 2026-11-03 (research queue, NOT collected data)

Seven external directories/repos were inspected from user-supplied discovery links. A directory or third-party re-hosted CSV is not evidence that its historical source is valid or licensed. These candidates are integrated into the **same five workstreams**; this section is not another plan. Each accepted original source must receive a source/version/date/units/geography/rights contract, a tested importer, persistent original evidence, a browser-visible collection action, source coverage and a reproducible audit before any new indicator can claim to exist.

| Agreed workstream | Original source / lead | Evidence-backed opportunity | Constraints and acceptance |
|---|---|---|---|
| **1 — 80-source repair** | [Groningen PWT 11.0](https://www.rug.nl/ggdc/productivity/pwt/pwt-releases/pwt110), released 2025-10-07 (185 countries, through 2023) | Canonical official release cross-check and independent version-pinned fallback for registered FRED PWT 11.0 country labour shares | Preserve old source observations, independently compare FRED country values to identical annual PWT variables, verify release/version; build UI-first recovery before relying on a new collector. Publicdatasets.dev still lists older PWT 10.0; do not downgrade or silently mix versions. |
| **2 — dated research/vintages** | [St. Louis Fed FRED-MD / FRED-QD](https://www.stlouisfed.org/research/economists/mccracken/fred-databases) | Official archived monthly macro panels from 1999-08 and quarterly panels from 2018-05, for reproducible publication-vintage forecasting/factor baselines | Keep archive release month, real observation date, last availability and independent ex-post labels; avoid leakage through revisions or previously unavailable variable transformations. These panels complement rather than substitute series-specific ALFRED as-of histories. UI-controlled bounded downloads, snapshot verification and out-of-time evaluation required. |
| **3 — labour/productivity comparison** | [EUKLEMS/INTANProd 2025](https://euklems-intanprod-llee.luiss.it/) (27 EU members, US, Japan; industry panel 1995–2021), [BEA/BLS integrated industry production accounts](https://www.bea.gov/data/special-topics/integrated-industry-level-production-account-klems) (US 1997–2024), [UNIDO INDSTAT](https://stat.unido.org/data/database-descriptions) | Matched industry value added, compensation, hours, price indexes, and manufacturing wages/output for expanded country cohorts | Validate each country/industry/year and concept; wages and salaries exclude some labour compensation; sectoral samples do **not** establish a genuine global productivity-vs-compensation gap. UNIDO API source/version/estimates must be checked before ingestion. |
| **4 — global corporate entities** | [GLEIF Level 2 LEI ownership relationships](https://www.gleif.org/en/lei-data/access-and-use-lei-data/level-2-data-who-owns-whom), plus original UK Companies House, Baltic, French, Norwegian and Colombian filed accounts linked in [World Company Database](https://github.com/Alessandro114/world-company-database) | Cross-border legal-entity/parent identifiers, limited original jurisdiction financials and domestic corporate-account concentration benchmarks | LEI parent coverage and historical timestamps are incomplete; registry 'free search' is not equivalent to bulk licensed download. S.C.A.L.A. contains model-estimated revenue and nonlegal business records. Do **not** count estimated firms or sum parent+subsidiary filing profits into a purported worldwide listed-company net profit numerator. Exact worldwide consolidated profits and licensed MSCI constituent histories remain blocked. |
| **5 — industry accounting**, **highest priority newly verified source** | [OECD 2025 national input-output tables](https://www.oecd.org/en/data/datasets/input-output-tables.html) (1995–2022 with compensation, consumption of fixed capital and net operating surplus); [OECD STAN 2025](https://www.oecd.org/en/data/datasets/structural-analysis-database.html) (industry output, value added, capital stock, investment, labour); cross-check against [EUKLEMS 2025](https://euklems-intanprod-llee.luiss.it/documentation/) | Reproducible primary **industry** accounts for gross/net surplus and depreciation, and separate potentially matched net productive fixed assets | Acquire original official files and checksum/metadata. Explicit industry and country/year concordance, harmonize accounting units, currencies, gross/net assets and investment valuation, reconcile SNA identities and missing STAN imputation flags; attach productive-sector/self-employed/capital turnover sensitivity. A national-account profit-rate analogue must never be relabelled a directly observed Marxian profit rate. Add original-source import and scenario controls in the dashboard in the same implementation phase. |
| **5 / 3 — supply chain context** | [OECD ICIO 2025](https://www.oecd.org/en/data/datasets/inter-country-input-output-tables.html) (95 economies + rest of world, 1995–2022); [Groningen WIOD 2016](https://www.rug.nl/ggdc/valuechain/wiod/) (43 economies + rest of world, 2000–2014) | Official international production/trade-flow reconciliation and historical cross-check of imports, intermediate inputs, domestic value added | Do not sum cross-border input/output gross flows as world GDP or world corporate profits. WIOD is a historical comparison dataset, not a current update. Country-industry coverage/residual must be shown. |
| **2 / risk evidence — optional new indicators** | [Gold Barometer open repository](https://github.com/thegoldbarometer/data) provides derived CFTC futures positioning (weekly from 2006), IMF-reporters gold aggregate, real-rate inputs and a composite gold score with a reconstructed 1971+ backtest; [econdata](https://kvasilopoulos.github.io/econdata/) indexes research replication datasets, including the excess bond premium | Proposed **separate secondary indicators**: CFTC managed-money net exposure/open interest, reported central-bank gold accumulation, official US excess bond premium; compare with existing gold/real-yield/MSCI charts | Prefer direct [CFTC](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm), [IMF](https://data.imf.org/) and [Federal Reserve](https://www.federalreserve.gov/) originals. Gold Barometer raw Cboe GVZ and SPDR holdings are explicitly **not redistributed** in its inputs; enforce rights. Its reconstructed historical score changes the number of active pillars and cannot count as a stable publication-time observation without separate testing. No vendor score as predictor without expanding-window independent validation. |

**Source-directory rejections / caveats:**

- [publicdatasets.dev/economics](https://publicdatasets.dev/economics): an index (125 entries observed), not evidence of fresh 2026 official source content; prioritize original sources above and reject unrelated retail-price/popularity series as macroeconomic indicators.
- [Boston University economics guide](https://library.bu.edu/economics/datasets) and [free data guide](https://library.bu.edu/bizdata/free-data): useful pointers to official UNIDO, LIS, NBER, BEA and other sources; no bulk datasets supplied by those pages. LIS measures household income distribution, not corporate surplus value.
- [econdata](https://kvasilopoulos.github.io/econdata/): academic replication samples/methods and original-source discovery, not automatically real-time historical vintages; individual datasets require source, date and licence validation.
- [Kaggle World Economic Dataset 2025](https://www.kaggle.com/datasets/ahmadfirman/world-economic-2025): schema, original publisher, revision history and licence could not be independently verified. **Not eligible for ingestion** until audited.
- The **Gold Barometer** composite and 1971+ reconstructed monthly scores are research hypotheses; the author's own daily publication archive only begins in August 2026, with changing historical pillar availability. Keep provenance/rights separate from direct CFTC/IMF/FRED data.
- The original **unresolved global demands remain unresolved**: licensed continuous MSCI global constituent weights; truly consolidated and deduplicated global listed-firm earnings/GDP; a complete global productivity/compensation matched series; exact worldwide private credit gap; audited capital-stock/net-surplus account match; real out-of-time probability calibration.

**Prioritization:** after deployment/source acceptance, pursue **OECD IOT 2025 + STAN** under workstream 5 in parallel with the already ordered original-data acquisition checks; pursue **FRED-MD/QD historical vintages** under workstream 2 for the existing prediction-validation blocker; and use GLEIF only as a workstream 4 identity crosswalk. Optional gold and macro-shock indicators must not displace the original five required workstreams or turn the UI into a disconnected chart collection.

**Next actual action:** build and deploy the two-button revision without changing the existing `/data` mount; confirm the main UI shows only **Sync current data** and **Sync history**, inspect both progress/result paths and a verified backup. Then perform the real 80-source audit and complete workstream 1. Research/source licensing gaps remain blocked until original records are imported and independently audited.
