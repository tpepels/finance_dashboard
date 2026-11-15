# Research expansion: implementation and evidence checkpoint

**Date:** 15 November 2026  
**Programme:** [Research audit and development roadmap](RESEARCH_AUDIT_ROADMAP_2026-11-14.md)  
**Baseline warning:** The 14 November roadmap's deployed ZIP was version
`0.2.2`. Later GitHub commits, green CI and new source contracts **do not**
prove that production has ingested any of the new originals. The user's next
diagnostic ZIP is needed for a measured post-deployment account.

## What the current code implements

| Programme phase | Code work carried through | Empirical/release boundary |
| --- | --- | --- |
| Phase 0 — integrity | ICIO source-to-consumer dependence reporting; per-source failures and bounded original-row diagnostics; conservative source/assessment states. | Do not accept any matrix implicated by unresolved accounting failures. V03's blocking valuations and G03's listed-parent universe remain evidence-gated. |
| Phase 1 — wage distributions | L08 original-source research, percentile/minimum/median distinction, BLS/OECD source contracts and regression fixtures. | Publisher BLS HTTP 403 and exact current-history coverage must be rechecked from production originals. |
| Phase 2 — consumer/asset inflation | C07 linked to C06 and portfolio/valuation follow-ups, original-source research with statistical and temporal restrictions. | Only verified aligned data can support a claimed correlation. Missing prices and unsupported causal claims remain withheld. |
| Phase 3 — Piketty/WID | L07 presents historical concentration, broad-group and 12-bin income-growth incidence, national/private/public wealth ratios, an accounting capital-income yield versus real growth, and asset composition. All 72 new percentile registrations are part of the existing WID ingestion and acceptance path. The world WID original upload/download path checks the older five required histories plus 27 optional Piketty measures from **the same CSV pair**. Original source quality codes and verified receipt identities are exposed. | Missing publisher percentile observations stay empty. Inheritance and empirically commensurable Piketty \(r-g\) are **not validated**. The WIR 2026 2025 global reference is a dated publication snapshot, never appended to a different WID series. Original country/year and report-method reconciliation require actual publisher evidence. |
| Phase 4 — navigable research | All 39 approved analyses are in a versioned 65-link directed follow-up network, with typed economic scope, source roles, citations, accepted/conditional/deferred state and contextual next questions. Research pages and catalogue show these directly without nested evidence disclosure buttons. Required evidence is counted separately from optional extensions; scientific changes refresh an open page automatically. | The graph proposes further research. It never treats a suggested link as a proven statistical or causal result. Browser and keyboard/mobile verification is part of CI. |
| Phase 5 — outstanding originals | Each question now has a conservative next-step classification derived from current scientific acceptance: awaiting owner information, publisher observations, an original source definition, or methodological review. The Data & diagnostics ZIP includes `diagnostics/research-next-actions.json` with required and optional role counts; a report failure cannot suppress the rest of the ZIP. | G01/G02/P01/P04/P05 and G03 must remain limited by actual original holdings, issuer/sector, policy, timestamp, FX and consolidated-profit evidence. No new original data, source rights, owner input or accepted real-world result is invented. |

## New WID manual-collection contract

The world original-source flow is automatic after the data and metadata pair
has been obtained. It performs all of the following in the **existing**
canonical importer:

1. Preserve the five legacy WID share series as independent required imports.
2. Scan the same hash-recorded world original pair for all 27 registered
   optional WID/Piketty measures, including 12 percentile-income groups.
3. Import each optional series with genuine observations, mark absent
   publisher variables `not_published_in_original`, and isolate an
   unexpected optional parsing/ingestion failure without discarding a
   successfully imported core series.
4. Treat the completed check as current for its configured publisher interval;
   automatically reassess a prior-release five-only job after a version
   upgrade instead of incorrectly treating it as full source coverage.
5. Keep user-uploaded original bytes clearly identified as
   **owner-supplied**, distinct from an HTTPS publisher download; a local
   successful import cannot certify first-publication dates or publisher
   origin for original-method acceptance.

## Next deployed evidence check

Use the normal **Data & diagnostics** report. The new ZIP is expected to
contain:

- `diagnostics/source-coverage.json` and `source-audit.csv` for which
  original histories are present, stale, absent or failed.
- `diagnostics/source-fixture-samples.json` with small hash-verified
  source rows or an explicit source-unavailable result.
- `diagnostics/research-next-actions.json` for each question's original
  evidence state, core/optional roles, and any actual owner action.
- `diagnostics/icio-consumer-dependencies.json` and accounting-failure
  manifest for source matrix lineage into accepted calculations.
- Collector/maintenance outcomes and the per-source failure journal for
  attempts and unresolved errors.

A phase's implementation passing unit/browser/release-image checks means
**the feature and gates are wired**. Completion of the evidence-dependent
phase requires a production ZIP proving actual original ingestion,
reconciliation, appropriate scientific acceptance, and no newly introduced
failures. Deferred original methods stay visibly deferred until those gates
pass; no manual source download is requested from the owner unless the
application shows a genuine restricted-publisher file requirement.
