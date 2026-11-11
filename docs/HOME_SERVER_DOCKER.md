# Add to an existing home-server Compose project

Reviewed 2026-11-11. For a standalone local or Linux LAN-server install, use **[RUNNING.md](RUNNING.md)**. This page is only for integrating the same service into an existing Compose stack.

Add the [service snippet](home-server-finance-service.yml) under the existing `services:` block, with the repository checked out at `./finance_dashboard` relative to the main Compose file. Use one `finance-dashboard` service and retain its current host data mount if already installed. Do not start the standalone repository stack beside an existing container with the same name.

The snippet mounts `/srv/finance-dashboard:/data`; ensure it exists and is writable by the server's configured UID/GID. Set these and provider keys in the existing server-side `.env`, preserving unrelated entries. `.env` values are only passed to the container when the service environment references them.

From the existing Compose project's directory:

```bash
rtk docker compose config --quiet
rtk docker compose build finance-dashboard
```

Before replacing the running container, retain its image and a complete verified stopped-data recovery copy as described in the runbook. Then:

```bash
rtk docker compose up -d --no-deps --wait --wait-timeout 120 finance-dashboard
rtk docker compose ps finance-dashboard
rtk docker compose logs --tail=100 finance-dashboard
```

Open `http://SERVER_LAN_IP:5052/` and check `/api/health` from another LAN device. The app is unauthenticated; LAN users can edit portfolio settings and trigger sync. Keep access on the trusted network. An existing authenticated reverse proxy can instead use a loopback host binding, but is not required.

The same container contains UI, API, SQLite, scheduled collection and backups. No Node server, separate worker/database or additional scheduler is needed. See [source setup](SERVER_SOURCE_SETUP.md) for optional credentials and actual readiness; a health check does not certify data completeness.

Backup currently omits saved portfolio inputs and publisher-policy state. Follow the runbook's full stopped-tree preservation procedure before updates/transfers, rather than assuming the scheduled database/evidence bundle captures the entire installation.
