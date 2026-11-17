# Backtesting and allocation module — design

**Status:** design proposal, 17 November 2026. Not implemented. Requires an owner-approved charter amendment (section 1) before any code lands.
**Scope:** a walk-forward backtesting and monthly allocation engine for EUR-based index/ETF investors. It combines established indicators and financial econometrics with Claude as one ensemble member. It produces **general recommendations** (a market outlook and model portfolios at five risk levels) and, optionally, recommendations personalised to the owner's own policy and holdings.
**Governing documents:** [scientific charter](../../PHASE1_SCIENTIFIC_CHARTER.md), [analysis catalogue](../../PHASE1_ANALYSIS_CATALOGUE.md), [architecture](../../ARCHITECTURE.md), [source policy](../../SOURCE_POLICY.md), [agent handoff](../../AGENT_HANDOFF.md).

---

## 0. Owner decisions (interview, 17 November 2026)

| # | Question | Owner answer | Design consequence |
|---|---|---|---|
| 1 | Prediction target and horizon | **12-month only** | Every forecast target is the 12-month-ahead EUR excess return distribution, or a 12-month event probability. No 1–3-month tactical layer and no separate 5–10-year model. Existing P06/V05 long-horizon ranges are a prior, not a target. |
| 2 | Form of the actionable output | **Strategic allocation** plus **rebalance/defer alerts** | Each month: a full recommended mix across the buckets, its ETF implementation and a trade list. Also drift-band alerts telling the investor to rebalance now, defer, or do nothing. |
| 3 | Asset universe | **Core regions + bonds; gold + commodities; equity factors; credit + REITs** | 19 buckets (section 3). Satellite buckets have a neutral weight of zero and can only enter through validated views. |
| 4 | Decision cadence | **Monthly** | Month-end information set; trades executed on the next month's first trading day; turnover penalised. |
| 5 | Role of Claude | **Ensemble member** | Claude produces structured, as-of-dated probabilistic views from point-in-time data. Its weight comes only from scoring after its training cutoff. It also writes the monthly explanation. |
| 6 | Model and budget | **Configurable** | Model, effort, samples and a hard monthly spend cap are settings. Without a key, the module works with Claude's weight at zero. |
| 7 | Data rigour | **Two labelled tiers** | Tier E (real-time vintages) for headline results; Tier R (revised data with conservative publication lags) for longer history, labelled optimistic. |
| 8 | Data rights | **Free, including free API keys** | The charter's free-data rule stands. Registered free keys (FRED/ALFRED, Tiingo/EODHD free tiers) are allowed; paid feeds are not. |
| 9 | Generality | **Owner only, EUR** | One EUR investor profile in `owner_inputs.json`. Bucket and instrument mappings are data, so other UCITS/US ETFs or index funds can be substituted without code changes. No multi-user profiles. |
| 10 | Risk budget and benchmark | **Moderate, around the profile's neutral policy** | Each reference portfolio is its own benchmark. Ex-ante tracking error ≤ 3%, equity share ±15 pp, per-bucket caps. |
| 11 | Follow-up (17 November): portfolio dependence | **"Not too fixed on the provided portfolio; also give general recommendations"** | The primary output is **portfolio-independent**: a market outlook per asset class (layer 1) and recommended model portfolios at five risk levels (layer 2). The owner's policy and recorded holdings are an **optional** personal layer (layer 3) that reuses the same forecasts. The forecasting and backtest never read holdings. See section 7. |

---

## 1. Charter amendment required, and how the design honours it

The charter currently states "context only, never a timing signal". It also forbids unsupported crash probabilities and treats predictive claims as **category E**, which requires real-time data, leakage controls, baselines, independent holdouts and calibration. A monthly 12-month allocation is a conditional, slow-moving timing decision, so it needs an explicit owner revision. Proposed wording, to be added to the charter's revision log once approved:

