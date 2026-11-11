# Research and presentation release — 2026-11-11

This follows the [first completion release](RELEASE_VERIFICATION.md). The owner requested further research, source and presentation work, confirmed a concise dashboard with expandable research detail, and supplied holdings to combine across accounts.

## Delivered and checked

- Brief findings for all 37 questions, computed in Python from each result's own units, population and native dates. Original-method limits remain distinct from usable alternatives.
- Concise overview and focused research workspace; all question/source fragments and browser history remain usable. Both holdings and model-scenario drafts survive navigation and delayed saves without overwriting later edits.
- Actual holdings use a separate typed, revisioned store, exact-ISIN grouping and Decimal money totals. Unknown inputs remain unknown. Recorded positions, published fund examples and model replays are labelled separately.
- OECD annual-date trimming, evidence-aware shared publisher originals, bounded WID pacing and durable request rotation. Failed parsing cannot monopolize the next publisher budget; policy deferrals retain their place.
- G03's cap/P-E calculation is explicitly an implied index earnings proxy. Its verified Brazilian original sample covers 442 consolidated income reporters, among 671 filing issuers and 761 versions; worldwide listed-parent coverage remains unverified.
- Current evidence assessment remains **24 accepted, 12 conditional, one deferred; none incomplete**. These scientific states describe actual coverage, not a software completion percentage.

Independent review reproduced four important defects (pending-save overwrite, navigation draft loss, broken explorer anchors and failed-source starvation). Regression tests reproduced each before the fixes. Further checks corrected the G01 population labels, actionable holdings warnings, reload-state persistence, mobile P06 overflow and F07 financial-assets terminology.

## Verification

- **1,215 Python tests: OK, 10 optional skips** for original-artifact/PostgreSQL checks without their inputs.
- **149 frontend tests**, TypeScript and production build pass in the frozen Docker build.
- **16 real Chromium fixture flow groups**, including controlled failures, delayed saves, history navigation, actual holdings import/conflicts, independent saved figures and exact exports. The same checks pass against UI files extracted from the final image.
- **74 populated, read-only question checks**: all 37 at desktop width and all 37 at 390px, with no page/console errors or whole-document overflow. Both themes were inspected; owner/model/saved documents remained unchanged.
- Actual overview height is approximately 1,410px at desktop width and 2,292px at 390px, replacing the former continuous page of approximately 58,143px/88,122px. Wide graphics have explicit scrolling and table alternatives.
- Final-image checks pass fresh storage, UID/GID 23456/23457, offline startup, holdings save and container replacement, complete state recovery, and preservation of an unwritable directory's existing files.
- Both live installations pass targeted Chromium checks: overview, recorded holdings, unsaved navigation drafts, mobile P06/G03, legacy chart links and a Germany-only indexed figure with matching exact export. Full research assessment returns HTTP 200 on each host with the counts above. No unexpected page/console errors remain; holdings, model inputs and saved-view documents are unchanged.

Code commit: `84230be` (the release record includes its full hash). Image: `finance-dashboard:release-84230be`. Docker image identity on both hosts: `sha256:7bd537b37eca7c55784b3c990ddd422d8f4a59866a5490e60bde23e4365800c4`. Installed Python source matches the reviewed tree: `1c07ad0bfe665ed053a44c8e622a282993294b8ad6c8033a78b15b0044b7870f`.

The main production JavaScript chunk remains about 1.07 MB (339 KB gzip); the size warning is retained. No hosted CI execution or formal owner visual approval is claimed.

## Source and recovery evidence

All 29 selected scalar sources eventually refreshed successfully through canonical acquisition, including the nine previously rejected OECD windows. Five US WID series completed from their native two-file pair under the unchanged 360-second spacing. The CVM annual original was acquired in one governed request. Earlier policy deferrals remain recorded; no failed original, prior observation or receipt was erased.

Stored economic histories remain **397/398**. The legacy source-attention count changes from **247 to 221**; observations and refresh outcomes are now separate. The independent age inventory is 281 within the expected age/pinned release, 116 older than that window, and one missing. An age heuristic does not certify the latest publisher release. The remaining daily gold quote and blocked historical-source refresh are explicit; existing verified histories and named research alternatives remain available.

Sealed version-2 recovery manifest: `finance-20261111T185626582578Z.json`. It contains all four components, including the private holdings snapshot and consistent source-policy SQLite state. The consistent main database contains 398 series, 15,746 runs and 391,813 observation versions; the evidence archive contains 15,839 files. All five transferred files match local hashes and were verified/restored into a new server directory using the matching image.

The independent local recovery copy is `/home/tom/.local/share/finance-dashboard/research-presentation-20261111/recovery/`; the server copy is the new release's `recovery/` directory. Credentials are excluded from bundles and preserved privately through separate environment backups.

## Deployment and rollback

- Local: **http://localhost:5052/**, data at `/home/tom/.local/share/finance-dashboard/research-presentation-20261111/data`.
- Server: **http://192.168.1.200:5052/**, data at `/home/tom/finance-dashboard-releases/20261111-research-presentation/data`.
- Both use the same verified image. Daily collection remains enabled, with `FINANCE_REFRESH_ON_START=0` so the initial corpus assessment precedes scheduled acquisition.
- The server reuses configured credentials and a verified direct OECD network origin. Credentials never appear in source or browser assets.
- Previous local image/data and the server's previous active release remain intact. The divergent original server corpus at `/srv/finance-dashboard` is also retained. Only the finance service was recreated; unrelated service configurations/container identities were checked unchanged. Restart policy is `unless-stopped`; no shared-host reboot was performed.
- Local rollback: `/home/tom/.local/share/finance-dashboard/research-presentation-20261111/local-rollback.sh`.
- Server rollback: `/home/tom/finance-dashboard-releases/20261111-research-presentation/rollback.sh` on `media-server`. Each script restores its matching previous environment/image/data selection.

Both live services are healthy and fully assessed. Private deployment records, browser/test reports and recovery manifests are retained alongside each release; local verification evidence is under `/home/tom/.local/share/finance-dashboard/research-presentation-20261111/verification/`, with a separate copy in the server release's `verification/` directory. The temporary staging API was stopped after verification; the two production services remain running. See [research boundaries](RESEARCH_COMPLETION.md), [recorded holdings](PORTFOLIO_HOLDINGS.md) and [collection reliability](SOURCE_COLLECTION_RELIABILITY.md).
