# Data & diagnostics: single operator workspace

This page is the authoritative operator entry point for source collection, current progress, source health, research limitations, diagnostic evidence and maintenance. The existing Source Explorer remains a separate research/chart exploration tool, not a competing data-administration view.

## User-facing hierarchy (top to bottom)

1. **Overview:** What is the state? What is missing? What will happen next? Three distinct counts: available data series, missing data series, and available series requiring review. Keep each series in one count. Show configured collection cadence and next scheduled run when known. Always-visible primary action: **Find and download missing data**. Disable it during a running collection, without hiding or changing its name.
2. **Collection activity:** What is the current or last requested collection doing? Show download progress, then the individual download results within the same section. Show missing-data checks separately and distinguish attempts, new data saved, failures and postponed requests.
3. **Needs attention:** Keep the files a person must download at the start of this section, followed by affected data series, their latest saved dates and next steps. Valid uploads start processing automatically.
4. **Research quality:** Show research findings that require a closer look, with clear priorities and the suggested next step. Load the list automatically and offer a button to check for changes. Preserve scientific distinctions in the underlying calculations and downloadable technical evidence.
5. **Troubleshooting and other checks:** Create or download a troubleshooting report, view detailed errors on request, use three clearly described additional checks, and add or verify OECD files. Display results beneath the operation that produced them.

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

- Name sections after the decision they support: **Collection activity**, **Needs attention**, **Research quality**, and **Troubleshooting and other checks**. Download history belongs in Collection activity. Manual download and upload controls belong in Needs attention.
- Show users what happened, the current state, and the next useful action. One or two sentences are enough for normal states. Avoid generic statements about how the architecture works.
- Buttons use a specific verb and object: **Find and download missing data**, **Check for newly published data**, **Look for older historical records**, **Create troubleshooting report**. Put one brief explanation beside specialized actions.
- Use plain terms such as "data series", "saved files", "missing data", "publisher", "check" and "research results". Reserve internal terms such as ingestion, synchronization, preflight, source-health, native matrices, release journals, HTTP codes and raw enum values for the technical event log and troubleshooting ZIP.
- State limitations as direct outcomes with an identified next step. Avoid repetitive disclaimers or constructions contrasting what a feature is with what it isn't.
- The main page and quick status popup contain no expandable disclosure arrows. Technical details can be opened deliberately with an explicitly labeled button.
- Keep missing series separate from available series needing review. A completed check must retain unresolved failures and delays.

## Regression acceptance

- Render the unified hierarchy and direct collection action without any `<details>` inside the operator page.
- Route old diagnostics/source-coverage links into the new page and focus the correct section.
- Preserve per-source progress, manual fallback upload, research caveats and file import/reassessment paths.
- Show failed or missing evidence as unresolved; do not equate an attempted source with repaired coverage.
- Maintain keyboard-focusable buttons, labeled progress, accessible tables, mobile layout, and dark theme.
- Execute frontend, Python, browser and release-image workflows after changes.
