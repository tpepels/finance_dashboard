# Complete server data-source configuration


> **Operator reference only.** This file describes source configuration, data-preserving imports and backups. Implementation order and original Phase 1–4 acceptance are defined **only** in [Development plan](DEVELOPMENT_PLAN.md).

This is the operator checklist for the **single existing** finance-dashboard Docker service in the media-server Compose project. Every configured source has a distinct evidence state: mapping present, credential present, collection enabled, original observations stored, and scientifically validated are **not** synonymous.

## Preserve the existing data before changing configuration

Use the existing repository at `~/media-stack/finance_dashboard` and existing Compose project at `~/media-stack`. The recommended persistent volume remains **`/srv/finance-dashboard:/data`**. Do not change its host path when updating environment variables. Do not use `docker compose down -v`, `docker volume prune`, delete `/srv/finance-dashboard`, or redeploy the repo's separate Compose project against a fresh volume.

A GitHub Actions secret is **not** injected into this server. The server reads its own Compose `.env`. Edit rather than replace the existing file; preserve unrelated keys. Restrict permissions (e.g. `chmod 600 ~/media-stack/.env`).

Existing startup backup creates an online SQLite copy. The updated backup also archives genuine ALFRED snapshots, parsed SEC filings/fund mapping and imported OECD accounts, with archive SHA-256 and member checks; it still must be replicated off the same disk. Before deploying new code, independently preserve the existing `/srv/finance-dashboard` tree if an older backup has not captured these evidence directories.

Check `docker compose config --quiet` for valid Compose syntax; it does not disclose secret values.

## Environment settings: full collection profile

Add/update the following lines **in the existing `~/media-stack/.env`**, without deleting existing values:

```dotenv
FRED_API_KEY=REPLACE_WITH_REAL_32_CHARACTER_REGISTERED_FRED_KEY
WISESHEETS_API_KEY=REPLACE_WITH_REAL_WISESHEETS_API_KEY
SEC_USER_AGENT="GlobalCapitalMonitor/1.0 (your-real-contact@example.org)"
FINANCE_AUTO_REFRESH=1
FINANCE_INCLUDE_MARKETS=1
FINANCE_WISESHEETS_REFRESH=1
FINANCE_VINTAGE_REFRESH=1
FINANCE_SEC_HOLDINGS_REFRESH=1
FINANCE_AUTO_BACKUP=1
FINANCE_BACKUP_KEEP=14
REFRESH_INTERVAL_SECONDS=86400
```

These values are examples; **do not leave placeholders**. SEC User-Agent must contain your genuine name/organization and a monitored email address; it is sent to the SEC. Obtain the FRED key from https://fred.stlouisfed.org/docs/api/api_key.html and the Wisesheets key from your own Wisesheets account. Do not add either secret to GitHub source, a browser form, URLs, logs or the repository YAML.

Your Compose service's `environment:` must **pass through the variables** (the recommended full-collection template is `docs/home-server-finance-service.yml`); setting an `.env` value cannot override a literal `FINANCE_INCLUDE_MARKETS: "0"` already hardcoded in Compose.

```yaml
FRED_API_KEY: ${FRED_API_KEY:-}
WISESHEETS_API_KEY: ${WISESHEETS_API_KEY:-}
SEC_USER_AGENT: "${SEC_USER_AGENT:-}"
FINANCE_AUTO_REFRESH: "${FINANCE_AUTO_REFRESH:-1}"
FINANCE_INCLUDE_MARKETS: "${FINANCE_INCLUDE_MARKETS:-1}"
FINANCE_WISESHEETS_REFRESH: "${FINANCE_WISESHEETS_REFRESH:-1}"
FINANCE_VINTAGE_REFRESH: "${FINANCE_VINTAGE_REFRESH:-1}"
FINANCE_SEC_HOLDINGS_REFRESH: "${FINANCE_SEC_HOLDINGS_REFRESH:-1}"
FINANCE_AUTO_BACKUP: "${FINANCE_AUTO_BACKUP:-1}"
FINANCE_BACKUP_DIR: "/data/backups"
FINANCE_BACKUP_KEEP: "${FINANCE_BACKUP_KEEP:-14}"
REFRESH_INTERVAL_SECONDS: "${REFRESH_INTERVAL_SECONDS:-86400}"
```

