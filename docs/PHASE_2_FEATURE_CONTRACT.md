# Phase 2 — locked feature contract

Status: **baseline frozen on 2026-11-02**. This specifies the full Phase 2 product features and acceptance conditions drawn from the opening Phase 2 exchanges in the owner's project conversation, reconciled with the implementation already on `main`. "Frozen" is a project change-control rule, not a GitHub branch-protection setting.

## Product purpose and scope

Provide source-traceable global macroeconomic, valuation and market datasets to power a subsequent combined-chart dashboard. Phase 2 delivers the data layer, not a finished React dashboard or trading system. The outputs must preserve economic definitions; a readily available proxy never silently replaces the requested original.

### Required capabilities (all required; no sample-only completion)

**F01 — Canonical macro/index catalogue.** Maintain all **34** agreed definitions in `definitions/series.json`, currently **32 mapped** and **2 open**. For each: stable ID, economic measure, provider/source key/URL, geography, native frequency, unit, provenance, revision semantics, rights and explicit source status. An unmapped item remains visible as unresolved; it must not return fabricated chart values.

**F02 — Historical source ingestion.** Fetch and validate every mapped macro/index source (BIS, ECB, FRED, BEA, World Bank WDI/Pink Sheet, IMF, Shiller, ILO/UNSD, MSCI, Siblis, gold spot as applicable). Support full-history backfill, incremental refresh, explicit nulls, error isolation and source-specific observation periods. The three BIS harmonized US/euro-area/Japan policy feeds must work as real historical daily sources.

**F03 — Full listed market catalogue.** Ingest **all 24** agreed global, US and European stocks/ETF exchange listings from `definitions/instruments.json`. Distinguish ticker, security, share class, exchange MIC, ISIN verification, trade currency, fund currency and accumulating/distributing policy. Never infer a missing ISIN or change venues silently.

**F04 — Market price integrity.** Preserve daily raw close, vendor adjusted close, volume, cash dividends and original split ex-dates, including non-trading days. Expose price-only, vendor-adjusted and cash-dividend-reinvested returns as different methods. Retain adjusted-history revisions and historical actions. Validate ticker changes/venue continuity separately.

**F05 — ECB FX and EUR performance.** Ingest USD/EUR, GBP/EUR and CHF/EUR ECB daily reference series, with correct foreign-currency-per-EUR orientation and limited historical lookback for holidays; calculate EUR-comparable returns only when valid rates exist. No synthetic FX history.

**F06 — Original economic measures.** Preserve all six source-definition commitments:
- `valuation.us.tobins_q` — BEA Q1 replacement-cost valuation (implemented, 1960–2024 history).
- `labour.world.productivity_compensation` — explicitly accounting-implied ILO all-labour-income/output-per-hour identity (implemented; not independently surveyed wages).
- `credit.world.private_gdp_gap` — GDP-weighted BIS national credit-gap composite plus coverage series (implemented; not official BIS global gap).
- `gold.world.equity_correlation` — World Bank monthly average gold against MSCI ACWI NETR USD index returns, rolling 36 months (implemented; not an ETF pair).
- `concentration.global.top10` — **missing original**: historical *MSCI ACWI 892400* security-level free-float top-ten constituent-weight sum.
- `profit.global.corporate_share` — **missing original**: historical worldwide listed-company consolidated net earnings / world nominal GDP, with comprehensive coverage and issuer-level deduplication.

**F07 — Transparent alternatives without substitution.** Existing `proxy.gold_vt_36m_usd` and `proxy.gold_vt_36m_eur` are ETF proxies. `profit.us_sec_filers.world_gdp_share` is the supplementary, coverage-limited Wisesheets/SEC issuer aggregate; it cannot close `profit.global.corporate_share`. Historical ACWI ETF holdings, Yahoo fund holdings and market-cap/P-E-derived earnings may be *added under separate IDs only*, with scope, methodology, dates, coverage and rights. A derived index earnings proxy is **not** an independently audited global sum of listed-company net profits.

**F08 — Auditable storage and read-only access.** Preserve original observations, revisions and ingest outcomes in PostgreSQL with migrations; expose canonical metadata, observations, status, market calculations and supplementary source metadata through documented FastAPI read-only endpoints.

**F09 — Full reproducible static data.** Export all implemented mapped series, the 24 instruments, 3 FX feeds, original calculated measures and separately labelled proxies as browser-safe JSON; maintain unresolved manifest entries. Secret-bearing collection occurs only in scheduled jobs. Exports should fail on a missing required mapped source rather than presenting a silent subset.

**F10 — Wisesheets monthly enrichment.** Use `WISESHEETS_API_KEY` only in Actions, enumerate the full *accessible* SEC-filer directory, deduplicate issuers by SEC CIK, preserve negative earnings, validate SEC provenance and non-USD reporting currencies, convert with ECB historical FX, align with World Bank nominal GDP and report year-by-year omissions/coverage and freshness. 2026-11-02 verified observation: 8,179 distinct CIKs, 6,161 with traceable net income, 2021–2025, 150 API requests. This is not proof of worldwide coverage or delisted-issuer completeness.

**F11 — Provenance, safety and publishing policy.** Every returned value must carry source, time period, definition, revision/observation semantics and quality/rights metadata. Do not expose FRED or Wisesheets credentials. An Actions artifact is not a deployed Pages site; redistribution rights are evaluated before public hosting.

## Explicit non-goals in Phase 2

The React/ECharts interactive dashboard (Phase 3), allocation/risk analytics and portfolio tooling (Phase 4), trading execution, real-time streaming, recommendations, unlicensed market feeds, artificial frequency fills and claims of true provider vintages where unavailable.

## Exit checklist — all gates required

- [x] All 32 mapped original macro/index series live-source checked, combined real PostgreSQL historical backfill and API readback completed.
- [x] All 24 stock/ETF instruments and 3 ECB FX feeds verified in real PostgreSQL market ingestion, API and static export.
- [x] Four of the six originally missing economic definitions source-mapped and tested with explicit methodology.
- [x] Wisesheets supplementary SEC-filer scan and API/static export completed with truthful coverage labelling.
- [ ] **Full historical original `concentration.global.top10` dataset and series integration.** Isolated MSCI factsheets or ACWI ETF holdings alone do not pass.
- [ ] **Full historical original `profit.global.corporate_share` dataset and series integration.** Wisesheets SEC current universe or a valuation-derived proxy alone does not pass.
- [ ] Independent issuer NAV/distribution reconciliation for relevant ETFs.
- [ ] Verified continuity across historical ticker/venue changes.
- [ ] Full repeatable acceptance run including new original sources, revision and coverage checks, publication restrictions and API/export parity.

**Decision rule:** Phase 2 remains open until *every* unchecked requirement is complete, or the owner explicitly approves a documented amendment that changes the original scope. Partial examples, passing unit tests, or adding a proxy are insufficient.

## Change control and traceability

This specification, [architecture contract](PHASE_2_ARCHITECTURE_CONTRACT.md), and [implementation contract](PHASE_2_IMPLEMENTATION_CONTRACT.md) are the baseline. Any future change must update the three contracts as appropriate and link a GitHub issue explaining the requirement delta, source semantics, migration/tests, and owner approval. The existing tracking issue is [#1](https://github.com/tpepels/finance_dashboard/issues/1). Related details: [Phase 2](PHASE_2.md), [original gaps](ORIGINAL_GAPS.md), [markets](MARKET_DATA.md), [Wisesheets](WISESHEETS.md).