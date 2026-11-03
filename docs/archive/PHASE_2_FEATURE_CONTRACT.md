# Phase 2 — locked feature contract

Status: **baseline frozen on 2026-11-02**. This specifies the full Phase 2 product features and acceptance conditions drawn from the opening Phase 2 exchanges in the owner's project conversation, reconciled with the implementation already on `main`. "Frozen" is a project change-control rule, not a GitHub branch-protection setting.

## Product purpose and scope

Provide source-traceable global macroeconomic, valuation and market datasets to power a subsequent combined-chart dashboard. Phase 2 delivers the data layer, not a finished React dashboard or trading system. The outputs must preserve economic definitions; a readily available proxy never silently replaces the requested original.

### Required capabilities (all required; no sample-only completion)

**F01 — Canonical macro/index catalogue.** Maintain **42 mapped** macro/index definitions in `definitions/series.json` (32 previously mapped + four world aggregate valuations + three owner-approved free-source replacements + three OECD corporate/coverage measures). The two inaccessible original historical specifications are preserved, with reasons and replacement IDs, in `definitions/superseded_series.json` rather than misreported as live series. For each: stable ID, economic measure, provider/source key/URL, geography, native frequency, unit, provenance, revision semantics, rights and explicit source status. An unmapped item remains visible as unresolved; it must not return fabricated chart values.

**F02 — Historical source ingestion.** Fetch and validate every mapped macro/index source (BIS, ECB, FRED, BEA, World Bank WDI/Pink Sheet, IMF, Shiller, ILO/UNSD, MSCI, Siblis, gold spot as applicable). Support full-history backfill, incremental refresh, explicit nulls, error isolation and source-specific observation periods. The three BIS harmonized US/euro-area/Japan policy feeds must work as real historical daily sources.

**F03 — Optional listed market catalogue (already implemented, not a blocking macro requirement).** Preserve the existing **24** global, US and European stocks/ETF exchange listings from `definitions/instruments.json`. Distinguish ticker, security, share class, exchange MIC, ISIN verification, trade currency, fund currency and accumulating/distributing policy. Never infer a missing ISIN or change venues silently.

**F04 — Optional market price integrity (existing feature).** Preserve daily raw close, vendor adjusted close, volume, cash dividends and original split ex-dates, including non-trading days. Expose price-only, vendor-adjusted and cash-dividend-reinvested returns as different methods. Retain adjusted-history revisions and historical actions. Validate ticker changes/venue continuity separately.

**F05 — Optional investment FX performance, required FX methodology where used.** Preserve USD/EUR, GBP/EUR and CHF/EUR ECB daily reference series, with correct foreign-currency-per-EUR orientation and limited historical lookback for holidays; calculate EUR-comparable returns only when valid rates exist. No synthetic FX history.

**F06 — Economic measurements and explicit owner-amended source substitutions.** Retain the four mapped original economic identities and the archived source definition of two replaced historical indicators:
- `valuation.us.tobins_q` — BEA Q1 replacement-cost valuation (implemented, 1960–2024 history).
- `labour.world.productivity_compensation` — explicitly accounting-implied ILO all-labour-income/output-per-hour identity (implemented; not independently surveyed wages).
- `credit.world.private_gdp_gap` — GDP-weighted BIS national credit-gap composite plus coverage series (implemented; not official BIS global gap).
- `gold.world.equity_correlation` — World Bank monthly average gold against MSCI ACWI NETR USD index returns, rolling 36 months (implemented; not an ETF pair).
- Archived `concentration.global.top10` required complete monthly MSCI ACWI 892400 security-level weights. **Owner-approved replacement:** `concentration.global.msci_acwi_published_top10`: actual MSCI ACWI **index** top-ten published weights on eight dated snapshots (2019–2026), no filled missing months; source and exact report date recorded per point.
- Archived `profit.global.corporate_share` required comprehensive worldwide listed-company consolidated net earnings/world GDP. **Owner-approved macro alternative:** `profit.eu27.corporate_operating_surplus_gdp`: ESA2010 **EU27** non-financial+financial corporate gross operating surplus as percent of **EU27** GDP, 24 matched annual years. The earlier quarterly OECD API request failed. Correctly specified official annual OECD sector accounts are now integrated as a separate OECD38 GDP-weighted series; this EU27 indicator itself remains EU-only. Additional independent published `profit.eu27.nonfinancial_gross_surplus_value_added` is sector gross operating surplus as percent of **S11 GVA**, not GDP.

