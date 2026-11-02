# Phase 1 feasibility audit — 2026-11-02

The repository began empty. This phase supplies a machine-validated catalog with real, externally documented source IDs. **No external API was called by the application itself, no history was backfilled, and no UI exists.**

## Mapping results

- **BIS WS_CBPOL 1.0, D.US / D.XM / D.JP**: the first combined graph uses one harmonized provider for Fed/ECB/BOJ policy-comparison history. BIS may change underlying instruments over time; the graph must show that caveat.
- **ECB FM.D.U2.EUR.4F.KR.DFR.LEV**: exact deposit facility series, a separate monetary instrument from BIS harmonized policy rates.
- **FRED DFEDTARU, DFII10, SAHMREALTIME**: US corridor upper bound, real 10Y yield, and US real-time Sahm Rule respectively. Note that 'real-time Sahm' refers to the indicator's construction, not necessarily full source-wide vintage availability.
- **World Bank NY.GDP.MKTP.KD.ZG**: annual real GDP growth, with documented regional country IDs.
- **World Bank CM.MKT.LCAP.GD.ZS**: domestic listed market cap/GDP; neither a validated global Buffett Indicator nor market value of all corporations.

## Unresolved/high-risk

- Global Shiller CAPE: the original Shiller series is US-specific; licensed global comparators need sourcing.
- Global corporate profits and labour/capital share: cross-country definitions, coverage and units need a harmonized series.
- Historic global market and earnings concentration: index constituent history likely needs a licence.
- Tobin's Q: hard to estimate comparably outside US.
- Gold spot/total return: choose a legally redistributable series and decide currency/return methodology.
- BIS API response formats, historical completeness, publisher rights and all external source connectivity must still be tested.

## Gate 1 exit and next work

Mapped entries and chart definitions pass strict offline validation and have linked provenance, comparison caveats, and rights flags. Next: implement the BIS adapter on **D.US/D.XM/D.JP**, fetch and validate real observations, record source timestamps, store revisions in PostgreSQL, expose query endpoints and render the first combined chart. This should be a single vertical slice rather than a broad UI scaffold.
