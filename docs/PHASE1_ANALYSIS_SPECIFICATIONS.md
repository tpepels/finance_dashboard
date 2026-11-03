# Phase 1 — scientific specifications for all 35 comparative analyses

**Status: full first-pass scientific specification for review; product intent approved, Phase 1 scientific sign-off still open.** Decision date: 2026-11-03. This is the **100%-ideal research definition**, not an implementation gap audit, a claim that any series is imported, or a statement that all proposed global data already exist. It supplements the [analysis catalogue](PHASE1_ANALYSIS_CATALOGUE.md) and follows the only active [development plan](DEVELOPMENT_PLAN.md).

## Specification standard and reproducibility

Each record specifies (1) original measured variable/source or source-defined proposed worldwide universe, (2) research basis, (3) reproducible method, (4) meaningful alternative, (5) comparison validity, (6) permitted interpretation, and (7) recommended graph. These scientific identities are independent of today's application schema and cannot be renamed because a different feed is easier to obtain.

**Shared conventions.** Time t is the original reference period. Date of publication/first availability a_t and retrieved release/vintage v are separately recorded. Published local series keep native units; no automatic monthly interpolation, backfilled missing observations, line segment crossing long unknown gaps or silently carried stale figures. In equations percentages multiply ratios by 100, percentage-point differences subtract published percentages; log growth is `100 ln(X_t/X_(t−1))` and discrete percentage growth is `100 (X_t/X_(t−1)−1)`, with a label indicating which. Real versus nominal, flows versus stocks, market-value versus current-cost stocks, country/sector population, price-return versus net/gross total-return, and release availability are distinct dimensions. True published series are never confused with researcher-defined estimates or a proxy. Every denominator needs positive/appropriate domain, missing/negative values are handled explicitly. All temporal joins use matched source dates and eligibility, not hindsight knowledge. Reference register S01–S42 at end provides **original publisher or primary scholarly links**; some original data contracts are intentionally rights-restricted and must not be invented. No numeric results are asserted.

**Formulas below are research designs derived from the cited definitions; a citation to one source does not claim that the source published every proposed comparison.** Source series IDs are supplied where publisher identifiers were checked. Named original variables are authoritative in settings where a unique public API key is not stable or a licensed data product is needed. A proposed "global" aggregate without authorized full-country/issuer coverage is an **unfulfilled ideal data definition**, never a source-present measurement.

**Default visual rule:** multi-indicator comparison when economic questions demand it, but two unrelated units go into aligned small multiples rather than a misleading common axis. Each graph has its own country selection, source-vintage choice, transformations, figure type, events and saved state.


## C — Business-cycle dynamics and recession

### C01 — Are real activity and leading indicators turning?

**Published variables and exact source identity.** OECD DSD_STES@DF_CLI: amplitude-adjusted CLI (monthly index, average 100), with reference trend; quarterly real GDP volume (chained-volume national accounts); monthly real industrial-production index (US G.17; INDPRO); harmonized unemployment (e.g. BLS UNRATE for US).

**Original research/method.** OECD CLI publisher methodology [S01]; OECD GDP volume national accounts [S03]; Federal Reserve G.17 IP [S04].

**Reproducible calculation and comparison.** Use raw CLI level and sign of ΔCLI_t; separately show Δlog(IP_t)×100 and quarterly Δlog(realGDP_q)×100. Do not normalize CLI to growth rate. Turning-point dates require a specified peak/trough algorithm and release-vintage dating.

**Method alternatives.** CLI growth-cycle turning points versus NBER classical-cycle recession dates; OECD CLI versus Conference Board LEI with source-specific component rules.

**Conditions for a valid comparison.** Monthly CLI and IP panels, quarterly GDP as separately reported observations; identical country definition and real series; US NBER context is labelled US-only.

**Interpretation boundary.** CLI implies qualitative deviations from trend, not annual percentage GDP growth or a recession probability.

**Recommended figure.** Three aligned line panels with shared time, separately labelled units; no default bars.

### C02 — Do the yield curve and Sahm Rule agree about recession risks?

**Published variables and exact source identity.** FRED T10Y3M daily nominal 10-year minus 3-month US Treasury spread (percentage points); SAHMREALTIME monthly unemployment three-month-average rise from trailing 12-month minimum (percentage points); UNRATE input (monthly, SA); NBER USREC chronology with announcement availability.

**Original research/method.** Estrella–Mishkin recession research [S05]; Sahm release and original real-time definition [S06]; NBER cycle dating [S02]; ALFRED [S07].

**Reproducible calculation and comparison.** For raw rates, T10Y3M_t=DGS10_t−DGS3MO_t on common market days. For a separately labelled recomputation, m_t=(U_t+U_{t−1}+U_{t−2})/3; S_t=m_t−min(m_{t−k}, k=0,…,11), with original contemporaneously available U releases. Prefer the published SAHMREALTIME values for display. Compare indicator readings at actual publication as-of, not retroactive USREC event labels.

**Method alternatives.** 10y–2y curve; probit recession model after preregistered horizons; Sahm current-revised series SAHMCURRENT as clearly retrospective alternative.

**Conditions for a valid comparison.** Market-day observations do not inherit monthly unemployment release dates; choose monthly end/known-as-of selectors without backfilling unknown unemployment. NBER is ex-post classification.

**Interpretation boundary.** A 0.5 pp Sahm signal or a negative curve slope is not a validated combined near-term crash probability.

**Recommended figure.** Two synchronized line panels and source-specific annotation/baseline.

### C03 — Is real growth converging internationally?

**Published variables and exact source identity.** World Bank NY.GDP.MKTP.KD.ZG (annual % real GDP growth, country); IMF WEO NGDP_RPCH (annual real GDP growth %, country and named area aggregates); IMF WEO NGDPD (current-price GDP USD, for *separate* size comparisons).

**Original research/method.** IMF World Economic Outlook [S08]; World Bank WDI GDP growth [S09]; national-accounts real-volume methods.

**Reproducible calculation and comparison.** For like-for-like real levels g_{i,t}=100×(Yreal_{i,t}/Yreal_{i,t−1}−1); an unweighted convergence dispersion d_t=SD({g_{i,t}}) over a declared fixed country cohort. If using official WEO country-group aggregates, use their publisher-defined aggregation rather than a mean of national rates.

**Method alternatives.** GDP per capita growth vs aggregate growth; PPP-weighted versus market-exchange-rate group growth; growth dispersion vs convergence in income levels.

**Conditions for a valid comparison.** Compare same annual year, IMF vintage, country membership and actual-versus-forecast status. WEO projections must not be presented as observed historical GDP.

**Interpretation boundary.** Smaller cross-country variance of growth is not convergence of levels or living standards.

**Recommended figure.** Multi-country annual lines plus a separate composition/dispersion chart.

### C04 — Is economic weakness spreading across industries?

**Published variables and exact source identity.** Federal Reserve G.17 Table 6 industrial-production diffusion indexes (published); industry IP series and sector weights from G.17; US BLS PAYEMS total nonfarm employment (monthly); BEA real PCE and real private fixed investment by NIPA component (quarterly).

