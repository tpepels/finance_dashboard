# Phase 1 scientific research charter — draft for owner decisions

**Status: PROPOSED, NOT APPROVED.** Governed by [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md). This is a normative description of the desired application, not an audit of current features/data. Research reference URLs are methodological starting points, not proof of import eligibility or complete empirical results.

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

## Ten decisions for the owner (assistant default unless explicitly changed; do not mark unanswered as approved)

1. **Primary outcome:** default understand long-term risks to ETF allocations; secondary macroeconomic research.
2. **Reader profile:** default serious self-directed investor/researcher, one concise reading layer and one scholarly methods layer.
3. **Overview density:** default six curated *comparative* analyses visible on entry, with ~30+ in the research library.
4. **Scope balance:** default genuinely global question set with US/Europe/Japan and other countries added per-chart when source definitions permit.
5. **Political-economy place:** default a full distinct research domain, integrated where theoretically meaningful rather than forced into every chart.
6. **Portfolio role:** default optional actual holdings input/import, with no compulsory connection, and neutral historical scenario research, no buy/sell calls.
7. **Narrative depth:** default brief factual evidence summary + expandable detailed method/source/contradictions, never generic prose.
8. **Customization freedom:** default independent per-graph chart type, country, indicators, transforms and saved views, with statistically invalid combinations disabled.
9. **Historical overlays:** default muted official NBER recession shading (US only), independent per-chart optional pandemic shock/recovery/crisis annotations with sourced dates.
10. **Product form:** default local single-user desktop-first responsive interface with light/dark, overview + research workbench + portfolio + sources/admin, operations secondary; no dashboard-global country switch.

Questions are for **user intent**, not asking the user to choose empirical methods. A missing answer is provisionally the assistant default, subject to review.

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
