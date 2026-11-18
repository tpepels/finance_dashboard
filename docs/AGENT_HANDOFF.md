# Global Capital Monitor — agent handoff (17 November 2026, eighth checkpoint)

**Purpose:** Resume the existing work in `tpepels/finance_dashboard` without reopening the completed audit or rebuilding implemented fixes. The authoritative source is code on `main`; this file is the investigation checkpoint, not a substitute for tests or new production evidence.

## Last verified checkpoint

- **Verified code commit:** `13823dc`. CI passed all four jobs on every commit pushed today; the last full run is for `13823dc`.
- **Deployed release:** `0.2.29+1b798d5ccfe24263`, activated 2026-11-17T17:01:35Z by the agent. The owner authorised the agent to deploy itself: `ssh media-server 'cd ~/media-stack/finance_dashboard && git pull --ff-only && cd .. && sh finance_dashboard/deploy.sh'` after green CI.
- **Verified research state on 0.2.26/0.2.28:** 28 accepted, 10 conditional, 0 incomplete, 1 deferred (G03). The 0.2.29 descoping (item 24) is deployed; confirm P04 and P05 have no open gates after the next assessment.

## Completed and tested work — do not repeat

The preceding commits already implemented and verified:

1. SEC N-MFP3 actual publisher header `NETASSETOFSERIES`, including independent verifier and regression fixtures; avoid the previously guessed `NETASSETSOFSERIES`.
2. OECD NFC accounts SDMX accounting-entry selection for multi-code response cases; independent reconciliation updated.
3. Scheduled source refresh promptly resumes after interruption/manual collection instead of idling until the next 24-hour interval.
4. Selected BIS nominal residential source publication bounds for US/DE/PT/EA Q2 2026; expire **2026-11-26**, do not generalize to Japan.
5. A dedicated `PublisherMeasureUnavailable` outcome for exact WID optional measures absent from a verified data/metadata pair. Runs are marked `unavailable` with `wid_measure_unavailable`; missing observations remain missing, are never replaced with zero, and are distinguished from parser/transport faults.
6. Invalid/quarantined WID metadata and incremental-window emptiness cannot be classified as genuine publisher absence.
7. Source coverage, data page, source audit, developer journal and developer report present that absence separately from collector failures, with relevant regression tests.

8. SEC N-MFP3 weekly-liquidity bound (`b833082`). One government fund files fractions of 1.0001-1.0004 of total assets; the strict `> 1` bound rejected the whole month for all four SEC measures. Collector and independent verifier accept up to `1.01`, store values as filed, and still reject larger values as an unresolved scale convention. All 16 published months (2025-07..2026-10) were downloaded and parse identically in collector and verifier; 15 of them failed before.
9. WID registered codes (`b8602a8`). 23 of the 40 "absent" WID measures were registered under codes that exist in no area file. Ratios are `wnweal`/`wpweal`/`wgweal` (unit `% of national income`), and the world file writes the suffix as `i999`. Collector identities and `definitions/series.json` source keys are corrected, and a test asserts they are equal.

