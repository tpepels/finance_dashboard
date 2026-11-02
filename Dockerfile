FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml README.md /app/
COPY src/ /app/src/
COPY definitions/ /app/definitions/
COPY migrations/ /app/migrations/
COPY alembic.ini /app/alembic.ini
RUN pip install --no-cache-dir .
USER 65532:65532
CMD ["uvicorn", "finance_dashboard.api:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8080"]
