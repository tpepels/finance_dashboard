# Wisesheets local SEC filer earnings

The existing Wisesheets account and key support the accessible SEC-reporting listed company directory and annual financial data. Previous verified collection on 2026-11-02 found **8,179 unique SEC CIKs, 6,161 filers with filing-traceable net income, and five publishable fiscal-year observations (2021–2025)**. That source-validated aggregate remains in `data/wisesheets/sec_filer_profit.json` as a starting fallback. It is a current-universe cross-section with survivorship bias.

**The numerator is only SEC-reporting US-listed-company earnings**, including some foreign issuers listed on US exchanges. The denominator is World Bank *world* nominal GDP. The resulting percentage is **not** the world listed-company share of profits. Unverified original SEC filing accessions, unavailable currency conversion and sparsely represented years are omitted.

## Fully local execution

No GitHub Actions workflow, GitHub snapshot downloader or GitHub-hosted secret is involved. Configure `WISESHEETS_API_KEY` in the existing home-server Compose `.env`; the service definition passes the key only to the Python process (not to the browser).

The single existing background refresh thread invokes `wisesheets_local.refresh_local_wisesheets()` at the start of each daily cycle. Its state is stored on the existing bind-mounted volume. A complete authorized scan is attempted when a validated local snapshot is absent or about 30 days old; failed scans have a seven-day cooldown (avoids repeated charges against monthly request quotas on restarts). A local metadata marker is written before collection to prevent unbounded retries after crashes. The scan uses the existing rate-spaced, batch-100 collector and safety cap of 800 Wisesheets API requests per run, and preserves the previous aggregate when a provider request fails.

The provider client enumerates all accessible SEC company pages, deduplicates by CIK, fetches five-year annual net income, preserves negative earnings, requires actual SEC filing provenance, and converts reporting-currency records to USD using source-validated ECB daily FX histories. It excludes unconvertible values and reports annual reporting/converted issuer coverage. World Bank GDP is matched to the corresponding reported fiscal year; that fiscal year may not coincide with calendar year.

A successful collection atomically replaces `/srv/finance-dashboard/wisesheets/sec_filer_profit.json`. The read-only endpoint `GET /api/earnings/sec-filers` was retired on 2026-11-10 with the pre-engine dashboard; it returned the validated file and its recorded date/stale status. The separate **Supplementary company earnings** chart displays annual net income/world GDP, counts and FX-conversion coverage. Page views do not invoke Wisesheets.

No full-universe collection is run if `WISESHEETS_API_KEY` is absent; the bundled snapshot remains available and eventually reports its age. Do not expose the API token in exported chart configuration or Docker logs.

Reference: https://www.wisesheets.io/api/docs