10. WID retired-key rebinding (`178806c`). Production kept the 23 database rows under the old nonexistent codes, so every refresh on 0.2.20 stopped at the mapping guard with `source_mapping_mismatch` before reading the original. `WID_RETIRED_SOURCE_KEYS` lists the exact retired keys; `IngestionService.refresh` rebinds a row only when its stored key equals the listed key **and** it holds no observations. Any other key, or any stored observation, still raises "requires explicit migration".
11. Optional BLS operator contact (`6d9bfce`). `BLS_USER_AGENT` is empty by default; when set it must contain a contact and is sent on the BLS index and archive requests. Wired through `docker-compose.yml` and `.env.example`. Not verified against the live publisher, because no contact was sent from this workspace.
12. Upload-status race (`f03237a`). `OriginalImportManager.public_status` raised `FileNotFoundError` when an import moved a file between listing and sizing; the file is now skipped. This also failed the offline suite intermittently.
13. MSCI tamper test (`8fd7642`) selects the hash-named evidence bundle instead of the first directory entry. Test-only.
14. WID quarantine reason (`37c20fd`). On 0.2.22 the eight world series were reported as `wid_observation_invalid`: the collector replaced each quarantine reason with a generic message whose prefix maps to the observation code. `parse_piketty_original(..., return_invalid=True)` now returns a `{variable: first failed rule}` mapping and `WidClient.fetch` raises that rule, so a blank source citation reports `wid_metadata_invalid`. Acceptance is unchanged.
15. Known publisher limitations (`550bf70`). `KNOWN_SOURCE_LIMITATIONS` in `source_coverage.py` lists the 17 absent and 8 uncited WID series with expected state, failure code, reason and `review_by` 2027-07-01. `known_limitation()` applies only while the series has no stored data and state and code match exactly, before the review date; otherwise it counts as attention again. Matching series are excluded from `needs_attention`, the health snapshot's `attention_items`, the group `collection_failed` count and the repair census, and are listed in `known_limitations` (folded section on the data page). The scheduled refresh still checks them; a recurring reviewed failure is journalled as `source_known_limitation` at warning level, any other failure stays `source_failed`/error. Owner-approved on 2026-11-17. Do not add series to the list without checking the archived original.
16. Nightly quota retry (`f114404`). The scheduled refresh used to stop serving a provider for the night once a publisher's hourly quota was used; with OECD's 20 requests per hour only ~5 of the 46 OECD corporate account series were refreshed per night and 69 sources showed a deferred refresh for up to 6 days. `retry_quota_deferred` in `worker.py` retries quota-deferred and suppressed sources once the ledger's own retry time passes, within `FINANCE_QUOTA_RETRY_SECONDS` (default 14400, 0 disables, max 43200). It stops at once for a manual collection or shutdown, and every request still goes through the policy ledger. Only the scheduled refresh uses it.
17. Limitation assessment knows the reviewed limitations (`f114404`): a matching `known_limitation` is `documented_publisher_limitation` / information / documented; any other state of the same series still needs evidence.
18. ICIO consumer materiality (`47b1622`). The 28 hash-pinned 2025 regular (January 2026) matrices that L04 reads also fail exact closure: per year 40-228 rows and 1-36 columns exceed the 4-decimal bound; the largest row residual is 0.089% of a node's own output (ISL_L 1998), at most 0.0036% of world output in total, concentrated in real estate (L) and households as employers (T). Recorded in `definitions/icio_2025_regular_materiality.json`; `classify_icio_dependencies` reports it as `consumer_materiality`, and the ICIO finding becomes documented information only if every pinned year is covered, every hash matches, every relative residual is at most 0.1% (threshold chosen by the agent on the owner's behalf) and no failing archive is read by an analysis. Nothing is rebalanced; the 54 archives stay quarantined.
19. Independent readers for copper and OECD earnings (`befa540`). The Pink Sheet reader lacked copper (`source_identity_mismatch`); OECD earnings had no reader and fell through to the BIS JSON branch (`source_schema_invalid`). Against the production originals all 20 OECD earnings series and copper (802 months) now read with the same period counts as the stored histories. This should move C07 and L08 off `incomplete` once deployed and the assessment reruns; verify that rather than assume it.
20. Owner inputs count only saved fields (`584d82f`). `validate()` fills absent fields from the example; `supplied_roles` used to accept those as owner-supplied. `save_owner_inputs` now records `supplied_fields`; `load_owner_inputs` returns `supplied_fields`/`example_fields`; P04/P05 are labelled examples while any field they read is an example.
21. G01/G02 measured on the ACWI ETF (`bb6fa4e`, owner-approved 2026-11-17). The iShares MSCI ACWI ETF N-PORT holdings contracts are now the primary roles (previously an accepted fallback for licensed MSCI weights); MSCI factsheet bindings and the published top-ten comparison stay. Specification updated.
22. Fund look-through (`feb90c6`, `0b406b1`). `fund_lookthrough.py` reads the owner's 11 equity ETFs from their issuers and computes the value-weighted euro-area share for P04: iShares via the BlackRock fund-document workbook (portfolio ids 253743, 284219, 296576, 319084; ISIN in Key Facts; trading currency), SPDR via `holdings-daily-emea-en-spya-gy.xlsx` (ISIN in header; currency), VanEck via fund page (ISIN) plus `/ie/en/investments/{semiconductor-etf,space-etf,quantum-computing-etf}/downloads/holdings/` (Bloomberg exchange code; unknown codes fail), Vanguard via `www.de.vanguard/gpx/graphql` (port ids 9679, 9677, 9694; ISIN in the fund query; issuer country, because Vanguard gives no currency per holding). Originals are archived under `source-evidence/fund-lookthrough/<ISIN>/<date>/<digest>` with receipts; a deferred fetch falls back to the newest hash-verified archive of at most 45 days. Run: `docker exec finance-dashboard python -m finance_dashboard.fund_lookthrough --apply`; report in `/data/maintenance/fund-lookthrough.json`. Result on 2026-11-17: equity euro share 0.0569, saved as the owner's `equity_euro_share`.
23. Source policies for `www.blackrock.com`, `www.ssga.com`, `www.vaneck.com` and `www.de.vanguard`. POST is allowed only for a policy with `read_only_graphql_post` (declared paths, JSON body of at most `max_body_bytes`, a `query` and no `mutation`/`subscription`); every other policy stays GET/HEAD.
24. Descoped under the owner's delegation (`13823dc`): P04 `convexity` (the calculation is first-order only) and P05 `constituent_total_returns` and `benchmark_weights` (the replay uses asset-class index returns and compares rules without benchmark attribution). Each `descoped_roles` entry says when to re-add it.

