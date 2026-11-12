# Browser diagnostics and original research imports

The **one** production `finance-dashboard` service serves the UI, API, data store,
scheduled collector, support ZIP and original-data importer. There are no
extra containers, databases or alternate ingestion services.

## Header health light

The small header status button is always available. It opens the redacted
structured event console and offers **Download debug ZIP**. The colours mean:

- Green: no recent recorded failure and no source needing attention.
- Orange: assessment/import is active, a recent warning exists, or sources
  have missing, stale or deferred observations.
- Red: a recent actual error event (excluding the old acceptance-pending
  HTTP 503s, which were historically mislabeled as collector failures).

The status is advisory: a scheduled refresh can partially succeed and retain
previous observations. Status is not a guarantee of a full scientific corpus.
The ZIP contains redacted structured events, source coverage, publisher quota
metadata, selected maintenance status, import progress and README. It deliberately
does not contain raw Docker stderr, credentials, request URLs, database values,
holdings or raw publisher documents.

The HTTP middleware no longer misclassifies acceptance-pending HTTP 503 with
Retry-After as a source collector failure.

## Upload originals from the browser

Go to **Source data → Import original research files**, choose one or more
official OECD archives and their ReadMe workbook. Upload begins upon choosing
files. The browser streams bytes directly into the existing /data volume and
automatically starts one background registration job. Progress, outcomes and
failures are shown inline. Completed registration invalidates the shared
research-acceptance cache and refreshes the dashboard.

Supported file families:

- Publisher-direct January-2026 edition regular OECD ICIO archives:
  `1995-2000_SML.zip`, `2001-2005_SML.zip`, `2006-2010_SML.zip`,
  `2011-2015_SML.zip` and `2016-2022_SML.zip`. These use the
  pre-existing canonical full row/column numeric audit and pinned byte hashes.
- OECD 2025 extended `*_EXT.zip` originals, including browser duplicate names
  such as `2011-2015_EXT (1).zip`. The import validates year-by-year native
  CSV matrices (85 × 50 industries, 81 × 6 final demand columns), original
  row/column accounts when provided, and explicit split-country identities.
- Earlier `ICIO2018_*.zip` and `ICIO2021*.zip` originals, validated against
  their own industry counts (36 and 45) and economy populations. Auxiliary
  `econA`/Rdata archives are preserved as supporting originals, without
  a false claim that they are audited annual CSV matrices.
- The overlapping `2016-2020_SML.zip` is recorded as a distinct unverified
  source and cannot replace the pinned publisher January-2026 series.

The exact `ReadMe_ICIO_small.xlsx` is needed for the regular publisher
matrices. The importer **reuses an existing hash-matched copy** in source
evidence; if there is none, the owner can select that workbook from the browser
(the repository includes the pinned fixture file). Unrecognised filenames,
mismatched workbooks, path escapes, symlinks, encrypted/corrupt ZIPs and
oversized archives are rejected. A completed import stores immutable original
bytes and receipts, then removes only the redundant upload staging copy.

**Evidence levels remain separate.** Publisher 2025 regular inputs receive
their existing pinned original-accounting audit. Extended and earlier editions
receive hash/CRC verification and streaming edition-native CSV audits: native
row/column accounting residuals, exact source-country totals, direct foreign
final-demand sales, country split status, and conservative industry aggregation
to common 2018-level sector buckets. Every archive's expected annual years are
checked. No missing accounts, failed residuals or unmappable sectors are silently
treated as valid.

ICIO 2025 sector `D86T89` cannot be losslessly allocated to the older
`D86T88`; it is explicitly excluded from that sector comparison. Country
splits `CN1/CN2` and `MX1/MX2` are not summed with potentially overlapping
unsplit parent countries. Ambiguous combinations are withheld.

The existing G06 research engine loads these audited originals as **supplementary
native direct final-demand** evidence, displaying separately labelled
edition-by-edition comparison charts when accounts verify. These are direct
output flows and **are not** the published OECD TiVA domestic-value-added
embodied in foreign final demand (FFD_DVA). Reconstructing FFD_DVA requires
the separate Leontief value-added tracing method and a tested reconciliation
against the actual uploaded publisher originals. The main G06 calculation
remains grounded in the original published TiVA data. The newly added Source
data → ICIO original accounting and edition comparisons panel always exposes
verified/missing original years and the native audit results.

The older and extended archive hashes have not been independently pinned
against the publisher, so `source_authenticity_verified=false` and
`tiva_comparability_certified=false` even if numeric source accounts reconcile.
All originals and audits remain in the existing canonical ICIO evidence store.

All records are kept under the existing `FINANCE_SOURCE_EVIDENCE_DIR`,
and uploads are staged under `/data/incoming/icio-2025` unless
`FINANCE_ORIGINAL_UPLOAD_DIR` is explicitly set. The upload size cap is
2 GiB per file; importer jobs survive as journal summaries across restarts
(interrupted work is reported, staged originals remain recoverable).

## API

- `GET /api/diagnostics`: current colour/severity and last 200 structured events
- `GET /api/diagnostics/download`: redacted ZIP
- `GET /api/originals`: staged file inventory, pinned ReadMe availability and jobs
- `POST /api/originals/upload?filename=...`: single raw octet-stream file;
  requires `X-GCM-Action: dashboard` and same-origin browser checks
- `POST /api/originals/import`: JSON `{"filenames":["..."]}` to register
  selected staged archives through `finance_dashboard.icio.import_original_archive`;
  returns a job ID and progress is polled through `GET /api/originals`
- `GET /api/source-evidence/icio`: regular-year coverage and
  `additional_editions` inventory