**Original research/method.** Federal Reserve G.17 industrial-production diffusion tables [S04]; BEA national accounts [S10].

**Reproducible calculation and comparison.** Primary breadth is the **published G.17 diffusion index**, with its documented formula; do not reinterpret it as an invented sector share. Optional original construction B_t=Σ_i w_i·1(Δlog IP_{i,t}<0)/Σ_i w_i on a fixed documented industry sample, explicitly labelled analyst-defined weakness breadth.

**Method alternatives.** Equal-weight versus value-added-weight sector count; diffusion from surveys versus realized production, industry vs geographic breadth.

**Conditions for a valid comparison.** Industrial classifications, weight versions, seasonal adjustment and frequency must align. Do not add quarterly GDP components as if observed monthly.

**Interpretation boundary.** Breadth of contraction is descriptive and its early-warning skill requires separate study.

**Recommended figure.** Published diffusion line plus aligned industrial production/employment growth panels.

### C05 — How persistent are economic shocks and recoveries?

**Published variables and exact source identity.** BEA real GDP GDPC1 (quarterly chained quantity via FRED); BLS total employment PAYEMS (monthly); Fed INDPRO (monthly); NBER U.S. peaks/troughs and separate documented shock-event dates.

**Original research/method.** NBER recession dates and classification rule [S02]; BEA GDP [S10]; Fed IP [S04]; BLS employment series.

**Reproducible calculation and comparison.** For a chosen pre-shock reference t0, Xindex_t=100·X_t/X_{t0}; shortfall=100−Xindex. First recovery t* must meet a predeclared criterion, e.g. Xindex≥100 for two consecutive *observed* same-frequency periods; record t*, or censored if never reached.

**Method alternatives.** Pre-shock peak recovery versus projected no-shock trend counterfactual; classical recession dates versus health/economic-disruption event windows.

**Conditions for a valid comparison.** Never mix quarterly GDP with monthly dates by interpolation; event overlays carry geography, legal/publication and observation date.

**Interpretation boundary.** Recovery to past level is not recovery to a trend, welfare or employment quality; COVID recession is March–April 2020, shock can extend beyond [S02].

**Recommended figure.** Aligned pre-shock=100 lines, US recession gray, separately labelled shock/recovery annotations.

## M — Monetary policy, yields and currency

### M01 — How are monetary policy settings diverging?

**Published variables and exact source identity.** Federal Reserve effective federal funds rate EFFR (overnight % pa, daily) plus official target range (bounds, not a midpoint presented as actual); ECB FM.D.U2.EUR.4F.KR.DFR.LEV (deposit facility rate %, daily policy changes); BoJ FM01'STRDCLUCON (uncollateralized overnight call rate, daily average %, or FM02'STRACLUCON monthly).

**Original research/method.** New York Fed federal funds reference method [S11]; ECB official DFR series [S12]; BoJ overnight call rates [S13].

**Reproducible calculation and comparison.** Show each published level on its original effective/market observation date. Pairwise difference Δ^{i,j}_t=r^i_t−r^j_t in percentage points only after selecting *comparable overnight realized* or *declared policy-setting* concepts. A policy change is r_t−r_previous effective date.

**Method alternatives.** Official target/range comparator; realized interbank overnight EFFR vs euro STR vs BoJ uncollateralized rate; Taylor-rule policy gap as a separate model (not implicit).

**Conditions for a valid comparison.** Differing facilities and tools, negative-rate regimes, trading calendars, source time zones and zero-lower-bound periods must be identified.

**Interpretation boundary.** Nominal rate gaps do not determine exchange rates or prove equal restrictiveness across countries.

**Recommended figure.** Three prominent policy lines with period-instrument annotations; optional signed spreads below.

### M02 — Do real yields or inflation compensation explain discount-rate movements?

**Published variables and exact source identity.** FRED DGS10 10-year nominal Treasury constant maturity yield (% annual); DFII10 10-year inflation-indexed TIPS constant maturity real yield (%); T10YIE published 10-year breakeven inflation (%).

**Original research/method.** Federal Reserve H.15 market rates [S14]; FRED 10-year breakeven methodology [S15].

**Reproducible calculation and comparison.** On same valid market date and nominal maturity, BE10_t=DGS10_t−DFII10_t (percentage points); verify independent published T10YIE within documented rounding/method details. Changes: ΔDGS10=ΔDFII10+ΔBE10 by construction.

**Method alternatives.** Inflation swap compensation vs TIPS breakeven; affine term-premium decomposition (external model) or survey expectations, in separately labeled methods.

**Conditions for a valid comparison.** Same maturity, units, days and original yields; missing dates omitted, not interpolated. Inflation compensation includes TIPS liquidity and inflation-risk premia.

**Interpretation boundary.** Breakeven is not pure household expected inflation, nor are measured term premiums observable market truths.

**Recommended figure.** Three matched-market date lines and a verified decomposition/small multiples.

### M03 — Why are different yield curves steepening or flattening?

**Published variables and exact source identity.** FRED DGS10, DGS2, DGS3MO (% nominal Treasury constant maturity); T10Y3M published derived spread; EFFR when discussing short policy rates.

**Original research/method.** Fed H.15 rate series [S14]; Estrella–Mishkin theory [S05].

**Reproducible calculation and comparison.** s10_3m_t=DGS10_t−DGS3MO_t; s10_2y_t=DGS10_t−DGS2_t; track Δs and component changes Δlong−Δshort. Compare published T10Y3M against derived values at common dates.

**Method alternatives.** Zero-coupon curve slope, forward-rate spread, term premium estimates; separate choices and measurement versions.

**Conditions for a valid comparison.** Same calendar day, nominal basis and maturity convention. EFFR overnight differs from 3m constant-maturity market yield.

**Interpretation boundary.** Term-structure slope changes reflect multiple expectations, premia and liquidity; they do not uniquely identify policy shocks.

**Recommended figure.** Paired term-spread lines and component contribution line panels.

### M04 — Are currency movements coinciding with monetary divergence?

**Published variables and exact source identity.** ECB official euro foreign exchange reference rates (named currency and EUR base); BoJ FM08'FXERD04 (USD/JPY Tokyo close); Fed EFFR; ECB DFR; BoJ uncollateralized overnight rate; national CPI inflation rates for optional real differential.

**Original research/method.** ECB policy source [S12], BoJ FX/overnight primary series [S13], international parity/asset-pricing hypothesis as testable theory rather than proven mechanism.

**Reproducible calculation and comparison.** For quote FX units CCYbase per CCYforeign, signed ΔlogFX_t=100·ln(FX_t/FX_{t−1}); policy differential rd_t=r_home−r_foreign (pp) at same observed day. Correlation on matched monthly log FX changes and lagged rate differentials; compare rolling 36m when enough observations.

**Method alternatives.** Uncovered interest parity with forward premium, covered parity basis, nominal vs ex-post real rate differences; explicit hypotheses, not implicit forecast.

**Conditions for a valid comparison.** Declare quote direction, fixing time, weekends, central bank instrument differences, real-time availability and common frequency.

**Interpretation boundary.** Co-movement does not establish rate-driven causal FX response or exploitable arbitrage.

