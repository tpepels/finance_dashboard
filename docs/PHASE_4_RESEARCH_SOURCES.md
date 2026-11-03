# Phase 4 research data: actual historical releases, fund holdings and surplus accounts


> **Technical reference, not a separate development roadmap.** The sole current implementation path and phase acceptance are in [Development plan](DEVELOPMENT_PLAN.md). Historical phase files have been archived.

**Operator requirement:** Historical ALFRED and SEC N-PORT imports must be initiated, monitored and resumed from **Data & sync** in the local dashboard. Commands below are developer diagnostics and reproducibility references, not the operating workflow. See [Development plan](DEVELOPMENT_PLAN.md).

**Status:** Independently confirmed SEC identities for VT and BND are bundled with their official N-PORT filing-index references. The FRED API-key/basic endpoint preflight succeeded on the target server on 2026-11-03; the preceding 180-request historical backfill downloaded zero new snapshots. The initial SEC collector attempted zero XML downloads because its strict submissions-primary filename filter excluded eligible SEC index-based filings. These importers now have corrected discovery/diagnostics but successful local SEC holdings collection, ALFRED backfill, OECD account extraction and independently validated predictive results are not yet confirmed. Dataset-dependent results must remain unavailable until collection and auditing.

The application remains **one** Docker service and stores data in its existing /data bind volume. All downloads run in a CLI or the one in-process background refresh; browsers never request arbitrary external URLs or send the FRED/SEC credentials.

## 1. Actual source-publication vintages: ALFRED

Official source contract:
- https://fred.stlouisfed.org/docs/api/fred/series_observations.html
- https://fred.stlouisfed.org/docs/api/fred/realtime_period.html
- https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html

`src/finance_dashboard/vintage.py` requests `realtime_start=realtime_end=ASOF_DATE` for three pre-registered US macro series: `T10Y3M` (US Treasury 10-year minus 3-month, daily), `SAHMREALTIME` (monthly Sahm Rule calculation), and `USREC` (monthly retrospectively dated NBER recession indicator). It rejects observations issued after that as-of date, persists each true source-vintage identity under `/data/vintages/{series}/{YYYY-MM-DD}.json`, and makes the data available read-only through `/api/vintages` and `/api/vintages/{series}?asof=YYYY-MM-DD`.

To build 2000–2004 historical vintages (the **180-request limit** means splitting longer windows into non-overlapping five-year blocks):

```bash
# Set FRED_API_KEY in the existing service's .env, then build/recreate once.
docker compose exec finance-dashboard python -m finance_dashboard.vintage \
  --series T10Y3M --series SAHMREALTIME --series USREC \
  --start 2000-01-01 --end 2004-12-31

# Continue 2005–2009, 2010–2014, 2015–2019, 2020–2024 as desired.
# Or backfill the entire historical interval in resumable 180-request batches.
# Re-run this identical command until missing_after_run is zero.
docker compose exec finance-dashboard python -m finance_dashboard.vintage \
  --backfill --max-requests 180 \
  --series T10Y3M --series SAHMREALTIME --series USREC \
  --start 2000-01-01 --end 2026-10-31
```

Each run reuses cached observations and reports failures without leaking request URLs containing API keys. Daily in-process refresh captures the **last completed calendar month's as-of** snapshots automatically when `FINANCE_VINTAGE_REFRESH=1` and `FRED_API_KEY` is set; if no key exists it safely skips. This is not a backfill.

**The source's observation period, ALFRED information-availability date, and the dashboard's original collection timestamp are three different dates.** No latest-revised series may be called a publication-vintage backtest.

## 2. SEC N-PORT ETF historical holdings

Primary sources:
- https://www.sec.gov/data-research/sec-markets-data/form-n-port-data-sets
- https://www.sec.gov/about/webmaster-frequently-asked-questions

