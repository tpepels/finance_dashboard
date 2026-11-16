# Global Capital Monitor — agent handoff (16 November 2026, second checkpoint)

**Purpose:** Resume the existing work in `tpepels/finance_dashboard` without reopening the completed audit or rebuilding implemented fixes. The authoritative source is code on `main`; this file is the investigation checkpoint, not a substitute for tests or new production evidence.

## Last verified checkpoint

- **Verified code commit:** `b8602a8db4120f053dae7a64dc144d75bcf84c79`
- **CI run:** https://github.com/tpepels/finance_dashboard/actions/runs/43859621541
- CI **passed** all four jobs: Python (1,557 tests, 10 skipped), frontend, browser, release-image.
- **Deployed release:** `0.2.20+caa79472d4a8f406`, activated 2026-11-16T11:58:41Z, server checkout at `3be6760` (contains the SEC and WID fixes). Checked over SSH on `media-server` (`~/media-stack`).
- **Post-deployment export:** `finance-debug` for `0.2.20`, prepared 2026-11-16T12:15:26Z. On the production originals the deployed code now replays the SEC July 2025 archive as `accepted_shape_not_certified` (was `sec_nmfp_liquidity_invalid`), and the WID samples find rows for the corrected codes (for example US `wnweal999i` 226 rows, WO `mnninci999` 225 rows).
- **Not yet re-ingested:** no collection has run on `0.2.20`. The newest attempt is 2026-11-16T00:47Z under `0.2.18`, the scheduler is `waiting`, and the next refresh is due 2026-11-16T23:41Z. Source states and the count of 75 attention items are therefore still the pre-fix records.

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

The scientific-acceptance and independent original-source gates were **not** weakened.

## Production state on 0.2.19 (export 2026-11-16T11:16Z, before any refresh)

**651** registered histories, **605** stored, **75** attention items (baseline on 0.2.18: 79). Research assessment is unchanged: 24 accepted, 12 conditional, 2 incomplete, 1 deferred. The 54 ICIO failing originals and 24,869 failed equations are unchanged and stay quarantined; do not rebalance or waive them.

| Source | Count | State in export | Verdict |
| --- | --- | --- | --- |
| BIS_PROPERTY | 5 -> 1 | US/DE/PT/EA now `available` | **Resolved** by the expiring bounds (expire 2026-11-26). `property.jp.nominal_residential.bis` stays stale: the live BIS series ends 2025-Q4, so this is publisher lag. |
| SEC_NMFP | 4 | `collection_failed`; replay on 0.2.19 gives `sec_nmfp_liquidity_invalid` | **Newly diagnosed**, code-fixed in `b833082`, not deployed. The header fix is confirmed: `missing_columns` is empty. |
| OECD_NFC_ACCOUNTS | 5 | `refresh_failed_with_data`, `source_invalid`, attempts from 0.2.18 | **Unverified in production.** The deployed parser reads all six transactions from the live ESP and FRA Table 14 documents fetched on 2026-11-16 (through 2025). |
| WID optional measures | 40 | `collection_failed`, `wid_measure_unavailable`, attempts from 0.2.18 | **Reclassified**, code-fixed in `b8602a8`, not deployed. See the breakdown below. |
| WID aged histories | 22 | `stale` (21 end 2023, 1 ends 2022) | **Unchanged.** Needs a newer publisher release. |
| BLS_OEWS | 2 | one `provider_http_403`, one `source_policy_deferred` | **Unchanged.** `https://www.bls.gov/oes/tables.htm` returns Access Denied to a client without a declared contact. |
| EUKLEMS | 1 | `stale`, `labour.us.euklems_labour_compensation` ends 2020 | **Unchanged, publisher gap.** The archived US growth-accounts workbook has a blank 2021 `LAB` cell for `TOT`. |

WID 40, checked against the archived originals (hashes equal the production samples):

- **15 national wealth-to-income ratios** (US, FR, PT, CN, IN x national/private/public) parse with data after `b8602a8`.
- **8 world series** (3 ratios, 5 totals) are published, but the world metadata leaves the source citation blank. The citation rule quarantines them, so after deployment they should fail as `wid_metadata_invalid`, not show as publisher-absent. Accepting uncited world aggregates is an owner decision; the rule was not relaxed.
- **17 are genuinely absent:** `wcapsh999i` in all six areas, `aptinc` `p99p99.9` in all six, and `aptinc` `p90p99` in US, FR, PT, CN and WO.
- `wcapsh999i` exists in no file. The national files publish `wcsnni999i` ("Capital share of total national income at factor-price", 1970-2024) with empty descriptions, so the registered "30% of mixed income" method cannot be confirmed. It was left unchanged; re-registering it is an owner decision.

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

1. `0.2.20` is deployed. Wait for the refresh due 2026-11-16T23:41Z, or have the owner start a collection, then take a new export. Do not judge re-ingestion from an export taken before a refresh.
2. In that export expect: SEC 4 `available` with 16 months from 2025-07; OECD NFC 5 `available`; WID 15 ratios `available`, 8 world series `collection_failed`/`wid_metadata_invalid`, 17 `publisher_measure_absent`. Report any deviation by exact source ID.
3. Ask the owner about the two WID decisions above (uncited world aggregates, `wcsnni999i`). Do not decide them in code.
4. BLS OEWS: the owner must either approve a declared contact User-Agent for `www.bls.gov` (as `SEC_USER_AGENT` does for the SEC) or download `oesm21nat.zip`..`oesm25nat.zip` manually. Do not bypass the refusal.
5. BIS nominal bounds expire 2026-11-26. Re-check US/DE/PT/EA and Japan against the live BIS series then; do not extend the bounds without a newer publication.
6. Keep the ICIO originals quarantined. Add regression tests from minimal original samples with source identity; keep full publisher files and credentials out of Git.

Local notes: the virtualenv lacked the declared `numpy` dependency, which made 10 ICIO tests error until it was installed at the locked version. `test_msci_regional_factsheets...reuses_verified_cdx` fails locally with and without these changes and passes in CI.

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
