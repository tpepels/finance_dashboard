# Phase 2 original holdings, profits and return evidence — 2026-11-04

This is a source investigation record under the authoritative [development plan](DEVELOPMENT_PLAN.md). It does not certify an analysis or close Phase 2. Integrated verification and commit status are recorded in that plan.

## SEC identities, cash and derivative evidence

The existing 57 original N-PORT XML bundles were read from the independently restored prior backup. Their archive hashes, manifests, acquisition receipts and immutable version-1 position payloads passed verification. The current position view now derives direct holding-level issuer fields and attributed security identifiers from original XML. An underlying derivative reference instrument's LEI or ISIN is never promoted to the holding issuer. Native contract trees preserve repeated counterparties, reference instruments, notionals, payment currencies and their original hierarchy. Securities-lending fields are retained separately.

The [original SEC Form N-PORT](https://www.sec.gov/files/formn-port.pdf), Parts B.1/B.2 and C.1/C.11, identifies these fields. B.2.f is cash and cash equivalents **outside Parts C and D**, so it is neither total cash nor an inferred NAV residual. Across all 57 originals: **782,927 positions**, **415,579 reported issuer LEIs**, **782,927 positions with at least one reported security identifier**, and **924 derivative positions**. All 57 fund balance sheets satisfy assets minus liabilities equals net assets exactly; all contain the B.2.f cash field. These are reported identifiers, not independent LEI-registry validation or proved ultimate-parent consolidation. Derivative market values are not notionals or geographic look-through exposures.

Original aggregate JSON and archived position payloads remain unchanged. The new view is reconstructed from verified original XML. Exact first dissemination is still unverified; the existing filing-date-plus-two-days research eligibility buffer remains. General Instruction F describes public third-fiscal-month information upon filing, while current [SEC submissions/API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) distinguishes dissemination and processing. Neither retrieval time nor an acceptance timestamp with unverified timezone supplies proof of the first public instant.

The 2021, 2020 and 2015 iShares III `gls-download` annual-report URLs were rechecked. Each returned HTTP 200 with the **same HTML directory/error content**, not a PDF. Status 200 does not establish an original historical schedule. The existing 2022–2026 PDF holdings evidence remains valid; earlier UCITS history, historical issuer-parent mappings, share-class hedges and exact first dissemination remain incomplete.

## Original global multiasset output — scientific failure retained

The [author's data page](https://laurensswinkels.com/data/) links the [original published workbook](https://laurensswinkels.com/wp-content/uploads/2025/11/public-data-file-jimf-3.xlsx) for Doeswijk and Swinkels, [*The risk and reward of investing*](https://doi.org/10.1016/j.jimonfin.2025.103453). Acquired original: **1,048,583 bytes**, SHA-256 `a66ce1c1c1852fbac0c5c56bfe8b02c42900a5a820c9f13f2219325486c96d2d`. The native workbook contains 637 index dates, including the December 1969 base, and **636 monthly returns, January 1970–December 2022**, in ten currencies and nominal/real/excess variants.

`global_market_returns.py` reads native cached XML numbers with Decimal arithmetic, without following external workbook links or recalculating formulas. It checks all **19,080** index/return identities. The numerical budget propagates 15-significant-digit cell serialization and binary64 arithmetic; it is not fitted to observed failures. **579 EUR nominal identities fail**, maximum **2.404083310391274 percentage points** in March 2022; the other 29 currency/return-type pairs pass their numerical bounds. January 1970 EUR nominal index moves from 100 to 95.934598387927878, while the published return is −2.985057035631522%. Both original fields are retained. No value is substituted with the ratio-derived result.

The original workbook also warns that a previous version accidentally supplied government-bond series in place of the global market portfolio. This is publisher evidence for a prior correction; it does not explain the current EUR mismatch. The paper's published portfolio output is a global **multiasset** research portfolio, not a separate all-country equity net-return or global aggregate-bond index. Common FX/CPI/risk-free inputs, source first releases and portfolio reconstruction remain unverified. The synchronized cross-currency corpus remains `original_index_return_identity_failed`. The independently consistent USD nominal pair is integrated as `returns.doeswijk_swinkels.global_multiasset.usd.nominal`: 636 months through the existing ingestion/router/source-evidence path, with an explicit separate P02 fallback panel. Repeating ingestion added zero versions; all pre-existing rows were preserved.

Reproduction:

```sh
python -m finance_dashboard.global_market_returns --file original.xlsx --output audit.json
```

## Worldwide profit research — original Brazilian evidence acquired

The original [CVM DFP dataset](https://dados.cvm.gov.br/dataset/cia_aberta-doc-dfp) documents annual statements, restatements and [history since 2010](https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/). The **2025 original ZIP** was acquired: **12,806,186 bytes**, SHA-256 `85f53d6aba99557ebb8a5f8b247c0610973230c1a0f97ab267da2216816a8ab6`. The [publisher dictionary ZIP](https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/META/meta_dfp_cia_aberta_txt.zip) is preserved separately, SHA-256 `1c0066a38257c11c6f602a6676f00b11095bba0ffe3b4d4220fec912a466342e`.

`cvm_profits.py` selects the original **consolidated DRE**, current fiscal-period rows and latest matching filing revision, preserving CNPJ/CD_CVM, fiscal start/end, native currency/scale, filing document ID and authority receipt date. It keeps every available filing version in the evidence report. It never substitutes consolidated total income for missing parent-attributable income. The source's fixed parent-income accounts differ by reporting template: `3.11.01`, `3.09.01` and `3.13.01`; account labels and corresponding consolidated/minority controls are checked together.

Actual original coverage: **669 filers / 759 filing versions**, **440 consolidated-income reporters**, including **83 losses**, **105 zero parent-income values**, **11 non-calendar fiscal periods**, **430 REAL/MIL** and **10 REAL/UNIDADE** reporters. Native scale conversion to BRL is explicit and is not FX conversion. The original includes **105 identical repeated current-period rows**; row numbers remain disclosed and identical facts are counted once. **312** parent-plus-minority partitions reconcile exactly; **128** have nonzero source residuals, retained without modifying values or fitting a tolerance. Zero attribution fields alongside positive consolidated income remain an observed discrepancy, not imputed parent earnings.

The resulting state is `regional_source_partial`. CVM reporting entities have not been proved to be a listed-only population; the 229 other filers do not receive invented consolidated income. Cross-listed/parent-subsidiary deduplication, all missing jurisdictions, fiscal-calendar and FX alignment, actual public release dates and a worldwide coverage denominator remain open. No regional or world profit aggregate is produced. The [XBRL repository's own documentation](https://filings.xbrl.org/docs/about) independently confirms that its European collection remains incomplete; its [published API field](https://filings.xbrl.org/docs/api) can be null and depends on source meaning, while repository-added time is a different event.

Reproduction:

```sh
python -m finance_dashboard.cvm_profits --file dfp_cia_aberta_2025.zip --year 2025 --output audit.json
```

## Verification and private evidence

Initial focused execution passed **32 holdings tests**, **three global-output tests** with the full original workbook, and **three CVM tests** with the full original archive. Factual, bounded original excerpts are in `tests/fixtures`; full originals remain in private content-addressed evidence with shared append-only receipts. Opt-in real-artifact tests use `TEST_GLOBAL_MARKET_PACKAGE` and `TEST_CVM_PACKAGE`. Final integrated verification and backup/restore results are recorded in the authoritative development plan. This investigation made no production database changes.