Original SEC N-PORT public filings provide fund series identity, reported portfolio date, individual holdings, reported USD value/percentage of net assets and issuer country. Public aggregated N-PORT datasets go back to **October 2019**. They **do not** provide country exposure from issuer revenues/operations or daily ETF holdings. Some securities can be undisclosed or aggregated, and fund-of-funds needs independent look-through.

`src/finance_dashboard/sec_holdings.py` verifies:
- The registered instrument is a US-domiciled ETF (it **rejects** Irish UCITS such as VWCE);
- Exact registrant CIK, official SEC filing accession and independently supplied SEC series ID;
- An original `www.sec.gov/Archives/edgar/data/...` XML file and its SHA256;
- SEC submission form `NPORT-P` or amendment, the reported holdings reference period and percentage-of-NAV coverage;
- Short positions, derivatives, unknown issuer countries, and incomplete coverage are **not** silently normalized to 100% exposure;
- Later filed amendments only become selectable as of their own eligibility dates.

**Important SEC timing limitation:** the SEC says actual public dissemination may lag acceptance and does not publish a guaranteed visibility timestamp. `acceptanceDateTime` in historical submissions JSON may also contain inconsistent timezone formatting. Instead of falsely claiming an exact public timestamp, this importer uses **official filingDate + two calendar days** as a conservative **research-eligibility convention**; it is not verified actual dissemination time or a guarantee. The interface labels this uncertainty.

Two US-ETF share classes are independently mapped to their original registered fund series in the default collector:

