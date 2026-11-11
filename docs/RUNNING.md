# Running locally and on a LAN server

Reviewed 2026-11-11. The supported deployment is the repository's **single-service Docker Compose project** on your computer or a Linux server, with access by IP and port. Existing multi-service installations can use [home-server integration](HOME_SERVER_DOCKER.md).

Commands use this workspace's `rtk` wrapper. On a server without it, remove the leading `rtk` or `rtk proxy`; Docker/Python/npm commands are otherwise unchanged.

## Prerequisites and storage

- Docker Engine and the Docker Compose plugin; use `docker compose`, not the old standalone `docker-compose` program.
- A writable local filesystem for the bind mount. SQLite belongs on the server's own disk, not a shared SMB/NFS database file.
- Free space for the database, originals and backup retention. The reviewed installation uses about **67 GB** in its data directory, including archives/backups; budget from your actual data, rather than a small empty install.
- No Python or Node installation is needed on the Docker host. Image builds require outbound access to image/package registries; source collection separately requires publisher access.

Each installation has its own `.env` and data directory. Choose one installation as the authoritative research store. Do not run local and server processes as writers against the same SQLite files.

## New local installation

Run from the repository root. Preserve an existing `.env`; the copy below does not overwrite it.

```bash
rtk proxy cp -n .env.example .env
rtk proxy id -u
rtk proxy id -g
rtk proxy mkdir -p data-local
```

Edit `.env`:

```dotenv
UID=1000
GID=1000
FINANCE_DATA_DIR=./data-local
FINANCE_BIND_HOST=127.0.0.1
FINANCE_PORT=5052
```

Replace `1000` with the actual IDs just printed. The data directory must be writable by those IDs. Keep any existing provider keys; optional sources are explained in [source setup](SERVER_SOURCE_SETUP.md).

```bash
rtk docker compose config --quiet
rtk docker compose up -d --build --wait --wait-timeout 120
rtk docker compose ps
rtk proxy curl -fsS http://127.0.0.1:5052/api/health
```

Open **http://localhost:5052/**. Expected health JSON: `{"status":"ok","database":"connected"}`. If the port is already used, choose another `FINANCE_PORT` before starting. This repository explicitly names the container `finance-dashboard`; an existing container of that name must be managed in its existing Compose project, or intentionally renamed in a separate override with separate storage and port.

## New Linux LAN server

Clone the repository on the server, then follow the same setup. Set a persistent absolute path and LAN binding in the **server's own** `.env`:

```dotenv
UID=1000
GID=1000
FINANCE_DATA_DIR=/srv/finance-dashboard
FINANCE_BIND_HOST=0.0.0.0
FINANCE_PORT=5052
```

Create `/srv/finance-dashboard` with ownership matching the chosen IDs **before** starting Docker. For example, for IDs 1000/1000 on a new server:

```bash
rtk proxy sudo install -d -o 1000 -g 1000 -m 0750 /srv/finance-dashboard
rtk proxy chmod 600 .env
rtk docker compose config --quiet
rtk docker compose up -d --build --wait --wait-timeout 120
rtk proxy curl -fsS http://127.0.0.1:5052/api/health
```

Open **http://SERVER_LAN_IP:5052/** from another device and request `/api/health` there too. Use the server's real LAN address; `localhost` on your laptop refers to the laptop. If host access works but another device fails, check the published bind address, server firewall and network segmentation for TCP 5052. `0.0.0.0` binds all server interfaces; binding the specific LAN IP is also supported.

The app has no login and LAN users can change portfolio inputs or trigger sync. Keep access within your trusted network; do not forward the port to the internet. A reverse proxy or public hosting is not required for this deployment.

## First-start readiness and source collection

Startup validates the catalogue, runs Alembic migrations and starts Uvicorn on container port 8080. Compose maps that to host port 5052. The API becomes healthy independently of data acquisition and scientific acceptance.

A new data directory contains no research histories. The scheduled collector starts asynchronously; additional original archives, vintages and owner-supplied files may still be necessary. While acceptance evaluates, analysis requests may return **503 with `Retry-After`**; the panels retry. An empty or withheld chart is not proof of installation failure.

Use **Data & sync**, `/api/source-coverage`, `/api/operations` and `/api/analysis` to distinguish stored observations, failed/deferred collection and accepted research. A successful sync does not certify all source roles. P06 was incomplete in the reviewed populated installation; see [the review](PROJECT_REVIEW.md).

## Transfer the existing research installation

Cloning code does **not** transfer the roughly 67 GB of private research state. Transfer the complete data tree: SQLite, originals/receipts, source evidence, holdings, vintages, portfolio inputs, policy ledger, maintenance state, journals and backups.

1. Record the source checkout revision/image and exact host data mount. Keep its existing `.env` privately; prepare the destination's own keys, IDs and path.
2. Build the destination image first, but do not start its collector against the destination data yet. Keep the source image available.
3. Stop the source service and wait for it to exit. Stop the destination service if already running.
4. Copy the **whole stopped** source data directory to a **new/empty** destination directory, preserving its relative paths and SQLite sidecars. Keep the source copy intact. For example, replacing host/path placeholders:

   ```bash
   rtk docker compose stop finance-dashboard
   rtk proxy rsync -a --checksum --info=progress2 ./data-local/ USER@SERVER:/srv/finance-dashboard/
   rtk proxy rsync -an --checksum --itemize-changes ./data-local/ USER@SERVER:/srv/finance-dashboard/
   ```

5. The second, dry-run comparison should report no changed file contents. Correct destination ownership for its configured UID/GID; do not apply recursive ownership changes to unrelated server paths.
6. On the destination, start Compose and check health, source counts, acceptance states, key original archives and saved portfolio inputs. Keep the source stopped while verifying the new authoritative installation.

