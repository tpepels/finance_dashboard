# Data page: automatic and manual source acquisition

The simplified **Data** page has one update area with two primary actions
(**Sync current data** and **Repair gaps**), a compact expandable
**Manual downloads and uploads** source catalogue, and collapsed
**Source coverage and audit**, **Scientific evidence and advanced monitoring**,
and **Source explorer** sections. The historical sync remains available
inside the advanced disclosure next to the update controls.

Manual uploads use the same production FastAPI application, the same canonical
catalogue identifiers, the same domain parsers, the existing append-only
SQLite observation versions and the existing immutable evidence directory.
There is no second ingestion database, no generic CSV field mapper and no
checkbox/confirmation after an accepted upload.

## Download and upload

Open **Data → Manual downloads and uploads**, expand the source and select
its publisher download link. Upload the corresponding file next to it.
For paired originals, upload both files; once all required roles exist,
validation and ingestion start automatically. The per-source row displays
the real result, period and number of new/revised observations. A failed
or interrupted import can be repeated from already staged files.

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

- The browser can certify **which bytes were uploaded**, their original
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
roles, staged-file inventory and recent jobs. `POST
/api/manual-sources/upload?dataset=...&role=...&filename=...` streams an
exact original file; validated uploads automatically start the canonical
ingest when the role set is complete. `POST
/api/manual-sources/import?dataset=...` explicitly retries a complete
staged set after an interrupted/failed job.

The existing `/api/originals` ICIO endpoints are unchanged. Neither
endpoint accepts a user-supplied URL or source mapping.

CI acceptance includes backend original ingestion, file-size/filename/
same-origin restrictions, WID five-series auto-import, EU KLEMS blank-year
preservation, gold USD timestamp validation, pinned Swinkels and MSCI
methodology integrity, MSCI capture/owner-upload conflict resolution,
and frontend link/upload/job rendering.

**Deployment is required.** GitHub CI exercises synthetic or pinned
fixtures in isolation and does not import files into the owner's private
Docker database. The live source-health audit must be rerun after actual
uploads before any of the previously unresolved sources can be certified.
