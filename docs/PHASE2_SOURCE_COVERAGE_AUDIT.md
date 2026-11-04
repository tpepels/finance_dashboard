# Phase 2 — approved-question source and empirical-evidence audit

**2026-11-03. Current state: source inventory recorded; the complete Phase 2 data corpus is NOT certified.**

Phase 1 is approved. This audit compares its 35 first-class analyses against the existing 53 registered macro series, 49 source/method references and the four preselected fallback hierarchies. Existing code registration is *not* original source acquisition or verified scientific coverage.

## Initial census

- 35/35 approved scientific question IDs now have an exact inventory record in `definitions/phase2_research_corpus.json`.
- 49 published sources are registered, with original references and HTTPS URLs.
- 26/35 scientific questions reference one or more existing macro series declarations. Those declarations may only cover a portion of a question's required data.
- 9/35 have no direct macro-series reference in the first-pass inventory: **F02, F04, F07, L05, L07, G03, G06, P01, P05**. Some have separate holdings or analytical code, but that is not a complete source.
- G01, G03, P01 and P02 have ordered, explicitly different fallback concepts documented; backups cannot silently inherit an original source's identity.
- **0/35 complete comparative data corpora are empirically certified by this first step.** Stored source histories and original release dates must still be checked on the user's running server.

## Source mapping per approved question

| ID | Existing source references (not completeness) | Unresolved original data and method requirement |
|---|---|---|
| **C01** | gdp.real_growth.us, gdp.real_growth.eu, gdp.real_growth.jp | CLI series and same-country IP/unemployment not in mapped macro definitions |
| **C02** | rates.us.treasury_10y_3m_spread, recession.us.sahm | As-of series release-date and NBER chronology not proven by two mapped current/revised series |
| **C03** | gdp.real_growth.world, gdp.real_growth.us, gdp.real_growth.eu, gdp.real_growth.cn, gdp.real_growth.in, gdp.real_growth.jp | Current real GDP growth mapped; WEO actual/forecast and publication vintages not verified |
| **C05** | gdp.real_growth.us | Real GDP output levels, monthly IP and employment recovery baselines not mapped |
| **C06** | gdp.real_growth.world, gdp.real_growth.us, gdp.real_growth.eu, gdp.real_growth.jp | IMF PCPIPCH and World Bank commodity series (except gold) not mapped |
| **M01** | policy_rate.us.bis, policy_rate.ea.bis, policy_rate.jp.bis, policy_rate.ea.ecb_dfr, policy_rate.us.fed_upper | BIS harmonized series and Fed upper-bound differ from exact overnight instruments; source matching needed |
| **M02** | bond.us.real_10y | Nominal DGS10, TIPS breakeven T10YIE and original decomposition not mapped |
| **M04** | policy_rate.us.bis, policy_rate.ea.bis, policy_rate.jp.bis | FX market source exists separately, cross-currency historical validity not established |
| **F01** | credit_gap.us.bis, credit_gap.ea.bis, credit_gap.jp.bis, credit.world.private_gdp_gap_coverage | Only three gap countries mapped; credit stock/GDP input and worldwide concept not established |
| **F02** | *No direct macro declaration* | Original BIS DSR household/corporate/total series absent |
| **F03** | credit_gap.us.bis, credit_gap.ea.bis, credit_gap.jp.bis | National BIS credit gap mapped; DSR original measures and crisis validation absent |
| **F04** | *No direct macro declaration* | OFR/Chicago Fed original financial stress and credit spread series absent |
| **F05** | fiscal.world.public_debt | Borrower-sector leverage and comparable private/public debt records incomplete |
| **F06** | credit_gap.us.bis, credit_gap.ea.bis, credit_gap.jp.bis | BIS RPP/CPP and matched CPI series not mapped |
| **F07** | *No direct macro declaration* | Fed Z.1 detailed NBFI funding and leverage series not mapped |
| **V01** | valuation.us.cape, bond.us.real_10y | CAPE mapped; original monthly Shiller data and real-yield sample alignment require evidence |
| **V02** | valuation.us.tobins_q | Only BEA Q1 mapped; exact published Q2/Q3 and component data absent |
| **V03** | valuation.world.global_trailing_pe, valuation.world.global_earnings_yield | Single Siblis worldwide ratio is not comparable regional index vendor valuation panel |
| **V05** | valuation.us.cape, equity.world.msci_acwi_netr_usd | CAPE + index return refs do not prove matured 10-year as-of total-return outcomes |
| **L01** | labour.us.nonfarm_productivity, labour.us.nonfarm_hourly_comp, prices.us.nonfarm_output_deflator, labour.us.nonfarm_real_compensation_cpi | US nonfarm source trio mapped; sector-matched global OECD series not yet mapped |
| **L02** | labour.us.pwt_labour_share, labour.jp.pwt_labour_share, labour.de.pwt_labour_share, labour.fr.pwt_labour_share, labour.it.pwt_labour_share, labour.us.nonfarm_labour_share_index | PWT labour-share variants present; matched S11 GVA, operating surplus and self-employment imputation absent |
| **L03** | profit.eu27.nonfinancial_gross_surplus_value_added, profit.oecd38.corporate_gross_surplus_gdp | Corporate gross operating surplus ratios are not net surplus/current-cost productive capital stock |
| **L04** | profit.eu27.nonfinancial_gross_surplus_value_added, profit.oecd38.corporate_gross_surplus_gdp | OECD accounts module exists; exact theoretical s/v and s/(c+v) methodology inputs not established |
| **L05** | *No direct macro declaration* | Official Fed DFA distribution groups original series not in mapped macro catalogue |
| **L07** | *No direct macro declaration* | WID and UNU-WIDER original historical series not mapped |
| **G01** | concentration.global.msci_acwi_published_top10 | Sparse official MSCI top-ten mapped; continuous issuer weights and VT source coverage/identity not audited |
| **G02** | valuation.world.listed_market_cap_usd, valuation.world.listed_market_cap_world_gdp | Domestic listed capital and world GDP mapped; actual free-float index-country weights absent |
| **G03** | *No direct macro declaration* | SEC filer profit sample is not global ultimate-parent consolidated income coverage |
| **G05** | credit.world.private_gdp_gap, credit.world.private_gdp_gap_coverage | World constructed gap is not BOP current-account / NIIP; true international balance rows absent |
| **G06** | *No direct macro declaration* | Original OECD ICIO full matrices and TiVA source keys absent |
| **P01** | *No direct macro declaration* | SEC NPORT component exists but exact 2015–2026 European UCITS history and as-of metadata not verified |
| **P02** | equity.world.msci_acwi_netr_usd, gold.usd.monthly_average, gold.world.equity_correlation | Gold/ACWI refs exist; original global bond total return and exact monthly/FX alignment absent |
| **P03** | equity.world.msci_acwi_netr_usd | An index level reference is not a portfolio total-return drawdown event corpus |
| **P04** | bond.us.real_10y | Yield refs exist, but complete portfolio duration/FX/inflation source rows missing |
| **P05** | *No direct macro declaration* | Market/portfolio code exists; original as-of holdings, dated cost/fund history evidence not complete |

