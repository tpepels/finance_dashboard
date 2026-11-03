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
    FINANCE_INCLUDE_MARKETS=0 \
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
COPY migrations/ /app/migrations/
COPY tests/ /app/tests/
COPY alembic.ini /app/alembic.ini
COPY scripts/run-standalone.sh /app/run-standalone.sh
COPY --from=frontend-build /build/frontend/dist/ /app/site/
RUN pip install --no-cache-dir . \
    && python -m compileall -q /app/src \
    && python -m finance_dashboard validate \
    && python -m unittest discover -s tests -p 'test_research.py' -v \
    && python -m unittest discover -s tests -p 'test_insights.py' -v \
    && python -m unittest discover -s tests -p 'test_risk_diagnostics.py' -v \
    && python -m unittest discover -s tests -p 'test_portfolio_risk.py' -v \
    && python -m unittest discover -s tests -p 'test_phase4_api.py' -v \
    && python -m unittest discover -s tests -p 'test_source_coverage.py' -v \
    && python -m unittest discover -s tests -p 'test_targeted_refresh.py' -v \
    && python -m unittest discover -s tests -p 'test_source_failure_codes.py' -v \
    && python -m unittest discover -s tests -p 'test_backup.py' -v \
    && python -m unittest discover -s tests -p 'test_vintage.py' -v \
    && python -m unittest discover -s tests -p 'test_sec_holdings.py' -v \
    && python -m unittest discover -s tests -p 'test_sec_holdings_sync.py' -v \
    && python -m unittest discover -s tests -p 'test_marx_accounts.py' -v \
    && python -m unittest discover -s tests -p 'test_historical_research_api.py' -v \
    && chmod 755 /app/run-standalone.sh
EXPOSE 8080
VOLUME /data
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3)"
ENTRYPOINT ["/bin/sh", "/app/run-standalone.sh"]