**Recommended figure.** Aligned FX-change and rate-difference lines; optional dated scatter with sample size.

## F — Private debt and financial fragility

### F01 — Is private credit growing faster than national income?

**Published variables and exact source identity.** BIS total credit to non-financial private sector (households+non-financial corporations) outstanding national stock, quarterly; BIS private-credit/GDP ratio (%); BIS published credit-to-GDP gap (pp) and trend series by country where available.

**Original research/method.** BIS total credit and one-sided credit gap [S16].

**Reproducible calculation and comparison.** R_{i,q}=100×CreditStock_{i,q}/Σ_{j=0..3}GDPnominal_{i,q−j}; gap=R_{i,q}−one_sided_trend_{i,q}, preserving the BIS published trend; researcher reconstructions must label choice of recursive one-sided HP smoothing and vintage.

**Method alternatives.** BIS gap vs national authority countercyclical-buffer gap, debt-to-income by sector, direct private debt growth.

**Conditions for a valid comparison.** Only same domestic jurisdiction and compatible national-credit/GDP accounting; don't aggregate gap values into a fictitious official world gap.

**Interpretation boundary.** High gap is a historical vulnerability signal, not a guarantee of financial crisis or precise timing.

**Recommended figure.** Published credit/GDP and one-sided gap in separate lines per country.

### F02 — Are private-debt service burdens rising in each economy?

**Published variables and exact source identity.** BIS DSR total private non-financial sector, household, and non-financial corporation (% of income, quarterly), with original coverage and assumptions; BIS underlying outstanding private credit stock for context.

**Original research/method.** BIS DSR original methodology and cross-country limitations [S17].

**Reproducible calculation and comparison.** Use DSR published estimate. For cross-country change, dev_{i,q}=DSR_{i,q}−mean(DSR_{i,q0…q1}) where baseline is a predeclared historically observed within-country interval (not official BIS adjusted series). Compare ΔDSR in pp and separate contemporaneous debt ratios.

**Method alternatives.** Fed household debt-service ratio distinct in coverage [S18]; debt-service to disposable income using micro-data (source and method separate).

**Conditions for a valid comparison.** Country/sector, income concept, assumed maturity, data revisions and chosen baseline must appear; direct absolute ranking across countries is discouraged by BIS.

**Interpretation boundary.** Approximate DSR levels do not measure actual household arrears/defaults or exact cross-country payment ratios.

**Recommended figure.** Quarterly line with country-specific historical baseline, sector separate small multiples.

### F03 — Do credit and debt-service early-warning signals coincide?

**Published variables and exact source identity.** Same-country BIS published private credit-to-GDP gap (pp, quarterly), total private DSR (income %, quarterly), independent dated banking crisis episodes with event-definition documentation if risk performance is evaluated.

**Original research/method.** Drehmann–Juselius evaluated differing warning horizons [S19]; BIS credit gap [S16] and DSR [S17].

**Reproducible calculation and comparison.** For visualization, combine **aligned separate quarterly panels** and per-country normalized DSR deviation. For claimed prediction, preregister forecast horizons h, indicator transforms, training/held-out crisis episodes, forecast origin availability; compute ROC/PR and calibration relative to baseline with blocked events.

**Method alternatives.** Alternative crisis definitions, logistic or survival risk models vs two independent uncombined signals; demonstrate limitations of published cutoff guides.

**Conditions for a valid comparison.** Do not optimize threshold on the same test crises; account for cross-country dependence and within-country time dependence.

**Interpretation boundary.** Descriptive signal alignment cannot be advertised as an independently validated composite systemic risk probability.

**Recommended figure.** Two synchronized panels + documented crisis bands and horizon controls.

### F04 — Are observable markets already under stress?

**Published variables and exact source identity.** Chicago Fed NFCI and ANFCI (weekly standardized indexes, zero=historical sample mean), OFR daily Financial Stress Index (standardized composite and regional contributions); ICE BofA US High Yield OAS BAMLH0A0HYM2 (%) when data rights permit.

**Original research/method.** Chicago Fed NFCI/ANFCI [S20]; OFR FSI [S21]; FRED ICE high-yield OAS methodology and licence [S22].

**Reproducible calculation and comparison.** Show each published standardized index without renormalizing to a different meaning; optional Δindex and percentile within a stated historical vintage. Compare direction in aligned panels, not add NFCI+FSI and call it a risk score.

**Method alternatives.** OFR FSI vs NFCI; corporate OAS, VIX or bid-ask liquidity measures separately depending on question.

**Conditions for a valid comparison.** Weekly versus daily sampling, index sample restandardization and ICE licence restrictions; no automatic mixed-unit stacking.

**Interpretation boundary.** A high stress index is contemporaneous stress, distinct from pre-crisis vulnerability indicators.

**Recommended figure.** Aligned weekly standardized index and credit spread panels.

### F05 — Which balance-sheet sectors carry leverage vulnerabilities?

**Published variables and exact source identity.** BIS household credit/GDP and non-financial corporate credit/GDP (quarterly, country); IMF WEO GGXWDG_NGDP general-government gross debt/GDP (annual %, where defined); Federal Reserve Financial Accounts bank/financial-sector leverage by specifically named balance sheet ratio.

**Original research/method.** Fed financial stability vulnerability categories [S23]; BIS total credit [S16]; IMF public debt WEO [S08].

**Reproducible calculation and comparison.** Compare Δ(debt stock)/income and debt/GDP *within each defined sector*, with matched calendar and denominator. Bank leverage candidate: asset/equity using consistently defined bank consolidated statements; show raw numerator/denominator.

**Method alternatives.** Debt/GDP vs debt service/income, gross versus net government debt, risk-weighted capital and bank asset/equity leverage.

**Conditions for a valid comparison.** Government vs private debt sectors and liability consolidation differ; do not rank unrelated denominator ratios as one universal exposure.

**Interpretation boundary.** Leverage measures financial sensitivity, not probability of loss absent assets, maturity structure and liquidity.

**Recommended figure.** Sector small multiples with units and country scope.

## V — Asset valuation and long-horizon returns

### V01 — Are US equity prices historically stretched relative to fundamentals?

**Published variables and exact source identity.** Robert Shiller original monthly price P, CPI, average prior 10-year *real* earnings, CAPE (ordinary versus distinct total-return CAPE), monthly dividend and yield components; FRED DFII10 (% US real yield) separate comparison.

**Original research/method.** Shiller original CAPE price/earnings data [S24]; Campbell–Shiller long-horizon valuation research [S25].

**Reproducible calculation and comparison.** CAPE_t=(P_t/CPI_t)/(mean_{k=0..119} E_{t−k}/CPI_{t−k}) using original Shiller source-defined monthly earnings and exact conventions. Adjusted earnings yield Y_t=100/CAPE_t (%) if CAPE>0. Historical percentile only on a named reference period/window.

**Method alternatives.** Total-return CAPE adjustment for dividend reinvestment; forward versus trailing P/E, dividend-price/price-to-book from source-defined datasets.

