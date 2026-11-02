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
- Yahoo Finance v8 chart is an **unofficial daily market data source**, not an index-constituent history API or an issuer NAV authority. Yahoo fundamental and holdings data, if integrated later, require separate adapters, provenance, coverage, and validation.

## Boundary B — temporal and financial modelling

- Store macro period **at native frequency**; never expand annual GDP to daily points or fill absent weekends with made-up prices.
- Preserve original market trading dates and corporate-action ex-dates separately. Apply non-trading-day splits to the next actual trading session for return calculation, without changing the original ex-date.
- Keep raw close, adjusted close, dividend, split, share class, index level and FX observations distinct; do not conflate fund NAV, market traded price and benchmark level.
- ECB `EXR.D.{USD,GBP,CHF}.EUR.SP00.A` is quoted foreign currency per EUR; conversion to EUR divides by that rate. Historical lookback for weekends/holidays is bounded; invalid/missing FX produces null and a coverage explanation.
- Application `first_seen_at` is ingestion provenance, **not** the source's release vintage. True as-of publication history exists only if provider revisions are actually supplied.

## Boundary C — persistence, ownership and API

- `src/finance_dashboard/database.py` + `migrations/` own SQL schema. Ingest run tables record successes/failures; observation versions and market/FX action versions append rather than rewrite history.
- `src/finance_dashboard/service.py` and `market_service.py` own normalization/persistence/read projections, never provider web UI.
- `src/finance_dashboard/remaining_sources.py`, `world_credit.py` and `market_analytics.py` own economics/formulas. Every calculation documents weighting, sampling alignment, missing-data policy, numerator/denominator definitions and output ID. The UI must not derive or relabel economic indicators.
- `src/finance_dashboard/api.py` exposes read-only series, chart, status, market and earnings routes; not a transaction/trading API. Responses distinguish unsupported, stale, missing and ready states. Authentication secrets never transit to the browser.
- Public static export `static_export.py` uses an explicit allowlist and a manifest of unresolved indicators; no hidden catch-and-ignore errors. It must not publish restricted datasets without the required rights.

## Boundary D — original vs proxy datasets

Keep a **typed and visible distinction** among:
1. **Original mapped:** exact requested measure with validated provider/definition (e.g. MSCI ACWI NETR gold correlation).
2. **Derived but explicitly defined original:** original concept implemented through an agreed accounting identity or national-gap composite, with caveats (ILO/BIS).
3. **Supplementary/proxy:** a different universe or instrument (Wisesheets current SEC filers, ACWI ETF holdings, index capitalization ÷ P/E, VT/GLD).
4. **Unresolved:** original measurement lacking an acceptable historical dataset.

Original `concentration.global.top10` must use month-dated MSCI ACWI free-float **security-level weights**, summing ten separate index constituents; keep issuer IDs for optional group-level comparisons. An ETF's reported holdings are a new proxy series with a different source contract and vintage.

Original `profit.global.corporate_share` must use worldwide **listed-company** consolidated net income including losses; deduplicate issuer/share classes/cross-listings and address subsidiary and multinational attribution, reporting currency, fiscal periods and world GDP year. Provider-universe changes and coverage belong in the data model. A cap/P-E-derived earnings figure is a separately titled index-universe estimate, with index methodology attached.

## Boundary E — scheduled collection and publication

- Daily `.github/workflows/static-data.yml`: validated mapped macro/index + every registered asset + three FX feeds + separate correlations, browser-safe artifact.
- Monthly `.github/workflows/wisesheets-refresh.yml`: free-tier quota-controlled confidential API collection; committed, audited `data/wisesheets/sec_filer_profit.json` aggregate only. No per-user request-time Wisesheets calls.
- `FRED_API_KEY` and `WISESHEETS_API_KEY` live in Actions secrets; never log them or publish raw authenticated URLs.
- Any new licensed historical MSCI, Worldscope, Compustat or Siblis provider must be isolated behind a new adapter and credential/rights policy; no provider-specific shortcut in the UI or existing Yahoo market adapter.
- A static Actions artifact is **not** public Pages deployment. Phase 3 may consume it after rights review.

## Quality/observability contract

Every provider and derived series needs validation for units, chronology, duplicates, invalid numbers, zero denominators, source/vintage identity, coverage, revisions, API and export parity; report source freshness. A complete ingestion test covers every promised canonical source, not a representative subset. Leave unverified assertions in the acceptance tracker explicitly pending.

## Decision change control

Modify this architecture only with the owner's explicit change approval recorded against [issue #1](https://github.com/tpepels/finance_dashboard/issues/1) (or a linked architectural decision), with corresponding feature/implementation contract and migration/test updates. The design is a normative baseline, not a guarantee of deployed branch protection.