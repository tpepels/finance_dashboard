# Requested economic indicator acceptance matrix

This inventory is generated from the 46 indicator declarations in `src/finance_dashboard/research.py` at the current revision. The 53 canonical macro-source contracts exist in `definitions/series.json`. **Code registration is not live-server source verification.** Latest user-supplied local ALFRED batch: 0 newly downloaded in 180 attempts, all HTTPStatusError; prior local source coverage cannot be certified from those logs.

| Scope | Research indicator | Implementation in code | Live source observations on user's server |
|---|---|---|---|
| World & OECD | `global_growth` — World real output growth | Published/source-derived ratio or level | Not independently checked |
| World & OECD | `global_labour_share` — Labour's share of world income | Calculated relationship | Not independently checked |
| World & OECD | `global_productivity` — World labour productivity growth | Published/source-derived ratio or level | Not independently checked |
| World & OECD | `oecd_corporate_surplus` — OECD corporate operating surplus / GDP | Published/source-derived ratio or level | Not independently checked |
| World & OECD | `oecd_surplus_coverage` — GDP coverage of OECD surplus estimate | Published/source-derived ratio or level | Not independently checked |
| World & OECD | `global_credit` — 43-economy credit-to-GDP trend gap | Published/source-derived ratio or level | Not independently checked |
| World & OECD | `global_credit_coverage` — Coverage of the international credit proxy | Published/source-derived ratio or level | Not independently checked |
| World & OECD | `global_equity_cap` — World listed domestic equities / world GDP | Published/source-derived ratio or level | Not independently checked |
| World & OECD | `global_pe` — Global equity-index trailing P/E | Published/source-derived ratio or level | Not independently checked |
| World & OECD | `global_concentration` — Largest ten firms' ACWI index weight | Published/source-derived ratio or level | Not independently checked |
| World & OECD | `global_gold_equity` — Gold vs global-equity historical return correlation | Published/source-derived ratio or level | Not independently checked |
| World & OECD | `global_public_debt` — World general government gross debt / GDP | Published/source-derived ratio or level | Not independently checked |
| United States | `us_growth` — US real GDP growth | Published/source-derived ratio or level | Not independently checked |
| United States | `us_policy` — US harmonized monetary policy rate | Published/source-derived ratio or level | Not independently checked |
| United States | `us_real_yield` — US 10-year real Treasury yield | Published/source-derived ratio or level | Not independently checked |
| United States | `us_tobins_q` — US nonfinancial corporate market-to-produced-asset replacement ratio | Published/source-derived ratio or level | Not independently checked |
| United States | `us_productivity_pay` — Productivity versus output-price-adjusted pay | Calculated relationship | Not independently checked |
| United States | `us_real_pay` — Worker purchasing power: real hourly pay | Published/source-derived ratio or level | Not independently checked |
| United States | `us_labour_share_gdp` — US labour share of GDP | Unit conversion + comparison | Not independently checked |
| United States | `us_income_distribution` — US GDP distribution: labour share and non-labour residual | Calculated relationship | Not independently checked |
| United States | `us_labour_share_nonfarm` — US nonfarm business labour share, index | Published/source-derived ratio or level | Not independently checked |
| United States | `us_yield_curve` — US Treasury 10-year minus 3-month spread | Published/source-derived ratio or level | Not independently checked |
| United States | `us_sahm` — US Sahm Rule unemployment deterioration | Published/source-derived ratio or level | Not independently checked |
| United States | `us_cape` — US Shiller cyclically adjusted price/earnings | Published/source-derived ratio or level | Not independently checked |
| United States | `us_credit` — US private credit relative to trend | Published/source-derived ratio or level | Not independently checked |
| United States | `us_cap_gdp` — US domestic listed market cap / GDP | Published/source-derived ratio or level | Not independently checked |
| Euro area & EU27 | `ea_growth` — Euro-area real GDP growth | Published/source-derived ratio or level | Not independently checked |
| Euro area & EU27 | `ea_policy` — Euro-area harmonized policy rate | Published/source-derived ratio or level | Not independently checked |
| Euro area & EU27 | `ea_credit` — Euro-area private credit gap | Published/source-derived ratio or level | Not independently checked |
| Euro area & EU27 | `europe_pwt_member_labour_shares` — Labour income share in Germany, France and Italy (PWT) | Unit conversion + comparison | Not independently checked |
| Euro area & EU27 | `eu27_corporate_surplus` — EU27 corporate gross operating surplus / GDP | Published/source-derived ratio or level | Not independently checked |
| Euro area & EU27 | `eu27_nonfinancial_surplus` — EU27 nonfinancial corporate surplus / sector GVA | Published/source-derived ratio or level | Not independently checked |
| Japan | `jp_labour_share` — Japan labour compensation / GDP (PWT) | Unit conversion + comparison | Not independently checked |
| Japan | `jp_income_distribution` — Japan GDP: labour and non-labour residual shares | Calculated relationship | Not independently checked |
| Japan | `jp_growth` — Japan real GDP growth | Published/source-derived ratio or level | Not independently checked |
| Japan | `jp_policy` — Japan harmonized policy rate | Published/source-derived ratio or level | Not independently checked |
| Japan | `jp_credit` — Japan private credit gap | Published/source-derived ratio or level | Not independently checked |
| Japan | `jp_equity_cap` — Japan listed domestic equity capitalization / GDP | Published/source-derived ratio or level | Not independently checked |
| Cross-country comparisons | `compare_pwt_labour_shares` — Labour's GDP income share: US, Japan, Germany, France and Italy | Unit conversion + comparison | Not independently checked |
| Cross-country comparisons | `compare_growth` — Real growth: US / euro area / Japan / China / India | Published/source-derived ratio or level | Not independently checked |
| Cross-country comparisons | `compare_growth_differential` — US minus euro-area real GDP growth | Calculated relationship | Not independently checked |
| Cross-country comparisons | `compare_policy` — Comparable policy rates: US / euro area / Japan | Published/source-derived ratio or level | Not independently checked |
| Cross-country comparisons | `compare_policy_differential` — US minus euro-area harmonized policy-rate spread | Calculated relationship | Not independently checked |
| Cross-country comparisons | `compare_credit` — Comparable credit-to-GDP trend gaps | Published/source-derived ratio or level | Not independently checked |
| Cross-country comparisons | `compare_credit_dispersion` — Cross-economy dispersion of credit-to-GDP gaps | Calculated relationship | Not independently checked |
| Cross-country comparisons | `compare_market_cap` — Domestic listed capitalization / GDP: US vs Japan | Published/source-derived ratio or level | Not independently checked |

