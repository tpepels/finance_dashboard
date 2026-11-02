# Phase 2 — locked architecture contract

Status: **baseline frozen on 2026-11-02**. Normative architecture for the [Phase 2 feature contract](PHASE_2_FEATURE_CONTRACT.md); the implementation truth is tracked in the [implementation contract](PHASE_2_IMPLEMENTATION_CONTRACT.md). This document fixes boundaries; it does not claim unimplemented components are working.

## Architectural style

A **single Python backend package**, a separate scheduled worker process and FastAPI query process, PostgreSQL append-only ingestion records, Alembic migrations, and a deterministic static JSON export for the future browser application. Docker Compose runs the database, migrations, API and worker. No Celery, Redis, Kafka, HTTP scraping in the browser, microservice split or speculative production deployment.

```text
definitions/series.json + definitions/instruments.json + charts.json
                         |
           canonical validation and identity
                         |
 provider-specific adapters + market feed + ECB FX + Wisesheets
                         |
          validation, dates, units, rights, provenance
                         |
       [PostgreSQL append-only version/history + runs]
                         |
          [Python transformations / view projections]
                      /       \
            FastAPI read API   static JSON export
                   |             |
             local queries    Actions artifact
                                (Phase 3 UI later)
```

## Boundary A — registry and provider acquisition

- `definitions/series.json` is the authoritative macro/index identity contract. `definitions/instruments.json` defines the 24 market *listings* and share classes; `definitions/charts.json` specifies charts only.
- An adapter maps a canonical ID to a *verified* provider endpoint. It cannot change units, provider, economic definition, index variant or geography without versioned catalog review.
- Source identities are validated independently of filename/ticker appearance: venue MIC, currency, ISIN verification, corporate-action semantics, index code 892400 and NETR USD where relevant.
- Source APIs have bounded timeouts/retries and explicit invalid/missing/error states. If a provider fails, preserve the last successful persisted data and log failure; the required full static export fails closed.
- Macro sources have priority over market listing detail. World Bank world market capitalization and GDP are aligned by annual calendar year; Siblis index aggregate valuations and their reciprocals remain *different-universe* month-dated snapshots, without inferred intervening months.
- Yahoo Finance v8 chart is an **optional** unofficial daily market data source, not an index-constituent history API or an issuer NAV authority. Yahoo fundamental and holdings data, if integrated later, require separate adapters, provenance, coverage, and validation.

## Boundary B — temporal and financial modelling

- Store macro period **at native frequency**; never expand annual GDP to daily points or fill absent weekends with made-up prices.
- Preserve original market trading dates and corporate-action ex-dates separately. Apply non-trading-day splits to the next actual trading session for return calculation, without changing the original ex-date.
- Keep raw close, adjusted close, dividend, split, share class, index level and FX observations distinct; do not conflate fund NAV, market traded price and benchmark level.
- ECB `EXR.D.{USD,GBP,CHF}.EUR.SP00.A` is quoted foreign currency per EUR; conversion to EUR divides by that rate. Historical lookback for weekends/holidays is bounded; invalid/missing FX produces null and a coverage explanation.
- Application `first_seen_at` is ingestion provenance, **not** the source's release vintage. True as-of publication history exists only if provider revisions are actually supplied.

## Boundary C — persistence, ownership and API

- `src/finance_dashboard/database.py` + `migrations/` own SQL schema. Ingest run tables record successes/failures; observation versions and market/FX action versions append rather than rewrite history.
- `src/finance_dashboard/service.py` and `market_service.py` own normalization/persistence/read projections, never provider web UI.
- `src/finance_dashboard/remaining_sources.py`, `world_credit.py`, `concentration_snapshots.py`, `eurostat_corporate.py` and `market_analytics.py` own economics/formulas. Every calculation documents weighting, sampling alignment, missing-data policy, numerator/denominator definitions and output ID. The UI must not derive or relabel economic indicators.
- `src/finance_dashboard/api.py` exposes read-only series, chart, status, market and earnings routes; not a transaction/trading API. Responses distinguish unsupported, stale, missing and ready states. Authentication secrets never transit to the browser.
- Public static export `static_export.py` uses an explicit allowlist and a manifest of unresolved indicators; no hidden catch-and-ignore errors. It must not publish restricted datasets without the required rights.

