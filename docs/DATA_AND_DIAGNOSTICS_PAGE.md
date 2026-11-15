# Data & diagnostics: single operator workspace

This page is the authoritative operator entry point for source collection, current progress, source health, research limitations, diagnostic evidence and maintenance. The existing Source Explorer remains a separate research/chart exploration tool, not a competing data-administration view.

## User-facing hierarchy (top to bottom)

1. **Overview:** Show the current job stage, the last completed check's time, available/missing/outdated data totals, and two immediately visible cards: **Next automatic step** and **Your action**. The automatic card shows a real scheduler deadline when observed, and explicitly flags an enabled service with no completed run. The action card distinguishes zero manual uploads from failed source requests requiring technical investigation. **Find and download missing data** stays visible but visually secondary while automatic checking is enabled; it becomes the dominant action only when a manual check is actually necessary.
2. **Collection activity:** Show automatic collection progress and individual download results. A separate, clearly identified historical-record search remains available here for occasional older economic releases and fund holdings. Do not duplicate the normal collection and repair actions.
3. **Add publisher files:** The single upload destination contains files explicitly requested by the current collection and other official publisher originals (WID, EU KLEMS, MSCI, Swinkels, gold and OECD). Choose one publisher from a labeled selector. Display download links, upload fields and processing status together, without nested expandable disclosures. OECD ZIP/ReadMe uploads and rechecks use the existing importer in this same section.
4. **Needs attention:** Show affected data series, their latest saved dates, status and next steps. Data needing investigation must not imply that a manual download is necessary.
5. **Research quality:** Show findings that require scientific review, prioritizing their current state and actual next step.
6. **Investigate a data problem:** An explicitly technical area, only for exportable failure evidence and on-demand event logs. It never starts a publisher collection or presents a file uploader.

Source lists can scroll vertically instead of hiding behind expandable disclosures. Put low-frequency, technical tools below actionable information, but do not hide their controls inside disclosure widgets.

## Navigation, preservation and operational contracts

- Primary navigation and toolbar use the same label: **Data & diagnostics**, canonical anchor `#research-sources`.
- Legacy deep links `#diagnostics` and `#source-coverage` focus their respective sections on the same page. `#research-quality` also addresses the integrated research assessment. Do not restore a duplicate Diagnostics page.
- The header Status indicator shows a short health summary and counts with one link to the consolidated page. Keep the status popup free from nested disclosures, repeated tables and raw event codes.
- Existing routes, action authorization, publisher quotas, immutable-original validation, cancellation and source-policy safeguards remain authoritative. Do not create new collection engines or substitute synthetic observations.
- Keep collection execution and diagnostics preparation asynchronous. Preserve last-known collection and coverage state if status polling fails, while explicitly flagging staleness and errors.
- The only top-level collection button is **Find and download missing data** and starts the established original-source queue plus the source-health repair workflow. More specialized operations remain available lower on the page, not as peers of the main action.
- The interface explains the result of every operation, including delayed checks and failures. Keep the original technical details in diagnostic exports and the user-requested technical log.

## Writing and grouping rules

- Name sections by purpose: **Collection activity**, **Add publisher files**, **Needs attention**, **Research quality**, and **Investigate a data problem**. Download history and optional historical searches belong in Collection activity. Every manual upload control belongs in Add publisher files.
- Show users what happened, the current state, and the next useful action. One or two sentences are enough for normal states. Avoid generic statements about how the architecture works.
- Keep one normal collection action: **Find and download missing data**. The separate **Search for older records** retrieves historical economic releases and fund filings. **Create troubleshooting report** only packages diagnostic evidence. Give specialized actions a brief purpose and show their actual results below them.
- Use plain terms such as "data series", "saved files", "missing data", "publisher", "check" and "research results". Reserve internal terms such as ingestion, synchronization, preflight, source-health, native matrices, release journals, HTTP codes and raw enum values for the technical event log and troubleshooting ZIP.
- State limitations as direct outcomes with an identified next step. Avoid repetitive disclaimers or constructions contrasting what a feature is with what it isn't.
- The main page and quick status popup contain no expandable disclosure arrows. The official-file catalogue uses one labeled selector; publisher links, uploads and results are visible for the selected source. Technical events open only on an explicit button.
- Keep missing series separate from available series needing review. A completed check must retain unresolved failures and delays.

- A failed publisher check is a technical issue, not an implicit request for the person to download a file. Distinguish **files requested now** (exact official links from active `manual_required` jobs) from the **optional official-file catalogue** for previously obtained originals. Both are presented together.
- Show the publisher request count, the number of series actually repaired, and the still-missing series separately. Policy-deferred requests are included in unsuccessful request totals, and should be labelled accordingly.
- Display source-level issues with plain statuses (**Failed**, **Postponed**, **Possibly outdated**) and their next step. Technical codes and internal source IDs belong in the ZIP.
- When a check is running, the page presents progress and postpones technical follow-up decisions until the result is known. When scheduler data has not loaded, display an unknown state rather than saying automatic checking is off.

## Regression acceptance

- Render the unified hierarchy and direct collection action without any `<details>` inside the operator page.
- Route old diagnostics/source-coverage links into the new page and focus the correct section.
- Preserve per-source progress, manual fallback upload, optional publisher file sources, OECD ZIP/ReadMe import and reassessment, research caveats, historical records and diagnostic export paths.
- Show failed or missing evidence as unresolved; do not equate an attempted source with repaired coverage.
- Maintain keyboard-focusable buttons, labeled progress, accessible tables, mobile layout, and dark theme.
- Execute frontend, Python, browser and release-image workflows after changes.