## Implemented Phase 2 structural foundation

- Machine-readable registry: `definitions/phase2_research_corpus.json`.
- Research-corpus validator/report: `src/finance_dashboard/research_corpus.py`.
- Read-only API: `GET /api/research-corpus` and `GET /api/research-corpus/{analysis_id}`. The API joins current stored-source period counts but never promotes a partially populated economic question to scientifically validated.
- Independent contract tests: `tests/test_research_corpus.py`; local test run not yet verified.

## Full Phase 2 acceptance — not yet met

1. Exact original source and fallback evidence, or explicit unavailable/conditional state, for every required measure across all 35 analyses.
2. Actual source period ranges, missing periods, original units/regions/sectors and proven native frequency from real downloaded observations.
3. Original first-publication/release date and vintage history separately from local ingestion `first_seen_at`; reconciliation and source corrections.
4. Full primary/fallback source acquisition and backfill, preserving existing SQLite observations, local files and recoverable backups.
5. Exact reconciliation, report/filing dates, method version and source-value sampling for ETF holdings, corporate profits and market returns.
6. Automated original-source, failure, data provenance, historical-consistency, backup/restore and regression tests on the integrated running corpus.

These are **Phase 2 tasks**, not deferrals to later phases. The earlier 80/80 operational source-history count is not scientific evidence that all approved analysis questions are complete.

## Dated 2026-11-04 follow-up — ALFRED release-time source histories

The Phase 2 code now supports eight additional original source mappings for BIS DSR, 10 further nominal/real-rate/Brent/CPI/stress/BEA series, four Fed DFA net-worth groups plus other original activities/imbalances, and eight BIS property series, totaling **93 registered macro series**. New source adapters/record IDs do not imply any observation is present. Nine ALFRED source-as-of histories can be captured, including four wealth-group histories, with real release-vintage snapshots retained. Full 35-analysis source/test/corpus acceptance remains open. Source tests have not run in this remote GitHub connector environment.

## Publisher evidence sampled independently — Federal Reserve Z.1, Q2 2026

On 2026-11-04, the original FRED/ALFRED series pages were checked for Q2 2026: broker-dealer financial assets **7,241,760**, liabilities **6,803,297**, broker-dealer repo funding liabilities **3,115,829** and US money-market-fund assets **8,441,374**, all **millions of USD**, quarterly end-of-period, not seasonally adjusted, shown with a September 11, 2026 update. The immutable reference is `data/reference/fed_nonbank_z1_2026q2.json` with four original source URL/series IDs and explicitly `api_retrieval_confirmed=false`, `local_database_import_confirmed=false`. It enables a concrete subsequent exact-source regression check without claiming that the app has imported those observations or the whole historical F07 corpus. This sample covers **only one observed quarter and one national institutional group**, not the global non-bank research question.