Leave `DATABASE_URL`, mounted data path, user IDs, existing Wisesheets snapshot location, published port and unrelated service configuration intact. The same source data will still be under the original bind mount.

## Provider inventory and actual acquisition rules

| Source family | What is collected | Access/configuration | Remaining evidence obligation |
|---|---|---|---|
| FRED / BLS / PWT | 15 registered FRED macro series, including US BLS productivity, compensation, Treasury rates, PWT labour shares | `FRED_API_KEY`; normal provider can use public FRED tables if no key, but that is **not** ALFRED publication-vintage evidence | Check 15 per-series ingestion records and source-date coverage |
| ALFRED historical release data | T10Y3M, SAHMREALTIME, USREC month-end as-of snapshots | Same registered `FRED_API_KEY`; `FINANCE_VINTAGE_REFRESH=1` captures each previous month, separate explicit backfill is essential | The past is not populated by automatic current refresh; verify every required origin and independent event sample |
| BIS / BIS credit gaps | Policy rates, domestic credit gaps, researcher 43-country GDP-weighted gap and coverage | Public adapters, no secret. Requires `FINANCE_AUTO_REFRESH=1` and provider access | Keep country/GDP coverage restrictions and dates explicit |
| World Bank / IMF | Country and world GDP, listed equity capitalization, public debt, gold, denominators | Public adapters, no secret | Check actual API response and aligned geography/denominator |
| ECB | Euro-area interest rate and 3 FX conversion histories (USD, GBP, CHF) | Public adapter, no secret. FX history collected with `FINANCE_INCLUDE_MARKETS=1` | Check stored common monthly FX observations |
| UN SDG / ILO | Global labour share and labour productivity-growth measure | Public adapters, no secret | Preserve international aggregation limitations and self-employment methodology |
| Eurostat / OECD macro | EU27 corporate surplus, OECD GDP-weighted gross operating surplus, coverage | Public adapters, no secret | Verify matched reporting countries and ratios; **not** OECD industry net accounts |
| Shiller / BEA / Siblis / MSCI | CAPE, produced-assets Q1 variant, sparse index P/E, real published concentration snapshots, global equity/gold correlation | Existing authorized public-source adapters; no generic secret. Some use static published snapshots | Missing historical publications remain unavailable; MSCI reuse rights must be reviewed separately |
| Yahoo market / ECB FX | 24 registered fund/equity price histories and FX for EUR comparisons | `FINANCE_INCLUDE_MARKETS=1`; Yahoo is an unofficial source and can block access | Check adjusted-price/FX alignment and absence of missing trading periods |
| Wisesheets SEC filer earnings | Current US SEC filer earnings/GDP context and reporting/FX coverage | `WISESHEETS_API_KEY`, `FINANCE_WISESHEETS_REFRESH=1`. API subscription/quota determine coverage | A US-filer aggregate is **not** global consolidated listed-company net profit |
| SEC N-PORT dated ETF holdings | Original reported positions for specifically verified US-registered funds | Real `SEC_USER_AGENT`, `FINANCE_SEC_HOLDINGS_REFRESH=1`, verified CIK + SEC series mapping | Historical filing completeness and issuer-country coverage; UCITS require separate original source |
| OECD harmonized industry IOT accounts | National industry employee pay, depreciation, net surplus, optional capital stock | **Separate audited CSV importer, not an env toggle** | Original OECD archive, reproducible extraction, same-unit reconciliation, explicit sector/model assumptions |

The macro providers are pulled by one in-process scheduled cycle when `FINANCE_AUTO_REFRESH=1`. The original publication-vintage, SEC N-PORT and manual OECD-account import paths are separate from the current macro map. A "mapped" series is not proof it has observations in your local SQLite database.

## Deployment and non-secret readiness checks

```bash
cd ~/media-stack
git -C finance_dashboard pull --ff-only
docker compose config --quiet
docker compose build finance-dashboard &&
docker compose up -d --no-deps finance-dashboard
docker compose ps finance-dashboard
```

The single-page dashboard's **Local source coverage, refresh and backup status** shows enabled collectors, credential presence (booleans only), macro/market/FX coverage, vintage file counts, SEC filing counts and whether audited industry accounts are installed.

The equivalent read-only endpoint is `http://media-server:5052/api/operations`; original source status is `/api/data-status`, and `/api/vintages` inventories actual ALFRED files. A "configured" flag does not mean authentication or import succeeded.

