# Economic research indicators — definitions, interpretation and verification
*Local-only finance dashboard, 2 November 2026*

## What changed

The main dashboard is now driven by `GET /api/research` and `GET /api/research/{id}`, and **not** by the original arbitrary source chart list. It displays **46 question-led indicators** in five clearly identified geographical and institutional scopes:

- **World & OECD**: World Bank/ILO/IMF worldwide aggregates, OECD38 *reporting-country* corporate-surplus estimates, and **separately labelled** global-equity index characteristics.
- **United States**: BLS nonfarm business sector, PWT total-economy labour compensation/GDP, FRED/BIS monetary and credit indicators, domestic equity market value and nonfinancial replacement-cost Q. Those scopes cannot be casually combined.
- **Euro area & EU27**: euro-area/EMU policy rates, real GDP and BIS credit gap; EU27 gross corporate surplus; separately country-level PWT labour/GDP shares in Germany, France and Italy. Neither national data nor the EU27 is the euro area.
- **Japan**: Penn World Table labour/GDP share and its explicitly non-profit residual, World Bank growth and listed domestic equity capitalization/GDP, BIS credit and policy rates.
- **Compare regions**: only equally defined and properly scaled real GDP growth, harmonized central bank rates, national BIS credit-to-GDP gaps and domestic equity market cap/GDP. No global aggregate is used as an equally weighted country.

All source indicators are actually mapped in `definitions/series.json` and collected by existing provider adapters. Eleven **additional** primary-source FRED/BLS/Penn World Table/FRED Treasury source mappings are included, bringing the catalogue to **53**. The original 21 source charts, detailed datasets and local Wisesheets SEC filer supplementary research remain available in the expandable source explorer.

## New actual measured data

| Primary source and code | Native frequency/unit | Exact use |
|---|---|---|
| BLS via FRED **OPHNFB** | Quarterly, index 2017=100 | Nonfarm business output per hour |
| BLS via FRED **COMPNFB** | Quarterly, index 2017=100 | Nonfarm business total hourly compensation, nominal |
| BLS via FRED **IPDNBS** | Quarterly, index 2017=100 | Same nonfarm business sector value-added output price deflator |
| BLS via FRED **PRS85006173** | Quarterly, index 2017=100 | Labour's share of nonfarm business value added **INDEX**, not GDP percentage |
| BLS via FRED **COMPRNFB** | Quarterly, index 2017=100 | Consumer-price-deflated hourly compensation, separate purchasing-power question |
| Penn World Table 11 via FRED **LABSHPUSA156NRUG** | Annual, ratio 0–1 | US total-economy labour income share; display multiplies source values by 100 |
| Federal Reserve via FRED **T10Y3M** | Daily, percentage points | 10-year minus 3-month US Treasury yield spread; zero inversion reference |

All seven have primary FRED landing pages at `https://fred.stlouisfed.org/series/{code}`. No invented observations or proxy data fill any missing series.

## Derived research measurement: distribution of productivity growth

The displayed **US BLS nonfarm-business productivity versus output-price-adjusted hourly compensation** is a simple, documented production-accounting transformation. Each source index shares the same 2017=100 base and is observed in the **same quarter**:

```
output_per_hour_index(t) = OPHNFB(t)
output_price_real_hourly_pay_index(t) = 100 * COMPNFB(t) / IPDNBS(t)
relative_productivity_pay_gap_pct(t) =
    100 * (output_per_hour_index(t) / output_price_real_hourly_pay_index(t) - 1)
```

This is a **post-2017 indexed ratio**, not the ratio of dollars of produced output to dollars of wages, not median pay, and not a direct measure of the Marxian surplus-value/variable-capital ratio. The comparison is limited to exact common quarters with valid positive input values; a missing price deflator does not produce a point.

The BLS explains why the *output price deflator* is appropriate when comparing compensation relative to produced value, while **CPI-adjusted compensation** answers workers' purchasing-power question. The application plots the CPI-based measure separately, rather than mixing definitions and generating a misleading wage/productivity 'gap'.

Primary sources:
- https://fred.stlouisfed.org/series/OPHNFB
- https://fred.stlouisfed.org/series/COMPNFB
- https://fred.stlouisfed.org/series/IPDNBS
- https://fred.stlouisfed.org/series/PRS85006173
- https://fred.stlouisfed.org/series/COMPRNFB
- https://www.bls.gov/opub/btn/volume-6/understanding-the-labor-productivity-and-compensation-gap.htm
- https://www.oecd.org/en/publications/oecd-compendium-of-productivity-indicators_f25cdb25-en/full-report/component-7.html

## Marxian political economy and observable distribution

The **empirical** questions include the distribution of value added and labour compensation; the trends in labour's share over time; whether compensation keeps pace with productivity at comparable prices; and how much gross surplus arises in corporate accounts.

The **theoretical** Marxian questions include capital ownership, surplus appropriation, relative and absolute surplus value, and paid versus unpaid socially necessary labour time. The current national-accounts aggregates are related **but not equivalent** concepts. Gross operating surplus includes depreciation; GDP labour share may account for imputed self-employed labour; PWT, BLS, Eurostat and OECD have different sector boundaries; and aggregate labour income share cannot identify wage inequality among workers. The interface explicitly distinguishes the observed series from the contested mapping into a Marxian *rate of exploitation*. It avoids the unsupported inference that `100 − labour_share` is directly the profit rate or surplus value.

