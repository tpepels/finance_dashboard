# Release verification — 2026-11-11

This is the first completion release record. The subsequent [research and presentation release](RESEARCH_RELEASE_VERIFICATION.md) records the current improvements and deployment paths.

## Scope and outcome

The implementation extends the existing private research workbench and single-container runtime. It does not invent missing source histories or certify a deferred original method. G03 keeps its documented verified alternatives and original-method deferral.

Fresh read-only assessments of the owner's local research database and the restored live server corpus agree: **37 questions; 24 accepted, 12 conditional, one deferred; no incomplete analysis**. P06 is accepted after its rolled-off September Siblis value is independently re-read from the matching archived original. Both original snapshots and all stored versions are retained.

## Delivered capabilities

- Independent configurable figures with valid geography/series/period/transform/encoding/event choices, reset and explicit unavailable-choice explanations.
- Server-backed save, duplicate, rename, compare, explicit linking, method-version revalidation and conflict recovery across tabs/devices.
- One server computation supplies the figure, table, method and exact-view export. Complex structured results expose their complete table and reject misleading date filters; unknown-cadence histories offer dots/tables.
- Original acceptance is bound to exact observation-version digests and original filesystem identities. Revised data, changed/missing originals or new archives withhold results until a fresh content audit succeeds.
- Strict finite/structured portfolio-input validation, corrected real-wealth gap handling, independent arithmetic checks and visible hedging/tax/cash-flow assumptions.
- Frozen Python/npm locks and pinned build/runtime images; configurable refresh, quiet startup, complete defined application-state recovery and CI checks.
- Mobile/keyboard/light/dark flows, request coalescing and deferred offscreen chart initialization.

## Verification evidence

- Full Python offline suite: **1,166 tests, OK, 10 optional skips** for original-artifact/PostgreSQL checks whose inputs are absent. Command: `python -m unittest discover -s tests -p 'test_*.py' -q`.
- **129 frontend tests**, TypeScript and production build pass using the frozen image build.
- **14 real Chromium flows** pass: empty and seeded data, all question sections, exact export, independent save/reset/compare, two-tab stale update recovery, portfolio form, loading/evaluation/connection failures, keyboard and light/dark at 390px.
- Phone document width is **390px at a 390px viewport**, corrected from 1053px overflow. Screenshots were inspected.
- Isolated final-image test passes fresh storage, UID/GID 23456/23457, offline startup, populated container replacement, complete backup/restore and preservation of an unwritable directory's existing files.
- Both live installations pass health and full-corpus checks, Germany-only indexed figures with matching exact exports, temporary saved-view create/read/delete preserving existing records, and real Chromium configuration at desktop/390px widths without console errors. The LAN server's dark theme was also checked. Verification records are retained locally under `/home/tom/.local/state/finance-dashboard/deployments/20261111/` and in the server release directory.
- Critical review findings were reproduced with failing tests and corrected: stale acceptance exposing revisions, connected sparse derived histories, mixed FX quote units, structured date bounds doing nothing.
- Source-evidence guard measured over **22,043 filesystem identities**: capture approximately 0.22s; unchanged check approximately 0.04s on the development machine. Database versions are also checked in a pinned transaction.

CI configuration includes Python, frontend, container/recovery and isolated browser jobs. No push was requested; GitHub execution is not claimed. Fixture timings and browser screenshots do not establish full-corpus predictive validity or formal owner visual approval.

## Deployment record

Target: **media-server**, LAN **192.168.1.200**, existing Compose project `/home/tom/media-stack`. The owner explicitly selected a staged copy of the verified local corpus, preserving the divergent server corpus rather than merging conflicting originals.

- Previous server image: `sha256:ddb62a955898ca6592498287847b122b47070dd37d38854b47672e50344eb38d`.
- Previous server data: `/srv/finance-dashboard`, retained intact. Its original schema is `20261104_05`; the verified local corpus is `20261105_06`.
- Staged release: `/home/tom/finance-dashboard-releases/20261111-completion/` with `source`, `recovery` and restored `data` directories.
- Release commit: `d0c7f37fbf2859e6a0b0711fe6405b2fa7887208`; image: `finance-dashboard:release-d0c7f37`.
- Image ID on both hosts: `sha256:741c7c55b4d99aa16cf6f3b43bbda305ec3fc1b5e0280a3c72ccb4abe704dbd6`.
- Local service: **http://localhost:5052/**, using its existing `data-local` mount. Previous image retained as `finance-dashboard:local-before-d0c7f37`.
- Server service: **http://192.168.1.200:5052/**, using `/home/tom/finance-dashboard-releases/20261111-completion/data`. Previous image retained as `finance-dashboard:server-before-d0c7f37`.
- The original media-stack Compose files remain intact. Its `.env` adds the release override through `COMPOSE_FILE`; the original environment is preserved privately in the release directory. Only the finance service was recreated; unrelated container identities were checked unchanged.
- `deployment.json` records image, data paths, Compose files and restart policy. To return to the matching previous server image **and** original data mount, run `/home/tom/finance-dashboard-releases/20261111-completion/rollback.sh` on `media-server`.

Both live services are healthy, and both full-corpus `/api/analysis` reports return the counts above. The server is reachable from the development computer over the LAN. Restart policy is `unless-stopped`. A shared-host reboot is outside the scoped application update because unrelated media/network services run there; container replacement and restart policy are the reliability checks.

The version-2 recovery manifest is `finance-20261111T172143470266Z.json`. All four components and the manifest were transferred with matching hashes, then verified and restored into a new directory using the release CLI. The consistent primary snapshot contains 398 series, 15,709 runs and 391,787 observation versions; archived evidence contains 15,783 files. The policy SQLite state is included. No owner-input or saved-view file existed at this checkpoint, so those optional files are correctly absent. Credentials are excluded.

An independent verified copy is retained off the server at `data-local/backups/release-20261111/` in the local workspace; the server copy is in the release's `recovery/` directory. This bundle contains the defined current research/application state; historical backup archives and operational logs remain in their original trees.

## Operating limits

Initial acceptance over the complete corpus can take several minutes. Health/source diagnostics remain available; retryable analysis loading is expected until the audit finishes. `FINANCE_REFRESH_ON_START=0` allows this audit before the first scheduled publisher collection, while subsequent daily updates remain enabled.

The main production JavaScript chunk remains large: 1,038,297 bytes (approximately 327 KB with gzip). The preview and editor are separate lazy chunks; duplicate in-flight API reads and offscreen chart initialization have been reduced. The build's size warning remains visible. Fixture timings do not establish a full-corpus performance guarantee.

Sources can legitimately move from accepted to conditional/incomplete after revisions; the app must explain that state. Model approximations remain in every applicable bundle/export. Native currency/frequency and scientific compatibility constrain figure choices; the app explains unsupported options rather than fabricating a conversion or shared axis.

Use [RUNNING.md](RUNNING.md) for ordinary operation and verified recovery. Keep an independent recovery copy; a previous data tree on the same disk alone is not disaster recovery.
