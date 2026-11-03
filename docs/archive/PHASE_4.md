# Phase 4 — Economic risk diagnostics, investment-proxy evidence and local resilience
*Implementation dated 2026-11-02. This phase is **partially implemented**, not accepted complete.*

## Scope and implementation

The primary [economic research dashboard](ECONOMIC_RESEARCH_METHODS.md) still leads with 46 curated economic questions based on 53 canonical macro sources. Phase 4 adds a permanently accessible **Risk evidence and observed market outcomes** section, directly under the primary visible economic research graphs and before the original source explorer.

Phase 4 now has two independent analytical surfaces:

1. **Macro risk diagnostics:** `GET /api/risk` and `GET /api/risk/{world|us|europe|japan}`. Each rule has a documented provider, native unit/frequency, publisher-defined criterion (if one exists), exact source date, sample size, stale/no-data state and caveat.
2. **EUR/USD ETF, equity, gold and portfolio comparison:** `POST /api/market/compare` for 2–5 registered assets, 3–20-year ranges, EUR or USD reporting, optional weights totaling exactly 100%. It uses the 24 *already registered* market instruments and the three ECB FX currencies; no additional financial-data product is required. The full-source server configuration enables market ingestion; existing deployments with a literal `0` must explicitly enable it.

Existing `/api/market/query`, `/api/market/gold-world-proxy`, macro research APIs, Wisesheets and source charts are retained.

## Financial-risk evidence, no synthetic crisis score

| Canonical source | Criterion | Interpretation |
|---|---|---|
| FRED SAHMREALTIME | observed value at or above **0.50 percentage points** | The Sahm unemployment deterioration criterion associated with recession onset. Not a recession forecast. |
| FRED T10Y3M | daily US 10-year minus 3-month Treasury spread **below 0** | Inverted yield curve. Does not supply a recession probability or exact timing. |
| BIS US, euro-area, Japan credit-to-GDP gaps | observed gap **at or above +2 percentage points** | Basel III countercyclical-capital-buffer *reference guide* only. Supervisors use additional judgment and the national measures may differ. |
| US Shiller CAPE | empirical rank where ≥24 original monthly observations are available | Describes relative location in the latest-revised historical sample, not fair value or forecast return. |
| International BIS 43-economy weighted credit gap | descriptive level, **no trigger** | Researcher composite requiring separate coverage series; not an official world BIS gap. |

Sources:
- BIS credit gap data: https://data.bis.org/topics/CREDIT_GAPS
- Basel credit-gap decision framework: https://www.bis.org/committees/bcbs/basel-consolidated-guidelines/module/cad/20
- Sahm source/definition: https://fred.stlouisfed.org/series/SAHMREALTIME
- NY Fed term spread methods: https://www.newyorkfed.org/research/capital_markets/ycfaq.html
- Shiller original data: https://shillerdata.com/

No projected data, risk scores, invented thresholds, nationally mislabelled observations or portfolio guidance are produced. A stale diagnostic retains its last reading and date but **never claims an active threshold signal**. Historical ranks use the **latest ingested, potentially revised** observations and therefore are not valid real-time event-study evidence. The duration of a threshold signal is reported as **consecutive source observations**, not an invented count of elapsed trading/calendar days. Date gaps terminate streaks.

## Currency and monthly market return convention

Source: Yahoo unofficial daily chart feed, vetted registry (symbol, exchange MIC, trading currency), separately recorded splits/dividends, and ECB reference rates. The optional loader **does not** infer missing market prices, dividends or FX observations.

`GET /api/markets` lists supported instruments.

```json
POST /api/market/compare
{
  "instrument_ids": ["vt", "gld", "bnd"],
  "currency": "EUR",
  "start": "2021-01-01",
  "weights_pct": { "vt": 60, "gld": 20, "bnd": 20 }
}
```

