# Build Vite/React inside the image; Node is not present at runtime.
FROM node:24-alpine@sha256:a34ab6d7f6f4813f4d0c5469d74685604b962fbdbf5793a7bc7b4998ecb867c8 AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/tsconfig.json frontend/vite.config.ts frontend/index.html ./
COPY frontend/src ./src
# Explicitly build the same-origin API client, not the public static-data mode.
ENV VITE_DATA_MODE=api
RUN npm test \
    && npm run build

FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b AS standalone
COPY --from=ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 /uv /bin/uv
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FINANCE_DASHBOARD_ROOT=/app \
    FINANCE_DASHBOARD_UI_DIR=/app/site \
    FINANCE_AUTO_REFRESH=1 \
    FINANCE_INCLUDE_MARKETS=1 \
    FINANCE_WISESHEETS_REFRESH=1 \
    FINANCE_SEC_HOLDINGS_REFRESH=0 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    WISESHEETS_SNAPSHOT_PATH=/data/wisesheets/sec_filer_profit.json \
    REFRESH_INTERVAL_SECONDS=86400 \
    DATABASE_URL=sqlite+pysqlite:////data/finance.sqlite3
WORKDIR /app
COPY pyproject.toml uv.lock README.md /app/
RUN uv sync --frozen --no-dev --no-install-project
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
RUN uv sync --frozen --no-dev --no-editable \
    && python -m compileall -q /app/src /app/tests /app/migrations \
    && python -m finance_dashboard validate \
    && python -m finance_dashboard.runtime_release build --output /app/release.json \
    && chmod 755 /app/start.sh
EXPOSE 8080
VOLUME /data
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3)"
ENTRYPOINT ["/bin/sh", "/app/start.sh"]
