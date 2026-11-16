# Data & diagnostics: operator-facing page contract

The page prioritizes measured data availability, observed progress, and the
few occasions when a person must provide a file or share a diagnostic bundle.
It has one authoritative status view. The Source Explorer remains a separate
chart-and-source reading tool.

## Reading order

1. **Current data status** — registered economic histories and saved observations
   across the full catalogue, with missing and review totals.
2. **Next scheduled update** — the actual automatic schedule when known.
3. **What needs your input** — the sole place for standalone command buttons.
   With no intervention required it contains no buttons. A manual collection
   button appears only when automatic collection is disabled or unavailable
   and data needs checking. A technical ZIP preparation button appears only
   when an issue calls for investigation. Creating a report requires a
   deliberate user request; routine source checking does not.
4. **Collection activity** — passive progress and individual download results.
   The initial publisher-download queue counts **download groups**, such as a
   WID or OECD file family. The total registered series count in the overview
   counts **individual economic time series**. A run with 9 download groups and
   651 registered histories is therefore expected, and both units are labeled.
   Additional maintenance job results are read-only; they never offer another
   start, retry or stop button here.
5. **Add publisher files** — one destination for collection-requested manual
   originals and optional official files a user already possesses. The
   optional publisher selector is initially empty. No upload field is shown
   for an optional source until a user deliberately chooses it. On uploading,
   the existing, publisher-specific importer starts automatically; staged
   OECD archives are recovered after a restart without another button.
6. **Needs attention** — individual histories with missing data, outdated
   observations, publisher failures and waiting states. This is a data
   availability list; it never assumes that a user can repair a provider
   error by pressing a button.
7. **Research quality** — read-only research assessment that updates on the
   normal page poll and on accepted data updates. It excludes duplicate
   source-availability warnings (shown above) and informational method notes.
   High-impact findings describe the measured discrepancy, any verified
   connection to a current research input, and the actual next technical
   step. A missing acceptance snapshot (0 of 39 questions evaluated) is
   explicitly marked *unavailable*, never portrayed as 39 failed results.
   The full original diagnostics remain available in the technical ZIP.

## Interaction and architecture constraints

- One data-collection owner and one original-source validation pipeline.
  The page reuses existing APIs and never creates a new collector, queue,
  verification service, import path or diagnostic status engine.
- Automatic updates do not require user confirmation, repeated refresh,
  manual reassessment, or checks of stored source files. Those buttons have
  been removed from the page. Existing maintenance and reassessment APIs
  remain available to support automated recovery and software maintenance.
- A user file is only requested where the API provides a registered original
  identity and official publisher URL. File inputs stay in the single upload
  section; selection automatically validates/imports. Failures remain visible
  and are recorded for the developer.
- The diagnostic ZIP contains the current archived technical evidence.
  Preparing the ZIP is an explicit user action when sharing it for
  investigation. Raw event logs remain accessible in the header's existing
  System status interface; the Data page has no separate technical console.
- Deep links `#diagnostics`, `#manual-files`, `#source-coverage` and
  `#research-quality` keep their current section destinations.
- Historical maintenance records are shown as recorded facts. Do not imply
  that historical backfilling is automatically scheduled unless observed
  schedule evidence says so.
- Long-page sections use editorial hierarchy, not nested disclosure arrows.
  Keyboard focus, accessible labels, responsive widths, dark appearance and
  explicit active/error states are required.
- Panel backgrounds, borders, normal text and subtitles use the shared
  `--dx-*` palette. `--dx-tertiary` is the orange used for editorial
  subtitles, including the Source Explorer eyebrow, in both themes.

## Acceptance criteria

- Normal scheduled collection: zero standalone page action buttons.
- Automatic collection unavailable with unresolved histories: exactly one
  one-time collection control, in **What needs your input**.
- A technical problem: diagnostic ZIP creation and download are available
  in that same action area, with preparation status. No unrequested manual
  file tasks are fabricated.
- All publisher file inputs are under **Add publisher files**; optional
  upload controls are absent until a publisher is selected. A selected OECD
  archive reuses its canonical importer, including restart recovery.
- Download-group counts are explicitly distinguished from the whole source
  catalogue counts.
- Research-quality summary has no manual refresh/recheck buttons, explains
  whether a result affects a live consumer, and reports unavailable acceptance
  without inventing completed scientific checks.
- Frontend, Python, browser and release-image CI must pass.