- Native **Yahoo adjusted closes**, not independently audited issuer NAV or licensed benchmark index returns.
- EUR valuations use `adjusted_close_eur` already derived by dividing the quote-currency adjusted close by the ECB units-of-foreign-currency-per-EUR rate; a preceding published FX reference no older than 5 calendar days is permitted. Missing FX yields no EUR observation.
- USD mode is **restricted to USD-traded instruments** rather than silently converting EUR listings without actual EUR/USD source quotes. For mixed EUR+USD listings, select EUR mode.
- The market data shown are last **actual trading closes** in each calendar month. The chart's date coordinate represents the *month-end accounting period*, and each instrument retains the true last-trade date. Other exchanges may close on different dates in that same month.
- Comparisons use the most recent contiguous run of **shared calendar months**, requiring at least 2. Earlier disjoint runs are excluded and counted; neither prices nor FX are forward-filled across missing months.
- Each price index is 100 at the first shared month. Return at month *t* is the ratio of consecutive monthly adjusted-price levels minus 1.
- Drawdown at each month is `100 × (level / running_max_level − 1)`. The API returns the entire drawdown curve and maximum peak, trough and subsequent recovery, if observed.
- Annualized return is `100 × ((last/first)^(12 / number_monthly_returns) − 1)`. Annualized sample volatility is `100 × sqrt(12 × sample_variance(monthly_returns))`. Both are **omitted for fewer than 12 consecutive returns**.
- Pairwise correlations are Pearson correlations of 12 or more consecutive, matched monthly returns, not price-level correlations.
- Optional **fixed-weight monthly rebalanced scenario** calculates `R_port,t = sum_i(w_i × R_i,t)` using constant fixed weights and rebalances after each month. It is hypothetical, with **no** commissions, spreads, taxes, deposits, leverage, or historical constituent exposure claims.
- ETFs labelled “world” (VT, VWCE) represent investable share-class proxies; benchmark and domicile metadata are **not** the fund's date-specific regional holdings. The API reports `geographic_holdings_status: not_verified` and `holdings_country_weights: not_available_without_verified_holdings_history`.
- The original gold/VT 36-month USD/EUR ETF proxy correlation endpoint remains available. It is separate from the original spot gold vs genuine MSCI ACWI **index return** series, which has its own source methodology.

## Enable optional market evidence on your server

Keep only your **existing one** `finance-dashboard` service. To populate EUR asset analyses, set on that service:

```yaml
environment:
  FINANCE_INCLUDE_MARKETS: "1"
```

Then `docker compose up -d finance-dashboard`. The in-process daily refresh will attempt the existing 24 Yahoo instrument histories and three ECB FX histories. Yahoo is unofficial and can reject or rate-limit requests. Missing/failed instruments remain explicitly missing, with no substitute invented. The current complete-source Compose profile defaults to enabled; this does not guarantee the unofficial provider supplies every historical period.

The Phase 4 frontend offers selecting 2–5 instruments, EUR/USD, a 3/5/10/20 year maximum window, a monthly rebalanced hypothetical portfolio and normalized performance, drawdown and correlation graphs. The data browser and market registry endpoints are available regardless of whether collection is enabled.

## Observable one-container operations

`GET /api/operations` reports count of macro sources with recorded observations, market instruments with recorded prices, ECB currencies with observations, failed source-ingestion run count, last successful source run, optional collection settings and verified backup-manifest count. It **does not** expose API keys or raw provider error messages.

The same process's existing daily refresh loop now makes a consistent online SQLite database copy after source ingestion (enabled by default), with the current separately validated SEC filer snapshot and a source-evidence archive of ALFRED/SEC/OECD local files when present. Manifests record SHA-256 hashes and the SQLite integrity check result. By default **14** backup bundles are kept under `/data/backups`. Wisesheets collection retains its existing monthly quota-aware schedule.

### Manual backup and verification

```bash
docker compose exec finance-dashboard \
  python -m finance_dashboard.backup --output-dir /data/backups --keep 14

# Replace the wildcard with the exact generated file:
docker compose exec finance-dashboard \
  python -m finance_dashboard.backup \
  --verify-manifest /data/backups/finance-YYYYMMDDThhmmssffffffZ.json
```

