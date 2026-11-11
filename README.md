# Global Capital Monitor

A private research workbench for a EUR-based long-term ETF investor. It combines macroeconomic, valuation, credit, labour and portfolio evidence, with original sources, reproducible calculations and explicit limitations.

One Docker container serves the React/TypeScript/ECharts UI and FastAPI API, keeps SQLite and research archives in `/data`, and performs scheduled source updates. The same image runs locally and on a Linux server on your network.

## Status — reviewed 2026-11-11

All 37 catalogue questions have engine definitions. The overview, workbench, analysis panels, owner portfolio form, methods, sources and exports are implemented. Remaining work includes configurable/saved figures, portfolio validation and release operations.

The running installation reports **23 accepted, 12 conditional, one deferred and one incomplete** analysis. P06 is withheld because `global_earnings_yield` is unresolved. This is a report from the existing running image, not a fresh certification of all originals against the checkout.

Verification: 1,111 Python tests ran successfully (10 optional checks skipped), 108 frontend tests passed, the frontend built, and an isolated Docker Compose installation passed startup and persistence checks.

See the [project review](docs/PROJECT_REVIEW.md), [authoritative roadmap](docs/DEVELOPMENT_PLAN.md) and [completion implementation plan](docs/superpowers/plans/2026-11-11-project-completion.md).

## Run locally or on your LAN server

Follow [Running and deployment](docs/RUNNING.md) for complete setup, native development, data transfer, updates and recovery. On a **new checkout** with Docker Engine and the Compose plugin installed:

```bash
rtk proxy cp -n .env.example .env
rtk proxy mkdir -p data-local
```

Edit `.env`: set `UID` and `GID` to the values from `id -u` and `id -g`, and make `FINANCE_DATA_DIR` writable by that user. Set `FINANCE_BIND_HOST=127.0.0.1` for local-only access or `0.0.0.0` for LAN access.

```bash
rtk docker compose config --quiet
rtk docker compose up -d --build --wait --wait-timeout 120
rtk docker compose ps
```

Open **http://localhost:5052/** locally, or **http://SERVER_LAN_IP:5052/** from another device. Check `/api/health` for service health and **Data & sync** for source readiness. This is a trusted-network application with no login.

A fresh install has an empty database; collection and acceptance evaluation take time. A healthy API does not certify a research corpus. To preserve existing research, migrate the complete stopped data directory using the runbook. Do not replace an existing `.env` or data mount.

## Development checks

The runbook uses a project virtual environment (Python 3.12 is the tested runtime) and Node 24 for frontend development. After installing dependencies:

```bash
rtk proxy .venv/bin/python -m unittest discover -s tests -p 'test_*.py' -q
rtk proxy .venv/bin/python -m finance_dashboard validate
rtk proxy npm --prefix frontend test
rtk proxy npm --prefix frontend run build
```

Docker builds run frontend tests/build, Python syntax compilation and catalogue validation. The full Python suite runs separately and in `.github/workflows/python-static.yml`.

## Documentation

| Document | Purpose |
|---|---|
| [Development plan](docs/DEVELOPMENT_PLAN.md) | Sole roadmap and completion gates |
| [Project review](docs/PROJECT_REVIEW.md) | Measured state and verification limits |
| [Running and deployment](docs/RUNNING.md) | Local, native and standalone LAN-server operation |
| [Architecture](docs/ARCHITECTURE.md) | Runtime, evidence and calculation boundaries |
| [Server source setup](docs/SERVER_SOURCE_SETUP.md) | Credentials, collection and readiness |
| [Home-server integration](docs/HOME_SERVER_DOCKER.md) | Existing Compose project integration |
| [Commands](docs/COMMANDS.md) | Research/source CLI |
| [Charter](docs/PHASE1_SCIENTIFIC_CHARTER.md), [catalogue](docs/PHASE1_ANALYSIS_CATALOGUE.md), [specifications](docs/PHASE1_ANALYSIS_SPECIFICATIONS.md), [visualization contract](docs/PHASE1_VISUALIZATION_CONTRACT.md) | Scientific and interaction requirements; dated approval statements are historical |
| [Source policy](docs/SOURCE_POLICY.md), [data policy](docs/DATA_POLICY.md) | Publisher pacing, original evidence and preservation |
| [Archive](docs/archive/) | Superseded plans and investigations |

## Research principles

Preserve native observations, revisions, original responses, receipts and citations. Missing or unverified inputs remain missing; alternatives retain their own names and limitations. Acquisition follows shared publisher budgets, backoff and cooldowns; it never bypasses authentication, paywalls or technical access controls. Provider keys stay on the backend. Private research access does not establish redistribution rights.
