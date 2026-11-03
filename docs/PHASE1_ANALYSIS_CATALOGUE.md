# Phase 1 — proposed question-led analysis catalogue

**Status: CANDIDATE, NOT APPROVED.** An **ideal research product** catalogue; it is **not** a current feature inventory or gap report. All entries need their own formal research record and peer-reviewed/official source review before Phase 1 sign-off. IDs are stable proposed question identities, not chart or database IDs. Citation keys R01–R16 point to the [scientific charter](PHASE1_SCIENTIFIC_CHARTER.md); a source for one method never certifies every related derived inference.

## Design rules

- Curated **six** analyses on first launch by default; the full approved catalogue stays available in the research library. Same question can have multiple saved chart specifications.
- Prefer **2+ meaningfully related observations per analysis**, with synchronized multiple panels when the units cannot share a y-axis. The answer must distinguish independent evidence, direct transformations and model estimates.
- Country/geography is **independent per graph**. A country switch never changes navigation or other figures; global questions can compare several regions within one figure.
- A default chart is a scientific recommendation, not an immutable constraint; permitted overrides must be dimensionally valid. Include the raw values, provenance, explanatory interpretation, alternative methods and reproducible transform.
- Official events, analyst-defined shocks, and recovery-to-baseline overlays are distinct, selectable per-chart, and always dated/cited.
- No single-series tile solely to increase chart count; no "composite systemic risk" without independent construction/validation.
- Exact global/European historical inputs may be unavailable: the question remains an ideal target, labelled as an acquisition/research requirement, not silently proxied by a narrower source.

## Initial default overview — six recommended analyses

1. **C02** — Do yield curves and labour-market deterioration agree? (turning point evidence and nonidentical horizons)
2. **M01** — How far apart are major central bank policy settings? (global monetary context)
3. **F03** — Do credit gaps and debt service send consistent signals? (vulnerability, not current stress)
4. **V01** — How stretched is US equity valuation in historical context? (long-horizon caution)
5. **L01** — Is real hourly compensation matching productivity? (distribution/production link)
6. **P02** — How have stocks, bonds and gold diversified each other? (personal portfolio context)

Other research domains—particularly global concentration and Marxian profit-rate research—are prominent library analyses and can replace overview panels after owner preference is established. The six are a proposed editorial balance, **not** a demand that all six be available in every data-vintage region.

## Complete proposed comparative-analysis inventory

