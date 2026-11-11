# Server source setup and readiness

Reviewed 2026-11-11. Use **[RUNNING.md](RUNNING.md)** for local/remote installation, data transfer and recovery. [Development plan](DEVELOPMENT_PLAN.md) owns implementation order. This page covers source settings for the same single Docker service in either environment.

## Configure the server's own environment

Edit the `.env` used by that Compose project; do not replace an existing file. GitHub secrets do not configure your server. Provider keys belong in the backend environment, never browser code, URLs or committed YAML. Validate with `docker compose config --quiet`, which avoids displaying resolved keys.

| Setting | Purpose |
|---|---|
| `FRED_API_KEY` | Registered FRED access and genuine ALFRED snapshots; current observations and historical release evidence are distinct |
| `BEA_API_KEY` | Optional BEA fixed-asset API access |
| `WISESHEETS_API_KEY` | Optional subscription/quota-dependent filer collection; not required to start the dashboard |
| `FINANCE_INCLUDE_MARKETS` | Optional instrument-price and ECB FX collection; `.env.example` defaults to 0 |
| `FINANCE_VINTAGE_REFRESH` | Capture previous month ALFRED snapshot when configured; does not automatically reconstruct all historical vintages |
| `FINANCE_SEC_HOLDINGS_REFRESH` | Leave 0 until actual fund/SEC-series mappings and a real contact User-Agent are configured |
| `SEC_USER_AGENT` | Real operator/contact identity sent with SEC requests |
| `FINANCE_SOURCE_POLICY_ACKNOWLEDGED` | Comma-separated operator attestations; add `oecd-sdmx` only after verifying permitted direct outbound access |
| `FINANCE_AUTO_BACKUP`, `FINANCE_BACKUP_KEEP` | Backup cycle and retention; backups share the refresh thread and must be copied off the source disk |

Use `.env.example` as the current variable inventory. The standalone Compose file and existing-stack snippet pass refresh flags/interval through `.env`. Set `FINANCE_AUTO_REFRESH=0` for fully offline operation. Set `FINANCE_REFRESH_ON_START=0` with automatic refresh enabled to warm acceptance against a restored corpus first, then start collection after the first daily interval.

All publishers share the managed source-policy client and durable `/data/source-policy/rate-ledger.sqlite3`. Observe publisher pacing, denial/backpressure cooldowns and original-response capture. A missing key or unavailable provider must produce an explicit state, never invented observations. See [SOURCE_POLICY.md](SOURCE_POLICY.md).

## Assess readiness

Start the service, then inspect **Data & sync** and:

- `/api/health`: process/database connectivity.
- `/api/source-coverage`: catalogue sources, actual stored periods, freshness, failures/deferred requests and linked evidence.
- `/api/operations`: collector settings, observed source counts and backup state.
- `/api/analysis`: empirical states of the 37 questions.
- `/api/analysis/P06`: example of an analysis that may correctly withhold values when a required role is unresolved.

Mappings, credentials, successful download, original-value reconciliation and scientific acceptance are separate states. The reviewed catalogue has 398 mapped series; do not interpret that as 398 verified live histories. G03's original method remains deferred; some verified alternatives are shown under their own names.

Ordinary **Sync current data** and **Sync history** preserve earlier observations and serialize collection. Neither guarantees every original archive, release-vintage window, issuer field or scientific role exists. Source failures retain previous valid observations and expose a reason.

For a fresh read-only assessment of an existing populated installation:

```bash
rtk docker compose exec -T finance-dashboard python -m finance_dashboard research operating --output /data/source-readiness-UNIQUE_DATE.json --details
```

Choose a new output filename outside original-evidence directories. The report identifies open gates; nonzero exit status may mean unresolved evidence. Do not add `--acquire` just to generate a report. Acquisition changes the corpus and requires the established verified before/after backup procedure. See [COMMANDS.md](COMMANDS.md) for supported research/source CLI routes.

## Original archives and special imports

Transfer existing originals, receipts, holdings and vintages together with SQLite. A clean repository does not contain the owner's full corpus. Missing licensed/unpublished or publisher-blocked files stay unavailable; no generic key or toggle makes them scientifically valid.

Detailed evidence investigations remain in [OECD evidence](PHASE2_OECD_EVIDENCE.md), [native inputs](PHASE2_NATIVE_INPUT_EVIDENCE.md), [holdings/benchmarks](PHASE2_HOLDINGS_BENCHMARK_EVIDENCE.md) and [source coverage audit](PHASE2_SOURCE_COVERAGE_AUDIT.md). They are dated investigations, not current completion claims. Retired modules such as `finance_dashboard.marx_accounts` are not supported commands; use current engine bundles and original-artifact paths.

## Recovery coverage

`finance_dashboard.backup` creates a verified online SQLite copy plus selected source-evidence/vintage/holdings/maintenance/surplus and earnings components. Version-2 bundles also preserve portfolio inputs, saved figures and a consistent policy-ledger snapshot including committed WAL state. Verify and restore to a separate new/empty directory, retain an independent copy off the same disk, and keep the prior image/data pair for rollback. Transient hidden collector markers are not original evidence; restoring them is not required for numerical reproducibility.
