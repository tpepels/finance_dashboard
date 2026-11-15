# ECB DWA, Eurostat house prices and SEC N-MFP3 originals

These 27 series use the existing ProviderRouter, managed HTTP transport,
publisher policy registry, SourceAcquisition response archives, content hashes,
retrieval receipts, source reconciliation, canonical series catalog, incremental
history and post-ingestion acceptance refresh. No parallel acquisition worker.

## Sources

* ECB Distributional Wealth Accounts: eight quarterly series for Portugal,
  Germany, France and the fixed euro area (I9), each with net household wealth
  shares for the top 10% and bottom 50%. ECB S14 household estimates differ
  from WID per-adult net personal wealth; the L07 comparison remains separate.
* Eurostat prc_hpi_q: fifteen quarterly HPI 2015=100 histories for Portugal,
  Germany, France, EA20 and EU27, in TOTAL, DW_NEW and DW_EXST purchase groups.
  C07 uses only exact quarterly joins and matching HICP for real changes;
  missing national inflation remains unpaired.
* SEC N-MFP3: four monthly original-filing measures from July 2025 onward:
  non-feeder series net assets (USD million), asset-weighted WAM/WAL (days),
  and latest disclosed weekly-liquidity proportion. Filings are a sampled,
  as-filed reporting universe, not a complete US money-market total or a
  redemption-risk probability.

## Source verification

Publisher data must be downloaded via the central managed policy gate.
Successful responses preserve exact bytes, sources, hashes, capture dates and
receipts in the existing source-evidence directory; HTTP denials remain
rejected. An independent original reader checks the selected archived
responses, official keys, query dimensions, reporting periods, fund identities,
filing amendments and economic units. No history is promoted from missing,
unverified or altered originals.

SEC requests require the existing SEC_USER_AGENT setting with a genuine
operator contact address or URL. No contact is invented, no fallback provider
is used to bypass access refusal, and each publisher's original data rights
are recorded independently of network access.

These are supplemental roles of existing L07, C07 and F07 questions. When
originals are absent, their panels show unavailable evidence; existing
accepted core analysis is not falsely demoted or populated with proxies.

## Verification contract

Run tests/test_extra_publisher_sources.py, offline Python, frontend,
Chromium/browser and release image workflows. Validate real archive receipts,
source histories and scientific acceptance in the next production Data &
diagnostics report. CI does not prove publisher availability on the server.