**Conditions for a valid comparison.** CAPE starts only after ten years of real earnings, no interpolation of missing months; bond real yields are distinct risk instrument and a naive yield difference is not formal ERP.

**Interpretation boundary.** High valuation has long-horizon empirical associations but cannot time short-term drawdowns.

**Recommended figure.** CAPE line with distribution markers, separate inverse yield/real rate panel.

### V02 — Do replacement-cost Q ratios corroborate earnings valuations?

**Published variables and exact source identity.** BEA Q1=(market corporate equity)/(net current-cost produced assets); Q2=(market equity+book corporate bonds)/same; Q3=(market equity+market bonds+net liquid assets)/same, original annual source tables E and supporting numerator/denominator; Shiller CAPE [S24].

**Original research/method.** BEA 2026 published domestic nonfinancial corporate Q1/Q2/Q3 and capital-return definitions [S26].

**Reproducible calculation and comparison.** Use published BEA Q1/Q2/Q3, inspect annual components and values. Qspread_{j,t}=Qj_t−1; CAPE indexed separately to own common base if demonstrating historical trend coherence, never equating numeric ratios.

**Method alternatives.** Hayashi marginal versus average Q structural interpretation; Fed market equity/net worth proxy as a **separate** named approximation with explicit incompatible denominator.

**Conditions for a valid comparison.** BEA scope domestic nonfinancial corporations (not S&P 500) and annual frequency; Shiller US listed equity universe different, so associations require restricted interpretation.

**Interpretation boundary.** Q ratios are not the same variable as index CAPE, nor guaranteed investment or profitability signals.

**Recommended figure.** Three original annual Q lines + distinct CAPE contextual panel.

### V03 — Can equity valuation levels be compared across global regions?

**Published variables and exact source identity.** MSCI ACWI developed/emerging and constituent region index forward P/E (consensus next-year EPS), trailing P/E (last-12m EPS) and country/sector compositions; index return currency, inclusion rules and free-float weighting.

**Original research/method.** MSCI Global Investable Market and Fundamental Data methodologies [S27]; Campbell–Shiller [S25]; Fama–French regional factor evidence [S28].

**Reproducible calculation and comparison.** For supported index data, E/P_{region,t}=EarningsMeasure_{region,t}/MarketPrice_{region,t}; specify MSCI earnings/aggregate-weighting convention precisely; if P/E is published, prefer that source ratio. Compare historical percentiles *within each region* before absolute cross-region ranking.

**Method alternatives.** Cyclically adjusted region valuation when ten-year comparable earnings exist; country-neutral sector-standardized P/E as a modeled alternative.

**Conditions for a valid comparison.** Same vendor, index family, earnings horizon, accounting period, currency convention and constituents; avoid mixing country GDP profit rates and equity-index EPS.

**Interpretation boundary.** Higher regional P/E can reflect sector mix, expected growth or accounting rather than pure overvaluation.

**Recommended figure.** Aligned regional multiples/yields, plus sector mix diagnostic.

### V04 — How do equity valuation yields and bond yields relate?

**Published variables and exact source identity.** Shiller CAPE ordinary and 100/CAPE earnings yield [S24]; US DFII10 real ten-year Treasury yield (%); source-defined dividend yield and 10-year nominal Treasury yield DGS10 (%).

**Original research/method.** Campbell–Shiller return-decomposition work [S25]; Fed H.15 real yields [S14]; Fama–French caution about pricing expected returns [S28].

**Reproducible calculation and comparison.** Plot the named earnings/dividend yield next to real and nominal Treasury yields. A descriptive yield spread d=earningsYield−realYield may be calculated **only** as 'yield difference'; it is not an observed equity risk premium or a return forecast.

**Method alternatives.** Gordon dividend-growth constant-growth approximation E[R]≈D/P+g under explicit assumptions; residual-income and discounted cash flow models as separate calibrated methods.

**Conditions for a valid comparison.** Net/gross cash-flow yield definitions, inflation horizons, equity earnings growth, investment currency, bond duration and country are incomparable unless independently modeled.

**Interpretation boundary.** Cash-flow yields omit capital growth/risk, and expected stock returns cannot be read directly from yield differences.

**Recommended figure.** Aligned yield time series and calculation annotation; optional model-sensitivity panel.

### V05 — Do valuation–forward-return relationships survive regime and horizon changes?

**Published variables and exact source identity.** Historical source-defined valuation at t (Shiller CAPE or dividend-price), contemporaneous real yield, subsequent inflation-adjusted equity total-return index through t+120 months, current and historic price/revision data.

**Original research/method.** Campbell–Shiller long-run evidence [S25], real-time ALFRED semantics [S07] and portfolio testing concerns.

**Reproducible calculation and comparison.** For matured month t: y_t=(TRreal_{t+120}/TRreal_t)^(1/10)−1; regress *only with data known at t* y_t on log(CAPE_t) and real yield. Report scatter, explicit origin, t+120 maturity and horizon-consistent repeated samples.

**Method alternatives.** Shorter 5-year horizon, dividend-price regressions, recursive versus expanding forward models, excess returns over real Treasuries.

**Conditions for a valid comparison.** Overlapping 10y windows create dependence; use 10y-spaced cohorts and event-block sensitivity; macro revisions and contemporaneous earnings are true-vintage constrained.

**Interpretation boundary.** Historical explanatory slope is not verified out-of-sample expected equity return or a timed crash forecast.

**Recommended figure.** Matched-origin scatter and decade-spaced holdout plot with uncertainty.

## L — Labour, distribution, Marxian political economy

### L01 — Is average labour compensation matching productivity in the same sector?

**Published variables and exact source identity.** OECD industry matched real gross value added, total hours worked, employee-plus-self-employed-imputed total labour compensation and *same-sector* value-added deflator; US BLS FRED OPHNFB (output/hour), COMPNFB (nominal compensation/hour), IPDNBS (output price index), COMPRNFB (CPI-real compensation/hour, a separate question).

**Original research/method.** OECD Compendium productivity/pay identity and scope [S29]; BLS nonfarm business published indexes [S30].

**Reproducible calculation and comparison.** productivity_t=(GVA_nom_t/GVA_deflator_t)/Hours_t; pay_t=(Comp_nom_t/GVA_deflator_t)/Hours_t. Both index to 100 at common reference t0. Ratio R_t=100·(productivityIndex_t/payIndex_t−1). In US index form payIndex=100·(COMPNFB_t/IPDNBS_t)/(COMPNFB_{t0}/IPDNBS_{t0}), not merely 100·COMPNFB/IPDNBS unless base appropriately aligned.

**Method alternatives.** Median versus average compensation and CPI-deflated purchasing power, separate published OECD decomposition; total economy vs OECD market-industry subset.

**Conditions for a valid comparison.** Every series has equal sector/hours definition and deflator, base-year alignment, units and self-employment treatment. Quarterly and annual releases not forward-filled.

**Interpretation boundary.** Average pay–output divergence does not alone measure median wage welfare, causal bargaining mechanisms or Marxian surplus value.

**Recommended figure.** Two indexed multi-lines plus subordinate derived ratio and alternative methods.

### L02 — How is value added divided between labour and other components?

