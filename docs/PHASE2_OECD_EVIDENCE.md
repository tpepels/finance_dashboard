# Phase 2 OECD source discrepancy investigation — 2026-11-04

G06 remains incomplete. Original source values, the existing 0.001pp TiVA threshold, the ICIO serialization bounds and all previously archived evidence remain unchanged.

## Original definition checks

The [publisher's 2025 TiVA Guide](https://stats.oecd.org/wbos/fileview2.aspx?IDFile=2143f34e-6feb-41a9-abaf-cb52132608c4) is dated September 2025 (47 pages). Despite an old URL/file title, the actual document is the 2025 edition. Its SHA-256 is `ca3f3db9024a6f870ff6bec061537ea2230abf7880a8e56c3f5c16cd5518bdb4`.

Section 4.2, printed page 13, defines TiVA `VALU` as basic-price value added plus net taxes on intermediate products. Section 6.3, page 34, defines foreign-final-demand reliance as `100 × FFD_DVA / VALU`. Thus omitting taxes from a reconstructed denominator would change the concept; the existing comparison uses the publisher's actual `VALU` and requires no denominator substitution. The [2025 ICIO annex](https://webfs-sti.oecd.org/files/STI-PIE/ICIO/2025/ICIO2025annex.pdf), SHA-256 `16809b1684d44cf7f1ac4e410a8bd08d8638dce80678ef1bb0b26e17242c9cb5`, confirms 80 target economies plus ROW and 50 activities. The [publisher ICIO page](https://www.oecd.org/en/data/datasets/inter-country-input-output-tables.html) states that TiVA uses the extended table with China/Mexico splits. The regular matrix must not be treated as an exact reproduction of published TiVA.

## TiVA: independently printed values remain inconsistent

The exact original selected-country CSV bodies (588 values across 21 series) are retained as small original-data fixtures with source URLs and checksums. All 196 country-years use total activity `_T`, world counterpart `W`, the same 1995–2022 coverage, current USD millions for levels and percentage points for shares.

Nine country-years exceed the existing 0.001pp comparison threshold: Japan/Germany/France in 1998, France in 1999, and India/Portugal/Japan/Germany/France in 2009. The largest signed residual is France 1998: `100 × 294533.93 / 1388825.064 − 21.209 = −0.0015824760316969625…pp`.

A separate interval diagnostic gives each independently serialized level ±0.0005 USD million and the share ±0.0005pp. These conservative intervals use the actual maximum three-decimal source precision, including omitted trailing zeros. **46/196 country-years have disjoint intervals**, including all nine existing failures. The smallest additional violation is India 2008; it is retained rather than rounded into an apparent match. Source-level rounding alone does not explain these discrepancies under the stated printed-value model. This is a diagnostic of the retained publications, not proof of an OECD implementation error or its cause. Common-release identity and exact first dissemination remain unverified.

Reproduce without database writes:

```sh
python -m finance_dashboard.tiva_diagnostics \
  --levels tests/fixtures/oecd_tiva/tiva_2025_levels.csv \
  --shares tests/fixtures/oecd_tiva/tiva_2025_shares.csv
```

## ICIO: signed localization, no rebalancing

The retained 2022 regular matrix is still exactly SHA-256 `fbab8fd2727bda9fd8c6cfee8227816db82d33bef6aa4b90194ca5dcbc5ad14b`, identified by the [World Bank replication catalogue](https://reproducibility.worldbank.org/catalog/511) as OECD's January 2026 update. The replica hash ledger agrees. All 4,050 nodes and source output vectors remain unchanged.

The new optional detailed audit reproduces **123 row and 26 column failures** at the existing four-decimal serialization bounds. All 26 failing columns belong to China. The largest is `CHN_L`, signed −82.0320 current USD millions. Of 123 row failures, 66 are real estate (`L`) and 24 are household-employer activity (`T`); the largest is `USA_L`, +238.6058 million, followed by `JPN_L`, +52.3301 million. Signed totals over *all* nodes are +670.1066 million for row-use-minus-output and −93.3633 million for column-input-plus-TLS-plus-VA-minus-output.

This concentration narrows the investigation but does not establish the cause. No publisher erratum or consistent replacement explaining these exact residuals was obtained. The default version-1 archived audit remains byte-reproducible; signed diagnostics are a separate opt-in output, never a rewrite of the prior manifest.

```sh
python -m finance_dashboard.icio --diagnose \
  --package /path/to/RR_WLD_2026_593.zip \
  --readme tests/fixtures/icio/ReadMe_ICIO_small.xlsx
```

## Historical matrix access evidence

The five original regular-history links published by OECD were requested by ordinary GET from both the local computer and the configured media server on 2026-11-04: `1995-2000_SML.zip`, `2001-2005_SML.zip`, `2006-2010_SML.zip`, `2011-2015_SML.zip`, and `2016-2022_SML.zip`. All ten attempts returned HTTP 403 Cloudflare responses. Exact response bodies, hashes, safe headers, timestamps, URLs and originating hosts are retained separately. This proves these attempts failed; it does not prove worldwide unavailability or license restrictions. No access control was bypassed. The later public-replica acquisition below expands historical availability without changing this publisher-direct access evidence.

The evidence package includes the original publisher Guide and annex, source CSVs, the precise signed/rounding diagnostic outputs, and those HTTP responses. It does not contain fabricated historical matrices, a balanced substitute, a claim of synchronized release vintages, or a completed G06 certificate.

## Integrated historical increment — 2016–2022 public replica

An ordinary unauthenticated download from the [public replica at immutable revision `9376a67717c1ab5f1ba24379ce5ea8669b72eacb`](https://huggingface.co/datasets/aditya1240/liberation-day-data/tree/9376a67717c1ab5f1ba24379ce5ea8669b72eacb/data/OECD_ICIO_SML_2016_2022) succeeded for **all seven 2016–2022 regular matrices**, totalling **616,342,717 original CSV bytes**. Each file matches the replica's LFS SHA-256 and byte count; the pins are explicit in `icio.py`. The 2022 bytes also match the independently retained World Bank original and ledger exactly. Matching dimensions and a replica's content hashes alone do not independently verify the earlier years' OECD update. Their publisher update and synchronized release remain unverified. The replica repository's MIT label does not supersede the OECD matrix's CC BY 4.0 rights, documented by the [World Bank source catalogue](https://reproducibility.worldbank.org/catalog/511).

Every matrix matches the existing original publisher ReadMe's complete 4,050 industry codes, 486 final-demand columns and ordering. The canonical ICIO adapter now stores CSV originals, ReadMe, computed audit and immutable manifest through the same atomic source bundle and append-only receipt boundary as the 2022 package. It does not create macro observations or substitute regular matrices for extended-table TiVA. All acquired years fail the existing serialization accounting tests:

| Year | Row failures | Column failures | Maximum absolute row residual, USD million | Maximum absolute column residual, USD million |
| --- | ---: | ---: | ---: | ---: |
| 2016 | 90 | 27 | 17.5126 | 5.8167 |
| 2017 | 126 | 32 | 120.8953 | 38.2013 |
| 2018 | 123 | 25 | 107.9849 | 37.9260 |
| 2019 | 96 | 34 | 100.8708 | 33.9345 |
| 2020 | 119 | 23 | 459.2797 | 146.3979 |
| 2021 | 41 | 25 | 8.7216 | 3.3677 |
| 2022 | 123 | 26 | 238.6058 | 82.0320 |

Every failing column belongs to China in every acquired year. Real-estate rows dominate failures in most years. This is a reproducible localization across multiple original files, not proof of a cause. The publisher's Guide, page 9, places the expenditure statistical discrepancy within final demand; its presence is not a justification for dropping the row identity. The original four-decimal row/column bounds remain **0.22685/0.20265 million USD**. No cell, output vector, negative value or tolerance is adjusted. Original 1995–2015 regular matrices, publisher-direct historical bytes and extended matrices remain missing.

Reproduce one historical acquisition using an already downloaded, hash-pinned original:

```sh
python -m finance_dashboard.icio --matrix /path/to/2021_SML.csv --year 2021 \
  --readme tests/fixtures/icio/ReadMe_ICIO_small.xlsx --root /path/to/source-evidence
```

`read_icio_evidence(root)` now returns the verified historical audits and explicit missing years alongside the retained 2022 evidence. Optional `include_residuals=True` derives signed diagnostics from the same original package; archived version-1 audit bytes are unchanged. Every reader rehashes complete originals and validates manifests/receipts. Independently reproduced audit digests are pinned by original SHA, ReadMe SHA, year and method version, avoiding repeated 130-million-cell accounting on cold API reads. Acquisition and explicit diagnostic commands still run the full calculation. Unknown combinations and altered audit payloads fail closed; no editable audit certificate is trusted.

`read_tiva_evidence(root)` now selects the canonical original TiVA pair by its acquisition receipts, validates source dimensions/attributes and both raw-body hashes, and recomputes the interval diagnostic. The actual local canonical pair still has **588 values, nine failures of the existing 0.001pp check, and 46 disjoint rounding intervals**. Partial pairs return explicit missing years and no fabricated full-history rounding result. This read-only integration adds no parallel diagnostic store and rewrites no sealed source manifest. Neither API certifies G06, original first publication or a common release.

Focused Docker verification passed **23 OECD tests with no skips**, including the real World Bank original, native TiVA fixtures, database ingestion and API integration. The seven full historical matrices were separately audited and retained through the same canonical store. Final integrated verification and backup/recovery results are recorded in the authoritative development plan; deployment is a separate operation.

The integrated `research_artifact_evidence` boundary now reads ICIO, TiVA and native CVM evidence independently; an explicitly supplied holdings root also enables the existing verified SEC and UCITS readers. Its holdings/profit outputs contain source dates and hashes, population/state/position/currency/identifier counts and unresolved scope flags, with no raw issuer or holding records. Missing holdings differ from holdings not checked. Corruption in one artifact fails that artifact without hiding valid evidence in the others. Five focused Docker artifact tests pass using canonical original excerpt stores, including byte-preservation, redaction and independent corruption checks. This is partial input evidence, not an additional certification registry.