- **VT**: CIK `0000857489`, fund series `S000022482`; [SEC NPORT-P filed 2026-09-28](https://www.sec.gov/Archives/edgar/data/857489/000085748926000275/0000857489-26-000275-index.htm).
- **BND**: CIK `0000794105`, fund series `S000002564`; [SEC NPORT-P filed 2025-08-27](https://www.sec.gov/Archives/edgar/data/794105/000079410525000080/0000794105-25-000080-index.htm).

For these two verified funds, no configuration file is needed. They do **not** have holdings values until SEC collection succeeds. Other US-registered ETFs require independently identified registrant and series IDs; Irish UCITS cannot use this importer. To explicitly override the built-in mappings, create `/data/holdings/sec_funds.json` containing your complete desired list, for example:

```json
[
  {"instrument_id":"vt", "cik":"YOUR_VERIFIED_SEC_REGISTRANT_CIK", "series_id":"YOUR_VERIFIED_S#########"}
]
```

These are **placeholders**, not published mappings. Do not paste them as functional values. Use `SEC_USER_AGENT` with a **real organization/contact email**, as SEC requires declared bot identification; do not use invented contact details.

The SEC submissions JSON may identify an **HTML** `primaryDocument` even when the official filing index contains the original `primary_doc.xml`. The collector now scans each official filing index, checks its disclosed SEC series ID where available, and accepts only an explicitly linked, syntactically safe XML filename. Original XML is independently checked against CIK, accession, fund series, period and holdings fields before storage. A verified locally cached accession is reused without re-downloading its large XML. Index scanning is capped at `max(120, --limit × 50)` candidate filings per registrant (bounded by the actual SEC submission history), with up to `max(12, --limit × 3)` XML downloads. The requested limit counts **matching original fund-series filings**, not unrelated registrant filings; a short collection reports `partial`, not `complete`.

Perform the two-index preflight first; this makes no holdings downloads:

```bash
docker compose exec finance-dashboard python -m finance_dashboard.sec_holdings_sync --check
```

Then collect up to 12 **matching fund-series** filings per configured fund:

```bash
docker compose exec finance-dashboard python -m finance_dashboard.sec_holdings_sync --limit 12
```

To collect later updates automatically (roughly monthly), set `FINANCE_SEC_HOLDINGS_REFRESH=1` in the **same** Compose service and supply `SEC_USER_AGENT`. It will not run without a verified built-in or user-supplied mapping and real SEC contact. Periodic updates avoid repeated downloads for 28 days after a completed collection. Historical full backfill depends on SEC archive coverage and matching fund IDs; annual/per-fund coverage is not assumed.

The API is `GET /api/holdings/vt?asof=2024-12-31`. The dashboard shows the original holdings period, conservative eligibility date, issuer-country weights and residual/unclassified percentages. It is **not** a verified revenue-by-country portfolio exposure.

**Irish UCITS** (VWCE, VWRL, EUNL, etc.) require reproducible historical issuer positions/allocation documents and a separate authenticated importer; SEC N-PORT simply does not cover them.

## 3. OECD IOT surplus, labour and capital-stock sensitivity

Primary sources:
- https://www.oecd.org/en/data/datasets/input-output-tables.html (harmonised national industry IOT **2025**, 1995–2022; download the **value-added components** package)
- https://www.oecd.org/en/data/datasets/inter-country-input-output-tables.html (separate ICIO international production flows; not interchangeable with national IOT surplus components)
- https://data-explorer.oecd.org/ (Annual value added by economic activity, Table 6, additional national-accounts cross-check)

`src/finance_dashboard/marx_accounts.py` has a strict, **operator-normalized** CSV ingestion contract. It validates: country/year/ISIC industry, identical current-currency units, source release and URL, unique industry rows, finite compensation/CFC/net surplus and optional independently documented self-employed compensation and net capital stock. The accepted columns are:

```text
country,year,isic_section,employee_compensation,consumption_fixed_capital,net_operating_surplus,imputed_selfemployed_compensation,net_fixed_capital_stock,gross_value_added,net_taxes_on_production,unit,currency,source_release,original_table,source_url,imputation_method,capital_stock_source
```

The `gross_value_added` and `net_taxes_on_production` columns are optional but must both be present for an accounting-identity cross-check. When supplied, gross value added must reconcile to employee compensation + depreciation + net operating surplus + net taxes within a declared rounding tolerance (larger of 0.01 source units or 0.0001% of GVA). The dashboard explicitly states whether every included industry passed this arithmetic check. This test catches mapping mistakes but **does not independently authenticate the source archive**.

Normalizing the OECD bulk file into this schema requires a transparent, audited mapping against the publisher's documentation. **The code does not automatically validate every row against the original OECD ZIP. A locally supplied CSV carrying the OECD URL is not independently certified OECD data.** Reproducible source-archive hashes and a formal mapping audit are required before calling a real-world result research-grade.

The resulting accounting views distinguish three **explicit assumptions**: `all_industries`, `market_broad` and `market_narrow`, using published ISIC letters and clearly disclosed sector inclusion. Self-employment adjustments can only be calculated if every selected sector has a separately documented imputation. Without matched **net fixed capital stock**, no profit-rate ratio is provided.

Compute, only with recorded inputs:

- Net surplus relative to employee compensation = net operating surplus / total employee compensation.
- Assumption-adjusted surplus/variable-capital analogue = (net surplus − explicitly documented self-employment imputation) / (employee compensation + imputation).
- Net operating surplus relative to net capital stock, *only when every included sector has a verified same-unit stock observation*.

These are **national-account sensitivity exercises**, not a direct observation of Marx's `s/v` or `s/(c+v)`. Productive/unproductive labour, cross-border surplus transfers, self-employment, price basis, capital turnover and land/financial assets remain theoretical/measurement choices. Sector choices can materially change the results. Differences must not be interpreted as historical proof of exploitation without further source and theoretical validation.

An audited normalized CSV may be imported after its SHA-256 is independently recorded:

```bash
sha256sum /data/your_oecd_2025_normalized.csv
docker compose exec finance-dashboard python -m finance_dashboard.marx_accounts \
  --csv /data/your_oecd_2025_normalized.csv --sha256 ACTUAL_OUTPUT_SHA256
```

Replace filenames and hashes with the **actual on-server volume paths**. The importer never invents missing industries or capital stocks and won't silently overwrite a changed extract. API `/api/marx` reports source availability; `/api/marx/US/2020?scenario=market_narrow` reports source-derived accounting quantities only after ingestion.

## 4. Explicitly evaluated predictive model, not a fabricated live forecast

`src/finance_dashboard/vintage_backtest.py` is a deterministic, pure-Python, expanding-window **L2-regularized logistic** research model using only the two verified ALFRED as-of features (Treasury 10y–3m and Sahm Rule). The source target is USREC's later **NBER retrospectively dated** recession indicator.

Pre-specified evaluation horizons are 6 and 12 months. At month-end origin `t`:
1. Features are taken from the actual **ALFRED as-of-t** snapshot, within source-specific age tolerances.
2. Training features are from **earlier origins** only. A training outcome is eligible only if the necessary USREC future months **were already reported in the ALFRED USREC snapshot at t**; otherwise it is excluded, even if today's data show the outcome.
3. Standardization is calculated on training samples only. Fixed L2 coefficient penalty is 1. No random hyperparameter tuning on test results.
4. An evaluation outcome from the last dated USREC vintage is used only after the **entire future 6/12-month window is observed**. Right-censored predictions are excluded, never treated as safe/no recession.
5. At least **60** historical training cases with sufficient event diversity and a separate retrospective test of at least **24 predictions / 5 positive / 12 negative outcomes** are required before Brier, expanding historical-prevalence baseline, AUC and calibration bins are displayed.
6. Overlapping future windows violate test independence. The model now counts approximate event clusters and reports a deterministic, chronologically chosen, nonoverlapping subsample's Brier/AUC **only if the regular sample-size and outcome-diversity gates pass**. Those diagnostics reduce one source of dependence but are not independent recession episodes. Retrospective NBER event dating means **even a successful historical evaluation is not independently validated live forecast calibration**. The model does not claim a statistically significant crisis probability, economic causation or universality.

The API is `GET /api/vintage/backtest?horizon_months=12` and the dashboard includes its status, source dates, sample counts and documented metrics. If the source cache cannot meet test requirements, it displays **insufficient_vintages** or **insufficient_holdout_events**, with no fictitious probabilities.

## 5. Acceptance status

| Research obligation | Implemented | Still required for accepted real-world results |
|---|---|---|
| Genuine publication-vintage analysis | ALFRED source-specific collection/validation, read-only historic comparison, month-end capture | Fetch full historical ALFRED vintages locally and inspect actual release-by-release source parity |
| Dated ETF holdings | Source-identity-checked SEC N-PORT XML importer, bounded official collector, as-of eligible snapshot query | VT/BND source identities verified; collect original documents and audit as-of coverage, then verify remaining US ETF mappings; issuer country is not full look-through |
| Marxian surplus/profit accounting | OECD normalized-input engine; optional gross-value-added accounting reconciliation; explicit industry and self-employment scenarios; capital-stock gate | Real OECD 2025 source extraction and row-level mapping audit, STAN capital stock reconciliation and methodological research review |
| Validated predictive model | As-of training, true historical-label availability filter, deterministic walk-forward logistic model, Brier/AUC/calibration gates | Actual ALFRED backfill, enough independent event periods, uncertainty analysis, model comparison, out-of-time scientific replication and stability tests |

No GitHub Actions are used. Python modules have focused tests inside the Docker build. **Current production evidence (2026-11-03 18:14 UTC):** both browser data sync actions completed, all 80 registered sources have stored observations, the requested ALFRED historical month-end cache reports 0 missing within published vintage bounds, and VT/BND original SEC filing collectors completed with 28/29 matching filings. Original source-value audits, exact UCITS and worldwide holdings coverage, raw OECD IOT/STAN extracts, net industry capital stock and independently validated predictive models remain **OPEN**. The authoritative phase status and priorities are in [Development plan](DEVELOPMENT_PLAN.md), not this reference.