**Published variables and exact source identity.** Same country/industry/year IOT compensation of employees CE, net operating surplus NOS, consumption of fixed capital CFC and net taxes on production NTP; gross value added GVA; optional matched self-employed labour imputation I with documented method.

**Original research/method.** OECD national IOT 2025 value-added components [S31]; OECD STAN [S32]; PWT labour share definition.

**Reproducible calculation and comparison.** National-account identity GVA=CE+NOS+CFC+NTP plus source-defined adjustments. LabourShare=100·(CE+I)/GVA; NetSurplusShare=100·(NOS−I)/GVA where imputation I is a transfer from mixed income with documented accounting scope. Show residual/coverage rather than enforcing 100 from incompatible series.

**Method alternatives.** PWT LABSHP... total economy labour-income share, OECD business sector adjusted share, gross surplus/GVA; every alternative has own population.

**Conditions for a valid comparison.** Same sector, country, year, currency and accounting unit, self-employment treatment and identities. No overlap of industry rows.

**Interpretation boundary.** Non-labour residual is not exclusively capitalist profit; production taxes, mixed income and depreciation matter.

**Recommended figure.** Audited additive component bars when identity matches, trend share lines otherwise.

### L03 — Are corporate net surplus and productive capital evolving together?

**Published variables and exact source identity.** Country-industry-year net operating surplus NOS, consumption fixed capital CFC, compensation CE, net produced fixed-capital stock K_net, gross value added GVA from same-sector matching; BEA net operating surplus/net produced assets as published US comparator.

**Original research/method.** OECD STAN net capital stock/output [S32]; OECD national IOT components [S31]; BEA nonfinancial produced-capital returns [S26].

**Reproducible calculation and comparison.** National-account analogue r_t=100·NOS_t/K_net,t (year-matched; average beginning/end-year stock as sensitivity); net surplus wage ratio NOS_t/(CE_t+I_t) and capital intensity K_net/Hrs where relevant. Coverage weights and capital-stock valuation explicit.

**Method alternatives.** Gross surplus/gross capital stock, gross operating surplus/GVA, post-tax corporate profits/total capital; not interchangeable without reconciliation.

**Conditions for a valid comparison.** Nominal flow and current-cost net stock in same currency/year/classification; stock/flow timing and self-employed income allocations explicit.

**Interpretation boundary.** NOS/net fixed assets is not a theory-neutral Marxian profit rate, nor annual net return to shareholders.

**Recommended figure.** Same-industry line comparisons and sensitivity small multiples.

### L04 — How sensitive are Marxian surplus and profit estimates to theoretical assumptions?

**Published variables and exact source identity.** Industry-level wages in productive labour V, productive new surplus estimate S, constant-capital advance C and turnover/capital-stock valuation; national-accounts source CE, mixed income, NOS, depreciation, gross intermediate inputs, net fixed capital, industry productivity classification.

**Original research/method.** Rotta & Kumar 2024 43-country WIOD productive-sector framework [S33]; OECD IOT/ICIO and STAN [S31,S32,S34].

**Reproducible calculation and comparison.** Within **one explicitly selected published framework**, s/v=S/V and rate of profit r=S/(C+V) with theoretical treatment of stock versus advanced capital and turnover documented. As separately labelled *accounting analogues*, ratio NOS/(CE+I) and NOS/K_net; these are not exact substitutions for S,V,C. Compare scenario changes Δr under productive-sector and labour-imputation choices.

**Method alternatives.** Rotta–Kumar industry classifier vs alternative inclusive all-industries accounting; current-cost vs historical-cost capital; wages of productive/unproductive labor and circulating capital sensitivity.

**Conditions for a valid comparison.** WIOD and OECD panels differ in years/countries/industries, and original paper parameters must be followed before claiming replication. Country aggregation must avoid double counting intermediate flows.

**Interpretation boundary.** Neither accounting analogue nor one paper's estimate directly validates Marx's theoretical law or establishes moral exploitation measurement.

**Recommended figure.** Scenario heatmaps, paired rate trajectories and full assumptions table.

### L05 — How concentrated is household financial wealth?

**Published variables and exact source identity.** Fed DFA US quarterly household net worth and balance-sheet asset group shares: top 0.1%, next 0.9%, next 9%, next 40% and bottom 50%; source financial-wealth asset components by group and total assets/liabilities.

**Original research/method.** Fed Distributional Financial Accounts (DFA) publication and underlying SCF/Z.1 harmonization [S35].

**Reproducible calculation and comparison.** Group wealth share_t=100·wealth_group,t/total_household_wealth_t. For top 1% add published top0.1% + next0.9% only when both use same release; group asset composition=100·asset_category_g/total_assets_g, with negative wealth/debt handling.

**Method alternatives.** Survey of Consumer Finances triennial microdata with sampling uncertainty; World Inequality Database under separately named income/wealth definitions.

**Conditions for a valid comparison.** Household unit, top-group partition, rebenchmark/revision, source time and stock versus flow; avoid mechanically comparing these wealth shares to pay/GDP shares.

**Interpretation boundary.** Wealth concentration is not equivalent to corporate ownership concentration or median wages.

**Recommended figure.** Group share lines plus 100%-stacked wealth composition when components reconcile.

### L06 — Are pay, output and corporate surplus moving differently?

**Published variables and exact source identity.** Same-sector real GVA/hour, hourly compensation deflated by GVA deflator, net operating surplus, GVA, CE, CFC, industry unit labour costs ULC (nominal compensation per unit real output), matched annual industry inputs.

**Original research/method.** OECD output/compensation and industry-account identities [S29,S31,S32].

**Reproducible calculation and comparison.** ULC_t=Comp_nom_t/RealGVA_t (currency per volume unit, normalized to t0 for comparability); compare indexed productivity/pay alongside NOS/GVA or NOS/(CE+NOS) with consistent sector and inflation adjustments.

**Method alternatives.** Gross vs net surplus, employer compensation versus CPI-real median wage, within-industry versus sector-mix decomposition.

**Conditions for a valid comparison.** Sector/country/year and units aligned, CE vs imputed self-employed compensation stated, corporate vs full-industry scope preserved.

**Interpretation boundary.** A rising surplus ratio does not prove the cause or quantify unpaid labour without a separate identifiable model.

**Recommended figure.** Aligned indexed line panels, not additive disparate index stacks.

## G — Global market concentration and capital transmission

### G01 — How much of ACWI market capitalization is concentrated in the largest constituents?

**Published variables and exact source identity.** Dated original MSCI ACWI free-float-adjusted security index weight w_{security,t}; security-to-issuer/company crosswalk (including multi-share classes), number of constituents and full index universe definition.

**Original research/method.** MSCI GIMI free-float methodology and constituent rules [S36].

**Reproducible calculation and comparison.** First combine multiple security classes by ultimate issuer where supported w_{issuer,t}=Σ_security∈issuer w_{security,t}; then C10_t=100·Σ_10_largest_issuers w_{issuer,t}, where weights fractions sum to 1. Store original dated constituents and methodology vintage; compare with top 10 security-weight version separately.