The database is copied using **SQLite's online backup API**, safe with concurrent WAL activity. Never create an online backup using `cp finance.sqlite3` without handling its WAL. The verified database backup is then installed atomically. Independent SEC earnings snapshot copied via atomic source-file read is recorded separately. Dated ALFRED vintages, N-PORT holdings files and imported OECD national industry accounts are also archived separately and hashed; copy the whole bundle offsite.

**Disaster recovery:** copy backup bundles to a different physical disk or remote encrypted archive. Backup bundles stored only in `/data/backups` will be lost with the original volume. To restore: stop the finance container, verify the manifest and SHA-256/integrity, preserve the damaged original database in a separate location, restore the verified `.sqlite3` with correct UID/GID into the bind-mounted data directory, restore the verified SEC snapshot if present, then restart the service. Remove stale database WAL/shm files only *after the application is stopped* and when restoring an intact standalone backup file. Do not overwrite a live database.

SQLite official online backup contract: https://sqlite.org/backup.html

## Access / network control

The default service remains LAN-accessible and **has no user login**. Neither licence metadata nor model analysis restricts local use. Do not forward port 5052 directly to the internet.

If using an existing local Caddy proxy with authentication, configure `FINANCE_BIND_HOST=127.0.0.1` in the Compose environment, rebuild/recreate the finance service and proxy to `finance-dashboard:8080` from Caddy in the same Docker Compose network (or `127.0.0.1:5052` from a host-networked Caddy). Keep TLS and authentication in that existing proxy. Default `FINANCE_BIND_HOST=0.0.0.0` permits LAN access. This is an *optional* network control, not a new required container or a data-use gate.

## Verification and remaining Phase 4 scope

New focused local regression files:
- `tests/test_risk_diagnostics.py`
- `tests/test_portfolio_risk.py`
- `tests/test_phase4_api.py`
- `tests/test_backup.py`
- `frontend/src/Phase4Panel.test.tsx`

`Dockerfile` runs the focused Python and complete frontend Vitest/TypeScript build **locally**, without GitHub Actions. These checks are **not asserted to have passed** in the absence of an actual local Docker build/log output.

**Remaining Phase 4 requirements that cannot be claimed complete:**
1. Actual provider and browser runtime acceptance on the user's server, including corrected source ingestion.
2. Independently validated historical country/fund **holdings** exposure weights, if that becomes a requirement; domicile/benchmark labels are deliberately not substituted.
3. Historical **publication-vintage** (“as known then”) panel models only with genuine published vintages (such as ALFRED). Current `snapshot_at` records when *this application* saw a data revision, not the historical market release vintage. No false historical out-of-sample backtest is implemented.
4. Research-grade Marxian rate-of-exploitation/profit-rate accounts would require reconciled multi-industry labour input-output accounts, depreciation, productive/unproductive labour assumptions and internationally consistent source series. Existing labour-income shares/gross surplus are clearly labelled **proxies/context**, not exact Marxian exploitation.
5. Probabilistic crisis forecasting, causally validated financial stress scores, issuer NAV reconciliation and transaction-cost-sensitive investment simulation require data/contracts and real validation beyond what has been implemented. No invented forecast or opaque number is exposed.

The Phase 4 tracker remains **open** until the full agreed acceptance evidence is available.

## Multinational labour-income-share measurements: same PWT, not a synthetic EU series

Phase 4 now also uses the exact Penn World Table 11.0 **annual fractional compensation/GDP shares** for Japan, Germany, France and Italy, through 2023. It retains the already implemented US PWT series:

