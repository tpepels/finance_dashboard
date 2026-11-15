# Data & diagnostics: single operator workspace

This page is the authoritative operator entry point for source collection, current progress, source health, research limitations, diagnostic evidence and maintenance. The existing Source Explorer remains a separate research/chart exploration tool, not a competing data-administration view.

## User-facing hierarchy (top to bottom)

1. **Overview:** What is the state? What is missing? What will happen next? Three distinct counts: stored histories, histories without observations, and *other* histories needing review. Missing histories are not counted again in the review figure. Show configured collection cadence and next scheduled run when known. Always-visible primary action: **Collect original data**. Disable it during a running collection, without hiding or changing its name.
2. **Collection activity:** What is the current or last requested collection doing? Show archive queue progress and independently tracked macro-history repair, explicitly distinguishing tasks checked, source gaps resolved, and publisher failures or deferrals. A missing past-build repair summary must not imply success.
3. **Needs attention:** Official manual-file download links with upload controls, exact source-level missing/stale/failed histories, dates, and next action. On valid upload, ingestion continues without another confirmation.
4. **Research quality:** Scientific acceptance counts and limitations, evidence gaps, methodological caveats, missing computations and source-accounting failures. Load the assessment when the page opens; allow an explicit reassessment. Source availability alone must never be represented as research acceptance.
5. **Diagnostics & maintenance:** Visible Prepare/Download diagnostic ZIP actions, an on-demand raw structured console (no diagnostics fetched until requested), separately named targeted checks, OECD original-file upload/reassessment, and per-operation outcomes.

Source lists can scroll vertically instead of hiding behind expandable disclosures. Put low-frequency, technical tools below actionable information, but do not hide their controls inside disclosure widgets.

## Navigation, preservation and operational contracts

- Primary navigation and toolbar use the same label: **Data & diagnostics**, canonical anchor `#research-sources`.
- Legacy deep links `#diagnostics` and `#source-coverage` focus their respective sections on the same page. `#research-quality` also addresses the integrated research assessment. Do not restore a duplicate Diagnostics page.
- The header Status indicator remains a quick view and links into the single page, rather than opening a second maintenance experience.
- Existing routes, action authorization, publisher quotas, immutable-original validation, cancellation and source-policy safeguards remain authoritative. Do not create new collection engines or substitute synthetic observations.
- Keep collection execution and diagnostics preparation asynchronous. Preserve last-known collection and coverage state if status polling fails, while explicitly flagging staleness and errors.
- The only top-level collection button starts the established original-source queue plus the source-health repair workflow. More specialized operations remain available lower on the page, not as peers of the main action.
- The operation labels, diagnostic download, archive upload and scientific acceptance limitations are direct user-visible output, not just developer-console data.

## Regression acceptance

- Render the unified hierarchy and direct collection action without any `<details>` inside the operator page.
- Route old diagnostics/source-coverage links into the new page and focus the correct section.
- Preserve per-source progress, manual fallback upload, research caveats and file import/reassessment paths.
- Show failed or missing evidence as unresolved; do not equate an attempted source with repaired coverage.
- Maintain keyboard-focusable buttons, labeled progress, accessible tables, mobile layout, and dark theme.
- Execute frontend, Python, browser and release-image workflows after changes.