**F07 — Transparent alternatives with the approved source substitution.** Existing `proxy.gold_vt_36m_usd` and `proxy.gold_vt_36m_eur` are ETF proxies. `profit.us_sec_filers.world_gdp_share` is the supplementary, coverage-limited Wisesheets/SEC issuer aggregate; it is never equivalent to the archived global listed-company profits specification. Historical ACWI ETF holdings, Yahoo fund holdings and market-cap/P-E-derived earnings may be *added under separate IDs only*, with scope, methodology, dates, coverage and rights. A derived index earnings proxy is **not** an independently audited global sum of listed-company net profits.

**F08 — Auditable storage and read-only access.** Preserve original observations, revisions and ingest outcomes in PostgreSQL with migrations; expose canonical metadata, observations, status, market calculations and supplementary source metadata through documented FastAPI read-only endpoints.

**F09 — Full reproducible static data.** Export all implemented mapped macro/index series (**42**), derived aggregate calculations, original measures and separately labelled proxies; preserve the previously implemented 24 instruments and 3 FX feeds as optional export modules as browser-safe JSON; maintain truthful unresolved manifests (currently none in the active catalog), and archive discontinued original requirements separately. Secret-bearing collection occurs only in scheduled jobs. Exports should fail on a missing required mapped source rather than presenting a silent subset.

**F10 — Wisesheets monthly enrichment.** Use `WISESHEETS_API_KEY` only in Actions, enumerate the full *accessible* SEC-filer directory, deduplicate issuers by SEC CIK, preserve negative earnings, validate SEC provenance and non-USD reporting currencies, convert with ECB historical FX, align with World Bank nominal GDP and report year-by-year omissions/coverage and freshness. 2026-11-02 verified observation: 8,179 distinct CIKs, 6,161 with traceable net income, 2021–2025, 150 API requests. This is not proof of worldwide coverage or delisted-issuer completeness.

**F11 — Provenance, safety and publishing policy.** Every returned value must carry source, time period, definition, revision/observation semantics and quality/rights metadata. Do not expose FRED or Wisesheets credentials. An Actions artifact is not a deployed Pages site; redistribution rights are evaluated before public hosting.

**F12 — Macro-first global market aggregates.** Integrate World Bank WLD listed-market-capitalization USD, a same-year World Bank WLD market-cap-to-world-GDP derived ratio, Siblis published sparse year-end global trailing P/E, and the same Siblis universe's derived earnings yield. Preserve source coverage and rights; **never multiply a Siblis selected-index P/E by a World Bank all-market capitalization** to claim world corporate earnings. Include these as four separate, source-verified chart definitions.

**F13 — Free historical index concentration and EU institutional-sector profit ratios.** Import, audit and display all eight source-dated MSCI ACWI 892400 top-ten index weight snapshots without invented monthly data; fetch official Eurostat EU27_2020 S11/S12 gross surplus and S1 GDP with nominal EUR matching and preserve missing years; separately ingest official S11 gross profit/GVA statistic. Require source identity, provenance, arithmetic, missing-data, rights and full 39-series integration tests for the interim EU-only baseline. A further OECD-wide member-weighted source is defined by F14; no claim of worldwide company net profits. [Owner approval and implementation semantics](PHASE_2_FREE_SOURCE_REPLACEMENTS.md).

**F14 — OECD corporate operating surplus/GDP (implemented and accepted).** Official OECD annual `DSD_NASEC10@DF_TABLE14` S11+S12 gross operating surplus `D/B2G`, divided by each member's nominal GDP (OECD S1 gross value added + product taxes, or restricted currency-validated WDI local GDP for USA/JPN/CAN only). Compute a WDI nominal-USD-GDP-weighted average for the current 38 OECD members, omitting years without >=35 member GDP weights, >=29 contributor countries or >=80% of member GDP. Publish separate coverage % and contributing-country counts; never pretend this is an official OECD aggregate or all 38 countries' complete history. [Detailed methodology and 42-series acceptance](OECD_CORPORATE_SURPLUS.md).

