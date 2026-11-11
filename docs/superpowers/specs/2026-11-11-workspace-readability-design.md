# Workspace readability and loading design

## Intent
The owner asks to fill implementation gaps, speed up individual items, and design then implement a cleaner, readable, flexible hierarchy with darker dark mode and distinctive colors. Preserve the established concise overview and expandable detail, private holdings, canonical calculations and local/LAN installation.

## Chosen approach
Keep the React/FastAPI application and its public hash routes. Refine the existing workspace rather than replace it. A wider top navigation would retain competing rows; a dense terminal would conflict with the owner's concise preference. Choose a left navigation rail on desktop, a labelled collapsible navigation on mobile, and a clear reading canvas. This is an implementation choice under the owner's explicit design-then-implement instruction; no additional approval stop is necessary.

## Visual and interaction design
Visual thesis: a calm analytical workspace, with near-black surfaces, crisp readable type, restrained separators and distinct data colors.
Content hierarchy: product/navigation → workspace or topic → individual research question → concise finding → primary visualization → configuration and expandable methods, sources and limits. Avoid repeating navigation and introduction text above the finding. Overview remains a short list of findings, not a wall of charts. Portfolio and source utilities remain reachable.
Desktop: persistent approximately 220px navigation rail, workspace links grouped above research topics, active route clearly marked. Main content uses readable text lengths and a generous chart area. Mobile: compact header with an explicit menu control; navigation closes after selection and keyboard focus remains usable. Preserve all legacy fragments, back/forward, skip link and independent saved/editor drafts.
Provide comfortable and compact density as a reversible appearance preference; only appearance preferences use browser storage. Compact reduces spacing, not legibility or touch target accessibility. Avoid new libraries.
Dark palette: page near #080b10, navigation #0c1017, raised panels #121923, primary text #edf3fc, muted text around #a3b1c6. Action accent cyan/blue; success teal, limits amber, failures rose, with textual labels. Distinct series use blue, orange, teal, purple, pink and yellow plus existing line/symbol differences. Keep consistent entity identities and preserve light-mode contrast. Use 120–180ms focus/hover/disclosure transitions with reduced-motion support; no decorative animation or marketing hero.

## Loading architecture
Measure actual live endpoint latency and per-stage cost before optimizing Python. Individual question navigation requests that question only; topic views progressively request their own questions. Repeated failed/loading retries should not refetch already successful sibling requests. Keep no private persistent browser cache and no unvalidated completed-result reuse. Server optimization may use bounded process memory and shared concurrent work only when guarded by current database/evidence/owner identity, assessment and effective date. Changes in inputs must continue to withhold output pending reassessment. Exact exports and configured figures must match the current canonical result.
Lazy-load secondary workspace code where it materially reduces initial JavaScript, without new frameworks. Skeleton/loading context must identify the selected question promptly. Do not prefetch every question or conceal genuine acceptance work.

## Completion gates
Regression tests cover selected-only requests, retry isolation, refresh and navigation races; backend tests cover cache reuse, invalidation and concurrent requests as applicable to measured causes. Verify all prior browser flows, keyboard navigation, mobile 390px and both themes on populated data. Record cold and repeated endpoint/browser measurements and initial bundle sizes. Deploy the same verified image to local and media-server, preserving current holdings revision 2, originals, previous images/data and recovery copies. Scientific gaps remain explicit; no invented data or loosened acceptance criteria.
