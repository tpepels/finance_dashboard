# Scheduled static-data pipeline for GitHub Pages

The backend generates source-traceable JSON from **every mapped catalog series** without a permanent FastAPI or PostgreSQL instance.

## FRED authentication

The repository Actions secret must be named **FRED_API_KEY** under Settings → Secrets and variables → Actions.

The workflow **.github/workflows/static-data.yml** injects it only into the server-side Python steps. The FRED probe tests all four mapped FRED series through the authenticated official observations API. A missing or invalid key fails the workflow instead of quietly using the public HTML fallback.

Never place the key in a Vite environment variable, browser fetch URL, frontend bundle, published JSON file, or committed .env file.

## Refresh

The workflow runs at 06:20 UTC each day, can be run manually, and is triggered by relevant code/catalog changes. It:

1. Runs offline security/format tests.
2. Tests the private FRED key against the official API.
3. Fetches all mapped sources concurrently (not a sample).
4. Generates index.json, charts.json, and one series/<canonical-id>.json for each mapped series.
5. Uploads the complete data as the **finance-dashboard-static-data** Actions artifact.

A failed source fails the entire job; no partial artifact is published. Six unresolved indicator definitions remain explicitly flagged in the manifest. Observations and decimal values preserve native frequencies and source attribution; no invented values are added.

The manifest uses an allowlist of catalog metadata. Secrets, raw authenticated URLs, headers, arbitrary API response bodies and exception strings are never written into the artifact. Full-history refreshes produce latest-known values but cannot reconstruct genuine historical release vintages.

## GitHub Pages

**The current workflow produces a downloadable Actions artifact, not a live Pages website.** The React UI and combined charts are scheduled for Phase 3. Their build can then consume the generated JSON and deploy to Pages. The secret stays in the Python/Actions job.

Pages publication is generally public; treating a project as personal-use does not make the generated website private.

## Local validation

Install the package and run the short offline test suite:

    python -m unittest discover -s tests -v

Generate static datasets manually:

    python -m finance_dashboard.static_export --output-dir build/static-data

Without FRED_API_KEY the existing local adapter uses FRED's public data tables, but the GitHub Actions workflow intentionally requires the configured secret.

See **docs/DATA_COVERAGE.md** for the exact source catalog and remaining methodology gaps.
