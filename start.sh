#!/bin/sh
set -eu
# The bind-mounted SQLite file is persistent in /data. Build-time code
# and frontend assets remain immutable in /app.
: "${DATABASE_URL:?DATABASE_URL must point to the persistent database}"
python -m finance_dashboard validate
alembic upgrade head
# Reset disposable diagnostic state only when the deployed build changes.
python -m finance_dashboard.runtime_release activate
exec uvicorn finance_dashboard.api:app_factory --factory --host 0.0.0.0 --port 8080 --workers 1 --no-access-log
