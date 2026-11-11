# Release verification — 2026-11-11

## Scope and outcome

The implementation extends the existing private research workbench and single-container runtime. It does not invent missing source histories or certify a deferred original method. G03 keeps its documented verified alternatives and original-method deferral.

Fresh read-only assessment of a consistent copy of the owner's local research database: **37 questions; 24 accepted, 12 conditional, one deferred; no incomplete analysis**. P06 is accepted after its rolled-off September Siblis value is independently re-read from the matching archived original. Both original snapshots and all stored versions are retained.

## Delivered capabilities

- Independent configurable figures with valid geography/series/period/transform/encoding/event choices, reset and explicit unavailable-choice explanations.
- Server-backed save, duplicate, rename, compare, explicit linking, method-version revalidation and conflict recovery across tabs/devices.
- One server computation supplies the figure, table, method and exact-view export. Complex structured results expose their complete table and reject misleading date filters; unknown-cadence histories offer dots/tables.
- Original acceptance is bound to exact observation-version digests and original filesystem identities. Revised data, changed/missing originals or new archives withhold results until a fresh content audit succeeds.
- Strict finite/structured portfolio-input validation, corrected real-wealth gap handling, independent arithmetic checks and visible hedging/tax/cash-flow assumptions.
- Frozen Python/npm locks and pinned build/runtime images; configurable refresh, quiet startup, complete defined application-state recovery and CI checks.
- Mobile/keyboard/light/dark flows, request coalescing and deferred offscreen chart initialization.

## Verification evidence

- Full Python offline suite passes; 10 optional original-artifact/PostgreSQL checks are skipped when their inputs are absent. Exact final command/count is recorded in the execution ledger and deployment record.
- **129 frontend tests**, TypeScript and production build pass using the frozen image build.
- **14 real Chromium flows** pass: empty and seeded data, all question sections, exact export, independent save/reset/compare, two-tab stale update recovery, portfolio form, loading/evaluation/connection failures, keyboard and light/dark at 390px.
- Phone document width is **390px at a 390px viewport**, corrected from 1053px overflow. Screenshots were inspected.
- Isolated final-image test passes fresh storage, UID/GID 23456/23457, offline startup, populated container replacement, complete backup/restore and preservation of an unwritable directory's existing files.
- Critical review findings were reproduced with failing tests and corrected: stale acceptance exposing revisions, connected sparse derived histories, mixed FX quote units, structured date bounds doing nothing.
- Source-evidence guard measured over **22,043 filesystem identities**: capture approximately 0.22s; unchanged check approximately 0.04s on the development machine. Database versions are also checked in a pinned transaction.

CI configuration includes Python, frontend, container/recovery and isolated browser jobs. No push was requested; GitHub execution is not claimed. Fixture timings and browser screenshots do not establish full-corpus predictive validity or formal owner visual approval.

## Deployment record

Target: **media-server**, LAN **192.168.1.200**, existing Compose project `/home/tom/media-stack`. The owner explicitly selected a staged copy of the verified local corpus, preserving the divergent server corpus rather than merging conflicting originals.

- Previous server image: `sha256:ddb62a955898ca6592498287847b122b47070dd37d38854b47672e50344eb38d`.
- Previous server data: `/srv/finance-dashboard`, retained intact. Its original schema is `20261104_05`; the verified local corpus is `20261105_06`.
- Staged release: `/home/tom/finance-dashboard-releases/20261111-completion/` with `source`, `recovery` and restored `data` directories.
- The exact final release image/commit, retained previous image, Compose files and rollback commands are written to the release directory's deployment record.

Rollout is being verified; this document is updated after the actual service cutover. A shared-host reboot is outside the scoped application update because unrelated media/network services run there. Container replacement and restart policy are the reliability checks.

## Operating limits

Initial acceptance over the complete corpus can take several minutes. Health/source diagnostics remain available; retryable analysis loading is expected until the audit finishes. `FINANCE_REFRESH_ON_START=0` allows this audit before the first scheduled publisher collection, while subsequent daily updates remain enabled.

Sources can legitimately move from accepted to conditional/incomplete after revisions; the app must explain that state. Model approximations remain in every applicable bundle/export. Native currency/frequency and scientific compatibility constrain figure choices; the app explains unsupported options rather than fabricating a conversion or shared axis.

Use [RUNNING.md](RUNNING.md) for ordinary operation and verified recovery. Keep an independent recovery copy; a previous data tree on the same disk alone is not disaster recovery.