- Japan: [LABSHPJPA156NRUG](https://fred.stlouisfed.org/series/LABSHPJPA156NRUG)
- Germany: [LABSHPDEA156NRUG](https://fred.stlouisfed.org/series/LABSHPDEA156NRUG)
- France: [LABSHPFRA156NRUG](https://fred.stlouisfed.org/series/LABSHPFRA156NRUG)
- Italy: [LABSHPITA156NRUG](https://fred.stlouisfed.org/series/LABSHPITA156NRUG)
- United States: [LABSHPUSA156NRUG](https://fred.stlouisfed.org/series/LABSHPUSA156NRUG)

Each series is multiplied by 100 to display percent. The comparative view overlays all **five countries** on an identical PWT methodology and uses exact shared years to calculate any high-minus-low range. The European research page displays Germany, France and Italy **individually**; no fake EU27 total or unverified euro-area aggregate is synthesized. Japan's labour/non-labour GDP split uses one Japanese PWT denominator and labels the complement as **not corporate profits or Marxian surplus value**. These observations currently end in 2023, and revised historical PWT data are not genuine publication vintages.



## Historical-research extension (2026-11-02)

The four previously unimplemented research areas now have actual local source/compute/API/UI contracts: **ALFRED dated observations and as-of revisions; exact SEC N-PORT fund filing/CIK/series issuer-country allocations; OECD 2025 IOT industry net-surplus accounting; and an expanding-window vintage-only US recession research model.** User-visible views show source methodology, exact missing inputs and appropriate restrictions rather than inventing outputs. The official SEC timestamp is **not** a guaranteed public dissemination instant; eligibility is conservatively delayed and marked approximate. Dated holdings for Irish UCITS are not provided by SEC, and OECD cross-country productive-capital stocks and published data still require independent reconciliation. Event-based model evaluation needs complete original ALFRED snapshots and adequate recession/non-recession cases. This phase remains open for real-data verification, historic look-through and external scientific validation.

For exact commands, source references, methodological assumptions and acceptance rules, see [Phase 4 primary-source research workflows](PHASE_4_RESEARCH_SOURCES.md).

## November 2026 continuation: source completeness and validation controls

The following changes have been committed to `main` and have regression tests
but **have not been executed in the production Docker environment**:

- Two US ETF fund/series SEC identities are independently verified and embedded
  in the SEC collector: VT (`0000857489`, `S000022482`) and BND
  (`0000794105`, `S000002564`). The collector now caps attempts separately
  from the requested number of *matching series* filings. Original country
  allocations remain unavailable until live SEC collection and source review.
- `python -m finance_dashboard.vintage --backfill` resumes a long ALFRED
  as-of history in **at most 180** fresh API requests per invocation, reporting
  the remaining date and count without fabricating gaps.
- Recession model evaluation displays approximate positive-event clusters and a
  deterministic nonoverlapping historical evaluation subset when enough
  admissible events exist. Even a good Brier or AUC is not scientific
  out-of-time validation.
- OECD IOT normalized inputs can optionally include `gross_value_added` and
  `net_taxes_on_production` to verify an internal current-price accounting
  identity. The dashboard marks this coverage and explicitly warns that
  operator-supplied CSV hashes do not authenticate the original OECD release.
  Independent archive hashes, full row-level mapping and OECD STAN capital
  stock consistency are still missing.

**Acceptance remains open.** Do not display any of the uncollected source
measurements as historical facts. See [the acquisition and audit commands](PHASE_4_RESEARCH_SOURCES.md).

## Comparative visual evidence integration

The main presentation now integrates accounting composition, independently calculated quarterly productivity/pay ratio history, historical observation ranks (minimum twelve actual periods), and exact-period country comparisons. The Phase 4 research panel adds a pairwise monthly-return correlation matrix and empirical walk-forward probability calibration plot. All use existing API observations; no new securities, fake source series, or post-hoc filled values are introduced.

The calibration plot compares actual per-bin **mean forecast probabilities** from the underlying scored cases against per-bin realized outcome shares. This is not a prospective probability guarantee; overlapping recession horizons reduce effective independent-event samples and are separately audited. Missing vintage models do not render calibration data.

These changes address visual/comparative functionality; original authentic-data acceptance remains open wherever the required historical sources have not been imported and independently verified.

### UI test scope

The local Docker build includes short Vitest assertions for: multi-geometry economic charts, dated same-source country ranking, stacked GDP residuals, a separate productivity/pay gap, actual risk/return comparison using matched currency histories, paired-return correlation matrix, and withheld model calibration on absent ALFRED source vintages. A separate mocked ready-data test checks that the chart shows observed frequency alongside bin-average predicted probability; it is not interpreted as empirical model validation.
