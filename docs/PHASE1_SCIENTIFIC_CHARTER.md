# Phase 1 scientific research charter — approved product intent, scientific scope in review

**Status: all ten product-intent decisions plus the revised six-story / 35-question / free-data-only scientific direction are APPROVED on 2026-11-03. Full scientific/method and integrated interface acceptance remains OPEN.** Governed by [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md). This is a normative description of the desired application, not an audit of current features/data. Research reference URLs are methodological starting points, not proof of import eligibility or complete empirical results.

## Revision 2026-11-06 (owner-directed, binding)

The original ten decisions were framed by an assistant and accepted without overrides. After an independent review the owner directed these changes:

* **Primary use:** long-term ETF portfolio decisions for a EUR-based investor (Lisbon). Home currency, euro area inflation and yields, hedging, costs, rebalancing and sequence risk are first-class. US series remain where they are the best free source.
* **Evidence tiers:** real-time, first-publication data only where a predictive claim is tested (C02, V05 and any backtest). Descriptive analyses use verified latest revised values and show that limitation. Category E in the evidence taxonomy is the predictive tier.
* **Forward-looking estimates allowed with uncertainty:** valuation-based expected-return ranges (P06) are model-based estimates (category C), calibrated by V05. They are not forecasts of crashes or timing signals.
* **Decision layer:** every analysis names the decision it informs; political economy (L01–L07) is research context ranked below portfolio decisions; L04 is a deferred extension.
* **Delivery:** Phase 2 completion is evidenced end states for the active analyses; work proceeds in end-to-end slices (data → analysis → chart) instead of waiting for the whole corpus. See [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) and the [catalogue revision](PHASE1_ANALYSIS_CATALOGUE.md#revision-2026-11-06--decision-layer-evidence-tiers-and-eur-investor-view-owner-approved).

## Approved research direction, coverage and data-rights rule

The user explicitly approved the [scientific coherence/free-source review](PHASE1_COHERENCE_AND_FREE_DATA_REVIEW.md). Six connected overview research experiences now govern the [active analysis catalogue](PHASE1_ANALYSIS_CATALOGUE.md); the former standalone C04/M03/V04/L06/G04 become preserved specialist subviews of C01/C02-M02/V01-M02/L01-L03/P02, and C06/F06/F07/L07/G06 become first-class analysis questions. All seven economic research domains remain represented.

**Required inputs must be freely accessible and legally usable for the local noncommercial research application** (including any source-specific free API limits and attribution). Paid MSCI indexes, commercial terminals and paid market-data APIs may not become required. No source is silently substituted by a misleading proxy. Four original worldwide data needs remain unresolved research requests: dated historical ACWI/global index constituents, dated European UCITS holdings, consolidated global listed-parent profits, original world equity and bond total-return histories. Free narrower alternatives may appear only with distinct economically accurate names, source-universe labels and limitations.

**Acceptance:** Approval of editorial structure does not establish empirically validated methodology, licensed dataset entitlement or implementation acceptance. No code gap analysis until final Phase 1 sign-off.

## Mission, audience and primary use

Build a focused, academically defensible **Global Capital Monitor** for a thoughtful long-horizon investor and an economics-oriented researcher. Primary function: understand how business cycles, monetary regimes, private credit, asset valuations, profitability and capital concentration interact; examine potential consequences for diversified ETF, bond and gold portfolios. Support descriptive monitoring and comparative historical inquiry. Avoid trading signal theatre, causal overclaim, simplistic automated market timing and sprawling individual-graph inventories.

The assistant's recommended default priority: **financial vulnerability and business cycle → valuation and monetary conditions → capital/labour distribution and global ownership → implications for long-term portfolio resilience**. Political economy is a substantive first-class analytical strand. Worldwide sources are a research goal, with honest geographic limits if unavailable. US is a strong *source coverage* region, not a mandatory global dashboard filter.

## Seven integrated research domains and intended decisions

| Domain | Central economic question | Why it matters | Core methodological basis |
|---|---|---|---|
| C — Business cycle and recession | How is activity moving and what is the distinction between signal, classification and forecast? | Contextualize current growth and cyclical turning points | [R04] OECD CLI, [R05] NBER, [R06] Estrella–Mishkin, [R07] Sahm |
| M — Monetary conditions and inflation | How do policy, inflation expectations, real yields and global monetary divergence affect financial conditions? | Interpret discounting, funding costs and currency differences | [R01] Fed framework, source definitions for Fed/ECB/BoJ policy decisions |
| F — Leverage, private credit and financial fragility | Are credit, leverage and debt-service vulnerabilities building? | Assess vulnerabilities separately from realized stress | [R01] Fed, [R02] BIS credit gaps, [R03] BIS debt service, [R08] BIS early-warning research |
| V — Valuation and expected returns | How do market prices relate to earnings, capital replacement and real yields? | Long-horizon valuation context, not precise short-term crash timing | [R09] Campbell–Shiller, [R01] Fed vulnerability framework |
| L — Labour, distribution and profit | How do income shares, productivity, compensation, operating surplus and productive capital evolve? | Connect real production with distribution and capital accumulation | [R10] OECD IOT, [R11] OECD STAN, [R12] Fed distributional accounts |
| G — Global ownership, concentration and transmission | How concentrated are investable global indexes, and where do currency/country/sector exposures lie? | Distinguish equity-index weights from GDP/worldwide ownership and actual portfolio exposures | [R13] MSCI float/index methods, [R01] Fed financial vulnerabilities |
| P — Portfolio exposure and historical resilience | What risk factors actually drive a diversified portfolio's vulnerability across different states? | See exposures, drawdowns, diversification and FX/cost effects without unsupported trade instructions | [R01] Fed, [R13] index methods, validated asset-pricing/diversification literature to be added for portfolio charter |

## Evidence taxonomy

- **Source measurement**: dated primary-release values, vintage, official definition and reuse permissions.
- **Derived comparison**: transparently calculated formulas with compatible time, geography, units and statistical treatment.
- **Model-based estimate**: theoretical assumptions, estimation steps, uncertainty and sensitivity explicit.
- **Proxy**: an operationally related but economically different measurable quantity, never silently promoted to exact.
- **Historically validated predictor**: additionally requires event/horizon labels, genuine time-available observations, leakage controls, baselines, independent holdouts and calibration.
- **Unresolved scientific question**: cite competing theories and evidence; do not force artificial precision or present normative frameworks as established causal fact.

### Required research record for every catalogue entry

`analysis_id`, precise question and intended inference, domain, theoretical motivation with original sources, default multiple-series comparison, explicit source variable definition/version, geography and population, source observation timestamp, earliest public/release availability, revision/vintage, permissible transforms and units, alignment/exclusion handling, approved figure type and alternatives, event annotation semantics, statistical uncertainty, what would falsify/restrict the interpretation, figure caption/limitations, alternative methods if debated, and planned portfolio significance when applicable.

**Selection rule:** a candidate earns overview placement only if it answers an important nonredundant question, has clear comparative evidence, and admits a defensible short interpretation. The catalogue is richer; the default overview is deliberately small (suggested 6–8 curated analyses, not 46 tiles). User-authored saved analyses may show any supported combination but must pass the comparison-validity engine.

**Statistical rules:** matched sector and price deflators for productivity/compensation; explicitly distinguished world versus reporting-country aggregate; growth rates vs levels; real vs nominal; currency and total-return vs price-return; not comparing PWT income fractions to unrelated labour share indexes as if same definition; explicit missingness and structural breaks. Avoid mechanical normalizations that simulate nonexistent records. A source's historical timestamp, date of publication and first usable date are different.

## Annotation, COVID and retrospective bias

The official NBER 2020 recession is **March–April 2020**, following the February peak and ending at the April trough ([R05]). A COVID **public-health/economic shock** overlay may extend over a sourced, separately selected interval, and the subsequent **recovery interval** must be defined against a specific indicator and pre-shock reference threshold. Never extend or rename the NBER band to match a desired visual width. Other events—2001, 2008–09, sovereign-debt episodes, inflation shocks—must likewise be independently dated and geographically scoped. Recession classifications can be retrospectively announced, so evaluation as-of dates must not treat later knowledge as contemporaneous.

## Interpretation standard

Every analysis should yield an evidence statement of the form **measurement → comparative pattern → historical context → limits/alternatives**. It must not auto-generate causal explanations from coincident lines. Forecasts are not displayed as "probability of market crash" without independently replicated skill and calibrated horizon. No arbitrary universal composite risk score: any index must disclose normalization, weights, sensitivity, uncertainty and its own predictive evaluation ([R15]).

## Ten approved owner decisions — binding product intent (2026-11-03)

The user explicitly accepted **all ten assistant recommendations**, without overrides. These choices are now binding product intent; they do not approve individual research hypotheses, datasets or figures.

| # | Approved product choice | Resulting design constraint |
|---|---|---|
| 1 | Macro-financial vulnerabilities and consequences for long-term diversified ETF investing are primary; economics research is substantive | Lead with comparative scientific questions, never trading tips |
| 2 | Economically literate reader, with academic-grade inspectable methods | Concise observed-evidence summary plus full reference, data and reproducibility layer |
| 3 | Medium-term cycles (~6 months–5 years) and structural decades-long developments | Horizons are analysis-specific; no universal forecast horizon |
| 4 | Globally oriented, comparing US/Europe/Japan plus China/other economies with compatible concepts | Country/region belongs to each graph, no global dashboard country mode; reporting-country proxies cannot masquerade as world statistics |
| 5 | Political economy is a first-class research domain | Labour, productivity, surplus, profitability, wealth, productive-sector assumptions and competing Marxian methods are substantive |
| 6 | Six curated comparative analyses on the default overview; approximately 35 question-led analyses in the library | Editorial relevance and complementarity determine the overview; catalogue size is not a graph quota |
| 7 | Full per-graph customization and saved views alongside expert-defined defaults | Independently change series, countries, horizons, transforms, chart types, event overlays; prevent scientifically invalid combinations |
| 8 | Brief evidence summary, contradictions and uncertainty, expandable scholarly methodology | No confident causal prose from coincident lines, no decorative risk gauges |
| 9 | Optional holdings/ETF exposure analysis, historical stress scenarios, no automated buy/sell advice | Maintain currency, total-return, vintage, cost and concentration transparency |
| 10 | Quiet monitoring, source updates and optional research summaries; no unvalidated alarms | Notify about observed research/data changes only; forecasts require independent validation |

**No further product-preference interview is needed to start methodology work.** The assistant owns selection and verification of literature, formulas, sources, theoretical alternatives, uncertainty and chart design. Any actual methodological fork must be documented with the case for and against, not outsourced as an unexplained technical preference.

## Binding research editorial method

Every analysis specifies: **question → research basis → original source variables → harmonized comparison → permitted inference → alternative explanations → practical significance**. This must be reviewable independently of whether the application already has the data.

Evidence categories are **(A)** direct primary measurement, **(B)** transparent derived relation, **(C)** model-dependent estimate, **(D)** explicitly scoped proxy, **(E)** historically validated predictor, and **(F)** scientifically unresolved hypothesis. A paper may validate one component but not an original synthesis of multiple components.

**Research distinctions confirmed against original publications:**
- BIS national credit gaps are deviations of private credit/GDP from a **recursive one-sided trend**. A weighted average of national gap values is not a published world credit-gap statistic ([R02], [R25]).
- BIS debt-service ratio **changes relative to each country's own history** are generally more comparable internationally than directly ranking raw country DSR levels ([R03], [R24]).
- OECD composite leading indicators address **growth-cycle deviations from trend**, not official NBER recession dating or calibrated GDP-level predictions ([R04], [R26]).
- Productivity–pay comparisons need **the same industry scope**, output per hour, hourly labour compensation and the **same value-added deflator**; CPI-adjusted pay and median pay answer different questions ([R17], [R18]).
- BEA has **three distinct domestic nonfinancial-company Q measures**. Q1 divides market equity value by net current-cost produced assets, Q2 adds book bonds and Q3 includes market bonds and net liquid assets; none is identical to an arbitrary Fed net-worth ratio ([R19]).
- Marxian rate-of-surplus/profit approaches require explicit productive/unproductive industry, capital stock/valuation and labour imputation assumptions; published world-input-output estimates are scholarly research, not theory-free measurements ([R10], [R11], [R20]).
- Markowitz portfolio covariance and the Brinson–Hood–Beebower benchmark attribution framework support diversification/asset-allocation analysis, not universal constant hedge correlations or deterministic portfolio prescriptions ([R21], [R22]).
- NBER labels February 2020 as the **peak** and April 2020 as the trough, hence two recession months March–April. Pandemic economic shock and output/employment recovery are separate sourced events/thresholds ([R05]).
- A valid world total requires a declared economic universe, non-overlapping aggregation units, currency basis, source vintage and coverage. Never silently conflate market-index weights, national GDP, world listed profits and issuer revenues.
- Sources must separate original observation period, first knowledge/release date, any revision effective interval, and retrieval time ([R14]).
- Chart selection follows comparison task and perceptual evidence, not whichever bar/line style is available ([R27]); composite scores additionally need weights/normalization/sensitivity and independent performance tests ([R28]).

## Phase 1 science review criterion

For all 35 candidate questions, specify source-authoritative definitions, exact numerator/denominator (where relevant), units and population, matched time/frequency, proposed comparison, referenced theoretical basis, formula or descriptive rule, alternatives and counterarguments, source availability/rights constraints in **principle**, uncertainty, a clear invalid-inference example, default graph type and acceptance tests. Do not conduct the code/data/UI gap analysis until the owner explicitly accepts the whole ideal-state specification. Being listed in a peer-reviewed or official reference is a **research basis**, not proof of today's values or forecast usefulness.

## Methodological reference register (primary/authoritative links)

- **[R01] Federal Reserve**, Financial Stability Report purpose and monitoring framework, 2026: https://www.federalreserve.gov/publications/2026-may-financial-stability-report-purpose-and-framework.htm
- **[R02] BIS**, Credit-to-GDP gaps definition (national one-sided trends; not an official world-gap series): https://data.bis.org/topics/CREDIT_GAPS
- **[R03] BIS**, Debt-service ratio data and method: https://data.bis.org/topics/DSR
- **[R04] OECD**, Composite Leading Indicators (turning points; qualitative short-term movements): https://www.oecd.org/en/data/datasets/oecd-composite-leading-indicators-clis.html
- **[R05] NBER**, Business cycle dating and 2020 peak/trough: https://www.nber.org/research/business-cycle-dating
- **[R06] Estrella and Mishkin** (1995/1998), *Predicting U.S. Recessions: Financial Variables as Leading Indicators*: https://www.nber.org/papers/w5379
- **[R07] St Louis Fed**, Sahm rule source and calculation: https://fred.stlouisfed.org/release?rid=456
- **[R08] Drehmann and Juselius** (2013), *Evaluating Early Warning Indicators of Banking Crises*: https://www.bis.org/publications/working-paper-421-evaluating-early-warning-indicators-banking-crises-satisfying-policy-requirements
- **[R09] Campbell and Shiller** (2001), *Valuation Ratios and the Long-Run Stock Market Outlook*: https://www.nber.org/papers/w8221
- **[R10] OECD**, harmonised national input-output tables, 2025, value-added components: https://www.oecd.org/en/data/datasets/input-output-tables.html
- **[R11] OECD**, STAN industry capital, labour and investment: https://www.oecd.org/en/data/datasets/structural-analysis-database.html
- **[R12] Federal Reserve**, Distributional Financial Accounts methods: https://www.federalreserve.gov/econres/feds/introducing-the-distributional-financial-accounts-of-the-united-states.htm
- **[R13] MSCI**, Global Investable Market and free-float index methodologies: https://www.msci.com/indexes/index-resources/index-methodology
- **[R14] Federal Reserve/St Louis**, ALFRED historical information/real-time periods: https://fred.stlouisfed.org/docs/api/fred/realtime_period.html
- **[R15] OECD/JRC**, *Handbook on Constructing Composite Indicators*, normalization/sensitivity: https://www.oecd.org/content/dam/oecd/en/publications/reports/2008/08/handbook-on-constructing-composite-indicators-methodology-and-user-guide_g1gh9301/9789264043466-en.pdf
- **[R16] Cleveland and McGill** (1984), *Graphical Perception* (quantitative chart encoding): https://faculty.washington.edu/aragon/classes/hcde511/s12/readings/cleveland84.pdf

Research sign-off must expand references for **each** accepted formula, especially alternative Marxian empirical profit-rate methods, portfolio return/covariance methods and geopolitical shock-event classifications. The above are confirmed source leads, not invented empirical results.

## Reviewed original research and authoritative methodology — additions (2026-11-03)

- **[R17] Schwellnus, Kappeler & Pionnier (2017)**, *Decoupling of wages from productivity: Macro-level facts*, OECD Economics Working Paper 1373, https://doi.org/10.1787/d4764493-en — decomposes the decoupling into labour share and median/average compensation; not a globally harmonized hourly wage series.
- **[R18] OECD (2024)**, *Labour income and productivity*, https://www.oecd.org/en/publications/oecd-compendium-of-productivity-indicators-2024_b96cd88a-en/full-report/component-9.html — aligned sector, hours, compensation, output deflator; CPI-real and median labour pay are distinct.
- **[R19] BEA (2026)**, *Returns for Domestic Nonfinancial Business*, https://apps.bea.gov/scb/issues/2026/05-may/0526-domestic-returns.htm — Q1/Q2/Q3 and current-cost net produced-assets denominator.
- **[R20] *Was Marx right? Development and exploitation in 43 countries, 2000–2014* (2024)**, Structural Change and Economic Dynamics, https://doi.org/10.1016/j.strueco.2023.12.001 — theoretical world-input-output/national-account estimates, not directly observed Marxian values.
- **[R21] Markowitz (1952)**, *Portfolio Selection*, Journal of Finance, https://doi.org/10.1111/j.1540-6261.1952.tb01525.x — diversification/covariance.
- **[R22] Brinson, Hood & Beebower (1986)**, *Determinants of Portfolio Performance*, Financial Analysts Journal, https://doi.org/10.2469/faj.v42.n4.39 — benchmark attribution, not a universal individual expected-return identity.
- **[R23] ESRB**, *Risk Dashboard* and indicator-methodology annexes, https://www.esrb.europa.eu/pub/rd/html/index.en.html — domain-oriented macroprudential research indicators.
- **[R24] BIS**, DSR methodology and FAQ, https://data.bis.org/topics/DSR and https://data.bis.org/faq — DSR estimates and cross-country interpretation.
- **[R25] BIS**, *The credit-to-GDP gap and countercyclical capital buffers: questions and answers* (2014), https://www.bis.org/publications/qr-201403/credit-to-gdp-gap-and-countercyclical-capital-buffers-questions-and-answers — one-sided trend and horizon interpretation.
- **[R26] OECD**, CLI methodology and growth-cycle semantics, https://www.oecd.org/en/data/datasets/oecd-composite-leading-indicators-clis.html.
- **[R27] Cleveland & McGill (1984)**, *Graphical Perception*, JASA, https://doi.org/10.1080/01621459.1984.10478080.
- **[R28] OECD/JRC (2008)**, *Handbook on Constructing Composite Indicators*, https://doi.org/10.1787/9789264043466-en.