## Boundary D — original vs proxy datasets

Keep a **typed and visible distinction** among:
1. **Original mapped:** exact requested measure with validated provider/definition (e.g. MSCI ACWI NETR gold correlation).
2. **Derived but explicitly defined original:** original concept implemented through an agreed accounting identity or national-gap composite, with caveats (ILO/BIS).
3. **Supplementary/proxy:** a different universe or instrument (Wisesheets current SEC filers, ACWI ETF holdings, index capitalization ÷ P/E, VT/GLD).
4. **Unresolved:** original measurement lacking an acceptable historical dataset.

The superseded complete-monthly `concentration.global.top10` is archived in `definitions/superseded_series.json`. Its owner-approved replacement `concentration.global.msci_acwi_published_top10` uses **only** published source-dated actual MSCI ACWI 892400 top-ten index **share-class constituent** totals, and is **sparse**: exact as-of date, URL and reported percentage are kept in `data/msci_acwi_published_snapshots.json`; values are indexed by report month for storage. Do not interpolate, backfill absent months, use ETF holdings, or merge issuer classes. Bundle the immutable archive in the container.

The superseded worldwide listed-profit/GDP original is archived and is no longer an active catalog source under the [second owner-approved amendment](PHASE_2_FREE_SOURCE_REPLACEMENTS.md). The implemented macro replacement `profit.eu27.corporate_operating_surplus_gdp` is strictly **EU27_2020** national accounts: nominal EUR (S11 B2A3G + S12 B2A3G)/S1 B1GQ GDP ×100, matching annual periods. Official Eurostat API `nasa_10_nf_tr` is the only ingested source. The separately published `profit.eu27.nonfinancial_gross_surplus_value_added` comes from Eurostat `nasa_10_ki`, unit PC and denominator **S11 GVA**, not GDP. These measures include unlisted companies. OECD sector data was inaccessible from CI (403) and no claim of OECD/world coverage or listed-company net profits is permitted.

## Boundary E — scheduled collection and publication

- Daily `.github/workflows/static-data.yml`: **all 39 mapped macro/index series are required**, plus the retained optional 24 registered assets and three FX feeds, in a browser-safe artifact. A future macro-first exporter may separate optional assets without affecting mandatory macro completeness.
- Monthly `.github/workflows/wisesheets-refresh.yml`: free-tier quota-controlled confidential API collection; committed, audited `data/wisesheets/sec_filer_profit.json` aggregate only. No per-user request-time Wisesheets calls.
- `FRED_API_KEY` and `WISESHEETS_API_KEY` live in Actions secrets; never log them or publish raw authenticated URLs.
- Any new licensed historical MSCI, Worldscope, Compustat or Siblis provider must be isolated behind a new adapter and credential/rights policy; no provider-specific shortcut in the UI or existing Yahoo market adapter.
- A static Actions artifact is **not** public Pages deployment. Phase 3 may consume it after rights review.

## Quality/observability contract

Every provider and derived series needs validation for units, chronology, duplicates, invalid numbers, zero denominators, source/vintage identity, coverage, revisions, API and export parity; report source freshness. A complete ingestion test covers every promised canonical source, not a representative subset. Leave unverified assertions in the acceptance tracker explicitly pending.

## Decision change control

The [owner-approved macro-first amendment](PHASE_2_MACRO_SCOPE_AMENDMENT.md) removes independent per-ETF NAV and historical ticker continuity audits as phase blockers, without deleting existing market code. Modify this architecture only with the owner's explicit change approval recorded in the [second macro free-source amendment](PHASE_2_FREE_SOURCE_REPLACEMENTS.md) and against [issue #1](https://github.com/tpepels/finance_dashboard/issues/1) (or a linked architectural decision), with corresponding feature/implementation contract and migration/test updates. The design is a normative baseline, not a guarantee of deployed branch protection.