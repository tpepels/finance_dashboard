# Phase 2 — stock, ETF and currency market data

## Implemented and verified (2026-11-02)

The market registry defines **24 exchange-listed instruments**:
- 6 EUR-listed UCITS ETFs, including VWCE.DE (FTSE All-World accumulating,
  IE00BK5BQT80) and VWRL.AS (FTSE All-World distributing, IE00B3RBWM25).
- 16 US-listed ETFs and equities: VT, VTI, VXUS, SPY, VOO, QQQ, IEMG,
  BND, AGG, GLD, IAU, AAPL, MSFT, NVDA, GOOGL and AMZN.
- 2 European equities: ASML.AS and SAP.DE.

**Issuer share-class ISIN, exchange MIC, Yahoo source symbol, trading currency,
fund base currency and distribution policy are separate registry fields.**
Unverified US ISIN values are null rather than guessed. Only whole-unit
EUR/USD quotes are registered (no GBp/GBP ambiguity).

### Market source and price conventions

The feed is Yahoo Finance's unofficial chart endpoint
(v8/finance/chart, interval 1d, events dividends/splits).
Each response must match the registered source symbol, exchange and trading
currency and must provide native timestamp-aligned raw and adjusted closes.
The response may be changed, rate-limited or unavailable without notice.
Historical adjusted prices are **vendor-defined**, not issuer NAV and not
independently licensed benchmark index total-return levels.

Every original dividend/split ex-date is preserved, including dates during
market closures (e.g. NVIDIA's 12 September 2001 split).
Splits/total-return effects are applied to the next actual trading bar rather
than inventing a bar during a closed market. Raw price, vendor adjusted close,
dividend cash, split ratio and volume remain separately queryable.

**Return conventions**, starting at 100 at the first observed price:
- price_index = 100 × raw close / first raw close (not split adjusted);
- vendor_adjusted_index = 100 × adjusted close / first adjusted close;
- cash_dividend_reinvested_index = chained split-adjusted raw closes and
  cash dividends reinvested at next trading close, gross of tax;
- eur_adjusted_index = 100 × (adjusted close / ECB foreign-per-EUR rate),
  normalized at the first EUR-convertible observation.

Indices carry separate labels. The cash-reinvested series may differ from the
vendor adjusted history due to dividend taxation, adjustments, date conventions
and rounding. Do **not** call raw close performance total return.

### ECB foreign exchange

Three ECB daily reference series:
- EXR.D.USD.EUR.SP00.A
- EXR.D.GBP.EUR.SP00.A
- EXR.D.CHF.EUR.SP00.A

**One EUR equals the quoted amount of foreign currency**. A USD asset price
converts to EUR by dividing by USD per EUR, not multiplying. The nearest
reference rate from the preceding five calendar days is allowed across market
holidays; no rates are invented before the ECB history starts, and missing FX
results in null EUR fields. ECB reference-rate timing is distinct from
exchange-market closes.

### Proxy correlation

Two output series are explicitly labelled as investable **ETF proxies**:
- proxy.gold_vt_36m_usd
- proxy.gold_vt_36m_eur

They use 36 consecutive monthly arithmetic **returns** of the last-trading-
day vendor-adjusted closes for the GLD gold ETF and VT total-world-equity ETF.
EUR results convert adjusted prices with official ECB reference rates.
The correlation is Pearson's on returns, with no forward-filled missing
months. GLD is not physical spot price and VT is not a licensed MSCI ACWI
total-return index. These proxies are **not** the original unresolved
gold.world.equity_correlation index benchmark.

## Database and APIs

Alembic migration 20261102_02_market adds:
- market_instruments;
- market_ingestion_runs;
- append-only market_price_versions;
- append-only market_action_versions (exact corporate ex-dates);
- fx_ingestion_runs;
- append-only fx_rate_versions.

Source response/adjustment revisions append new versions; old observations
are not overwritten. An application first-seen timestamp is **not** a market
publication vintage. Market histories are fully rescanned on refresh because
old adjusted closes may change after a corporate action. ECB FX refresh
overlaps 30 days by default; full refresh is available.

Read-only API routes:
- GET /api/markets
- GET /api/markets/{instrument_id}
- POST /api/market/query (instrument_ids, start/end, snapshot_at)
- GET /api/market/status
- GET /api/market/gold-world-proxy?currency=EUR&window_months=36

Example:

    curl -sS -X POST http://127.0.0.1:8080/api/market/query \
      -H 'Content-Type: application/json' \
      -d '{"instrument_ids":["vwce.de","vt","gld"],"start":"2025-01-01"}'

The scheduled worker refreshes macro sources plus all 24 instruments and FX.
To refresh only markets and FX:

    docker compose exec worker python -m finance_dashboard.worker --once --market-only

### GitHub Actions / Pages preparation

The existing secret-protected scheduled export generates **26 mapped macro
files + 24 instrument histories + three FX histories + two derived proxy
files**, as individual JSON files. It fails on an incomplete source, never
silently omitting instruments. The FRED_API_KEY remains server-side and
absent from all data files.

The static output is an Actions artifact, **not a deployed GitHub Pages UI**.
The React frontend is Phase 3 work. Actual Pages publication would be public
unless protected by another hosting layer.

## Acceptance evidence

- [Full-market static export: all 24 instruments](https://github.com/tpepels/finance_dashboard/actions/runs/41470215544).
- [Real Docker/PostgreSQL market ingestion and API verification](https://github.com/tpepels/finance_dashboard/actions/runs/41470443707):
  24/24 instruments, three ECB FX feeds, EUR queries, VWRL dividends, NVDA
  split with exact 2001 ex-date, 186 monthly gold/VT correlations.
- Short offline, migration and PostgreSQL CI on main.

## Still outside the complete original Phase 2 scope

Six original macro definitions remain unresolved: US replacement-cost Tobin
Q, global productivity-versus-pay, worldwide listed-company profit share,
historical top-ten free-float MSCI concentration, a defensible aggregate world
credit-to-GDP gap, and correlation against a genuine global equity **index**
total-return history rather than the implemented GLD/VT fund proxy.

No original definition is automatically relabelled as mapped due to the
availability of a separately named proxy. Phase 2 remains open.