## Coverage totals

- 46 economic research indicator cards: World/OECD **12**; US **14**; Europe **6**; Japan **6**; cross-country **8**.
- 35 source-level indicators (many already express genuine published ratios, e.g. market cap/GDP, CAPE, corporate surplus/GDP, credit gap).
- 7 independently calculated economic relationships (world/US/Japan labour/non-labour distributions, BLS productivity/pay gap, two signed regional differences and credit-gap dispersion).
- 4 unit-conversion views (PWT fractional labour-income shares to percent, including multi-country comparisons).
- 53 mapped canonical macro series; **not** 53 proven local histories.
- Phase 4 separately defines macro diagnostics, 24 registered Yahoo instruments, ECB FX, recession vintage backtest, dated SEC holdings, Wisesheets earnings context and OECD national-account scenario calculations. These are different from the 46 curated macro cards.

## Original research definitions still missing or replaced, not hidden

| Research ambition | Current source/implementation | Remaining condition |
|---|---|---|
| Replacement-cost corporate Tobin's Q | BEA Q1 produced-asset US nonfinancial variant registered | Validate original replacement-cost comparability, source vintage and locally imported history |
| Global labour productivity versus compensation | World output-per-worker growth and labour income share **separately** | No matched global hours-worked output-price compensation series; cannot calculate equivalent global historical BLS gap |
| Worldwide listed-company consolidated net profit / world GDP | OECD38 gross corporation operating surplus/GDP and EU27 surplus source ratios, plus US SEC-filer Wisesheets context | **Original exact global listed net profit numerator not acquired**; country, listed/unlisted and subsidiary coverage incompatible |
| Continuous historical top-ten equity concentration | Eight published, dated MSCI ACWI free-float index top-ten snapshots | Actual continuous constituent history/licensing not acquired; do not interpolate |
| Actual aggregate global private credit-to-GDP trend gap | GDP-weighted 43-reporting-economy country-gap proxy and world-GDP coverage | Not an official BIS world credit-gap series |
| Gold vs actual global equity index | World Bank gold plus MSCI ACWI net total return backtested 36-month correlation implementation | Verify source history, return conventions and local ingestion; ETF proxy is a separate view |
| Historical issuer-country ETF exposures | Verified SEC N-PORT identities VT/BND and dated filing importer | Collect/verify original filings and historic coverage; obtain original UCITS disclosures for European funds |
| Marxian surplus-value and profit-rate estimates | Source-gated national accounting sensitivity calculations | Audited industry employment/compensation/depreciation/net surplus/capital stock, sector models and independent reconciliation |
| Genuine real-time recession prediction validation | ALFRED point-in-time source system and walk-forward logistic backtest code | Successful historical vintage backfill, sufficient independent events, calibration and out-of-time replication |

## Acceptance rule

A line or chart passes **UI implementation** only after source-aware rendering and tests. It passes **empirical acceptance** only after a dated source observation is observed from the actual user's installed database, original unit/geography source parity is verified, and material missing coverage is disclosed. Predictive validity additionally requires enough genuinely independent holdouts and out-of-time replication. Do not close Phase 3/4 based solely on mapped definitions, frontend tests or an API key being configured.
