# Single Docker service in your existing home-server Compose

Only **one additional container**, `finance-dashboard`. The image includes the built React dashboard, Python/FastAPI, SQLite and an in-process daily macro refresh plus local monthly Wisesheets earnings collection. No PostgreSQL container, separate scheduler, Wisesheets GitHub fetch or separate Node server.

Copy the [service snippet](home-server-finance-service.yml) under your existing `services:` section, alongside Monochrome, Plex, yt-dlp, Vinted etc. Clone `tpepels/finance_dashboard` as `./finance_dashboard` relative to the existing Compose file. Ensure that the host `/srv/finance-dashboard` directory is writable by the `UID/GID` defined in your media-server `.env`.

**Add the Wisesheets key to the existing server-side `.env`** (a GitHub Actions secret is not automatically available in Docker):

```sh
WISESHEETS_API_KEY=your_existing_key
# FRED_API_KEY=...   # optional
```

Do not put credentials in Compose YAML, version-controlled files, browser code or URLs.

```sh
git -C finance_dashboard pull --ff-only
sudo install -d -o "$(id -u)" -g "$(id -g)" /srv/finance-dashboard
docker compose config --quiet
docker compose up -d --build finance-dashboard
docker compose logs --tail=100 finance-dashboard
```

Open `http://media-server:5052/` and `http://media-server:5052/api/data-status`. The integrated SEC earnings dataset is available at `/api/earnings/sec-filers`.

The first startup migrates persistent SQLite and immediately starts asynchronous data ingestion in a Python thread. The page remains usable before all 42 sources have completed their first backfill, but individual charts may initially show missing-data states. Every 24 hours the existing macro refresh cycles again. If a Wisesheets key is configured, a *full accessible SEC filer scan* is performed only when due (roughly 30-day period), with retry cooldown, source-quality checks and bounded provider requests. The last valid snapshot persists at `/srv/finance-dashboard/wisesheets/sec_filer_profit.json`. Without a key, the bundled last verified snapshot is still readable but becomes stale.

The port is accessible on your LAN by default, with **no login**. Do not forward it to the public internet. Source attribution metadata does not block access in this local installation. Third-party licences still govern any external redistribution.

If you use the repository as an independent Compose project instead, it now has a **single-service** `docker-compose.yml`, using `./data-local` by default. Do not run this separate stack alongside the same image in your main Compose; add the service to the existing project instead.
