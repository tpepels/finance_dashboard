# Global Capital Monitor

A self-hosted research dashboard for global equities, macroeconomic conditions, labour/capital distribution, credit risk, and gold.

**Current state: Phase 1 — source catalog and data contracts.** There is no running dashboard or live ingestion yet. No synthetic observations or prices are included.

## Phased delivery

| Phase | Scope | Exit condition |
|---|---|---|
| **1 — Data contracts and feasibility** | Architecture, source registry, exact source identifiers when confirmed, chart specifications, validation, evidence and licensing flags | All mapped series have identifiers and provenance; missing/unlicensed datasets are surfaced; contract tests pass |
| **2 — Reliable data pipeline** | BIS/ECB/FRED/World Bank adapters, immutable publication-vintage history, PostgreSQL, refresh worker and read-only FastAPI | Official observations are fetched, reconciled, stored, refreshed and queried; failures preserve prior data |
| **3 — Interactive research dashboard** | React, Apache ECharts, thematic views, combined charts, time-range controls, normalization and CSV export | Verified data flows from official source to chart and can be traced back to source |
| **4 — Macro analytics and portfolio exposure** | Derived indicators, broader labour/profit/concentration coverage, portfolio/gold analytics, monitoring and hardening | Each analytical claim has a reproducible methodology and no unsupported global proxies |

Phase 1 intentionally distinguishes **documented source mappings** from **live-verified data**. Mapping confirmation does not mean API connectivity, usage rights or complete observation coverage have been validated.

## Run Phase 1 checks

Requires Python 3.11+; no external dependencies.

```bash
PYTHONPATH=src python -m finance_dashboard validate
PYTHONPATH=src python -m finance_dashboard report
PYTHONPATH=src python -m finance_dashboard list --theme monetary_policy
PYTHONPATH=src python -m unittest discover -s tests -v
```

The canonical files are `definitions/series.json` and `definitions/charts.json`. The validator checks provenance, unique IDs, supported units and frequencies, source-mapping claims, chart references and comparability rules.

See [architecture](docs/ARCHITECTURE.md), [source policy](docs/DATA_POLICY.md) and [Phase 1 audit](docs/PHASE_1_AUDIT.md).