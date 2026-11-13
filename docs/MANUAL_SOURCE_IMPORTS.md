# Data page: automatic and manual source acquisition

The simplified **Data** page has one update area with two primary actions
(**Sync current data** and **Repair gaps**), a compact expandable
**Publisher downloads and manual fallback** source catalogue, and collapsed
**Source coverage and audit**, **Scientific evidence and advanced monitoring**,
and **Source explorer** sections. The historical sync remains available
inside the advanced disclosure next to the update controls.

Manual uploads use the same production FastAPI application, the same canonical
catalogue identifiers, the same domain parsers, the existing append-only
SQLite observation versions and the existing immutable evidence directory.
There is no second ingestion database, no generic CSV field mapper and no
checkbox/confirmation after an accepted upload.

## Automatic download and import

Open **Data → Publisher downloads and manual fallback**, then select
**Fetch missing sources** once. The server queues every source not already
successfully imported, downloads the registered publisher originals over HTTPS,
validates them with the existing source-specific parsers and ingests accepted
observations into the canonical database. No extra approval or checkbox is
required. Individual source rows also have **Refresh from publisher** to request
new originals even when a previous import succeeded.

Publisher access uses the same managed HTTP transport, durable rate ledger,
cooldowns and fixed URL allowlist as the other collection paths. A valid
deferred permit automatically resumes at the publisher's next allowed time;
for example, the WID data/metadata pair may require waiting between requests.
Already received role bytes are verified locally and not fetched again on
resumption. The Data page shows queued, active, deferred, failed and completed
jobs, along with the automatic retry time.

Manual upload remains a fallback for a publisher that returns an HTML challenge,
requires interactive authentication, is inaccessible to the server, or supplies
only a human download page. Choose the official link and upload the original
next to its source. Upload inputs stay enabled while other imports run; once a
source's complete required role set exists it becomes an immutable, persisted
queue job immediately. A restart resumes queued and interrupted jobs from their
retained snapshots.

The 2025 **OECD ICIO regular** original ReadMe and five pinned ZIP archives are
also attempted directly. The full edition-aware original importer remains
available for historical/extended archives, publisher-access failures and
reassessment. Full accounting and source-health acceptance still require the
original scientific checks; downloading a file alone does not certify its data.

| Source family | Download link shown | Required upload | Canonical effect |
| --- | --- | --- | --- |
| WID world income/wealth | Native WID world data and metadata links | `WID_data_WO.csv`, `WID_metadata_WO.csv` | All five world shares |
| MSCI EAFE | Exact canonical EAFE index factsheet | PDF | Trailing and forward P/E |
| MSCI Europe | Exact canonical Europe index factsheet | PDF | Trailing and forward P/E |
| MSCI Japan | Exact canonical Japan index factsheet | PDF | Trailing and forward P/E |
| MSCI fundamental methodology | Official March 2021 PDF | PDF, only if the archived methodology is unavailable | Strictly SHA-256 pinned underlying method; no numeric series |
| EU KLEMS US | Official 2025 growth accounts file | `.xlsx` | Native US/TOT/LAB only |
| Swinkels AU | Dataverse v6 source and metadata/ReadMe references | Exact original `.ods` | Original AU modelled 10-year sovereign returns |
| Gold | Current Gold API XAU/USD endpoint | `.json` | One source-dated indicative USD quote |
| OECD ICIO | Publisher 2025 direct ZIPs; official index for 2025 extended, 2023, 2021, 2018 | Supported original ZIP and matching ReadMe | Existing original-source importer and scientific auditing |

The OECD edition index is maintained by the publisher:
https://www.oecd.org/en/data/datasets/inter-country-input-output-tables.html .
The original 2025 regular links and the established ReadMe/extended/older
archive importer remain available; no previous import or reassessment
functionality was retired.

## Provenance, acceptance and limits

- For owner uploads, the browser can certify **which bytes were uploaded**, their original
  publisher-shaped identity and their validated numeric values; it cannot
  prove the user obtained the bytes from the official publisher. Every upload
  archive and linked ingestion record states
  `user_uploaded_publisher_origin_unverified` and preserves SHA-256 receipts.
- WID records must carry exact `WO` concepts, original percentile labels,
  equal-split adult populations, metadata and supported share units; no
  percentile substitution or interpolation is permitted.
- MSCI original PDFs must print the declared index identity and a
  nonfuture publication date. They use the pinned March 2021 methodology.
  Distinct factsheets and captured archive documents enter the **same
  conflicting-value gate**. An observed disagreement blocks that index-month
  and will not be silently overwritten.
- EU KLEMS uses the original `US/TOT/LAB` cells, preserving blank years.
  A successful import with data ending in 2020 does not establish a
  published observation for 2021.
- Swinkels accepts only the exact pre-existing version-6 ODS SHA-256.
  A same-named or differently edited workbook is rejected.
- Gold requires the declared source/currency and a recent timestamp.
  A 200 HTML challenge, stale quote or EUR conversion cannot be imported.
- The API accepts a fixed list of dataset/role names, same-origin guarded
  binary streams, bounded payloads and safe filename suffixes. Upload bytes
  are written directly to a private temporary file and atomically staged.
  Server-acquired bytes have separate publisher HTTPS manifests and receipts;
  a user upload is never relabelled as a publisher network request.
  Staged partial files are **never** classified as published observations.
- Import jobs run under the existing maintenance network lock, so they do
  not race a concurrent refresh. A successful file import uses the same
  `IngestionService` and preserves append-only versions; a later
  automatic publisher refresh may still independently fail.
- User-uploaded files do not remove source-policy deferrals, certify
  original first publication vintages or imply completion of other
  scientific acceptance gates.

## API and validation

`GET /api/manual-sources` lists the supported source downloads, exact
roles, staged-file inventory, persistent queued/deferred jobs and retry deadlines.
`POST /api/manual-sources/fetch` queues missing registered publisher sources;
`POST /api/manual-sources/fetch?dataset=wid-world` retries one publisher
source. Both endpoints forbid arbitrary URLs. `POST
/api/manual-sources/upload?dataset=...&role=...&filename=...` streams an
exact original file; validated uploads automatically start the canonical
ingest when the role set is complete. `POST
/api/manual-sources/import?dataset=...` explicitly retries a complete
staged set after an interrupted/failed job.

The existing `/api/originals` ICIO endpoints remain available. Neither
fetch nor upload accepts a user-supplied URL or generic source mapping.

CI acceptance includes backend original ingestion, file-size/filename/
same-origin restrictions, WID five-series auto-import, EU KLEMS blank-year
preservation, gold USD timestamp validation, pinned Swinkels and MSCI
methodology integrity, MSCI capture/owner-upload conflict resolution,
and frontend link/upload/job rendering.

**Deployment is required.** Repository tests exercise synthetic or pinned
fixtures in isolation and does not import files into the owner's private
Docker database. The live source-health audit must be rerun after actual
uploads before any of the previously unresolved sources can be certified.