**Method alternatives.** Herfindahl–Hirschman HHI=Σ_i w_i²; effective number of constituents 1/HHI; top 5 vs top 10, equal-weight versus float-cap index.

**Conditions for a valid comparison.** Float eligibility, securities vs issuers, index changes, currency, corporate actions and rights. Factsheet-only observations cannot be interpolated.

**Interpretation boundary.** Index weight concentration does not prove aggregate global wealth ownership or the political-economic concentration of productive assets.

**Recommended figure.** Concentration historical line + dated top-issuer bar contributions.

### G02 — How does investable equity geographic weight differ from economic size?

**Published variables and exact source identity.** Dated original MSCI ACWI country constituent free-float index weights (%); World Bank NY.GDP.MKTP.CD country nominal current-US$ GDP (annual) and properly scoped country-group/world numerator; alternative WDI CM.MKT.LCAP.GD.ZS (domestic listed-company cap/GDP) is a separate *different* stock universe.

**Original research/method.** MSCI ACWI country weights [S36]; World Bank WDI current GDP [S09].

**Reproducible calculation and comparison.** Index country weight w_i,t=Σ_{issuer in country i} w_issuer,t; GDP share g_i,y=100×GDP_i,y/Σ_{j∈declared_country_universe}GDP_j,y. Match year and explicitly expose the two different universes. If comparing, graph w_i vs g_i *side by side* and label the conceptual difference.

**Method alternatives.** Share of global listed domestic capitalization from WFE versus ACWI float weights; sector-standardized exposures; issuer domicile versus revenues by country.

**Conditions for a valid comparison.** MSCI country assignment is not tax domicile and not company sales geographic exposure; GDP is flow, market cap stock; track membership and residual rest-of-world.

**Interpretation boundary.** w_i>g_i is not a quantifiable overvaluation or proof of capital extraction.

**Recommended figure.** Two aligned country-ranked bars or side-by-side area compositions; no fused synthetic ratio as headline.

### G03 — How large are worldwide consolidated listed-company profits relative to world output?

**Published variables and exact source identity.** Full-world listed parent issuer universe U_y with fiscal-year consolidated net income after tax attributable to parent NI_{i,fy}, annual financial reporting currency and original filing date, ultimate parent/LEI, duplicate and fiscal-period mapping; world GDP current US$ NY.GDP.MKTP.CD from **separately defined aligned calendar year**.

**Original research/method.** Issuer consolidated GAAP/IFRS statements plus MSCI global listed universe [S36]; WDI nominal world GDP [S09]; GLEIF parent legal identity research [S37].

**Reproducible calculation and comparison.** For verified unique listed parents with full eligible fiscal periods: N_global,y=Σ_{i∈U_y} FX_USD,fy·NI_i,fy; ratio=100·N_global,y/GDP_world,y. Corporate profits can be negative; no unweighted ratio average. Report universe percentage of eligible global free-float market cap covered, and sensitivity to missing firms.

**Method alternatives.** OECD gross corporate operating surplus/GDP, MSCI aggregate index earnings, SEC-reported US listed income; **label as non-equivalent** alternatives, not a substitute for consolidated worldwide parents.

**Conditions for a valid comparison.** Global listed coverage, parent-subsidiary elimination, fiscal/calendar translation, currency FX, restatement availability, private-versus-public universe, GDP double counting and legal data rights documented.

**Interpretation boundary.** An incomplete issuer sample is NOT a published global listed-profits/GDP time series; profits of multinationals are not geographically where production occurs.

**Recommended figure.** Full denominator/numerator provenance panel + history/coverage plot, only when defined.

### G04 — How much of diversified equity-market risk is shared across regions?

**Published variables and exact source identity.** Matched-date country/regional MSCI equity net total-return indexes for named regions with explicit currency; region/sector FX rates; full index inclusion history and dated country membership; optional Kenneth French published developed/emerging portfolio total returns.

**Original research/method.** MSCI published net/gross/price index methods [S36]; Markowitz covariance [S38]; Ken French regional returns as alternative [S39].

**Reproducible calculation and comparison.** r_{i,t}=Index_i,t/Index_i,t−1−1 on matched month; ρ_{ij,t,W}=corr({r_i,r_j}_{t−W+1…t}) on complete W=36 months with 60/120 sensitivity; wealth index=100·Π(1+r). Report pair sample N and coverage.

**Method alternatives.** Rolling downside-only correlation, rank correlation, dynamic conditional correlation model with independent calibration; all distinct methodologies.

**Conditions for a valid comparison.** Currency/FX, distributions, emerging-market inclusion changes, index-type net/gross returns, missing months, survivorship, effective availability.

**Interpretation boundary.** Correlations are unstable across crises and sample windows, and cannot alone determine a risk-free diversification allocation.

**Recommended figure.** Country correlation heatmap + drawdown and indexed total-return small multiples.

### G05 — Do cross-border financial imbalances and private credit grow together?

**Published variables and exact source identity.** IMF BPM6/BPM7 balance of payments current-account balance (annual or quarterly, monetary USD), net international investment position (stock, end period), BIS private nonfinancial credit outstanding (quarterly), country nominal GDP and exchange-rate convention.

**Original research/method.** IMF BOP/International Investment Position source definitions [S40], BIS nonfinancial credit [S16], World Bank GDP [S09].

**Reproducible calculation and comparison.** CAshare_i,t=100·CurrentAccount_i,t/NominalGDP_i,t; NIIPshare=100·NIIP_i,t/NominalGDP_i,t; compare with BIS Credit/GDP within country and dated world-region panels. If converting credit stocks to USD, use compatible end-of-period exchange rates; flows use period-average where source supports.

**Method alternatives.** Current account vs NIIP stock, capital-flow gross exposure vs net position; regional net creditor/debtor groups rather than a misleading sum of gross flows.

**Conditions for a valid comparison.** Balance-of-payments identities, IMF version changes, goods/services/primary/secondary account, GDP denominator, bilateral double-counting and missing counterparties.

**Interpretation boundary.** Correlation across credit and external accounts does not prove capital flight, global profit transfer or a financial crisis.

**Recommended figure.** Matched-country annual/quarterly panels with clear flow-versus-stock axis distinctions.

## P — Portfolio exposure and historical resilience

### P01 — What are the actual economic exposures inside ETF holdings?

**Published variables and exact source identity.** Fund weights f_k at actual holding-as-of date; original fund reported constituents j with position fraction h_{k,j,t} (including cash, derivatives and residuals); security ISIN/CUSIP/LEI issuer, sector and registered country; separate dated revenue-country percentages when independently published.

**Original research/method.** SEC primary N-PORT filings [S41], MSCI index/security mappings [S36] and official UCITS issuer/fund filings as distinct regulatory disclosure systems.

**Reproducible calculation and comparison.** Underlying portfolio asset weight e_{j,t}=Σ_k f_{k,t}·h_{k,j,t} (plus direct holdings), look-through if nested funds with path multiplicative weights and a cycle-detection contract. Category exposure e_{country}=Σ_j e_j·1(j assigned original issuer-country), with explicit unclassified and derivatives residuals.

