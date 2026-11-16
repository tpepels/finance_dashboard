# Global Capital Monitor — agent handoff (16 November 2026, fourth checkpoint)

**Purpose:** Resume the existing work in `tpepels/finance_dashboard` without reopening the completed audit or rebuilding implemented fixes. The authoritative source is code on `main`; this file is the investigation checkpoint, not a substitute for tests or new production evidence.

## Last verified checkpoint

- **Verified code commit:** `37c20fd` (WID quarantine reason). Earlier in this checkpoint: WID rebinding `178806c`, BLS contact `6d9bfce`, upload-status race `f03237a`.
- **CI run:** https://github.com/tpepels/finance_dashboard/actions/runs/43981328973 — **passed** all four jobs: Python (1,566 tests, 10 skipped), frontend, browser, release-image.
- **Deployed release:** `0.2.22+627304a4cd605b11`, activated 2026-11-16T19:24:13Z, server checkout `612f523`. It contains `178806c`, `6d9bfce` and `f03237a` but **not** `37c20fd`; the owner deploys.
- **Post-collection export:** on `0.2.22`, prepared 2026-11-16T23:38:42Z, after collection run `4f370bd9b5414ba3a7a4caf79eaebbda` (22:31Z to 23:37Z).

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

The scientific-acceptance and independent original-source gates were **not** weakened.

## Production state after the collection on 0.2.22 (export 2026-11-16T23:38Z)

**651** registered histories, **624** stored, **51** attention items (0.2.18 baseline: 79; 0.2.20 after collection: 66). The 54 ICIO failing originals stay quarantined; do not rebalance or waive them. Research assessment was still running when the export was taken, so its counts were not re-read.

| Source | Attention | State in export | Verdict |
| --- | --- | --- | --- |
| SEC_NMFP | 0 | all four `available`, 16 months through 2026-10 | **Fixed and verified in production** (`b833082`, since 0.2.20). |
| OECD_NFC_ACCOUNTS | 0 | ES and FR transactions `available` through 2025 | **Verified in production** (since 0.2.20). `profit.es.nfc_net_fixed_assets` and `profit.pt.nfc_net_fixed_assets` end 2023 and read `source_checked_no_newer_data`; not attention items. |
| WID national wealth-income ratios | 15 -> 0 | all `available`; 226 annual values 1800-2025 (PT: 46, 1980-2025), equal to the archived originals | **Fixed and verified in production** (`b8602a8` + `178806c`). No `source_mapping_mismatch` events. |
| WID world aggregates | 8 | `collection_failed`, reported as `wid_observation_invalid` | **Correctly rejected** (blank WID source citation), **mislabelled**. The label is fixed by `37c20fd`, not deployed; expect `wid_metadata_invalid` after the next deploy and collection. |
| WID absent measures | 17 | `publisher_measure_absent` | **Correct classification**, verified in production. |
| WID aged histories | 22 | `stale` (21 end 2023, 1 ends 2022) | **Unchanged.** Needs a newer publisher release. |
| BIS_PROPERTY | 1 | `property.jp.nominal_residential.bis` `stale` | **Unchanged, publisher lag.** The live BIS series ends 2025-Q4. Bounds for US/DE/PT/EA expire 2026-11-26. |
| BLS_OEWS | 2 | one `provider_http_403`, one `source_policy_deferred` | **Unchanged.** `BLS_USER_AGENT` is not set on the server; nothing has been sent with a declared contact yet. |
| EUKLEMS | 1 | `stale`, `labour.us.euklems_labour_compensation` ends 2020 | **Unchanged, publisher gap.** The archived US workbook has a blank 2021 `LAB` cell for `TOT`. |

The 17 absent WID measures are `wcapsh999i` in all six areas, `aptinc` `p99p99.9` in all six, and `aptinc` `p90p99` in US, FR, PT, CN and WO.

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

1. After the owner deploys a release containing `37c20fd`, start a collection (`POST /api/data/collection/start` with `Content-Type: application/json` and `X-GCM-Action: dashboard`; about an hour) and take a new export. Expect 51 attention items, with the 8 WID world series now `wid_metadata_invalid`. Report any deviation by exact source ID.
2. BLS OEWS: the owner still has to set `BLS_USER_AGENT` (a contact, e.g. `GlobalCapitalMonitor/0.2 name@example.org`) in the server environment and pass it through the `~/media-stack` Compose file. Then check whether the two OEWS series collect. If BLS still refuses, fall back to the owner downloading `oesm21nat.zip`..`oesm25nat.zip`. Do not bypass the refusal.
3. BIS nominal bounds expire 2026-11-26. Re-check US/DE/PT/EA and Japan against the live BIS series then; do not extend the bounds without a newer publication.
4. Keep the ICIO originals quarantined. Add regression tests from minimal original samples with source identity; keep full publisher files and credentials out of Git.
5. The remaining 51 items are publisher-side (22 WID stale, 17 WID absent, 8 WID uncited, BIS JP lag, EU KLEMS gap) or need the BLS setting. None is a known software defect.

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