## Explicit non-goals in Phase 2

The React/ECharts interactive dashboard (Phase 3), allocation/risk analytics and portfolio tooling (Phase 4), trading execution, real-time streaming, recommendations, unlicensed market feeds, artificial frequency fills and claims of true provider vintages where unavailable.

## Exit checklist — all gates required

- [x] Original 32 macro/index series live-source checked, combined real PostgreSQL historical backfill and API readback completed.
- [x] Four new macro aggregates source-checked through a complete 36-series static export: two WDI 51-year annual series and two Siblis 11-snapshot valuations.
- [x] Combined PostgreSQL/API acceptance covering **all 36** macro/index series (not just the original 32): [successful live PostgreSQL ingestion and API readback](https://github.com/tpepels/finance_dashboard/actions/runs/41494100275).
- [x] All 24 stock/ETF instruments and 3 ECB FX feeds have already passed historical market ingestion/API/static checks; these are retained as **optional supplementary infrastructure, not Phase 2 macro exit gates**.
- [x] Four of the six originally missing economic definitions source-mapped and tested with explicit methodology.
- [x] Wisesheets supplementary SEC-filer scan and API/static export completed with truthful coverage labelling.
- [x] Owner approved replacing the complete monthly index weights with **eight source-cited sparse historical MSCI ACWI index observations**; all original source semantics remain in the [superseded archive](../definitions/superseded_series.json).
- [x] Owner approved a **corporate gross operating surplus** national-accounts measurement instead of listed-company net earnings, and the working public Eurostat EU27 implementation explicitly identifies its narrower geographic coverage. Original definition archived; no claim of world/OECD coverage.
- [x] Full **42-series** macro PostgreSQL/API/static acceptance with the three OECD wide+coverage series: [PostgreSQL/FastAPI PASS](https://github.com/tpepels/finance_dashboard/actions/runs/41503545569), [static export PASS](https://github.com/tpepels/finance_dashboard/actions/runs/41503489558).

- [x] **OECD geographic coverage:** a 25-year (2000–2024) 38-member GDP-weighted national-accounts composite replaces the EU27-only limitation, with separate nominal GDP coverage and member counts. All [42 macro PostgreSQL/API](https://github.com/tpepels/finance_dashboard/actions/runs/41503545569) and [42 static exports](https://github.com/tpepels/finance_dashboard/actions/runs/41503489558) passed.

**Nonblocking optional market-data debt:** issuer NAV/distribution reconciliation and historical ticker/venue continuity were removed from Phase 2 gates by the owner's [macro-first scope amendment](PHASE_2_MACRO_SCOPE_AMENDMENT.md). No claim is made that these optional audits passed.

**Decision rule:** Phase 2 implementation is complete only when all currently agreed **42** macro definitions pass full integrated acceptance. The user explicitly approved the source substitutions recorded in [the second amendment](PHASE_2_FREE_SOURCE_REPLACEMENTS.md). Partial examples, passing unit tests, or adding a proxy are insufficient.

## Change control and traceability

The owner-approved [macro-first Phase 2 amendment](PHASE_2_MACRO_SCOPE_AMENDMENT.md) and [free-source amendment](PHASE_2_FREE_SOURCE_REPLACEMENTS.md) supersede the ETF-level and two inaccessible original-source completion conditions. This specification, [architecture contract](PHASE_2_ARCHITECTURE_CONTRACT.md), and [implementation contract](PHASE_2_IMPLEMENTATION_CONTRACT.md) are the baseline. Any future change must update the three contracts as appropriate and link a GitHub issue explaining the requirement delta, source semantics, migration/tests, and owner approval. The existing tracking issue is [#1](https://github.com/tpepels/finance_dashboard/issues/1). Related details: [Phase 2](PHASE_2.md), [original gaps](ORIGINAL_GAPS.md), [markets](MARKET_DATA.md), [Wisesheets](WISESHEETS.md).