Do not copy only a live `finance.sqlite3`: committed WAL data and independent original evidence can be omitted. The existing online backup is useful, but currently omits portfolio inputs and the source-policy ledger. A complete stopped-tree copy is the current migration/recovery procedure. Long transfers require corresponding downtime unless a separately verified online transfer procedure is introduced.

## Stop, update and recover

To stop while retaining all data:

```bash
rtk docker compose stop finance-dashboard
```

Before an update, retain the current image identity and an independent, verified stopped-tree copy. Build the new image before the maintenance window when possible; then stop, copy and verify the data, update/recreate only this service, and check health and acceptance. Startup migrations can change the schema: image rollback alone may not be sufficient. Restore the matching pre-update data copy with the previous image if needed.

Online database/evidence backups remain available:

```bash
rtk docker compose exec -T finance-dashboard python -m finance_dashboard.backup --output-dir /data/backups --keep 14
rtk docker compose exec -T finance-dashboard python -m finance_dashboard.backup --verify-manifest /data/backups/EXACT_MANIFEST_FILENAME.json
```

Use the actual returned manifest name. This backup is not currently a complete application-state backup. Keep a complete stopped-tree copy on another disk/device; backups beside the live database do not protect against disk loss. Restore into a separate directory with both services stopped; retain damaged/current files until the restored installation has passed checks.

Inspect failures without printing resolved credentials:

```bash
rtk docker compose config --quiet
rtk docker compose ps
rtk docker compose logs --tail=100 finance-dashboard
```

Do not use `down -v`, prune volumes or delete the data directory as a repair step.

## Native development without Docker

Use Python 3.12 and Node 24 (the image's versions). The package declares Python >=3.11; 3.12 is the verified target. Do not use the host's default Python 3.14 merely because it is installed. Existing `.venv` and frontend dependencies may already be ready.

```bash
rtk proxy python3.12 -m venv .venv
rtk proxy .venv/bin/python -m pip install -e '.[test]'
rtk proxy npm --prefix frontend install
rtk proxy npm --prefix frontend run build
```

Until dependency-lock adoption is implemented, installation resolves allowed versions and is not a reproducible release build. Do not overwrite existing lockfiles during an unrelated review.

In a shell at the repository root, configure a **separate development** data directory. Native execution does not automatically load Compose's `.env`:

```bash
export FINANCE_DEV_DATA="${XDG_DATA_HOME:-$HOME/.local/share}/global-capital-monitor-dev"
export DATABASE_URL="sqlite+pysqlite:///$FINANCE_DEV_DATA/finance.sqlite3"
export FINANCE_DASHBOARD_ROOT="$PWD"
export FINANCE_DASHBOARD_UI_DIR="$PWD/frontend/dist"
export FINANCE_SOURCE_EVIDENCE_DIR="$FINANCE_DEV_DATA/source-evidence"
export FINANCE_VINTAGE_DIR="$FINANCE_DEV_DATA/vintages"
export FINANCE_HOLDINGS_DIR="$FINANCE_DEV_DATA/holdings"
export FINANCE_SURPLUS_DIR="$FINANCE_DEV_DATA/surplus"
export FINANCE_OWNER_INPUTS="$FINANCE_DEV_DATA/owner-inputs.json"
export FINANCE_MAINTENANCE_STATE="$FINANCE_DEV_DATA/maintenance/jobs.json"
export FINANCE_SOURCE_POLICY_DB="$FINANCE_DEV_DATA/source-policy/rate-ledger.sqlite3"
export FINANCE_BACKUP_DIR="$FINANCE_DEV_DATA/backups"
export WISESHEETS_SNAPSHOT_PATH="$FINANCE_DEV_DATA/wisesheets/sec_filer_profit.json"
export FINANCE_AUTO_REFRESH=0
rtk proxy mkdir -p "$FINANCE_DEV_DATA"
rtk proxy .venv/bin/python -m finance_dashboard validate
rtk proxy .venv/bin/alembic upgrade head
rtk proxy .venv/bin/uvicorn finance_dashboard.api:app_factory --factory --host 127.0.0.1 --port 5053 --workers 1
```

Open **http://127.0.0.1:5053/**. Port 5053 avoids the Docker service's 5052. For Vite hot reload, leave that API running and use another terminal:

```bash
rtk proxy env VITE_API_PROXY_TARGET=http://127.0.0.1:5053 npm --prefix frontend run dev
```

Open the Vite URL it prints (normally `http://127.0.0.1:5173`). Browser API requests stay relative to `/api`; Vite proxies them to FastAPI. Remote deployment uses the built UI served by FastAPI, not the Vite development server.

## Disabling automatic collection for a smoke test

The current standalone Compose file hardcodes auto-refresh and Wisesheets-refresh enablement. `.env` cannot disable those literal values. Create an untracked `compose.override.yaml` containing:

```yaml
services:
  finance-dashboard:
    environment:
      FINANCE_AUTO_REFRESH: "0"
      FINANCE_WISESHEETS_REFRESH: "0"
```

Pass it explicitly: `docker compose -f docker-compose.yml -f compose.override.yaml up -d --build --wait`. This also disables the automatic backup cycle, which lives in the refresh thread. Keep manual backups. Remove the override from the command when resuming normal collection. Making these flags configurable in `.env` is task 2 of the completion plan.

References: [Docker Compose environment interpolation](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/), [Compose up and health waiting](https://docs.docker.com/reference/cli/docker/compose/up/), [bind mounts](https://docs.docker.com/engine/storage/bind-mounts/).
