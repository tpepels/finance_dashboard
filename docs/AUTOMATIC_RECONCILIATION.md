# Automatic ingestion and downstream reconciliation

Global Capital Monitor uses one single-container source refresh scheduler and
one authoritative ingestion path. A collection completed by an older release
does **not** need to be repeated after a deployment.

## Default lifecycle

1. **Scheduled collection** runs when `FINANCE_AUTO_REFRESH=1` (normally
   every 86,400 seconds, with restart-safe due time). Publisher-specific
   rate limits, original source identities and existing stored observations
   remain authoritative. Failed/deferred publisher calls do not delete data.
2. **Validate and commit** an individual source through
   `IngestionService.refresh`. A successful transaction publishes the
   `series_ingested` event **after** commit. A successful refresh reporting
   zero new versions still publishes because publisher-check evidence and the
   source's last attempt can have changed.
3. **Coalesce** source-change events for one second in
   `DataChangeCoordinator`. Source changes in different applications/engines
   remain isolated. The coordinator waits until the application's canonical
   refresh/maintenance lock has been released; it does not perform network
   collection itself.
4. **Invalidate research acceptance** and **rebuild cached source coverage**
   through the existing background workers. New changes arriving during
   either evaluation trigger another evaluation rather than allowing an old
   result to overwrite a newer one. An external evidence conflict gets at
   most two immediate scientific retries.
5. **Present results** from the new source-health snapshot and acceptance
   bundles. Existing research figures are recomputed from canonical, accepted
   input versions on demand. No missing observation is filled or guessed.
6. **Record exceptions**: Missing original files, publisher access refusal,
   scientific contract failure and old source observations remain visible
   with the exact series and next action in the limitation audit and debug ZIP.

These notifications also occur when manual originals are accepted, OECD ICIO
originals are imported/reassessed, maintenance completes and an automatic
scheduled cycle ends (which can update vintage and SEC evidence outside the
scalar ingestion service). All notifications share one coordinator and never
launch an independent publisher downloader.

## What the numbers mean

- **426/426 with data**: historical observations exist. It does not establish
  current publisher coverage or scientific acceptance.
- **Last source period before expected cadence**: a research input still needs
  publisher freshness assessment, even if its most recent download succeeded.
- **Publisher original checked; no newer value**: a bounded successful check
  has documented that the release contained no newer observations. No retry
  should be forced merely to improve the dashboard warning count.
- **Source repair complete/partial**: a targeted publisher health attempt
  finished. `issues_after` describes unresolved stale or missing source data.
  Retrying the same unchanged source immediately cannot manufacture new data.
- **Scientific acceptance updating**: a background evaluation is processing
  the last committed evidence. Its previous results are not promoted while a
  new source version is being assessed.

## Operational interface

The Data Collection page displays the scheduled refresh state, last
ingestion-triggered reconciliation and ongoing scientific assessment. The
latest independent source-health repair is distinguished from any previous
release's collection session. Archived download rows and manual maintenance
are collapsed.

A user action is required **only** if the system reports something it cannot
do autonomously, such as a named official original file that cannot be fetched
within publisher policy, unsupported publisher credentials/contact, or an
explicitly requested out-of-schedule recheck. The regular workflow has no
mandatory Start, Repair or Reassess button.

## Verification and boundaries

The implementation uses process-local pub/sub, matching the existing
single-process Docker deployment. A separate external CLI process does not
share these in-memory subscribers. The next acceptance read performs input
version/evidence guards and the normal source-health expiry triggers another
coverage evaluation; a true cross-process push would require a durable
outbox/polling mechanism.

Source-health and research evaluations may be heavy and remain asynchronous.
The new coordinator debounces updates and never performs SQLite scans inside
the publisher transaction or frontend request. If there is no newer published
WID/EU KLEMS observation, automatic reconciliation retains the stale state
until the evidence itself actually improves. No automatic remediation relaxes
scientific validation or bypasses publisher quotas.