**Method alternatives.** Issuer incorporation vs operating revenue geographic exposure, economic factor exposures, actual fund domicile or index-country mapping (all separately named).

**Conditions for a valid comparison.** Historical fund disclosure availability vs portfolio as-of dates, original filing amendments, holdings NAV percentages and fund share-class mapping; European UCITS cannot be populated from US SEC N-PORT.

**Interpretation boundary.** Reported portfolio issuer country does not measure revenue source, currency revenue risk or actual global economic ownership.

**Recommended figure.** Fund weights → underlying issuer/country/sector contribution bars with unclassified residual.

### P02 — Have stocks, bonds and gold provided stable diversification?

**Published variables and exact source identity.** MSCI ACWI NETR (net dividend-reinvested total return) currency-defined; licensed global aggregate bond total-return index (coupon/reinvestment; benchmark version explicitly recorded); World Bank Commodity Price Data 'Gold' London fixing USD/troy oz or source-specific LBMA benchmark; FX rates.

**Original research/method.** Markowitz portfolio selection [S38]; original index/return source definitions [S36]; World Bank Commodity Price Data gold and licensed bond total returns.

**Reproducible calculation and comparison.** For each matched month compute price/total-return convention-correct r_t=V_t/V_t−1−1, and ρ_{i,j;t,W}=Pearson correlation over N=W matched observations (W=36 default; 60/120 sensitivities). Common-currency indexed wealth W_t=100·Π_{s≤t}(1+r_s).

**Method alternatives.** Physical bullion price vs gold investable ETF TR net fees; inflation-deflated realized returns; Sharpe-style risk-adjusted returns and conditional drawdown correlation; risk-parity portfolio models are separate.

**Conditions for a valid comparison.** Spot gold omits storage/spread; total return index reflects fees/taxes conventions; bond duration and index reinvestment; avoid cross-currency price-only mixes and partial rolling windows.

**Interpretation boundary.** Historical diversification does not establish future negative correlation or a guaranteed hedge in inflation shocks.

**Recommended figure.** Three indexed wealth lines, rolling-correlation heatmap, optional underwater curves.

### P03 — How have official recessions and market crises affected actual portfolio drawdowns?

**Published variables and exact source identity.** Portfolio or asset investment-value total-return series in a single base currency, named risk-free/benchmark, original dated 2001/2008/2020 US NBER recession phases and independently documented market shock dates.

**Original research/method.** NBER US recession chronology [S02]; portfolio return and valuation theory [S38]; source-specific asset index methods [S36].

**Reproducible calculation and comparison.** Cumulative wealth V_t=V_0·Π(1+r_t); past peak H_t=max_{s≤t}V_s; drawdown DD_t=100·(V_t/H_t−1), percent. Define dated peak, trough and first return to prior peak on observed data, otherwise right-censored. Compare with event bands as separate evidence layers.

**Method alternatives.** Historical value-at-risk and expected shortfall, regime-conditioned scenario analysis, maximum drawdown in user-defined event windows.

**Conditions for a valid comparison.** Recession chronology and equity drawdowns need not coincide; correct total returns, trading calendar, fund inception/survivorship and missing observations.

**Interpretation boundary.** Past drawdown magnitude is not a forecast or loss bound; NBER 2020 recession band is only two months while pandemic risk episode may be longer.

**Recommended figure.** Indexed wealth line and underwater drawdown panel with distinct recession/shock/recovery overlays.

### P04 — How sensitive is a portfolio to inflation, rates and currency shifts?

**Published variables and exact source identity.** Currency weights of underlying holdings, nominal bond yield and modified duration D_mod (years), convexity C where documented, domestic and foreign FX spot, inflation index (CPI), asset-class allocation/total-return benchmarks.

**Original research/method.** Fed H.15 rates [S14], international asset returns [S36], standard bond modified duration/convexity accounting as scenario method.

**Reproducible calculation and comparison.** Bond price scenario ΔP/P≈−D_mod·Δy+0.5·C·(Δy)^2 with yield Δy in **decimal**, not percentage points; unhedged foreign asset domestic return 1+r_dom=(1+r_foreign)(FX_end/FX_start) using an explicitly declared domestic-currency quote convention; real return (1+r_nom)/(1+π)−1.

**Method alternatives.** Key-rate duration, option-adjusted convexity, full cash-flow repricing, historical versus hypothetical stress scenarios; none is automatically a forecast distribution.

**Conditions for a valid comparison.** Bond price approximation ignores spread/convexity irregularities, taxes and coupons; FX quote direction, inflation horizon and joint shock correlation must be predeclared.

**Interpretation boundary.** A conditional scenario is a sensitivity result; without a validated stochastic model there is no implied event probability.

**Recommended figure.** Scenario matrices and small multiples with assumption slider/value table, not ungrounded risk-colored KPI.

### P05 — How do rebalancing policies change historical portfolio resilience?

**Published variables and exact source identity.** Timestamped portfolio target weights, actual weights, investable dated constituent total returns, benchmark weights and total returns, rebalance dates, trading commissions/spreads, withholding/tax scenario policy and FX execution currency.

**Original research/method.** Markowitz [S38]; Brinson–Hood–Beebower attribution [S42]; benchmark return accounting from original index vendors.

**Reproducible calculation and comparison.** At each t before rebalance, wealth_{t+1}=wealth_t·Σ_i w_{i,t}·(1+r_{i,t+1})−transaction_costs_t; update weights mechanically with asset return drift, apply scheduled rebalancing using only available prices; performance vs specified baseline using same currency and dates; compare drawdown and turnover.

**Method alternatives.** Calendar annual vs threshold rebalancing, buy-and-hold, minimum-variance/mean-variance allocations (optimized only using preceding training information), tax-sensitive rebalancing with source-specific rules.

**Conditions for a valid comparison.** No future-known return estimates, future-index constituents, missing delisted funds, hindsight fee/tax assumptions or silent FX conversion. Reinvest distributions and document cash flow timing.

**Interpretation boundary.** Backtest superiority can be sample-dependent and disappears after realistic costs; no buy/sell signal implied.

**Recommended figure.** Matched-portfolio wealth/drawdown lines, turnover and cost attribution panels.

## Source and original research register

The following are original publisher, data-producer or scholarly publication pages used to define the scientifically preferred variables and methods. They do not imply a license to redistribute data. **Rights-check and exact data-access contracts belong to later approved phases**, not an inspection of the existing application.

