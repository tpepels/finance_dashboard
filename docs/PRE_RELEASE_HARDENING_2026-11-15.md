# Pre-release source and diagnostics hardening — 2026-11-15

Scope: ingestion response capture, SEC N-MFP3 original files, scientific
evidence reconstruction, failure provenance and support ZIP generation.
These changes are committed on main; a server-side deployment and a real
publisher collection are separate acceptance steps.

## Hardening controls

1. **Source-response batch bounds.** At most 32 originals and 260 MB of
   received source bytes are admitted per individual source collection,
   preserving the 50 MB per-response limit. Failed captures remain quarantined
   outside certified source evidence. If quarantine storage itself fails,
   the original parser/transport exception survives and the secondary I/O
   error is recorded in the sanitized failure journal.
2. **SEC ZIP originals.** The importer and *independent* original reader
   both reject ambiguous selected tables, duplicate headers, malformed TSV
   rows, unsafe internal filenames, ZIPs with excessive entries and implausible
   decompression ratios. Every source remains selected by the publisher
   index, exact filing accession, series, report date and latest amendment.
   No missing fund values are imputed.
3. **Failure codes.** Fixed, credential-free SEC reason codes distinguish an
   unavailable index, no matching filings, invalid archives, incorrect weekly
   liquidity scale and other original-layout failures. Codes are included in
   the existing safe source-coverage vocabulary.
4. **Diagnostics under failure.** An unavailable database/source census,
   ICIO metadata audit, failure ledger, downstream classification, manual
   status or scientific assessment does not suppress otherwise available
   diagnostic sections. The ZIP's new
   `diagnostics/section-health.json` identifies each unavailable section and
   warns that omitted evidence cannot be interpreted as a clean finding.
   The overview also distinguishes an *active* source collection from
   unresolved failures and exposes bounded progress.
5. **Export integrity.** The diagnostic-export manager validates ZIP
   structure, required status/release sections, member size bounds, CRCs,
   exact output size and SHA-256. It checks on generation, restart and
   download; status polling remains cheap. Corrupt, missing, truncated,
   legacy-unhashed or swapped cached ZIPs are not served.

## Regressions and publishing gate

`tests/test_pre_release_hardening.py` checks tampering with equal-length ZIP
replacement, missing required sections, restart/repair of cached ZIP state,
that polling does not rehash, capture-batch limits, quarantine I/O masking,
malformed SEC headers and archive filenames, and generation of a partial
support bundle when the source census fails.

The existing asynchronous diagnostic-export tests now construct full
status/release fixtures compatible with the integrity contract.

The tests are offline with synthetic publisher-shaped fixture rows.
Successful GitHub CI means the application code passes its regression suite,
not that the operator's server has acquired current SEC originals. The
production acceptance check is the next user diagnostics ZIP after deploying
a passing build, with the source history and research acceptance gates read
from verified archives. Preserve database and immutable source evidence.

## Remaining external-data limitations

- Real SEC N-MFP archives must still be collected and independently reconciled
  on the deployment. A blocked HTTP request or absent publisher field stays
  unavailable, without manual or proxy substitutions.
- WID registered percentile histories may legitimately lack observations for
  particular countries/years. Their absence must remain explicit.
- A BLS 403 is an upstream access outcome, not an importable source file.
- The 54 ICIO edition accounting failures cannot be relabelled as numerical
  tolerance noise without a publisher-accounting reconciliation.
