# Project review — 2026-11-11

Scope: repository at `40d743f` before this documentation update, operational documentation, installed development environment, existing local service and an isolated fresh deployment. The owner confirmed Linux + Docker Compose, LAN IP and port for the remote server.

## Findings

| Priority | Finding | Evidence / consequence |
|---|---|---|
| High | Running corpus no longer matches historical closure | `/api/analysis`: 23 accepted, 12 conditional, one deferred, one incomplete. P06's `global_earnings_yield` is open; its bundle correctly withholds values/estimates |
| High | Backup omits application state | `backup.py` covers SQLite, earnings and five archive roots, but omits `/data/owner-inputs.json` and `/data/source-policy`. Preserve the complete stopped data tree until backup support expands |
| High | Configurable/saved figures unfinished | `TimePanel` has zoom presets; analysis/export endpoints accept `today` only. No independent editor or persistent figure specification exists |
| Medium | Build inputs not reproducible | Docker uses `npm install` and unpinned Python resolution. `frontend/package-lock.json` and `uv.lock` existed untracked; neither was adopted or changed |
| Medium | Some Compose flags hardcoded | Auto refresh and Wisesheets refresh are literal `1`; interval is literal `86400`. `.env` alone cannot override those literals |
| Medium | Portfolio implementation needs release validation | P04 shocks and P05 replay already include costs, cash flows and tax modes; independent validation remains |
| Medium | Browser delivery needs measurement | Vite warns about a roughly 1.03 MB minified entry chunk. All panels mount at once; overview/panels can request duplicate bundles |
| Medium | CI lacks a full release gate | Existing workflow checks Python; frontend/container/browser/recovery checks need CI coverage |
| Low | Acceptance temporarily returns 503 | `Retry-After` is provided; panels retry. Saving portfolio inputs refreshes acceptance. Test visible recovery and request bursts |
| Low | Documentation drift | README, architecture and server setup had obsolete phase claims, counts, CI assertions and retired commands; entry-point documentation is updated here |

The existing container's image differs from the fresh build. Its P06 acceptance snapshot was evaluated at `2026-11-11T13:37:24.872879+00:00`. This review did not reacquire publishers, reconcile all 67 GB of local state or certify the full corpus against the fresh image. That read-only assessment is the first completion-plan task.

## Implemented capabilities

- FastAPI serves built React/TypeScript/ECharts assets and SQLite WAL storage.
- Append-only observations, revisions, receipts/original archives, source-policy pacing and diagnostics.
- All 37 questions have engine definitions. Acceptance gates and limitations accompany bundles; G03 can show labelled verified alternatives while its original method remains deferred.
- Six-story overview, searchable question workbench, eight panels, methods, sources, AI exports and portfolio inputs.
- Alembic startup migrations, scheduled refresh and verified online SQLite/evidence backups.

## Verification performed

| Check | Result |
|---|---|
| Full Python offline suite | 1,111 tests in 31.273 s; OK, 10 skipped |
| Frontend tests | 25 files / 108 tests passed |
| Frontend build | TypeScript/Vite passed; large-chunk warning |
| Docker build | `finance-dashboard:review-20261111` built; layers reused cache |
| Isolated Compose install | Empty database migrated; healthy under host non-root UID/GID |
| Fresh HTTP smoke | UI, health, series, analysis list, P06 bundle/export and owner-input endpoints returned 200; unaccepted analysis values withheld |
| Storage smoke | Valid portfolio saved; invalid allocation rejected with 422 without replacing saved input; saved input survived container recreation |
| Network binding | Health returned 200 through localhost and this host's LAN interface on isolated port 15052 |
| Chromium browser | Question catalogue and explicit unavailable states rendered; initial acceptance 503s resolved. Missing favicon produced cosmetic 404 |
| Native Python startup | Python 3.12, temporary SQLite migration, built UI, health and series API passed |
| Existing installation | Healthy on port 5052; acceptance result above |

The isolated deployment disabled source refresh/backups, used no provider keys and had separate temporary storage. Its container was removed after review. Existing service, research data, keys and user-created lockfiles were not changed.

Optional PostgreSQL/original-artifact checks were skipped when their inputs were absent. Fixtures do not prove live publisher availability. Host LAN-interface access does not prove reachability through the destination server's firewall: test from a second device after deployment.

## Documentation decisions

[Development plan](DEVELOPMENT_PLAN.md) remains the sole roadmap; [the completion plan](superpowers/plans/2026-11-11-project-completion.md) is its task breakdown. [RUNNING.md](RUNNING.md) owns local/native/standalone-server procedures.

Scientific contracts retain their requirements. Their dated “final acceptance open / do not audit yet” statements are historical: the owner explicitly requested this review on 2026-11-11. No new scientific or visual approval is asserted. Current readiness comes from the chosen installation's acceptance report, identified by code/image and evaluation time.

Recommended sequence: fresh empirical readiness and recovery coverage; validated view API and independent saved figures; independent portfolio validation; integrated browser/owner acceptance and a real server restore drill. Keep the single-container architecture for both environments.
