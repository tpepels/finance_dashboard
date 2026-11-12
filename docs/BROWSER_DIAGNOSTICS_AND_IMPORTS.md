# Browser diagnostics and original research imports

The **one** production \`finance-dashboard\` service serves the UI, API, data store,
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
  \`1995-2000_SML.zip\`, \`2001-2005_SML.zip\`, \`2006-2010_SML.zip\`,
  \`2011-2015_SML.zip\` and \`2016-2022_SML.zip\`. These use the
  pre-existing canonical full row/column numeric audit and pinned byte hashes.
- OECD 2025 extended \`*_EXT.zip\` originals, including browser duplicate names
  such as \`2011-2015_EXT (1).zip\`.
- Historical \`ICIO2018_*.zip\` and \`ICIO2021*.zip\` originals.
- The overlapping \`2016-2020_SML.zip\` is recorded as a distinct unverified
  source and cannot replace the pinned publisher January-2026 series.

The exact \`ReadMe_ICIO_small.xlsx\` is needed for the regular publisher
matrices. The importer **reuses an existing hash-matched copy** in source
evidence; if there is none, the owner can select that workbook from the browser
(the repository includes the pinned fixture file). Unrecognised filenames,
mismatched workbooks, path escapes, symlinks, encrypted/corrupt ZIPs and
oversized archives are rejected. A completed import stores immutable original
bytes and receipts, then removes only the redundant upload staging copy.

**Evidence levels remain separate.** Publisher 2025 regular inputs receive
the full existing matrix accounting audit, including explicit failed
identities. Extended and earlier editions currently receive cryptographic
archive identity, bounded member inventories and ZIP CRC verification, but
their differing statistical definitions and industry/region concordances are
not automatically interpreted as identical observations. They are available
in the same canonical ICIO evidence reader as \`additional_editions\`, explicitly
marked \`industry_accounts_validated=false\` and
\`tiva_comparability_certified=false\`. They do **not** silently fill TiVA
series or certify cross-edition changes.

All records are kept under the existing \`FINANCE_SOURCE_EVIDENCE_DIR\`,
and uploads are staged under \`/data/incoming/icio-2025\` unless
\`FINANCE_ORIGINAL_UPLOAD_DIR\` is explicitly set. The upload size cap is
2 GiB per file; importer jobs survive as journal summaries across restarts
(interrupted work is reported, staged originals remain recoverable).

## API

- \`GET /api/diagnostics\`: current colour/severity and last 200 structured events
- \`GET /api/diagnostics/download\`: redacted ZIP
- \`GET /api/originals\`: staged file inventory, pinned ReadMe availability and jobs
- \`POST /api/originals/upload?filename=...\`: single raw octet-stream file;
  requires \`X-GCM-Action: dashboard\` and same-origin browser checks
- \`POST /api/originals/import\`: JSON \`{"filenames":["..."]}\` to register
  selected staged archives through \`finance_dashboard.icio.import_original_archive\`;
  returns a job ID and progress is polled through \`GET /api/originals\`
- \`GET /api/source-evidence/icio\`: regular-year coverage and
  \`additional_editions\` inventory