## Verified execution and original-source expansion — 2026-11-04

Local Docker verification passed **361 Python tests** (three optional PostgreSQL checks skipped in the image build); the entire suite also passed **361/361 without skips** against disposable PostgreSQL. Frontend verification passed 63 tests and the TypeScript/Vite build. The three previously reported test failures and SQLite thread-affinity warning did not recur in isolated verification. Two further tests were corrected to isolate source-evidence directories and SEC contact configuration inherited from the production environment, preserving their scientific assertions.

The pre-change media-server census found stored observations for **97/97 macro series, 24/24 market instruments and 3/3 FX currencies**, with **30/35 analyses referencing at least one stored macro input and 0/35 fully validated**. A fresh read-only probe again sampled 15/15 sources from 2024 with no failures. Original ALFRED authentication/as-of access succeeded. A pre-deployment SQLite/source-evidence backup was created and verified: `finance-20261104T100134162247Z.json`.

The source catalogue now declares **142** series, adding these original inputs:

| Input | Exact native definition and live parser evidence | Remaining limitation |
|---|---|---|
| L07: 24 WID series | US, France, Portugal, China, India and world; pre-tax national-income and net-personal-wealth shares for top 10% and bottom 50%; equal-split adults over 20. Country keys `sptinc992j`/`shweal992j`; world keys `sptincj992`/`shwealj992`. Original fractional shares remain fractions. | National files end in 2024; older world file ends in 2023. Country/concept starting dates differ and historical years are sparse. WID estimates are not interchangeable with UNU-WIDER survey income concepts; original release vintages and redistribution licence remain unestablished. |
| G06: 21 OECD TiVA series | Seven countries (US/France/Portugal/China/Japan/Germany/India), annual 1995–2022; publisher `FFD_DVA`, `VALU`, and published `FFD_DVA` share `PT_VA`, total activities `_T`, world counterpart `W`. Monetary values retain USD millions; shares retain percent. | Published country inputs do not supply the complete bilateral industry ICIO matrices or validate a Leontief reconstruction. Original full ICIO ZIPs returned HTTP 403 during testing. |

Original WID [bulk downloads](https://wid.world/data/) and [OECD TiVA 2025 edition metadata](https://data-explorer.oecd.org/vis?df%5Bag%5D=OECD.STI.PIE&df%5Bid%5D=DSD_TIVA_MAINLV%40DF_MAINLV&df%5Bvs%5D=1.1) identify the sources. OECD states that its January 2026 revision retains coverage through 2022; that is a fixed-edition publication bound, not a claim of contemporary 2026 economic observations. [OECD data terms](https://www.oecd.org/en/about/terms-conditions.html) require appropriate attribution and attention to applicable third-party conditions.

Each new collector preserves raw data and metadata in immutable content-addressed bundles under `/data/source-evidence`, with append-only acquisition receipts recording subsequent downloads, including A→B→A source reversals. Receipts distinguish retrieval from publication, retain hashes and are included in verified backups. `scripts/phase2_source_reconcile.py` independently selects raw CSV values and compares them with latest stored observations, disclosing database storage precision, missing periods and preserved formerly published periods. It never validates an entire analysis or fabricates release-time evidence.

Ordinary WID/TiVA refreshes reconcile the full downloaded histories, including corrections older than five years. Ingestion compares values at their actual SQLite/PostgreSQL storage representation to prevent unchanged originals from creating fictitious revisions; raw source strings remain preserved. Existing observation versions are retained.

Source coverage/research APIs now expose safe source identity, units, geography, frequency, gap diagnostics, source-release bounds and methodological links. Irregular publications do not receive invented calendar-gap counts. New nonunique source/date indexes make coverage aggregation use covering indexes without deleting revisions. The obsolete 53-source maintenance limit now follows the actual canonical catalogue.

All eight BIS debt-service histories match the publisher's current Q1 2026 release. Their expiry-bounded freshness rule follows the official [DSR page](https://data.bis.org/topics/DSR) and [release calendar](https://data.bis.org/release-calendar?m=216), September 14 to December 6, 2026. The [sample evidence](../data/reference/bis_dsr_2026q1.json) explicitly distinguishes successful API retrieval from DB ingestion and first-publication proof. Japan residential property ends Q4 2025 and world residential property Q1 2026 in both the application and exact live BIS responses; neither receives an unsupported blanket freshness exemption.

**Deployment, persisted new-source reconciliation and post-change recovery evidence are recorded below after execution.** Full Phase 2 acceptance remains open: original release-vintage histories, matched comparative coverage for all 35 questions, international income-concept comparators, complete ICIO matrices, original historical holdings, worldwide consolidated listed-company profits, and original global equity/bond total-return histories remain separate requirements. G03/P01/P05 still lack direct macro-series references; their separate adapters cannot silently establish complete original evidence.