> **Revision 2026-11-xx (owner-directed): validated conditional allocation.** The application may publish monthly asset-class views and recommended allocations that deviate from declared reference portfolios (the market anchor, a five-rung risk ladder and, optionally, the owner's policy) within a declared risk budget, **only to the extent that the deviating forecasts have earned out-of-sample skill under the category-E protocol** (pre-registered holdout, point-in-time data, purged walk-forward validation, baselines, calibration, deflated performance statistics). When skill is not established, the recommendation equals the reference portfolio and says why. Recommendations are general, educational decision support for the investor using the installation. They are not automated trading or personalised advice to third parties.

The design enforces this by construction: forecasts enter the optimiser through a Black–Litterman posterior whose view confidence is the forecast's measured out-of-sample error (section 6.4). **An unskilled model has infinite view uncertainty and therefore no influence.** "No validated edge, hold the policy" is a legitimate and common output.

Existing rules that carry over unchanged:
- No fabricated or spliced observations. Proxies are named as proxies (category D) with their own labels.
- Real-time evidence is separate from revised evidence.
- No composite risk score without disclosed weights, normalisation, sensitivity and its own predictive evaluation.
- No parallel calculation path. The module is implemented as engine analyses with acceptance gating (section 10), not as a revived "vintage backtest" route.

---

## 2. What the system predicts

For every bucket *i* and month-end decision date *t*:

1. **12-month EUR excess log return distribution**
   `y_{i,t} = Σ_{k=1..12} [ ln(1+R^EUR_{i,t+k}) − ln(1+R^cash_{t+k}) ]`,
   reported as mean, standard deviation and the 10/50/90 % quantiles. R^EUR is the bucket's total return in EUR, after hedging for hedged buckets. Cash is the € short rate (€STR, previously EONIA, previously the Bundesbank day-to-day rate).
2. **12-month covariance matrix** Σ_t of the bucket excess returns.
3. **Event probabilities over the next 12 months, used for alerts and conditioning:**
   - `P(DD_eq > 15%)`: the global equity bucket has a peak-to-trough drawdown above 15% within 12 months.
   - `P(recession start, EA)` and `P(recession start, US)`: CEPR-EABCN and NBER chronologies, evaluated only with dates as announced at the time (C02 rules).
   - `P(y_eq < y_bond)`: equities underperform EUR intermediate government bonds.
4. **Regime probabilities** `π_t(s)` over four macro-financial states: expansion / slowdown / contraction / recovery, from growth momentum and financial stress (section 6.2 M5).

Not predicted: individual stocks, horizons other than 12 months, point "price targets", or crash timing.

---

## 3. Asset universe: buckets, backtest return histories and ETF mapping

A **bucket** is an economic exposure. The backtest uses the longest legally free index-level history for each bucket. The live recommendation maps the bucket to an owner-selected ETF. ETF tracking difference and costs are applied on top. ETF price history is never spliced onto index history; the ETF's own record is used only to estimate tracking difference.

New definition files are `definitions/allocation_buckets.json` (bucket → return recipe, currency, hedging, cost) and `definitions/allocation_instruments.json` (bucket → candidate ISINs; the owner picks one per bucket).

| Bucket | Backtest return source (free) | Tier R start | Category | Example UCITS implementation |
|---|---|---|---|---|
| EQ_US | Ken French US market (Mkt−RF+RF), USD→EUR | 1926 | A | iShares Core S&P 500 (IE00B5BMR087) |
| EQ_EUROPE | French *Europe* developed-region market | 1990 | A | iShares Core MSCI Europe (IE00B4K48X80) |
| EQ_JAPAN | French *Japan* market | 1990 | A | iShares Core MSCI Japan IMI (IE00B4L5YX21) |
| EQ_APAC_XJ | French *Asia Pacific ex Japan* | 1990 | A | iShares Core MSCI Pacific ex-Japan (IE00B52MJY50) |
| EQ_EM | French *Emerging* market | 1989 | A | iShares Core MSCI EM IMI (IE00BKM4GZ66) |
| EQ_VALUE | French HML long-only proxy: market + ½·HML, by region | 1926 US / 1990 dev. | D | Xtrackers MSCI World Value (IE00BL25JM42) |
| EQ_MOMENTUM | market + ½·UMD | 1927 / 1990 | D | iShares Edge MSCI World Momentum (IE00BP3QZ825) |
| EQ_QUALITY | market + ½·RMW (AQR QMJ as a cross-check) | 1963 / 1990 | D | iShares Edge MSCI World Quality (IE00BP3QZ601) |
| EQ_SMALL | market + ½·SMB | 1926 / 1990 | D | iShares MSCI World Small Cap (IE00BF4RFH31) |
| EQ_MINVOL | AQR BAB-scaled proxy: market·β_low + ½·BAB | 1930 / 1990 | D | iShares Edge MSCI World Min Vol (IE00B8FHGS14) |
| GOV_EUR_SHORT | Par-bond reconstruction from the Bundesbank 1–3y yield curve (P05 method) | 1972 | B | iShares € Govt Bond 1-3yr (IE00B14X4Q57) |
| GOV_EUR_INT | Bundesbank 5–7y curve; ECB AAA curve from 2004 | 1972 | B | iShares Core € Govt Bond (IE00B4WXJJ64) |
| GOV_EUR_LONG | Bundesbank 15y+ curve | 1972 | B | iShares € Govt Bond 15-30yr (IE00B1FZS913) |
| GOV_EUR_LINKER | Bundesbank inflation-indexed real yields → real par bond + realised HICP carry | 2006 | B | iShares € Inflation Linked Govt (IE00B0M62X26) |
| GOV_GLOBAL_H | Swinkels sovereign 10y returns (existing) + EUR hedge carry `i_EUR − i_local` | 1950s | B | Vanguard Global Aggregate EUR-hedged (IE00BG47KH54) |
| CREDIT_IG | Modelled: Moody's Baa yield (FRED, 1919+) → duration/carry return minus expected loss; EUR IG via ECB corporate yields when available | 1919 | C | iShares Core € Corp Bond (IE00B3F81R35) |
| CREDIT_HY | Modelled from HY OAS + Treasury yield (existing FRED archive series); spread-duration model | 1997 | C | iShares € High Yield Corp (IE00B66F4759) |
| REIT_GLOBAL | FTSE Nareit All Equity REITs monthly total return (Nareit free download, attribution required; US-only proxy, labelled) | 1972 | D | iShares Developed Markets Property Yield (IE00B1FZS350) |
| GOLD | LBMA PM via existing gold series, USD→EUR | 1968 | A | Invesco Physical Gold ETC (IE00B579F325) |
| COMMODITY | World Bank Pink Sheet index spot return + T-bill collateral (no roll yield, so a category D proxy). Bloomberg/GSCI total-return indexes are not free. | 1960 | D | iShares Diversified Commodity Swap (IE00BDFL4P12) |
| CASH | € short rate (€STR / EONIA / Bundesbank call money) | 1960 | A | Xtrackers II EUR Overnight Rate Swap (LU0290358497) |

**Currency.** `R^EUR = (1+R^local)·(S_{t}/S_{t−1}) − 1`, with S in EUR per local unit. Before 1999 the DEM rate (FRED/Bundesbank) is converted at the irrevocable 1.95583 rate and labelled "DEM-based EUR proxy". The hedged return is `R^H ≈ R^local + (i_EUR − i_local) − c_hedge`, using one-month interbank rates and a hedge cost of 0.10% p.a. Equity buckets are unhedged by default; the existing P07 informs whether that default should change.

**Costs.** Per bucket: TER (from the chosen ETF's KID), half-spread (default 5 bp core / 15 bp satellite), a per-trade broker fee (owner input) and measured tracking difference. Optionally, Portuguese tax: 28% on realised gains at sale, so routing contributions (deferring gains) is modelled explicitly. Taxes are applied only in "after-tax" backtest mode.

**Reference portfolios (general, not owner-specific).** Recommendations are made against a published, rules-based ladder, so they apply to any EUR index investor:

1. **Market anchor.** The investable *global market portfolio* is the theoretical neutral (CAPM; Doeswijk, Lam & Swinkels 2014/2019, whose return series the application already registers). Its free-float equity regional split comes from FTSE All-World regional weights at *t* (existing factsheet series), with French regional market caps for Tier R. Within bonds, the anchor holds EUR government bonds across maturities in proportion to the euro area AAA outstanding-debt maturity profile (ECB), plus hedged global government and IG credit in market-value proportion. Gold is held at its approximate share of investable wealth (~2–3%).
2. **Risk ladder.** Five reference portfolios differ only in their growth/defensive split, with the internal mix of each side taken from the market anchor:

| Reference | Growth assets (equity + REIT) | Defensive (gov + IG + gold + cash) | Typical investor |
|---|---|---|---|
| R1 Defensive | 20% | 80% | Short horizon, capital preservation |
| R2 Conservative | 40% | 60% | |
| R3 Balanced | 60% | 40% | |
| R4 Growth | 80% | 20% | Long horizon, accumulating |
| R5 Equity | 100% | 0% | Long horizon, high loss tolerance |

   Factors, HY, REIT (beyond its market share), commodities and extra cash have 0% reference weight. They can enter only through validated views, with caps (default ≤ 10% each; factor sleeve ≤ 20% combined).
3. **Owner policy (optional, layer 3).** The owner may define their own neutral policy in `owner_inputs.json`, for example by choosing a rung or editing weights. It is treated as one more reference portfolio. Nothing in layers 1–2 depends on it.

Constraints for every reference portfolio (decision 10): long-only; Σw = 1; growth share within ±15 pp of the reference; ex-ante tracking error `√((w−w_b)ᵀΣ(w−w_b)) ≤ 3%`; per-bucket caps; cash ≤ 20%. Risk aversion λ is set per rung so that each reference is optimal under equilibrium returns (reverse optimisation, 6.2 M1).

---

## 4. Extra data to acquire

All of these go through the existing `ProviderRouter` → managed source-policy client → `SourceAcquisition` path, with archived originals, receipts and independent reconciliation. Each new series is registered in `definitions/series.json` with `role: allocation_predictor` or `role: allocation_return`.

### 4.1 Return inputs (new unless noted)

| Source | Series | Access | Notes |
|---|---|---|---|
| Ken French data library | Developed/Europe/Japan/APxJ/EM 3- and 5-factor and momentum, monthly | keyless | Partly existing (developed/emerging). Add regions and UMD. |
| AQR datasets | QMJ, BAB, Century of Factor Premia, TSMOM | keyless, attribution | Factor cross-checks and trend reference |
| Bundesbank time-series DB | Svensson yield-curve parameters (daily since 1972), inflation-indexed yields, call money rate, DEM/USD | keyless | Makes the par-bond reconstruction possible for any maturity |
| ECB Data Portal | AAA and all-issuer euro area curves, €STR, EONIA, corporate bond yields, reference FX (existing) | keyless | |
| FRED | Moody's Aaa/Baa, ICE BofA HY/IG OAS (existing archive), DGS curve, T-bill, DEXGEUS | free key | |
| Nareit | FTSE Nareit All Equity REITs TR | keyless, attribution | Check terms before registering, as for every source |
| LBMA / existing gold series | Gold PM | existing | |
| Tiingo free tier (optional) | Daily UCITS/US ETF prices for tracking difference and realised volatility | free key | Optional; Yahoo Chart remains the existing source |

### 4.2 Predictors (by family)

| Family | Variables | Source | Real-time availability (Tier E) |
|---|---|---|---|
| Valuation | CAPE, excess CAPE yield (ECY = 1/CAPE − real 10y), D/P, E/P | Shiller (existing), French international country B/M, E/P, D/P portfolios (1975+, free) | Prices and dividends are not revised; earnings carry a reporting lag, so a 3-month lag is applied |
| Valuation, regional | Country/region E/P and B/M aggregated to buckets | French international data | As above |
| Rates and curve | 10y−3m spread (US, DE), Cochrane–Piazzesi forward factor (Bundesbank curve), real 10y yields, carry and roll-down | Bundesbank, ECB, FRED | Market data, unrevised |
| Credit and stress | Baa−Aaa, HY OAS, **excess bond premium** (Gilchrist–Zakrajšek, Fed free CSV), OFR FSI (existing), VIX (Cboe free history, 1990+) | Fed, FRED, OFR, Cboe | EBP is re-estimated, so the real-time version is captured going forward and Tier R is used before that |
| Credit cycle | BIS credit gap, DSR (existing) | BIS | Quarterly with a ~2-quarter lag; the one-sided gap is real-time by construction, but the input revisions are not, so it is Tier R |
| Growth | OECD CLI (existing), **EC Economic Sentiment Indicator** (unrevised survey), Philly Fed manufacturing survey, Sahm rule (existing RTDSM), industrial production | OECD, European Commission, Philly Fed, FRED/ALFRED | OECD MEI *Original Release Data and Revisions Database* gives CLI vintages; ESI and Philly surveys are effectively unrevised |
| Inflation | HICP, US CPI (ALFRED), inflation expectations: **ECB SPF** (1999+), **Philly Fed SPF/Livingston** (1946+) | Eurostat, ALFRED, ECB, Philly Fed | Surveys are real-time by construction |
| Monetary | Policy rates (existing), **Wu–Xia shadow rates** (free), ECB/Fed balance sheet size | Atlanta Fed / Wu website, ECB, FRED | Shadow rate is re-estimated, so Tier R |
| Trend and momentum | 12-1-month total-return momentum, 10-month SMA gap, per bucket | Computed from bucket returns | Unrevised |
| Volatility | Realised monthly volatility from daily index/ETF data, VIX/VSTOXX term structure | French daily, Cboe, Yahoo/Tiingo | Unrevised |
| FX | Interest differentials (carry), OECD PPP deviation, BIS REER | OECD, BIS | PPP revised, so Tier R |
| Text (Claude only) | FOMC statements and minutes, ECB monetary policy statements and press conferences, ECB Economic Bulletin summaries | federalreserve.gov, ecb.europa.eu (public, dated) | Stored with publication timestamp; given to Claude only if published ≤ *t* |

### 4.3 Point-in-time store (core infrastructure)

New append-only table `pit_observation`:

```
series_id, period_start, period_end, value,
known_from (UTC timestamp the value became public),
known_to (nullable: superseded by a later vintage),
tier ('E' real vintage | 'R' revised value with modelled lag),
vintage_source ('ALFRED' | 'RTDSM' | 'OECD_MEI_REV' | 'publisher_archive' | 'lag_model'),
evidence_ref (FK to the existing source evidence)
```

- **Tier E** rows come from the existing ALFRED snapshots (`vintage.py`, `alfred_acquisition.py`), the Philly RTDSM (`philly_rtdsm.py`), OECD MEI revisions, archived publisher originals with release dates, and series that are unrevised by nature (market prices, surveys).
- **Tier R** rows set `known_from = period_end + publication_lag(series) + safety_margin`. `definitions/publication_lags.json` holds one conservative lag per series, taken from the publisher's release calendar (for example, euro area GDP flash at t+30 days becomes 45 days; BIS credit at 2 quarters becomes 7 months). Every lag cites its calendar source.
- **One access function:** `as_of(series_id, t, tier)` returns the latest value per period with `known_from ≤ t < known_to`. All models read only through it. A test asserts that no model code imports the raw observation tables.

---

## 5. Backtest protocol (category E)

### 5.1 Walk-forward loop

```
for t in month_ends(start, end):                  # decision dates
    I_t   = pit.snapshot(t, tier)                 # only known_from ≤ t
    fit   = each model fitted on targets realised ≤ t     # y_{t−12} is the last complete target
    f_t   = each model's forecast distribution for t→t+12
    w*_t  = combine → Black–Litterman → optimise (section 6)
    trade = rebalancing rule (section 7) applied to w_{t−1} drifted to t
    execute at the first trading day of month t+1 with costs
```

- **Expanding window** by default. A rolling 30-year window is a sensitivity variant.
- **Purging and embargo:** 12-month targets overlap. When the model at *t* is fitted, any target window ending after *t* is excluded (de Prado purging).
- **Overlapping-return inference:** Newey–West with 12 lags and Hodrick (1992) 1B standard errors for predictive regressions.
- **Minimum training span:** 120 months before the first forecast. Earlier months produce "no forecast", not a fallback forecast.

### 5.2 Pre-registration and holdout

Researcher degrees of freedom are the main overfitting risk. Before any holdout evaluation:

1. Freeze the model specification (feature lists, transforms, hyperparameter grids, combination rule, optimiser settings) in `definitions/allocation_preregistration.json`. Its SHA-256 is recorded in the git commit message and in every backtest result bundle.
2. **Development period:** Tier R 1973–2009 and Tier E wherever available before 2010.
   **Locked holdout:** 2010-01 to the latest complete 12-month target.
   The holdout is evaluated **once** per registered specification. Each evaluation is logged in `backtest_trial_log` with a trial count.
3. **Live forward log:** from deployment onward, every monthly forecast is written to an append-only `forecast_log` before its outcome is known. This is the only evidence that is fully immune to look-ahead.

### 5.3 Baselines (always reported)

1. **The reference portfolio itself** (each rung R1–R5, the market anchor, and the owner policy when defined), rebalanced by the same rule; this is the benchmark for that portfolio.
2. 1/N across the core buckets.
3. EUR 60/40 (world equity / EUR aggregate government).
4. Risk parity (inverse volatility, then equal risk contribution).
5. Equilibrium-only Black–Litterman (no views); this isolates the value of the forecasts.
6. Historical-mean forecasts (the Goyal–Welch benchmark for out-of-sample R²).

### 5.4 Metrics

**Forecast quality** (per model, per bucket, per tier, development vs holdout):
- Campbell–Thompson out-of-sample R² vs historical mean, with Clark–West (2007) test.
- CRPS and log predictive score for distributions; PIT histogram uniformity.
- Brier score, Brier skill score vs climatology, reliability diagram, ROC-AUC for events.
- Direction hit rate of `y_i − y_neutral-weighted` (secondary only).

**Portfolio outcome** (net of costs; optionally after tax):
- CAGR, volatility, Sharpe and Sortino ratios; maximum drawdown, Ulcer index, time under water.
- **Certainty-equivalent return** at each portfolio's own risk aversion λ (primary economic metric).
- Tracking error, information ratio and active-return t-statistic vs neutral.
- Turnover, cost drag, tax drag.
- **Deflated Sharpe ratio** (Bailey & López de Prado 2014) of the active return, using the trial count from `backtest_trial_log`.
- Stationary block bootstrap (Politis–Romano, mean block 12 months) confidence intervals for every difference vs neutral.
- Hansen SPA test across all registered variants against neutral.

**Acceptance gate for showing a deviation as "validated"** (all of the following on the holdout, net of costs, Tier E where available):
- CE-return improvement vs neutral > 0, with a bootstrap 90% lower bound > −0.25% p.a. (it may not plausibly destroy value);
- deflated Sharpe probability of active return > 0.90;
- maximum drawdown not worse than neutral by more than 3 pp;
- calibration: reliability-slope confidence interval contains 1 for each event probability that is used.

If the gate fails, the UI shows the neutral policy as the recommendation, with the model output available as "unvalidated research view". This mirrors the existing conditional/deferred acceptance pattern.

### 5.5 Tier reporting

Each backtest runs in Tier E and Tier R where both exist. On the overlapping span, `Tier R − Tier E` is reported as the **revision/look-ahead bias estimate**. Headline numbers are Tier E. Tier R results always carry the label "optimistic: revised data with modelled publication lags".

---

## 6. The mathematics

Notation: N buckets, excess-return vector y_{t} ∈ ℝ^N over 12 months, information set I_t, neutral weights w_b.

### 6.1 Risk model (Σ_t)

- Monthly covariance from EWMA (λ = 0.97), blended with a 10-year sample covariance, then **Ledoit–Wolf (2004) shrinkage** toward a constant-correlation target. It is scaled to 12 months with a Newey–West-style autocorrelation adjustment, because bond and credit returns are autocorrelated.
- Volatility forecast per bucket from a monthly HAR model on realised volatility (Corsi 2009), where daily data exists. Otherwise EWMA.
- Regime-conditional covariance (6.2 M5) mixed by regime probabilities: `Σ_t = Σ_s π_t(s) Σ_s + Σ_s π_t(s)(μ_s − μ̄)(μ_s − μ̄)ᵀ`.
- Proxy buckets (category D) get an extra idiosyncratic variance term equal to their measured tracking error against the live ETF, so their risk is not understated.

### 6.2 Forecast models (each yields a predictive mean and variance per bucket)

**M1 — Equilibrium prior.** Reverse optimisation from the **market anchor** weights: `π_t = δ Σ_t w_mkt`, with δ the market's implied risk aversion (market excess return / variance, estimated on the expanding window). The prior is therefore the same for every investor. Per-rung λ values are then chosen so each reference portfolio is optimal under π (Black & Litterman 1992; He & Litterman 1999). This is the anchor every view is shrunk towards.

**M2 — Valuation and yield building blocks** (fully specified, few parameters):
- Equity: `E[y_eq] = a + b · ECY_t`, where `ECY = 1/CAPE − real 10y yield` (Campbell & Shiller 1998/2001; Asness 2003 caution on the Fed model). For regions, country E/P and B/M from French international data are used in a pooled panel with region fixed effects.
- Government bonds: the 12-month expected excess return of a constant-maturity bucket is approximately `yield − cash + roll-down − ½·convexity·σ²`, computed from the Bundesbank/ECB curve at *t* (an identity-based forecast, essentially unparameterised). Plus the Cochrane–Piazzesi (2005) forward factor as a predictor of excess bond returns.
- Credit: `spread_t − expected default loss`, where `expected default loss = PD(rating, regime) × LGD`, using Moody's historical default rates by rating (published summary tables) and an LGD of 60%.
- Gold: real-yield sensitivity (`Δy_real` beta) plus trend. Expected return is shrunk heavily to zero because the evidence is weak (Erb & Harvey 2013).
- Commodities: carry is unobservable in free data, so only trend and inflation-surprise betas apply, with heavy shrinkage.

**M3 — Shrunk predictive regressions with forecast combination.**
For each bucket and each predictor *j* in its registered list, fit a univariate OLS `y_{i,t} = α + β_j x_{j,t} + ε` on the expanding window. Apply Campbell–Thompson (2008) restrictions: set β to zero if its sign contradicts theory, and floor the forecast premium at zero for equity buckets. Combine with the **Rapach–Strauss–Zhou (2010) mean or discounted-MSFE combination**. This is deliberately more robust than a multivariate kitchen-sink regression, and is the standard answer to Goyal & Welch (2008).

**M4 — Trend.** Time-series momentum signal `sign(r_{t−12,t−1})` and the 10-month-SMA gap (Moskowitz, Ooi & Pedersen 2012; Hurst, Ooi & Pedersen 2017; Faber 2007). Mapped to a forecast via its historical conditional mean. Its main use is conditioning drawdown probabilities and Σ, not return levels.

**M5 — Regimes and recession probabilities.**
- Recession probit, separately for EA and US: `P(recession start within 12m) = Φ(γ₀ + γ₁·termspread + γ₂·EBP + γ₃·Δ ESI or Sahm)`. Estrella & Mishkin (1998), with Gilchrist & Zakrajšek (2012) and Favara et al. for EBP. Labels are aligned to announcement dates for the information set and to true start dates for the target.
- Four-state regime classifier from real-time growth momentum (CLI/ESI 6-month change) × financial stress (EBP/OFR FSI percentile). As a robustness alternative, a 2-state Hamilton (1989) Markov-switching model on world equity excess returns (Ang & Bekaert 2002).
- Regime-conditional means and covariances are estimated on the expanding window, with shrinkage to unconditional values in proportion to the regime's sample size.

**M6 — Volatility-managed adjustment.** Expected Sharpe ratios are constant-ish across volatility states (Moreira & Muir 2017), so `E[y_i] ← SR_i · σ̂_{i,t}`. This scales premia with forecast volatility instead of letting them be invariant.

**M7 — Claude.** Section 8. It produces the same quantities (quantiles per bucket, event and regime probabilities) and is scored by the same metrics.

### 6.3 Turning outputs into a predictive distribution

Each model *m* produces `μ_{i,t}^m` and a predictive variance `v_{i,t}^m`. Quantile outputs (M7) are converted with a skew-normal fit to the 10/50/90% quantiles. Event probabilities are **recalibrated** with isotonic regression (or Platt scaling below 50 events) fitted on the expanding window of past forecast–outcome pairs. Calibration models are refitted only on outcomes realised before *t*.

### 6.4 Combination and Black–Litterman posterior

1. **Model weights per bucket:** `ω_{m,t} ∝ exp(η · Σ_{s ≤ t−12} log score_{m,s})`. These are discounted (half-life 10 years) and **shrunk 50% towards equal weights** (the forecast-combination puzzle: Claeskens et al. 2016). The Claude weight is capped (default 25%) and is zero until it has 24 post-cutoff scored months (section 8.3).
2. **Combined view:** `q_t = Σ_m ω_{m,t} μ_t^m` (one absolute view per bucket, P = I).
3. **View uncertainty from measured skill:** `Ω_t = diag(MSFE_{i,t}^{comb})`, the out-of-sample mean squared forecast error of the combined forecast over the past (purged). If the combination's out-of-sample R² for bucket *i* is ≤ 0, Ω_ii → ∞ and the view is dropped.
4. **Posterior** (He & Litterman form):
   `μ_t^BL = [(τΣ)⁻¹ + Ω⁻¹]⁻¹ [(τΣ)⁻¹ π_t + Ω⁻¹ q_t]`, with τ = 1/T_eff.
   `Σ_t^BL = Σ_t + [(τΣ)⁻¹ + Ω⁻¹]⁻¹`.

This is the mechanism that makes "earned deviation" quantitative. A view moves the allocation only in proportion to its demonstrated out-of-sample precision relative to the equilibrium.

### 6.5 Strategic allocation optimiser

```
maximise    μ_BLᵀ w − (λ/2) wᵀ Σ_BL w − κ · Σ_i c_i |w_i − w̃_{t}|
subject to  Σ w = 1,  w ≥ 0,  w_i ≤ cap_i
            |1_eqᵀ(w − w_b)| ≤ 0.15
            (w − w_b)ᵀ Σ_BL (w − w_b) ≤ 0.03²
            w_cash ≤ 0.20
```

- w̃_t is the previous allocation drifted by realised returns; c_i is the round-trip cost of bucket *i*. κ = 1 means costs are charged once.
- The problem is convex (QP with one second-order cone constraint). It is solved with `cvxpy` and the `CLARABEL` solver (a new locked dependency), with an infeasibility fallback to the neutral policy that is logged.
- **Robustness:** the optimiser is run on 200 posterior draws of μ (resampled efficiency, Michaud) and the average weight is reported, together with the 10–90% weight range per bucket. This range is shown in the UI as the recommendation's uncertainty.
- **Partial adjustment:** the published target is `w_t = w̃_t + ρ (w*_t − w̃_t)`, where ρ (default 0.5) is selected on the development period only. This prevents month-to-month whipsaw.
- **One posterior, many portfolios:** μ_BL and Σ_BL are computed once per month, independent of any investor. The optimiser then runs once per reference rung (R1–R5) and, if defined, once for the owner policy. Each run uses that portfolio's w_b, λ and caps. The general recommendations and the personal one can never disagree about the market view; they differ only in risk level and starting point.

### 6.6 Rebalance / defer alert rules

**General signals (layer 1, no portfolio needed)** are published every month:
- *Outlook changes:* a bucket's posterior tilt changes sign or crosses its ±1 s.e. band. Example: "EUR long duration moved from neutral to overweight."
- *Rebalancing climate:* "rebalancing toward targets is normally fine" vs "stress regime: rebalance gradually or with new contributions; avoid forced selling" (F04 intent). This comes from the stress percentile and the calibrated drawdown model, and is shown only if the model passed its gate.
- *Model-portfolio changes:* when any rung's target weights move by more than its band, the rung is flagged as changed.

**Personal alerts (layer 3, optional)** apply the following table to the owner's recorded holdings (`portfolio_holdings.json`). Without holdings, they apply to a hypothetical investor tracking a chosen rung, so the backtest still covers them:

| Alert | Rule | Basis |
|---|---|---|
| **Rebalance now** | A bucket is outside its band: `|w_i − w_i^target| > max(5 pp absolute, 25% relative)`, **and** the certainty-equivalent gain of moving to target exceeds the transaction and tax cost. | 5/25 band rule; no-trade-region theory (Leland 1999; Donohue & Yip 2003) |
| **Defer** | In band, or the CE gain is less than the cost, or the recommended target moved by less than its own 10–90% uncertainty range. | Avoids trading on noise |
| **Defer de-risking sales** | `P(DD_eq > 15%)` is high **but** the calibrated drawdown model failed its gate, or the drawdown has already happened (stress percentile > 90 and 12-1 momentum negative). Prevents forced selling at stress peaks (F04 intent). | F04, P05 sequence-risk evidence |
| **Use contributions** | Move toward target by routing new contributions to underweight buckets before selling anything. This is always proposed first, because it is tax-free for an accumulating Portuguese investor. | Cost/tax minimisation |
| **Policy review** | The neutral policy itself falls outside the posterior 90% range for two consecutive quarters. Prompts the owner to review the policy; nothing is changed automatically. | |

The value of each alert rule is itself backtested against calendar (annual) rebalancing, reusing P05's rebalancing machinery.

---

## 7. Actionable output: three layers

The investor sees three layers, in this order. Layers 1 and 2 are general and identical for every user of the installation. They use no holdings and no personal input. Layer 3 is optional personalisation built on the same forecasts.

### 7.1 Layer 1 — Market outlook (general, portfolio-independent)

A monthly, dated table of **relative views per asset class and per key decision**, expressed against the market anchor rather than against anyone's portfolio:

| Decision axis | View (example layout) | Strength | Validation | Drivers |
|---|---|---|---|---|
| Equities vs bonds | Neutral / overweight / underweight | posterior tilt in s.e. units | validated / research view / no edge | M2 ECY, M5 recession probability |
| Regions: US vs Europe vs Japan vs EM | Ranking with 12m expected-excess-return ranges | | | Regional E/P, B/M, trend |
| Duration: short vs intermediate vs long EUR | | | | Curve slope, roll-down, CP factor |
| Inflation protection: linkers vs nominals | | | | Breakevens vs SPF expectations |
| Credit: IG / HY vs government | | | | Spread minus expected loss, EBP |
| Currency: hedge foreign bonds / equities? | | | | Carry, P07 |
| Diversifiers: gold, commodities, REITs | | | | Real yields, trend |
| Factors: value, momentum, quality, size, min-vol | | | | Factor spreads and trend |
| **Where to put new money now** | The 3 buckets with the highest posterior expected excess return per unit of marginal risk to the market anchor (`μ_BL,i / (Σ_BL w_mkt)_i`), within caps | | | |

Each row also shows the 12-month expected excess-return range (10/50/90%) and the probability that the view is wrong (`P(sign reversed)` from the posterior). For example: "EUR long duration: overweight, moderate, validated on holdout, 12m excess return median +2.1%, 10–90% range −6% to +9%". Views without validated skill are shown as **neutral**, with the unvalidated model view behind a fold.

"Where to put new money" is the general answer to "I have €X to invest this month". It is valid for any investor whose portfolio is close to market weights. Layer 3 gives the personalised version.

### 7.2 Layer 2 — Model portfolios (general)

The optimiser output for each reference rung R1–R5 (section 3):

| Bucket | R1 | R2 | R3 | R4 | R5 | Change vs last month | Example UCITS ETF |
|---|---|---|---|---|---|---|---|
| EQ_US | … | … | … | … | … | ▲/▼ pp | IE00B5BMR087 |
| … | | | | | | | |

For each rung the layer shows: reference weights, recommended weights, the 10–90% weight range, expected 12-month median and 10% quantile of excess return, `P(DD > 15%)`, tracking error and expected turnover. A **"simple version"** collapses buckets into 3–5 funds (for example world equity, EUR government, gold) for investors who want fewer positions. The simplified mix is solved with the same optimiser under the additional constraint, not by rounding.

Instrument mapping is data: each bucket lists alternative UCITS, US-listed ETFs and index funds. The recommendation is about the bucket, and the fund is a selectable implementation. ISINs are examples, not endorsements.

### 7.3 Layer 3 — Personal (optional)

Shown only when the owner has defined a policy and/or recorded holdings:
- The owner policy's recommended weights (the same posterior, the owner's own reference).
- A **gap analysis** of actual holdings (from `portfolio_holdings.json`) vs the chosen target: drift, alerts from section 6.6, and a trade list (contributions first, then sales and purchases in whole ETF shares, with cost and estimated tax). The application executes nothing.
- "Where to put this month's contribution" for the owner's actual holdings.

The numbers in any layout examples are illustrative, not forecasts.

### 7.4 Common elements

- **Claude memo:** half a page on the general outlook (layers 1–2), following the charter's interpretation standard (*measurement → pattern → historical context → limits*). If layer 3 is active, it adds an optional personal paragraph. Every number is checked against the result bundle (section 8.5).
- **Exports:** CSV/JSON of views, model portfolios, forecasts and (if present) personal trades; the existing AI export.
- **Backtest workspace:** results **per rung** and for the owner policy. Cumulative and drawdown charts vs all baselines; rolling 36-month active return; deviation-history heatmap (bucket × month); model-weight history; calibration/reliability plots; forecast scorecard (out-of-sample R², CRPS, Brier per model); a separate hit-rate table for the layer-1 relative views (for example, did "equities over bonds" pay off over the next 12 months?). Toggles for tier (E/R), costs, tax, rebalancing rule, Claude on/off, and development vs holdout. The holdout view states how many trials have been evaluated against it.
- **Forward-test scorecard:** the append-only `forecast_log` (views and all rungs) scored as outcomes arrive. This is the most honest evidence, and is displayed prominently.

---

## 8. Claude as an ensemble member

### 8.1 The look-ahead problem, stated plainly

A language model's training data contains the history being backtested. For any month before the model's training cutoff, Claude may "know" what happened next, so **pre-cutoff skill is not evidence**. The design therefore has three zones per model version:

| Zone | Months | Use |
|---|---|---|
| Contaminated | before the training cutoff (recorded per model ID in `definitions/llm_models.json` from Anthropic's published model documentation) | Diagnostics only (format reliability, calibration shape, memorisation probes). **Never** used for ensemble weights or performance claims. |
| Post-cutoff historical | cutoff → today | Genuine out-of-sample test. Replayed once per model version via the Batch API. |
| Live forward | from deployment | Logged before outcomes exist; strongest evidence. |

**Memorisation probe:** in the contaminated zone, a sample of prompts is sent with dates and country names masked ("Economy A, month 412"). Claude is then asked to identify the period. If identification accuracy is high, masking is shown to be ineffective. The result is recorded, and contaminated-zone results stay excluded either way.

When the configured model changes, the new model starts again at weight zero with its own cutoff. Scored history is kept per model ID.

### 8.2 Input pack (strictly point-in-time)

Built by `allocation/llm_pack.py` from `pit.snapshot(t)` only:
1. **Stable prefix** (cached): role and method instructions, bucket definitions, output schema, the charter's interpretation rules, and descriptions of each feature. It contains no dates and no volatile content, so prompt caching works.
2. **As-of block:** feature table (latest value, 1/3/12-month change, own-history percentile) for every predictor; quant model outputs M1–M6 and the regime probabilities; the bucket trailing-return and volatility table.
3. **Dated text:** central-bank statements published ≤ *t*, truncated to the last 3 meetings per bank.
4. **No tools.** Web search/fetch is disabled in all forecasting calls, because live search would leak the future into a historical replay and make live calls non-reproducible.

Privacy and generality: forecasting calls contain **no portfolio information at all**. Only macro and market data leave the server, so Claude's views are the same general views as layer 1. Only the optional personal memo paragraph receives bucket weights (never euro amounts).

### 8.3 Call design

- **SDK:** official `anthropic` Python SDK. Key from the `ANTHROPIC_API_KEY` environment variable in `.env` (never committed, never included in diagnostics ZIPs or backups). Outbound host `api.anthropic.com` is registered in the source-policy registry with its own budget.
- **Structured output:** `output_config.format` with a strict JSON schema:
  ```json
  { "as_of": "YYYY-MM-DD",
    "buckets": [ { "id": "EQ_US", "q10": -0.21, "q50": 0.03, "q90": 0.19,
                   "confidence": "low|medium|high",
                   "drivers": ["feature_id", "..."] } ],
    "events": { "dd_eq_15": 0.0, "rec_ea_12m": 0.0, "rec_us_12m": 0.0, "eq_lt_bond": 0.0 },
    "regimes": { "expansion": 0.0, "slowdown": 0.0, "contraction": 0.0, "recovery": 0.0 },
    "disagreements_with_quant": [ { "bucket": "...", "reason": "..." } ],
    "data_concerns": ["..."] }
  ```
  Validation rejects quantiles out of order, probabilities that do not sum correctly, unknown bucket or feature IDs, and any `drivers` not present in the pack.
- **Thinking and effort:** adaptive thinking; `output_config.effort` is a setting (default `high` for live runs).
- **Self-consistency:** K samples per month (default 5). The per-field median is taken, and the spread across samples is added to the predictive variance.
- **Refusals and failures:** check `stop_reason`; enable server-side `fallbacks` where the chosen model supports it. A refusal, schema failure or spend-cap stop produces a *missing* forecast for that month. It is never imputed, and the ensemble renormalises without it.
- **Reproducibility:** every request and response is stored in an append-only `llm_forecast` table: model ID, served model, prompt hash, pack hash, PIT snapshot hash, sample index, usage tokens, cost, stop reason and parsed JSON. Exact regeneration is not possible (outputs are stochastic), so stored outputs are the record of truth.

### 8.4 Model and budget settings (decision 6: configurable)

| Setting | Default | Notes |
|---|---|---|
| `llm.enabled` | false until a key is present | The module is fully functional without it |
| `llm.model_live` | `claude-opus-5-5` | Monthly forward forecasts and memo |
| `llm.model_replay` | `claude-sonnet-5-5` via Message Batches (50% price) | Post-cutoff historical replay |
| `llm.effort` | `high` | |
| `llm.samples` | 5 | |
| `llm.monthly_cap_eur` | 10 | Hard stop. Cost is estimated with `count_tokens` before each run and accrued from `usage` afterwards. |
| `llm.replay_contaminated` | false | Diagnostic replays of pre-cutoff months are opt-in because they cost money and cannot earn weight |

Indicative cost at current list prices, with a ~30k-token cached prefix and pack and ~3k output tokens per sample: a live month at 5 samples on Opus 5.5 costs well under €1. A post-cutoff replay of 12–24 months via Batch on Sonnet 5.5 costs a few euros. Model IDs and prices are read from configuration, not hard-coded in logic.

### 8.5 Claude as explainer

After the quantitative pipeline finishes, one call turns the final result bundle into the monthly memo. Guardrails:
- The input is only the result bundle and its limitations.
- A post-check extracts every number and percentage from the memo and requires it to match a bundle value within rounding. Any mismatch blocks the memo, and the plain bundle summary is shown instead.
- Banned claim patterns from the charter (causal claims from coincident lines, "crash probability" without a validated model) are checked with a lint list.
- The memo is labelled as model-generated.

---

## 9. Statistical and practical limitations (shown in the UI)

- 12-month return predictability is weak. Out-of-sample R² of 1–5% is typical even for successful predictors. Most months should produce small deviations, and the system is designed for that.
- Category D proxies (factor long-only, REITs, commodities) differ from investable ETFs. Their deviations are shown with tracking-error bands, and their caps are lower.
- Regional equity history before 1990 is US-only. Regional tilts are therefore evaluated on 1990+ data, which contains few independent 12-month windows (≈35 non-overlapping). Confidence intervals will be wide and are shown.
- The Tier E span is limited by vintage availability (ALFRED from the 1990s for many series). The Tier E/R gap is reported.
- Claude's evidence accrues slowly: two years of post-cutoff months is the minimum before any weight.
- Tax rules are simplified, and the owner must verify them for their situation.

---

## 10. Implementation architecture

Everything fits the existing single-container, single-SQLite design. No new services.

```
src/finance_dashboard/allocation/
    pit.py            # point-in-time store, as_of(), lag model, leakage guard
    buckets.py        # bucket recipes → monthly EUR total/excess returns
    features.py       # predictor transforms (changes, percentiles, ECY, CP factor)
    models/
        equilibrium.py    # M1
        building_blocks.py# M2
        predictive.py     # M3 (univariate + combination)
        trend.py          # M4
        regime.py         # M5 (probit, regime classifier, Markov switching)
        risk.py           # Σ: EWMA, Ledoit–Wolf, HAR, regime mixing
        llm.py            # M7 (pack, call, validate, aggregate)
    calibrate.py      # isotonic/Platt, PIT, reliability
    combine.py        # log-score weights, BL posterior
    optimise.py       # cvxpy QP/SOCP, resampling, partial adjustment
    alerts.py         # rebalance/defer rules
    backtest.py       # walk-forward loop, purging, costs, tax, tiers
    metrics.py        # OOS R², Clark–West, CRPS, Brier, DSR, bootstrap, SPA
    preregistration.py# spec hashing, trial log, holdout lock
    llm_client.py     # Anthropic SDK wrapper: caching, batches, budget, logging
```

- **Engine integration:** four new `AnalysisDefinition`s in `engine/analyses.py`, gated by `research_acceptance`, so that bundles, exports, limitations and saved views behave as for the other questions:
  - **A01** Market outlook: general asset-class views and "where to put new money" (layer 1)
  - **A02** Model portfolios R1–R5 and simple versions (layer 2)
  - **A03** Backtest results (per rung, tier and variant)
  - **A04** Forecast scorecard, view hit rates and calibration
  - **A05** Personal allocation, gap analysis and alerts (layer 3; returns an explicit "not configured" state without owner policy or holdings)

  They are added to `definitions/question_followups.json` and the catalogue under a new domain **A — Allocation** with decision-layer text.
- **Definitions:** `allocation_buckets.json`, `allocation_instruments.json`, `allocation_policy.json` (neutral weights, caps, λ, TE), `allocation_predictors.json` (bucket → registered predictors), `publication_lags.json`, `allocation_preregistration.json`, `llm_models.json`.
- **Migrations (Alembic):** `pit_observation`, `bucket_return`, `model_forecast` (all models, including Claude-aggregated), `llm_forecast` (raw calls), `backtest_run` (spec hash, tier, metrics JSON), `backtest_trial_log`, `forecast_log` (live, append-only, insert-only trigger).
- **Jobs:** a monthly job (posterior once, then the outlook, all rungs and the optional personal run) in `worker.py`/`standalone.py`, running on the 3rd business day after month-end following the scheduled refresh. Backtests run as maintenance background jobs (they are expensive) with status in the existing lightweight status API pattern.
- **API:** `GET /api/allocation/outlook`, `GET /api/allocation/model-portfolios`, `GET /api/allocation/personal`, `GET /api/allocation/backtests`, `POST /api/allocation/backtests` (start a registered variant; requires the action marker), `GET /api/allocation/scorecard`, `GET /api/allocation/forecast-log`, `PUT /api/allocation/policy`.
- **Frontend:** `MarketOutlook.tsx` (layer 1), `ModelPortfolios.tsx` (layer 2), `PersonalAllocation.tsx` (layer 3, folded unless configured), `BacktestWorkspace.tsx`, `ForecastScorecard.tsx`, using existing ECharts helpers and the visualization contract.
- **Backups:** policy, preregistration, `forecast_log` and `llm_forecast` are included in version-2 recovery bundles; the API key is excluded.
- **Dependencies (frozen via uv):** `anthropic`, `cvxpy` + `clarabel`, `statsmodels` (HAC, Markov switching, probit), `scikit-learn` (isotonic only; optional, can be hand-rolled). `numpy` is already present.

---

## 11. Delivery phases and gates

Each phase is an end-to-end slice with tests and passing CI. Production claims follow AGENTS.md: deploy, collect, then verify with a post-deployment diagnostic ZIP.

| Phase | Deliverable | Gate |
|---|---|---|
| **B0** | Charter amendment approved; this design reviewed; risk ladder, market anchor and cost assumptions confirmed by owner | Owner sign-off recorded in charter revision log |
| **B1** | New sources (French regions/UMD, AQR, Bundesbank curve, ECB curves/€STR, EBP, ESI, SPF, Nareit, Cboe VIX, CB statements) via the managed collector, with originals and reconciliation | Source fixtures and reconciliation tests; registered in `series.json`; production export shows them `available` |
| **B2** | `pit` store, lag table, `as_of()` and leakage guard; bucket return construction | Leakage tests (a value with `known_from > t` is never visible; a hand-built vintage fixture reproduces the ALFRED first-release value). Bucket returns reconcile to independent fixtures (par-bond arithmetic, FX conversion, hedge carry). |
| **B3** | Backtest harness with baselines only; metrics library | Neutral/60-40/risk-parity results reproduce hand-calculated fixtures and P05's rebalancing numbers on a shared period. Metric unit tests against published examples (Clark–West, DSR, Brier). |
| **B4** | Quant models M1–M6, calibration, combination, BL, optimiser, alerts; development-period results | Optimiser property tests (constraints always hold; infeasible inputs fall back to neutral). Development-period report. Pre-registration frozen and hashed. |
| **B5** | One-time holdout evaluation (Tiers E and R) and acceptance gate | Holdout report committed under `docs/`, including the trial count; gate result decides "validated" vs "research view" |
| **B6** | Claude member: pack builder, client with budget, schema validation, batch replay of post-cutoff months, memorisation probe, live forward log, explainer with number check | Offline tests with recorded responses (no network in CI). Budget-cap test. A schema-failure response becomes missing. A memo number mismatch blocks the memo. |
| **B7** | UI panels, exports, backups, documentation (README, ARCHITECTURE, RUNNING, handoff) | Frontend and browser tests; light/dark and mobile review |
| **B8** | Deployment and first live month | Post-deployment ZIP shows A01–A05 bundles, the `forecast_log` entry and the LLM spend ledger |

Testing principles: CI never calls the Anthropic API; responses are recorded fixtures. Every model gets a deterministic fixture test. Every backtest result bundle stores the spec hash, data snapshot hash and code commit.

---

## 12. Open points for the owner (to settle in B0)

1. Confirm the general reference ladder (section 3): five rungs at 20/40/60/80/100% growth assets, anchored on the global market portfolio. Separately, and optionally, define your own policy for the personal layer.
2. Your broker fee schedule and whether "after-tax" mode should be the default view.
3. Which example funds to list per bucket in the general layer (UCITS, and optionally US-listed and index-fund alternatives), and which ones you use personally.
4. Whether the €10/month Claude cap and the default models suit you.
5. Approval of the charter amendment text in section 1.

## 13. Primary references

Black & Litterman (1992); He & Litterman (1999); Campbell & Shiller (1998, 2001); Campbell & Thompson (2008); Goyal & Welch (2008); Rapach, Strauss & Zhou (2010); Clark & West (2007); Cochrane & Piazzesi (2005); Fama & Bliss (1987); Estrella & Mishkin (1998); Gilchrist & Zakrajšek (2012); Hamilton (1989); Ang & Bekaert (2002); Moskowitz, Ooi & Pedersen (2012); Hurst, Ooi & Pedersen (2017); Moreira & Muir (2017); Ledoit & Wolf (2004); Corsi (2009); Michaud (1998); Leland (1999); Donohue & Yip (2003); Bailey & López de Prado (2014); López de Prado (2018); Politis & Romano (1994); Hansen (2005); Hodrick (1992); Newey & West (1987); Claeskens, Magnus, Vasnev & Wang (2016); Gneiting & Raftery (2007, proper scoring rules); Erb & Harvey (2013); Asness (2003); Fama & French (1993, 2015).