The scientific-acceptance and independent original-source gates were **not** weakened.

## Production state after the collection on 0.2.23 (export 2026-11-17T11:36Z)

**651** registered histories, **626** stored, **52** attention items (0.2.18 baseline: 79). The 54 ICIO failing originals stay quarantined; do not rebalance or waive them.

| Source | Attention | State in export | Verdict |
| --- | --- | --- | --- |
| SEC_NMFP | 0 | all four `available`, 16 months through 2026-10 | **Fixed and verified** (`b833082`). |
| OECD_NFC_ACCOUNTS | 0 | ES and FR `available` through 2025; ES/PT net fixed assets `source_checked_no_newer_data` (end 2023) | **Verified.** |
| WID national wealth-income ratios | 0 | 15 `available`, 1800-2025 (PT 1980-2025), equal to the archived originals | **Fixed and verified** (`b8602a8`, `178806c`). |
| BLS_OEWS | 0 | both `available`, five annual values 2021-2025 | **Fixed and verified** with the owner's declared contact (`6d9bfce`). |
| WORLD_BANK | 0 | recovered | The nightly 2026-11-17T00:14Z run had `ReadTimeout` on 7 series; data was preserved and the next run succeeded. Transient, no code change. |
| WID world aggregates | 8 | `collection_failed`, `wid_metadata_invalid` | **Correctly rejected and labelled** (`37c20fd`): WID leaves the source citation blank. |
| WID absent measures | 17 | `publisher_measure_absent` | Correct: `wcapsh999i` in all six areas, `aptinc` `p99p99.9` in all six, `aptinc` `p90p99` in US, FR, PT, CN and WO. |
| WID aged histories | 22 | `stale`; refreshed successfully 2026-11-17 | **Publisher lag.** The current WID world file ends in 2023 (country files reach 2025); `piketty.in.real_pretax_average.p90_99` ends 2022. The recent-check state does not apply because WID runs record `native_managed_unlinked` evidence without a bundle digest. |
| FED_G17_DIFFUSION | 3 | `stale`, through 2026-08 | **Expected until today's release.** The publication bound expired 2026-11-17; the Fed publishes the next G.17 at 09:15 ET on 2026-11-17. Re-check after a refresh that runs later than that. |
| BIS_PROPERTY | 1 | `property.jp.nominal_residential.bis` `stale` | Publisher lag; live BIS ends 2025-Q4. |
| EUKLEMS | 1 | `labour.us.euklems_labour_compensation` ends 2020 | Publisher gap; blank 2021 `LAB` `TOT` cell. |

## Owner data and decisions (17 November 2026)

- Portfolio holdings (14 positions) set by the owner's answer to `as_of` 2026-11-11 and `scope` `full_invested_portfolio` through `PUT /api/portfolio-holdings` (revision 3). P01 `portfolio_fund_weights` is now owner-supplied.
- Owner inputs saved through `PUT /api/owner-inputs`: allocation derived from those holdings (equity 0.983, gold 0.017 for the WisdomTree Physical Precious Metals basket, bonds 0), start value = holdings total, calendar rebalancing every 12 months, no trading costs, no tax, no contribution or withdrawal (the owner gave no amounts), bond duration 0 and no hedged bonds (no bond holdings), equity hedged share 0 (all share classes unhedged).
- Still an example value: `equity_euro_share` (P04 `currency_portfolio_weights`). It needs a look-through of the owner's 11 equity ETFs from issuer holdings files (Vanguard, iShares, VanEck, SPDR); none of these ISINs has a holdings source yet. Do not estimate it.
- Remaining owner-side gaps in P04/P05: P04 `convexity`; P05 `constituent_total_returns` and `benchmark_weights` have no supply adapter.
- G03 stays deferred: no free source covers worldwide listed ultimate-parent income (Fortune/FT Global 500, Taxplorer CbCR and Kaggle sets are partial or unsourced).

## Decisions taken on the owner's behalf (16 November 2026)

