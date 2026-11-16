# Global Capital Monitor — agent handoff (16 November 2026)

**Purpose:** Resume the existing work in `tpepels/finance_dashboard` without reopening the completed audit or rebuilding implemented fixes. The authoritative source is code on `main`; this file is the investigation checkpoint, not a substitute for tests or new production evidence.

## Last verified checkpoint

- **Verified code commit:** `5195d5f165ae686dbd9ec4d8722bb732116964df`
- **CI run:** https://github.com/tpepels/finance_dashboard/actions/runs/43853221868
- CI **passed** all four jobs: Python (1,550 tests, 10 skipped), frontend, browser, release-image.
- The source inspection ZIP was collected from the **previous** deployed application release `0.2.18+8f10db0c0ebd7bc6` on 2026-11-16. It is a **pre-fix baseline** and should not be interpreted as a regression in `5195d5f`.
- **Production deployment of this commit was not verified in this handoff.** The owner deploys on a remote server. A local agent must not assume it has access to the remote container or its database.

## Completed and tested work — do not repeat

The preceding commits already implemented and verified:

1. SEC N-MFP3 actual publisher header `NETASSETOFSERIES`, including independent verifier and regression fixtures; avoid the previously guessed `NETASSETSOFSERIES`.
2. OECD NFC accounts SDMX accounting-entry selection for multi-code response cases; independent reconciliation updated.
3. Scheduled source refresh promptly resumes after interruption/manual collection instead of idling until the next 24-hour interval.
4. Selected BIS nominal residential source publication bounds for US/DE/PT/EA Q2 2026; expire **2026-11-26**, do not generalize to Japan.
5. A dedicated `PublisherMeasureUnavailable` outcome for exact WID optional measures absent from a verified data/metadata pair. Runs are marked `unavailable` with `wid_measure_unavailable`; missing observations remain missing, are never replaced with zero, and are distinguished from parser/transport faults.
6. Invalid/quarantined WID metadata and incremental-window emptiness cannot be classified as genuine publisher absence.
7. Source coverage, data page, source audit, developer journal and developer report present that absence separately from collector failures, with relevant regression tests.

The scientific-acceptance and independent original-source gates were **not** weakened.

## Production baseline that must be compared, not re-audited

From `finance-debug-0.2.18+8f10db0c0ebd7bc6-20261116T102128.zip`:

- **651** registered histories; **605** stored histories; **79** attention items.
- Of the 79: WID **40** missing exact registered source measures, WID **22** stale; OECD_NFC_ACCOUNTS **5** retained histories with failed refresh; SEC_NMFP **4** missing/invalid; BIS_PROPERTY **5** stale; BLS_OEWS **2** missing; EUKLEMS **1** stale. This list is a diagnostic snapshot, **not** proof these counts persist after redeployment.
- **39** research questions assessed: 24 accepted, 12 conditional, 2 incomplete, 1 deferred. A green source-health counter is not scientific acceptance.
- **54** ICIO other-edition original matrices failed strict accounting checks, with **24,869** recorded failed equations. The independent dependency audit found **zero exact hash matches** between those failing originals and direct current matrix consumers. Do **not** rebalance original cells or waive failed accounts; retain the evidence and investigate separately when it affects a consumer.

The old ZIP was provided to ChatGPT, **not copied into the Git repository or into the local agent's filesystem**. To compare item-level statuses, the agent needs the owner to place that ZIP in a private workspace, or should start from the summary above and a new ZIP.

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

1. Check current `main` and CI against this checkpoint; do not reimplement the changes above.
2. Confirm that the remote release is on the new code. If not deployed, request/perform the **authorized** deployment using the existing script, preserving volumes.
3. Obtain the first **post-deployment** diagnostic export. Compare its release ID, source-health **IDs and states**, repair status, error stages, source evidence receipts, scheduler progress and research assessment against the baseline. Report **resolved, unchanged, newly broken and unverified** by exact source ID.
4. For SEC **4** and OECD NFC **5**, determine whether their fixed parsers now ingest originals. If not, inspect quarantined publisher headers/sample rows and fix the next **specific** mismatch with regression fixtures.
5. Check WID **40** individually: a verified original with no matching row should be reported as `publisher_measure_absent`, not `collection_failed`, and remain an explicit missing scientific input. Re-evaluate after later publisher releases only. WID **22** aged histories need evidence of a newer release; do not invent publisher dates or extend freshness exemptions indefinitely.
6. Investigate BLS OEWS **403/access** on the actual permitted official route; do not bypass access policy. Recheck one EU KLEMS US labour history and any BIS key still stale after the expiring exact-source release bounds.
7. Keep the 54 ICIO accounting-failing originals quarantined as failed scientific evidence; only claim resolution if original balances, mappings and consumer dependence are independently verified. Do not count them as app crashes.
8. Add regression tests from minimal approved original-source samples (with source identity and expected values); keep full original publisher files/credentials out of Git. Run the Python, frontend, browser and release-image CI workflows, and document remaining limitations.

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
