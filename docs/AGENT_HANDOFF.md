# Global Capital Monitor — agent handoff (17 November 2026, sixth checkpoint)

**Purpose:** Resume the existing work in `tpepels/finance_dashboard` without reopening the completed audit or rebuilding implemented fixes. The authoritative source is code on `main`; this file is the investigation checkpoint, not a substitute for tests or new production evidence.

## Last verified checkpoint

- **Verified code commit:** `550bf70` (known publisher limitations). Earlier: WID quarantine reason `37c20fd`, WID rebinding `178806c`, BLS contact `6d9bfce`, upload-status race `f03237a`.
- **CI run:** https://github.com/tpepels/finance_dashboard/actions/runs/44078441400 — **passed** all four jobs: Python (1,578 tests, 10 skipped), frontend (242), browser, release-image.
- **Deployed release:** `0.2.23+4c5b87bf970451cc`, activated 2026-11-17T10:27:01Z, server checkout `b7bbc3a` (contains every fix above except `550bf70`). `BLS_USER_AGENT` is set in the container (value not recorded here).
- **Post-collection export:** on `0.2.23`, prepared 2026-11-17T11:36:58Z, after collection run `4543c85475494761b1d92b9dfbfdb655` (10:28Z to 11:36Z).

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

## Decisions taken on the owner's behalf (16 November 2026)

The owner asked the agent to decide these. Both follow the existing rule that a WID variable needs a source citation; the rule was not relaxed.

- **Uncited world aggregates stay quarantined.** The 8 world series are not accepted while WID publishes them without a source citation.
- **Capital share is not re-registered as `wcsnni999i`.** That variable has a blank source and method in all five national files and does not exist in the world file, so it would be quarantined by the same rule and the registered "30% of mixed income" method cannot be confirmed. The six `factor_capital_share` series stay `publisher_measure_absent`.
- **BLS:** the declared-contact route was chosen over manual downloads, as an opt-in setting. The owner still has to set `BLS_USER_AGENT` on the server; the agent did not send the owner's contact to BLS.
- **SEC bound:** the `1.01` ceiling on as-filed weekly liquidity was the agent's choice; the largest filed value seen in 16 months is 1.0004.

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

1. After the owner deploys `550bf70` and a collection or scheduled refresh has run, take an export. Expect attention to fall by 25 (to 27 with the G.17 series still pending, 24 once they update), `known_limitations` to list 25 series, and no `source_failed` error events for them.
2. After the next scheduled refresh later than 2026-11-17T14:15Z, check that the three G.17 diffusion series move past 2026-08. If they do not, read `diff_sa.txt` and compare it with the stored history before changing anything.
3. BIS nominal bounds expire 2026-11-26. Re-check US/DE/PT/EA and Japan against the live BIS series then; do not extend the bounds without a newer publication.
4. On or after WID's next annual release (review date 2027-07-01), re-check the 25 known limitations and the 22 aged WID histories against the new originals and update or remove the entries.
5. Keep the ICIO originals quarantined. Add regression tests from minimal original samples with source identity; keep full publisher files and credentials out of Git.

Local notes: the virtualenv lacked the declared `numpy` dependency, which made 10 ICIO tests error until it was installed at the locked version.

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
