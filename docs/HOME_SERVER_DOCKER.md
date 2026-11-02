# One-container finance dashboard inside your existing home-server Compose

This is a **single extra Docker container** called `finance-dashboard`. It bundles the React app, Python/FastAPI API, background data refresh and an on-disk SQLite database. It does not require a separate Docker Compose project, PostgreSQL container, migration container, worker container, Node runtime or reverse proxy.

**Do not combine Plex, Pi-hole, Transmission and all the other unrelated services into one container.** They remain separate services managed by your **one existing Compose file**. The finance dashboard needs only one additional service.

## Install

Place the [finance_dashboard repository](https://github.com/tpepels/finance_dashboard) next to your existing `monochrome/`, `yt-dlp-server/` and `vinted-dashboard/` directories so `./finance_dashboard` resolves inside the same Compose project:

```sh
git clone https://github.com/tpepels/finance_dashboard.git finance_dashboard
sudo install -d -o "$(id -u)" -g "$(id -g)" /srv/finance-dashboard
```

If the repository already exists, use `git -C finance_dashboard pull --ff-only`. If a different account runs Compose, ensure that `/srv/finance-dashboard` is writable by the UID/GID configured in the existing `.env`. The default service definition uses your existing `UID`, `GID` and `TZ` variables.

**Paste** the service block from [home-server-finance-service.yml](home-server-finance-service.yml) inside the **existing** `services:` block. This file is only a snippet, not another Compose stack. It assigns host port **5052** (avoids your 5050 Vinted, 5051 playlists, 5001 Monochrome, 4545 downloads, 9091 Transmission).

Run from the directory with your existing Compose file:

```sh
docker compose config --quiet
docker compose up -d --build finance-dashboard
docker compose logs --tail=80 finance-dashboard
docker compose ps finance-dashboard
```

Open `http://media-server:5052/` or `http://192.168.1.200:5052/` (only if that remains the server's current LAN address). `GET /api/health` validates the SQLite connection. On first startup, the app starts immediately and the background refresh imports historical observations one source at a time. Empty-source states are displayed until ingestion succeeds. Check `/api/data-status` for each source's last success/failure. Failure of one external provider leaves previous readings available.

## Verified single-container acceptance

The [single-container Docker smoke run](https://github.com/tpepels/finance_dashboard/actions/runs/41513402528) passed on 2026-11-02. The workflow built a multi-stage image with React/TypeScript and Python, booted one container as the host UID/GID with a persistent SQLite bind mount, applied Alembic migrations, served the built frontend at `/`, served all 42 macro definitions and 24 chart definitions over the existing `/api` routes, and successfully restarted against the same SQLite file. Focused tests also verify SQLite WAL and a single background refresh thread; the smoke run disables external network ingestion so it completes quickly. Full external source ingestion was independently validated in Phase 2.

## State and refresh

- **SQLite**: persistent files `/srv/finance-dashboard/finance.sqlite3` and journal/WAL siblings. Auto-migrated with Alembic at every startup. Back up the directory (including WAL/SHM; for consistent hot backup use SQLite backup API).
- **Automatic macro refresh:** at startup and then every 24h, using the **same existing source adapters**. One background thread in the FastAPI process, not another container or cron daemon.
- **Optional market histories and FX:** set `FINANCE_INCLUDE_MARKETS: "1"` if you want the 24 optional stock/ETF histories and ECB FX feeds refreshed as well; they are not needed for the macro dashboard and are disabled by default to reduce load.
- **FRED_API_KEY** is optional in the local service; an Actions secret is not automatically copied to the home-server environment. If using the authenticated FRED API, add it to the server's existing `.env` (never to this source repository).
- **Healthcheck** checks FastAPI + SQLite, not the success of all 42 external sources. Use `/api/data-status` for provider failures.
- **Access:** `5052:8080` makes the site reachable on your LAN. No authentication is provided; do not expose port 5052 to the public internet without access controls.
- **No public data redistribution:** the local UI uses your private service and all mapped observations; the rights-filtered public GitHub Pages workflow remains separate.

The original multi-container `docker-compose.yml` remains in the finance repo for existing PostgreSQL development/integration workflows; **do not run it** as part of your media-server Compose project. The dedicated `Dockerfile.standalone` is the small home-server deployment target.
