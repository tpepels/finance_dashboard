# Source-derived ingestion fixtures

The diagnostic ZIP now includes `diagnostics/source-fixture-samples.json`.
It is built on demand from **source archives already collected by the app**.
The user does not have to expand diagnostic sections or run a separate tool.

## Supported families

| Original | Excerpt | What the tests verify |
| --- | --- | --- |
| WID country data and metadata pair | Earliest and latest three literal annual rows for each registered relevant source variable and percentile, plus selected original identity/unit/method metadata | Exact country, variable, population and unit; actual published shares, original metadata, and rejection of altered content |
| BLS OEWS national ZIP | Exactly one national all-occupations row and its original column header from up to two verified annual workbooks | Matching mean and median hourly wages for the same population, workbook identity/year, nested ZIP paths and field description sheets |
| World Bank monthly Pink Sheet XLSX | Literal source column header, unit row and latest three published Copper rows | Official USD/metric-ton unit, month and value, correct commodity column and rejection of unapproved units |

The exporter reads source bytes only from the application's immutable publisher
archive directory (`FINANCE_SOURCE_EVIDENCE_DIR`). It verifies the complete
stored source hash before using any rows, follows exact registered source
identities, and records the original SHA-256 and official source URL in the
excerpt. A failed, missing or altered original produces an explicit
`unavailable` result. It never generates placeholder prices or wages.

Only bounded, selected source rows are added to the ZIP; complete originals,
HTTP denial bodies, credentials and arbitrary on-disk files remain excluded.
An error while sampling one source must not block exports for other publishers.

## Promoting an observed failure into a permanent regression test

1. Export a diagnostic ZIP after the app has attempted source downloads.
2. Open `diagnostics/source-fixture-samples.json` and locate the affected
   original with its `source_sha256`, source URL and literal rows. A
   `verified_..._unavailable` entry means the necessary source bytes were not
   available and the failure cannot yet be reproduced from that publisher.
3. Add the excerpt, with its SHA-256 provenance, to `tests/fixtures` and
   write a focused test that passes the exact source rows to the canonical
   parser. Assert both the accepted values and the source validation that
   would reject altered identity, units or data.
4. Keep a separate negative test for malformed or denied responses; never
   treat such content as accepted economic observations.

Existing checked-in originals are in `tests/fixtures/wid_top1` and
`tests/fixtures/native_source_families`. The new
`tests/test_source_fixture_samples.py`, `tests/test_bls_oews.py`, and
`tests/test_providers.py` cover row extraction, checksums, publisher-shaped
data, invalidation and isolated collector behavior. For an actual WID optional
measure unavailable from the publisher, keep the absent source explicit rather
than manufacturing observations.

## Distinguish fixture testing from data availability

A passing parser or ingestion test establishes that **the captured source
shape is supported**. It does not establish that today's publisher accepts
automated downloads, that the variable is published for the requested
country/period, that a source is more recent, or that production ingestion
succeeded. Those require a fresh production collection and a checked source
audit. The report's stored data and failure counts remain authoritative.