## Diagnose and import real ALFRED vintages

**Do this before a full backfill**. The current preflight checks genuine 2020-01-31 historical `realtime_start=realtime_end` parameters (earlier revisions only checked basic FRED authentication):

```bash
docker compose exec finance-dashboard python -m finance_dashboard.vintage --check
```

This makes one bounded official **historical ALFRED-as-of** USREC request (or no request for an invalid key format), reports only HTTP status and fixed error classifications, and never prints the key, query URL, source response body or bearer token. A previous `ready` from a plain FRED request established key validity, but was insufficient to verify historical request arguments. HTTP 400/401/403/429 now stops a large backfill after the first failing request. A 400 can be an invalid registered key **or** invalid API parameters; the probe's classification is decisive only as far as the actual provider error supports.

When the probe reports `"status": "ready"`, import month-end source-publication snapshots from 2000 through October 2026:

```bash
docker compose exec finance-dashboard python -m finance_dashboard.vintage \
  --backfill --max-requests 180 \
  --series T10Y3M --series SAHMREALTIME --series USREC \
  --start 2000-01-01 --end 2026-10-31
```

Repeat the same command **only after successful batches** until `missing_after_run: 0`. Cached valid snapshots are never removed or overwritten. The 966 requested series/month combinations include months before particular sources existed; genuine empty historical responses are recorded as `no_data`, not invented measurements. Full 6/12-month prediction evaluation remains data- and sample-gated.

## SEC: real contact and official N-PORT collection

An SEC User-Agent is **not an API key**. Use a genuine identifying name/organization with a working contact email, e.g. replace `your-real-contact@example.org` above. SEC's fair-access guidance recommends efficient requests and limits automated access to 10 requests per second (https://www.sec.gov/about/developer-resources).

Two vetted US fund identities are currently bundled: VT and BND. No arbitrary ticker is assumed to identify an SEC registrant. Their official SEC filing indexes list `primary_doc.xml` alongside `primary_doc.html`. The collector now resolves XML from the original filing index and verifies the series before parsing; it no longer requires the submission's `primaryDocument` field to end in `.xml`.

Probe official SEC index accessibility without downloading large holdings files:

```bash
docker compose exec finance-dashboard python -m finance_dashboard.sec_holdings_sync --check
```

If both report ready, import **one** real original filing per fund as a bounded first pass:

```bash
docker compose exec finance-dashboard python -m finance_dashboard.sec_holdings_sync --limit 1
```

Then resume collection of up to twelve verified filings per fund; already cached documents are preserved and reused:

```bash
docker compose exec finance-dashboard \
  python -m finance_dashboard.sec_holdings_sync --limit 12
```

Check `/api/holdings/vt` and `/api/holdings/bnd` for original dated holdings. The scheduled collector runs when `FINANCE_SEC_HOLDINGS_REFRESH=1`; collection is guarded by a 28-day success marker. Importing **all** historical N-PORT documents for all registered funds has not been established: the current collector targets two verified identities and has a 50-filing-per-fund/manual cap. Irish UCITS such as VWCE are outside the SEC registry and require original European fund disclosure sources. Do not manufacture country weights from currency, ticker or ETF domicile. The optional `/data/holdings/sec_funds.json` is a **replacement list**, not an additive list: include VT/BND as well if creating this mapping.

## Source-by-source audit and browser-managed PWT repair

The `GET /api/source-coverage` endpoint returns all **142** registered macro source rows, **24** market instruments, and **3** ECB FX histories without losing previous observations. For each source it reports its stored original-date count, first/last source date, most recent run status, last successful run and a fixed credential-safe failure code. The dashboard displays only aggregate missing/stale counts until you open **Source coverage**.

The public FRED sources for Germany, France and Italy are confirmed to be real PWT 11.0 annual **ratios** with latest source year 2023. Do not insert these numbers manually, and do not multiply values in the database by 100; the research view handles that presentation transformation.

For ordinary operation, open **Data & sync** in the dashboard. There are **two buttons**:

- **Sync current data**: imports/refreshes all 142 mapped macro sources (including Germany/France/Italy PWT), 24 markets and three ECB FX rates, plus the current quota-aware earnings snapshot, then creates and verifies a local backup.
- **Sync history**: requests complete source histories, continues genuine ALFRED monthly publication-vintage imports and collects original SEC holdings using independently verified fund series identities (up to 50 filings per fund), then verifies a local backup.