The owner asked the agent to decide these. Both follow the existing rule that a WID variable needs a source citation; the rule was not relaxed.

- **Uncited world aggregates stay quarantined.** The 8 world series are not accepted while WID publishes them without a source citation.
- **Capital share is not re-registered as `wcsnni999i`.** That variable has a blank source and method in all five national files and does not exist in the world file, so it would be quarantined by the same rule and the registered "30% of mixed income" method cannot be confirmed. The six `factor_capital_share` series stay `publisher_measure_absent`.
- **BLS:** the declared-contact route was chosen over manual downloads, as an opt-in setting. The owner still has to set `BLS_USER_AGENT` on the server; the agent did not send the owner's contact to BLS.
- **SEC bound:** the `1.01` ceiling on as-filed weekly liquidity was the agent's choice; the largest filed value seen in 16 months is 1.0004.

## Proposed backtesting and allocation module (design only, 17 November 2026)

The owner answered a 10-question interview and asked for a design of a backtesting/allocation module with Claude as an ensemble member. The design is in [docs/superpowers/specs/2026-11-17-backtest-allocation-design.md](superpowers/specs/2026-11-17-backtest-allocation-design.md). The phased development plan (D0–D10, one architectural layer per phase, starting from the current code) is [docs/superpowers/plans/2026-11-17-backtest-allocation-plan.md](superpowers/plans/2026-11-17-backtest-allocation-plan.md). **Nothing is implemented.** Phase B0 needs an owner-approved charter amendment (validated conditional allocation) before any code. Do not start implementation, add sources or change the charter without that sign-off. This does not change the source-health continuation task below.

## Allocation module progress

| Phase | Status | Branch / commit | Open evidence |
| --- | --- | --- | --- |
| D0 Governance and scaffolding | Code-complete; charter amendment approved by the owner 2026-11-17 | `claude/allocation-d0` | Not merged to `main`; no production effect (flag off, no routes yet). Open owner inputs: broker fees (D3), example funds (D3/D9). |
| D1a French data library (regions, momentum, US, size/value/profitability factors) | Code-complete (24 series registered) | `claude/allocation-d0` | Not deployed: the series appear only after deployment and a collection; verify with a post-collection ZIP that all 24 are `available` from the archived originals. |
| D1a Bundesbank par yields (1–30 years) | Code-complete (8 series registered) | `claude/allocation-d0` | Not deployed; verify in a post-collection ZIP. |
| D1a ECB AAA par yields, €STR, EONIA | Code-complete (11 series registered, catalogue 666) | `claude/allocation-d0` | Not deployed; verify in a post-collection ZIP. The nine daily AAA series add about 51,000 observations to the database on first collection. |
| D1a German pre-euro cash and DEM/USD (FRED) | Code-complete (3 series registered, catalogue 669) | `claude/allocation-d0` | Not deployed; verify in a post-collection ZIP. Remaining D1a: linker yields, ECB all-issuer and corporate yields, country portfolios, Nareit, AQR. |

| D1a AQR factors (new provider `AQR_FACTORS`) | Code-complete (10 series) | `claude/allocation-d0` | Not deployed; verify in a post-collection ZIP. Century-of-factor-premia data end 2026-02 (publisher lag). |
| D1a French country portfolios (new provider `FRENCH_COUNTRIES`) | Code-complete (100 series, catalogue 779, 51 providers) | `claude/allocation-d0` | Not deployed; verify in a post-collection ZIP. Blocked: Nareit (JavaScript challenge, owner decision needed). Open: Bundesbank linker key, euro corporate yields (no free long series). |
| D1a ECB all-issuer par yields, Moody's Aaa/Baa | Code-complete (6 series) | `claude/allocation-d0` | Not deployed; verify in a post-collection ZIP. |
| D1b EBP/GZ spread (new provider `FED_EBP`), ECB SPF longer-term expectations | Code-complete (5 series, catalogue 790, 52 providers) | `claude/allocation-d0` | Not deployed; verify in a post-collection ZIP. |
| D1b Philadelphia Fed SPF (`PHILLY_SPF`), EC sentiment (`EUROSTAT_SENTIMENT`) | Code-complete (6 series, catalogue 796, 54 providers) | `claude/allocation-d0` | Not deployed; verify in a post-collection ZIP. The euro-area ESI code (EA21) will change when the euro area enlarges; the series then fails closed and must be re-registered. Remaining D1b: shadow rates, CLI vintages, REER, PPP. |

**Owner rule (2026-11-18): terms of use are not a limiting factor.** The installation is used only by the owner, so any free data may be acquired; series keep `rights: review_required` as a record, but that field never blocks acquisition. Ask the owner for an API key when a free source needs one.