| ID | Research question | Default multi-measure composition | Preferred visualization | Methodological anchor | Non-negotiable interpretation guard |
|---|---|---|---|---|---|
| **C01** | Are economic activity and leading indicators turning? | OECD CLI; real GDP; industrial production; unemployment | Aligned small multiples + phase-marked lines | [R04], [R05] | CLI is an early turning-point signal, not a measured GDP forecast |
| **C02** | Do yield curves and labour-market deterioration agree? | 10y−3m term spread; Sahm Rule; real-time recession label | Two synchronized line panels + dated bands | [R06], [R07], [R05], [R14] | Different horizons; NBER dating is retrospective |
| **C03** | Is global growth converging or diverging? | Comparable real GDP growth: US; euro area; Japan; China; India; world where coverage allows | Country multi-line growth rates | [R04] | Mixed regional population, frequency and release dates require explicit harmonization |
| **C04** | Is weakness spreading across economic sectors? | Industry output; real income; employment; household consumption; business investment | Small multiples plus optional breadth plot | [R04] | Diffusion is not a forecast unless separately tested |
| **C05** | How long do shocks and recoveries last? | Pre-shock indexed output; employment; industrial production; official recession and shock interval | Indexed lines plus distinct event/recovery bands | [R05] | Recovery definition depends on series; pandemic period is not extended NBER recession |
| **M01** | How far apart are major central bank policy settings? | Fed; ECB; BoJ comparable policy-rate proxies | Multi-line with institution-specific rate definitions | [R01] | Deposit/target/range/maturity conventions cannot be treated as identical |
| **M02** | Are real rates or inflation expectations moving the discount-rate environment? | Nominal yields; inflation-linked real yields; breakeven inflation | Aligned lines; rate decomposition where valid | [R01] | Breakevens contain liquidity/risk premia and are not pure expectations |
| **M03** | Are yield curves steepening or flattening for the same reason? | Short policy rates; 2y/10y yields; 10y−3m and 10y−2y spreads | Small multiples with transparent signed spreads | [R06] | Different curve spreads should not be conflated |
| **M04** | How do monetary divergence and exchange rates coincide? | Policy differentials; currency pairs; inflation differences | Aligned panels / scatter only for matched periods | [R01] | FX movements are multiply determined; descriptive analysis is not causal |
| **F01** | Is private credit expanding faster than income? | Nonfinancial private credit/GDP by economy; credit gap against published one-sided trend | Country multi-line ratios + gap panel | [R02] | A weighted average of national gaps is not a world aggregate credit gap |
| **F02** | Are debt-servicing burdens historically elevated? | BIS household; corporate; combined debt-service ratios by country | Multi-line / sector small multiples | [R03], [R08] | DSR is model-estimated with different source coverage |
| **F03** | Do credit gaps and debt service send consistent signals? | BIS credit gap; BIS DSR; dated crisis episodes | Aligned comparable-period panels | [R02], [R03], [R08] | Long- and short-horizon indicators have different early-warning meanings |
| **F04** | Is financial stress already present? | Funding stress; credit spreads; market liquidity; volatility | Separate synchronized panels | [R01] | Market stress and slowly accumulating vulnerabilities are distinct states |
| **F05** | Where are leverage vulnerabilities concentrated? | Corporate leverage; household debt/income; public debt; bank leverage if defined | Sector and country small multiples | [R01] | Public/private denominator and scope differences need visible restrictions |
| **V01** | How stretched is US equity valuation in historical context? | Shiller CAPE; earnings yield; real government yield | Line panels with historical distributions | [R09], [R01] | Long-run association does not precisely date near-term corrections |
| **V02** | Does replacement-cost Q tell the same story as earnings valuation? | Source-exact Tobin Q; CAPE; corporate asset valuation numerator/denominator | Normalized comparison + method component panel | [R09] | Do not equate a shareholder equity/net-worth proxy with Tobin Q |
| **V03** | Are equity valuations similar across regions? | Region-consistent forward/trailing earnings yields; price/earnings; total-return benchmarks | Country region small multiples | [R09], [R13] | Different index composition/accounting conventions constrain comparisons |
| **V04** | How do equity and bond expected-return inputs contrast? | Equity earnings yield or dividend yield; real bond yield; inflation assumptions | Paired line panels and conditional spread | [R09] | Earnings yield is not a realized nor guaranteed equity expected return |
| **V05** | How sensitive are valuation interpretations to regime and horizon? | Valuation ratio; real rates; subsequent 10-year real return with maturity guards | Scatter plus chronological validation tables | [R09], [R14] | Overlapping forward returns and lookahead must be controlled |
| **L01** | Is real hourly compensation matching productivity? | Output per hour; compensation/hour deflated by matching output price; CPI-pay separately | Two indexed lines plus explicit divergence ratio | [R11] | Match countries, industry, deflator and base year; average pay is not median |
| **L02** | How do labour and non-labour income shares vary? | Matched labour income share; corporate surplus; sector value added | Country multi-line and separately stacked additive components | [R10], [R11] | Non-labour remainder is not automatically capitalist profit |
| **L03** | What are the trends in net corporate surplus and capital intensity? | Net operating surplus; depreciation; employee compensation; net capital stock | Aligned ratio panels with industry choice | [R10], [R11] | Net versus gross operating surplus and valuation basis differ |
| **L04** | How sensitive are Marxian profitability analogues to assumptions? | Published net operating surplus; compensation; productive capital; sector/self-employment scenarios | Scenario small multiples + assumptions sensitivity table | [R10], [R11] | National-account analogues are not direct observations of Marxian value magnitudes |
| **L05** | Is concentration of household wealth rising? | Official top 1%/next 9%/bottom 50% wealth shares; income and asset mix | Matched multi-line distribution + composition plots | [R12] | Wealth stocks differ from wages, GDP and market-index weights |
| **L06** | Are labour outcomes and corporate profits decoupling? | Real pay; productivity; net corporate operating surplus; real unit labour costs | Aligned lines with comparable sectors | [R10], [R11] | Cross-series comparison does not alone identify causal appropriation |
| **G01** | How concentrated is global listed equity ownership by market weight? | Dated ACWI largest-ten free-float weights; index weight universe; number of firms | Concentration line + dated constituent contribution bars | [R13] | MSCI historic continuous constituents require rights; no interpolation from factsheets |
| **G02** | How regionally diversified is the investable world equity market? | MSCI country weights; regional free-float market cap; world GDP shares as *separate* concepts | Small multiples and dated allocation bars | [R13] | Free-float index exposure ≠ national GDP share or sales exposure |
| **G03** | Where are global company profits recorded? | Consolidated global listed issuer net income; ownership crosswalk; world GDP | Reconciled geographic breakdown + ratio lines | [R10], [R13] | Public national-accounts corporate surplus is not consolidated listed net income |
| **G04** | How much of global portfolio risk is common across markets? | Country/sector returns; FX contribution; international correlation | Rolling correlation heatmap + regional drawdown panel | [R13] | Return history, currency and survivorship must be controlled |
| **G05** | Are global credit and capital imbalances moving together? | Comparable external balances; private credit stock; real output by region | Matched regional small multiples | [R02] | Countries and currency conversions must not produce duplicate global totals |
| **P01** | What economic exposures do the portfolio's funds actually represent? | Fund weights; original dated holdings country/sector; consolidated issuer look-through | Allocation bars + geographic/sector comparison | [R13] | Fund domicile, issuer location, sales exposure and underlying ownership differ |
| **P02** | How have stocks, bonds and gold diversified each other? | Common-currency total returns; adjusted reinvestment returns; rolling correlations | Three indexed lines + rolling correlation heatmap | [R13] | Gold price source and bond distributions/inflation must be aligned |
| **P03** | How have major crisis episodes affected portfolio drawdowns? | Asset/portfolio total returns; peak-to-trough drawdown; crisis/shock overlays | Synchronized price and underwater drawdown lines | [R05] | Stress episode dating and sample endpoints must be explicit |
| **P04** | How sensitive is a portfolio to inflation, FX and rates? | Inflation; nominal vs real return; bond duration; currency exposure | Scenario small multiples + stress assumptions | [R01], [R13] | Conditional scenario analysis is not a forecast |
| **P05** | How would plausible rebalancing choices affect historical resilience? | Portfolio weights; benchmark; transaction fees; FX conversions; tax scenarios | Comparable indexed portfolios and drawdown panels | [R13] | Backtests require actual available instruments, fees, no future leakage |

## Analysis-record approval gate

For **every** ID: (1) define population/geography; (2) choose source-original measures and exact units; (3) name one or more published papers/methodological sources and substantive disagreements; (4) supply date and revision semantics; (5) write calculations/valid comparisons and tests; (6) design default and allowed alternative chart types; (7) give one coherent example of its intended interpretive question **without inventing a result**; (8) define statistical uncertainty and source rights; (9) state what information would make the answer misleading; (10) identify whether actual exposure/portfolio context changes interpretation.

**Source acquisition, feasibility analysis, implementation status and gap estimates do not belong in Phase 1**. The catalogue establishes the ideal research question first. Once the user approves it, subsequent phases may surface impossible/rights-blocked inputs without silently substituting narrower evidence.

## Catalogue coverage

35 proposed analysis identities across C=5, M=4, F=5, V=5, L=6, G=5, P=5. Counts describe only proposed research questions, not product completeness. The current 46 individual indicator views remain an historical implementation inventory; they do not automatically determine the new product.