Both actions retain existing source observations, serialize with scheduled refreshes and show progress, completion or partial failures. There is no ordinary need to choose series IDs, providers, dates or request limits. The full 169-source table, source-period dates, original release boundaries, failure codes and CSV export are available only after opening **Source diagnostics**.

**Historical coverage is not automatically complete:** SEC collection still has a 50-matching-filing limit per fund, UCITS sources are not yet integrated and licensed historical global index weights are missing. A successfully completed button press does not mean unresolved source definitions are verified.

The browser never receives provider API keys. Developer command-line diagnostics remain documented elsewhere in this file for emergency recovery, but are not the normal source-collection workflow.

## Wisesheets, markets and source-level coverage

The Wisesheets key must be in this **server** Compose environment; a GitHub secret does not configure it. With the refresh toggle on, the app runs a quota-aware US SEC-filer earnings collector and persists the last valid snapshot under `/data/wisesheets/sec_filer_profit.json`. The bundled snapshot can be historical/stale and is not evidence that your new key authenticated. To make a non-secret authentication check:

```bash
docker compose exec finance-dashboard python -c \
  "import os,httpx; k=os.environ.get('WISESHEETS_API_KEY',''); r=httpx.get('https://api.wisesheets.io/v1/me/',headers={'Authorization':'Bearer '+k},timeout=15); print('Wisesheets HTTP:',r.status_code)"
```

Wisesheets subscription limits may prevent the requested full filer enumeration. Inspect `/api/earnings/sec-filers`, snapshot provenance and source coverage rather than assuming completeness.

Markets and ECB FX run automatically from the same existing service when `FINANCE_INCLUDE_MARKETS=1`; `/api/market/status` shows historical coverage and errors. Yahoo history is rate-limited/unofficial, and a configured collector cannot guarantee provider availability. Macro coverage can be checked through `/api/data-status`; 142 mappings are not 142 successfully imported histories.

## OECD industry input-output accounting

Macro OECD corporate **gross surplus/GDP** is separately sourced automatically. The deeper national-account profit/surplus analysis needs an authenticated, operator-normalized OECD **2025** Input-Output Table source extract. There is presently no general `OECD_API_KEY` that transforms the industry IOT archive into validated net surplus and net capital-stock quantities.

See `docs/PHASE_4_RESEARCH_SOURCES.md` for the complete required CSV schema and reconciliation rules. After independently obtaining and verifying the official archive, normalize it into `/srv/finance-dashboard/surplus/your_oecd_2025_normalized.csv`, record its true SHA-256 (on host), then run:

```bash
sha256sum /srv/finance-dashboard/surplus/your_oecd_2025_normalized.csv
docker compose exec finance-dashboard python -m finance_dashboard.marx_accounts \
  --csv /data/surplus/your_oecd_2025_normalized.csv --sha256 ACTUAL_SHA256
```

Do not substitute an unaudited CSV with invented accounting rows. The importer refuses unsupported sectors, wrong units and changed extracts without explicit version handling. National-account surplus/pay and net capital-stock ratios remain unavailable until their actual source values are present and verified.

## Backups: preserve everything, including non-database evidence

The updated backup writes a verified SQLite online copy, Wisesheets snapshot when present, and **a compressed evidence archive** when ALFRED/SEC/OECD files exist. Original WID bulk data/metadata and published OECD TiVA CSV snapshots are stored under `FINANCE_SOURCE_EVIDENCE_DIR` (default `/data/source-evidence`) and included in that archive. The manifest includes SHA-256 for every component. Backups stored under `/data/backups` share the same physical disk with the live source data and are **not** sufficient protection against drive loss.

```bash
docker compose exec finance-dashboard \
  python -m finance_dashboard.backup --output-dir /data/backups --keep 14
```

Record the exact manifest filename returned; verify with:

```bash
docker compose exec finance-dashboard \
  python -m finance_dashboard.backup --verify-manifest /data/backups/EXACT_MANIFEST_FILENAME.json
```

Copy the **whole bundle**, including the new `.evidence.tar.gz`, off the server and inspect the SHA-256 verification there. Restore only after stopping the service and preserving current files. Never copy a live WAL-mode SQLite file with raw `cp` as if it were a consistent backup.