The OECD's research shows why comparisons of productivity and real labour income require comparable deflators and why sector composition can affect labour share. Academic Marxian analyses have estimated surplus value from harmonized multi-country input-output accounts and modelling assumptions, but those estimates are not interchangeable with public GDP shares.

- ILO/UN metadata SDG 10.4.1: https://unstats.un.org/sdgs/metadata/files/Metadata-10-04-01.pdf
- OECD on decoupling: https://www.oecd.org/en/publications/oecd-compendium-of-productivity-indicators_f25cdb25-en/full-report/component-7.html
- Peer-reviewed 43-country Marxian accounting example: https://www.sciencedirect.com/science/article/pii/S0954349X23001753
- World Bank market-cap/GDP definition: https://databank.worldbank.org/metadataglossary/world-development-indicators/series/CM.MKT.LCAP.GD.ZS

## Equity market ≠ world economy

The World Bank **world domestic listed equity capitalization/GDP** is a different universe from the **MSCI ACWI free-float weighted global equity INDEX**. MSCI's September 30, 2026 factsheet reports **64.21% US country weight**, so a global index is clearly US-dominated. Its concentration and valuation statistics are labelled as those of the *equity index*, never the globally equal-weighted economy. Do not mix the published Siblis index trailing P/E with WDI all-listed market capitalization to infer a nonexistent global profit series.

- MSCI ACWI index: https://www.msci.com/indexes/index/892400/msci-acwi-index
- MSCI September 2026 ACWI factsheet: https://www.msci.com/documents/10199/255599/msci-acwi.pdf

## Three gray economic periods, no labels inside graphs

Every main chart and source chart can show only subtle gray unlabeled rectangles for US NBER-reported contraction months:

| Context | NBER recession months actually shaded |
|---|---|
| US dot-com crash recession | 2001-04-01 through 2001-11-30 |
| US financial-crisis recession | 2008-01-01 through 2009-06-30 |
| US COVID-19 recession | 2020-03-01 through 2020-04-30 |

These are the months **after NBER peaks through NBER troughs**, not arbitrary intervals selected around stock market crashes. They do **not** describe official EU, Japanese or worldwide recessions; that limitation is mentioned *outside* every plot. A chart only receives bands whose interval overlaps its actual observed date range. No text labels or event lines appear inside graph areas.

https://www.nber.org/research/data/us-business-cycle-expansions-and-contractions

## Evidence rules and scope boundaries

The research API:
- Never invents dates or carries observations forward.
- Enforces identical unit and frequency for any direct multi-source plot.
- Computes cross-region headline high/low differences only on one **exact common source date** shared by **all** series.
- Calculates a year-on-year change from the nearest **observed** period near one year earlier within an appropriate native-frequency tolerance. Both dates are displayed.
- Returns `no_data` where the local SQLite database has not ingested source observations yet.
- Exposes original provider URLs/measure definitions and scientific caveats with each graph.
- Supports source-native dates at 15-year, 30-year or full-history horizons.

All source data remain local. The official provider's copyright and licence terms still apply if someone redistributes raw observations externally. There are no GitHub workflows, cloud jobs or public-only data gates.

### Scope: Phase 3 vs Phase 4

**Phase 3:** user-facing visible layout, geographical classification, usable source graph library, legends, crisis recession background shading, provenance and descriptive visual context.

**Requested Phase 4 work now implemented:** real same-sector **derived productivity/output-price-pay index**, indexed ratio gap, source-aligned differences, separate national-accounts labour distribution lenses, and explicit economic relationships sourced and computed server-side. This does **not** constitute the whole planned Phase 4 (predictive modelling, formal theory-dependent surplus-value account estimation, robust macroeconomic risk scoring, historical backtesting and uncertainty quantification).

## Local checks

```bash
python -m unittest discover -s tests -p test_research.py -v
cd frontend && npm test && npm run build
docker compose up -d --build finance-dashboard
```

Source and transform contracts have been committed. The application is **not declared visually or runtime verified** until these tests/build and real-data browser inspection have been performed locally. The Docker build runs frontend tests, TypeScript compile and Python catalogue checks without GitHub Actions.

## Multinational labour-income-share measurements: same PWT, not a synthetic EU series

Phase 4 now also uses the exact Penn World Table 11.0 **annual fractional compensation/GDP shares** for Japan, Germany, France and Italy, through 2023. It retains the already implemented US PWT series:

- Japan: [LABSHPJPA156NRUG](https://fred.stlouisfed.org/series/LABSHPJPA156NRUG)
- Germany: [LABSHPDEA156NRUG](https://fred.stlouisfed.org/series/LABSHPDEA156NRUG)
- France: [LABSHPFRA156NRUG](https://fred.stlouisfed.org/series/LABSHPFRA156NRUG)
- Italy: [LABSHPITA156NRUG](https://fred.stlouisfed.org/series/LABSHPITA156NRUG)
- United States: [LABSHPUSA156NRUG](https://fred.stlouisfed.org/series/LABSHPUSA156NRUG)

Each series is multiplied by 100 to display percent. The comparative view overlays all **five countries** on an identical PWT methodology and uses exact shared years to calculate any high-minus-low range. The European research page displays Germany, France and Italy **individually**; no fake EU27 total or unverified euro-area aggregate is synthesized. Japan's labour/non-labour GDP split uses one Japanese PWT denominator and labels the complement as **not corporate profits or Marxian surplus value**. These observations currently end in 2023, and revised historical PWT data are not genuine publication vintages.