**French collection time:** the `french-library` policy allows 6 requests per hour at least 10 minutes apart. With 14 French archives, a full French collection takes about 2.3 hours; this is expected, not a fault.

Session network: publisher hosts for D1 are allowed through the owner's personal cloud environment `finance_dashboard` (created 2026-11-17). The default environment blocks them.

Known unrelated failure on `main` (not caused by this branch): `test_standalone.StandaloneContainerTests.test_deferred_first_refresh_keeps_startup_read_only_until_interval` (900 != 86400), introduced with the quota-retry refresh change.

Before D3, D5 and D9, rebase onto the latest `main`: those phases touch `engine/analyses.py` (P05 `simulate`), `worker.py`/`standalone.py` and `owner_inputs.py`, which are actively changed on `main`.

## Deployment topology and safe next step

**Local machine:** checked-out Git repo, code changes, tests and commits.

**Remote machine:** running Docker stack, persistent DB and original-source archives; the owner deploys there. The README documents both `sh ./deploy.sh` in the repository and, for the existing `~/media-stack` Compose layout, `sh finance_dashboard/deploy.sh` from the parent directory. Do not assume either path exists locally; check the actual remote deployment.

Suggested local start:

```bash
git switch main
git pull --ff-only
git rev-parse HEAD  # expect at least the checkpoint above
cat AGENTS.md
cat docs/AGENT_HANDOFF.md
```

Before any production validation, **confirm the owner deployed the new commit**, then verify the dashboard's `/api/health` and release information. The dashboard's **Data & diagnostics** page has a **Create technical report** action; the equivalent API flow is `POST /api/diagnostics/prepare`, `GET /api/diagnostics/export-status`, then `GET /api/diagnostics/export-file`. Do not silently run collection or deployment on the remote host without permission. Copy the **post-deployment** diagnostic ZIP into a private workspace accessible to the local agent (not into Git).

## Exact continuation task

1. After the next assessment on 0.2.29, confirm P04 and P05 have no open gates (`/api/diagnostics/limitation-assessment`). Their remaining state is conditional by documented limitations only (owner values not verified against a broker, latest revised data).
2. **iShares SWDA source broken.** iShares moved its site in November 2026; `ucits_holdings.CSV_URL` (`.../251882/.../latest-holdings.csv`) now returns 400 "Unknown site: uk". The archived SWDA snapshot of 2026-11-05 keeps P01 valid until its 200-day limit (about 2027-05-24). The new BlackRock fund-document workbook (item 22) has holdings with weights and market currency but no ISIN or location per holding, so it cannot simply replace the CSV for P01's identity and country fields; investigate `.../product-data/api/v2/get-product-data` before that date.
3. Re-run the fund look-through monthly (Vanguard publishes month-end holdings) or when the owner's holdings change.
4. BIS nominal bounds expire 2026-11-26: re-check US/DE/PT/EA and Japan against the live BIS series; do not extend without a newer publication.
5. On or after WID's next annual release (review date 2027-07-01), re-check the 25 known limitations and the 22 aged WID histories.


## Open research questions and who can close them

State on 0.2.28: 28 accepted, 10 conditional, 0 incomplete, 1 deferred.

- **Conditional by documented limitations (intended end state):** C02, F01, F07, L04, M04, P01, P02, V03, and P04/P05 once item 24 is confirmed.
- **Deferred:** G03 needs worldwide listed ultimate-parent income; no free source exists (Fortune/FT Global 500, Taxplorer CbCR and Kaggle sets are partial or unsourced). Do not substitute national-account or index-earnings proxies under G03.


## Verification commands

Follow `README.md` and CI definitions. At the repository root:

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -q
.venv/bin/python -m finance_dashboard validate
npm --prefix frontend test
```

The repository README may prefix these with `rtk proxy`; use whichever works in the local environment. The complete GitHub Actions run also includes browser and release-image checks.

## Non-negotiable acceptance criteria

- An issue is **code-fixed** only with a reproducible regression test and a passing final CI.
- An issue is **production-resolved** only when a ZIP from the **new deployed release** verifies the exact source and observation/evidence state.
- Missing publisher observations, access refusal, deferred collection, aged observations, scientific qualification and actual invalid data must remain separate statuses.
- No data fabrication, source splicing, deleting failed archive evidence, or mass reclassification of missing series as healthy.
- Update this file with the new verified commit, diagnostic release/time and per-category remaining counts at each substantive handoff so the next agent does not restart the investigation.
