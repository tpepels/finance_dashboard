# Build Vite/React inside the image; Node is not present at runtime.
FROM node:24-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/tsconfig.json frontend/vite.config.ts frontend/index.html ./
COPY frontend/src ./src
# Explicitly build the same-origin API client, not the public static-data mode.
ENV VITE_DATA_MODE=api
RUN npm install --no-audit --no-fund \
    && npm test \
    && npm run build

FROM python:3.12-slim AS standalone
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FINANCE_DASHBOARD_ROOT=/app \
    FINANCE_DASHBOARD_UI_DIR=/app/site \
    FINANCE_AUTO_REFRESH=1 \
    FINANCE_INCLUDE_MARKETS=1 \
    FINANCE_WISESHEETS_REFRESH=1 \
    WISESHEETS_SNAPSHOT_PATH=/data/wisesheets/sec_filer_profit.json \
    REFRESH_INTERVAL_SECONDS=86400 \
    DATABASE_URL=sqlite+pysqlite:////data/finance.sqlite3
WORKDIR /app
COPY pyproject.toml README.md /app/
COPY src/ /app/src/
COPY definitions/ /app/definitions/
COPY data/msci_acwi_published_snapshots.json /app/data/msci_acwi_published_snapshots.json
COPY data/wisesheets/sec_filer_profit.json /app/data/wisesheets/sec_filer_profit.json
COPY data/reference/ /app/data/reference/
COPY migrations/ /app/migrations/
COPY tests/ /app/tests/
COPY alembic.ini /app/alembic.ini
COPY start.sh /app/start.sh
COPY --from=frontend-build /build/frontend/dist/ /app/site/
# Fast, deterministic runtime build. The complete Python suite and repeated
# original-source integrity/identity verification run separately with
# python -m finance_dashboard stan overnight; no tests contact the publisher at build time.
RUN pip install --no-cache-dir . \
    && python -m compileall -q /app/src /app/tests /app/migrations \
    && python -m finance_dashboard validate \
    && chmod 755 /app/start.sh
EXPOSE 8080
VOLUME /data
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3)"
ENTRYPOINT ["/bin/sh", "/app/start.sh"]