| ID | Authoritative source and methodological purpose | Original link |
|---|---|---|
| S01 | OECD Composite Leading Indicators dataset/method | https://www.oecd.org/en/data/datasets/oecd-composite-leading-indicators-clis.html |
| S02 | NBER Business Cycle Dating chronology | https://www.nber.org/research/business-cycle-dating |
| S03 | OECD national accounts and quarterly real GDP | https://www.oecd.org/en/data/datasets/quarterly-national-accounts.html |
| S04 | Federal Reserve G.17 industrial production, including diffusion tables | https://www.federalreserve.gov/releases/g17/Current/ipdisk/alltables.htm |
| S05 | Estrella & Mishkin (1996), Predicting U.S. Recessions, NBER w5379 | https://www.nber.org/papers/w5379 |
| S06 | FRED SAHMREALTIME release and formula | https://alfred.stlouisfed.org/series?seid=SAHMREALTIME |
| S07 | FRED ALFRED realtime vintage API and availability | https://fred.stlouisfed.org/docs/api/fred/realtime_period.html |
| S08 | IMF World Economic Outlook: annual actuals/forecasts and variable codes | https://data.imf.org/Datasets/WEO |
| S09 | World Bank WDI indicator metadata (real growth/current GDP) | https://databank.worldbank.org/metadataglossary/all/series/viewall?search=value |
| S10 | BEA National Income and Product Accounts tables | https://www.bea.gov/data/gdp/gross-domestic-product |
| S11 | Federal Reserve Bank of New York: Effective Federal Funds Rate | https://www.newyorkfed.org/markets/reference-rates/effr |
| S12 | ECB FM.D.U2.EUR.4F.KR.DFR.LEV deposit facility official rate | https://data.ecb.europa.eu/data/datasets/FM/FM.D.U2.EUR.4F.KR.DFR.LEV |
| S13 | Bank of Japan main time-series codes for overnight call rates and FX | https://www.stat-search.boj.or.jp/info/nme_Mdframe_en.html |
| S14 | Federal Reserve H.15 Selected Interest Rates | https://www.federalreserve.gov/datadownload/choose.aspx?rel=h15 |
| S15 | FRED T10YIE and matched DGS10/DFII10 | https://fred.stlouisfed.org/series/T10YIE |
| S16 | BIS Credit-to-GDP gaps original definition and data portal | https://data.bis.org/topics/CREDIT_GAPS |
| S17 | BIS Debt Service Ratios original definition and limitations | https://data.bis.org/topics/DSR |
| S18 | Federal Reserve household debt-service ratio methodology (different universe) | https://www.federalreserve.gov/releases/dsr/about.htm |
| S19 | Drehmann & Juselius (2013), Early Warning Indicators, BIS Working Paper 421 | https://www.bis.org/publ/work421.pdf |
| S20 | Chicago Fed NFCI / ANFCI published series | https://www.chicagofed.org/research/data/nfci/about |
| S21 | Office of Financial Research Financial Stress Index | https://www.financialresearch.gov/financial-stress-index/ |
| S22 | FRED ICE BofA High Yield OAS BAMLH0A0HYM2 (licence constraints) | https://alfred.stlouisfed.org/series?seid=BAMLH0A0HYM2 |
| S23 | Federal Reserve Financial Stability Report 2026 framework | https://www.federalreserve.gov/publications/2026-may-financial-stability-report-overview.htm |
| S24 | Robert J Shiller original data (CAPE, earnings, dividends, CPI) | https://www.econ.yale.edu/~shiller/data.htm |
| S25 | Campbell & Shiller (2001), Valuation Ratios and Long-Run Outlook, NBER w8221 | https://www.nber.org/papers/w8221 |
| S26 | BEA (2026), Returns for Domestic Nonfinancial Business Q1/Q2/Q3 | https://apps.bea.gov/scb/issues/2026/05-may/0526-domestic-returns.htm |
| S27 | MSCI indexes: GIMI, fundamental data, country/earnings methodology | https://www.msci.com/indexes/index-resources/index-methodology |
| S28 | Fama & French (1992), Cross-Section of Expected Returns | https://doi.org/10.1111/j.1540-6261.1992.tb04398.x |
| S29 | OECD (2024) Labour income and productivity, price-deflator alignment | https://www.oecd.org/en/publications/oecd-compendium-of-productivity-indicators-2024_b96cd88a-en/full-report/component-9.html |
| S30 | BLS original nonfarm labour productivity/compensation via FRED | https://fred.stlouisfed.org/series/OPHNFB |
| S31 | OECD 2025 national IOT original value-added components | https://www.oecd.org/en/data/datasets/input-output-tables.html |
| S32 | OECD Structural Analysis Database STAN (industry capital and labour) | https://www.oecd.org/en/data/datasets/structural-analysis-database.html |
| S33 | Rotta & Kumar (2024), Was Marx right? 43-country WIOD accounting paper | https://doi.org/10.1016/j.strueco.2023.12.001 |
| S34 | OECD Inter-Country Input-Output (ICIO) 2025 | https://www.oecd.org/en/data/datasets/inter-country-input-output-tables.html |
| S35 | Federal Reserve Distributional Financial Accounts original table and methods | https://www.federalreserve.gov/releases/z1/dataviz/dfa/index.html |
| S36 | MSCI Global Investable Market Indexes methodology | https://www.msci.com/indexes/documents/methodology/1_MSCI_Global_Investable_Market_Indexes_Methodology_20260331.pdf |
| S37 | GLEIF ultimate parent accounting consolidation links | https://www.gleif.org/en/lei-data/access-and-use-lei-data/level-2-data-who-owns-whom |
| S38 | Markowitz (1952), Portfolio Selection | https://doi.org/10.1111/j.1540-6261.1952.tb01525.x |
| S39 | Kenneth R French developed/emerging return libraries | https://mba.tuck.dartmouth.edu/pages/faculty/Ken.French/data_library.html |
| S40 | IMF balance of payments dataset BPM6/BPM7 accounts | https://data.imf.org/Datasets/BOP |
| S41 | SEC Form N-PORT official source | https://www.sec.gov/data-research/sec-markets-data/form-n-port-data-sets |
| S42 | Brinson Hood & Beebower (1986), Determinants of Portfolio Performance | https://doi.org/10.2469/faj.v42.n4.39 |

## Scientific acceptance test for these 35 *definitions*

For each stable analysis ID, the Phase 1 charter must support a methods audit: (i) source/variable identity and exact unit/frequency; (ii) an identifiable methodological reference or a transparently **original proposed synthesis**; (iii) reproducible transformation and a stated datum/missingness policy; (iv) an actual scientifically meaningful alternative; (v) correct geography, population, timing and release-vintage pairing; (vi) an explicit false-inference boundary; (vii) a comparative default visualization and scientifically permitted alternatives. The final approved analysis catalogue will preserve the named research questions even if a later source-rights check classifies particular data as unavailable.

### Important discipline: no simulated completeness

- A source catalogue name or verified URL does not prove historical data availability, licensing, scientific accuracy or anything about today's code.
- The top-level source row for a licensed portfolio/index ratio is the *intended exact original measure*; it is **not** silently replaced with a similarly named ETF, index price feed, a Wisesheets-only US sample or a country-weight proxy.
- Country/sector imputation, industry classification, seasonal adjustment, currency convention, accounting changes, source-revision dates and valid predictive horizon must be specified for real-world empirical acceptance in subsequent phases; Phase 1 specifies the rule instead of claiming present verification.
- Forecasting/equity-return correlations, classifying recessions and testing causal theories require independent research evaluation. Descriptive time-series and referenced papers do not substitute for actual out-of-time test evidence.
- Final Phase 1 acceptance also requires the user to sign off on the **complete ideal product**, including these analyses and the [visualization contract](PHASE1_VISUALIZATION_CONTRACT.md), before any implementation gap review is allowed.
