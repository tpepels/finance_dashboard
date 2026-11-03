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


## Phase 4 market research and observability

The same single `finance-dashboard` container now includes **Phase 4 economic risk evidence** and an **optional** ETF/equity/gold historical comparison under the main economic research page. The market comparison needs prices and EUR FX; the full-collection configuration enables them. Older deployments may still have a literal disabled flag; verify the actual Compose service environment.

To enable local price research, add to the **existing** service's environment:

```yaml
FINANCE_INCLUDE_MARKETS: "1"
```

Then recreate only this container with `docker compose up -d finance-dashboard`. The existing local refresh thread will collect 24 registered Yahoo instrument histories and three ECB FX histories; failures remain visible under `http://media-server:5052/api/market/status`. Do not add a worker or another database container. The market feed is unofficial, so incomplete histories are not replaced with invented quotes.

The new **operational status** route is `http://media-server:5052/api/operations`. It reports local source and market history counts, ingestion failures, optional collection settings, and the most recent verified backup manifest.

### Daily SQLite backups

The same refresh thread now creates SQLite **online-backup API** snapshots once per cycle (24 hours by default), plus a separate verified archive of historical ALFRED, SEC filings and OECD industry accounts where present, with integrity checks and SHA-256 manifests in `/srv/finance-dashboard/backups` on the host (mounted as `/data/backups`). The default keeps 14 bundles. They remain vulnerable to loss of the same disk; copy to a second physical device/off-site encrypted backup.

Create and verify one immediately:

```bash
docker compose exec finance-dashboard python -m finance_dashboard.backup --output-dir /data/backups --keep 14
# Replace the path below with the real manifest file created above.
docker compose exec finance-dashboard python -m finance_dashboard.backup --verify-manifest /data/backups/finance-REAL_TIMESTAMPZ.json
```

Only restore while the finance service is **stopped**, after verifying checksum and integrity and retaining a copy of the damaged database.

### Optional network access policy

The default port 5052 remains reachable from your LAN **without any authentication**. Do not port-forward it to the internet. For use through an already-existing authenticated Caddy reverse proxy, set `FINANCE_BIND_HOST=127.0.0.1` in Compose and recreate the finance container. This changes only which host interface accepts the published port. If Caddy is in the same Docker network, its upstream should be `finance-dashboard:8080`; if Caddy runs on the host, use `127.0.0.1:5052`. Retain TLS and authentication in Caddy. This adds no container or restriction to the application's local source retrieval.

Source formulas, assumptions and remaining Phase 4 limitations: [PHASE_4.md](PHASE_4.md).
