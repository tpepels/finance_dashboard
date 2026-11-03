# Phase 1 — discovery routes for the four free-data research targets

**Researched:** 2026-11-03. **Status:** documented research/source discovery; NOT source acquisition, rights clearance, dataset implementation, scientific measurement acceptance or a current-code gap analysis. The owner-approved **free/no-fee legally usable** policy remains binding. We have **not downloaded/validated full historical series**; findings are primary publisher URLs and concrete samples. This file is a source research record under the sole [development plan](DEVELOPMENT_PLAN.md).

## 1. Historical global equity issuer/index concentration

**Free historical fund holdings: VERIFIED primary originals.** SEC Vanguard Total World Stock Index Fund series **S000022482**, ETF share class **VT**, CIK **0000857489**, contains 2010–2015 original full holding schedules and current NPORT-P filing XML:
- [2010 annual report](https://www.sec.gov/Archives/edgar/data/857489/000093247111000016/intlequityindexfunds_final.htm) — original dated fund securities/financial reports.
- [2015 January schedule of investments](https://www.sec.gov/Archives/edgar/data/857489/000093247115005869/internationalequity_final.htm) — individual securities and market values.
- [2026 July original filing NPORT-P + XML](https://www.sec.gov/Archives/edgar/data/857489/000085748926000275/0000857489-26-000275-index.htm).
- [SEC 2016 final rule](https://www.sec.gov/rules/final/2016/33-10231.pdf) describes N-Q transition to N-PORT; original pre-2019 N-Q and N-CSR filings retain schedules of investments, and 2019 onward original quarterly N-PORT is publicly reported. [SEC original N-PORT dataset](https://www.sec.gov/data-research/sec-markets-data/form-n-port-data-sets).

**Exact research label:** "Vanguard Total World Stock Index Fund reported issuer concentration", with filing date vs holdings date, top-ten share and residual, share-class deduplication, fund-vs-index tracking and time-availability. It is **not historic MSCI ACWI constituents**. Original MSCI world issuer history remains unverified for zero-fee reuse; use a separate conditional original series. Price/weights must reconcile to source fund assets, not impute missing months.

## 2. Historical EU UCITS holdings

**Historical legally required reporting: ORIGINAL route found, automated reuse rights NOT established.**
- [UCITS Directive 2009/65/EC](https://eur-lex.europa.eu/legal-content/EN/ALL/?uri=CELEX%3A32009L0065), articles 69–75 and Schedule B (portfolio in annual/half-yearly reports; reports available to investors free).
- [iShares Core MSCI World UCITS ETF provider page and archive](https://www.ishares.com/uk/individual/en/products/251882/ishares-core-msci-world-ucits-etf) lists annual financial reports (2021–2025 and older).
- [Original iShares III plc 2021 annual report](https://www.ishares.com/uk/individual/en/literature/annual-report/ishares-iii-plc-en-annual-report-2021.pdf) and [2024 original annual report](https://www.ishares.com/uk/individual/en/literature/annual-report/ishares-iii-plc-en-annual-report-2024.pdf) contain **Schedules of Investments**; provider page offers current/recent holdings CSV.
- [BlackRock/iShares UK website terms](https://www.ishares.com/uk/individual/en/compliance/terms-and-conditions) limit copying, publishing, redistribution and creation of derivative works from website content; a free page is **not** an unrestricted bulk-ingest license.

**Research solution:** annual/semiyearly holdings observations with true fund/share class, reporting and filing dates. Verify holdings schedule completeness across 2015/2020/2024/2026; confirm permitted automated personal local processing before proposing a collector. Manual access to individual UCITS reports is feasible and distinct from a free machine-readable 10-year monthly database.

## 3. Worldwide listed-parent consolidated income

**Free original regional raw reports confirmed, not a complete worldwide panel:**
- [SEC XBRL standardized financial statement quarterly archive, 2009–2026](https://www.sec.gov/dera/data/financial-statement-data-sets.html); US reporting entities and other registrants, including original accounting concepts/periods.
- [ESEF filings.xbrl.org](https://filings.xbrl.org/docs/about), including original reports, xBRL-JSON and [API](https://filings.xbrl.org/api/filings); ESEF official European financial-report regime [ESMA](https://www.esma.europa.eu/issuer-disclosure/electronic-reporting). XBRL repository self-reports incomplete (notably Germany and Ireland) and has its own no-restriction policy (underlying national issuer rights still need review).
- [ESMA official open-source ESEF toolkit](https://github.com/European-Securities-Markets-Authority/esef_toolkit) notes original national filings and incomplete third-party collection.
- [Brazilian securities regulator CVM DFP original annual company financial statements](https://dados.cvm.gov.br/dataset/cia_aberta-doc-dfp) and [ZIP archives 2010–2026](https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/) with source-defined consolidated-versus-parent report and restatement selections.
- [South Korean regulator OpenDART original financial reports](https://opendart.fss.or.kr/intro/main.do) and [primary data API](https://opendart.fss.or.kr/guide/main.do?apiGrpCd=DS003); OpenDART requires free key and terms review.
- [UK Companies House free iXBRL monthly accounts packages](https://download.companieshouse.gov.uk/en_accountsdata.html); coverage includes private companies and must be filtered for listed entities.

**Proposed original academic measure:** a regionally sampled, **coverage-labelled** listed-parent consolidated net income panel. Need company identifiers, consolidation status, fiscal-to-calendar mapping, parent-vs-subsidiary eliminations, GAAP vs IFRS net income comparability, all sign-correct earnings (including negative), currency rates, historical filing availability, issuer universe denominator, and global-market representation. This is NOT verified complete world listed corporate profits/GDP. Such a universal label must remain conditional unless its coverage is scientifically defended. Regional accounting profit/GDP and OECD national accounts surplus/GDP are distinct alternative questions, not substitutes.

## 4. Global equity and bond original total-return histories

**Free sources and partial alternatives:**
- [MSCI public index search](https://app2.msci.com/products/index-data-search/) gives official net/gross/price index returns and historic search controls; **rights to a complete no-fee programmatically downloadable original monthly level series unverified**.
- [MSCI member dataset at CFA Institute](https://rpc.cfainstitute.org/msci) describes **monthly MSCI net-total-return index levels** but is for **CFA members**, so a required paid membership does **not meet strict no-fee accessibility** without qualifying already-owned membership.
- [Vanguard VT original ETF product page](https://advisors.vanguard.com/investments/products/vt/vanguard-total-world-stock-etf) displays historic NAV total returns, with an **Export returns data** control and fund inception in 2008; export date coverage and reuse rights must be checked. VT fund net-of-fees performance ≠ exact MSCI/FTSE index net-return levels.
- [iShares Core Global Aggregate Bond UCITS AGGG provider](https://www.ishares.com/ch/professionals/en/products/291773/ishares-global-aggregate-bond-ucits-etf-fund) reports historical NAV-based fund total returns, with gross income reinvested, from 2017-era launch; [fund factsheet](https://www.ishares.com/uk/professional/en/literature/fact-sheet/aggg-ishares-core-global-aggregate-bond-ucits-etf-fund-fact-sheet-en-gb.pdf) has annual fund vs Bloomberg benchmark returns; continuous downloadable monthly index history **not yet verified**, nor public bulk-reuse license.
- [Kenneth French original research portfolio histories](https://mba.tuck.dartmouth.edu/pages/faculty/Ken.French/data_library.html) and [Damodaran historical U.S. stocks/bonds/gold returns](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/histretSP.html) are no-fee *different* return universes.

**Research recommendation:** strict original-ETF monthly NAV-distributions reinvested comparison **only if** fund history/export and rights are validated, labelled fund not index. For robust longer periods use explicit region academic portfolio data and original U.S. bond histories separately. Global bond index official monthly full history beyond 2017 and exact original ACWI NETR monthly returns at zero no-fee rights remain open.

## Status and source-review policy

| Target | Discovered free original evidence | Exact original benchmark complete? | Right to programmatic local research use |
|---|---|---|---|
| Global historical concentration | VT 2010/2015+SEC 2019 onward fund schedules | **No:** actual global **fund** portfolio, not MSCI ACWI | SEC public filings; respect SEC fair access/original terms |
| UCITS fund histories | iShares III 2021/2024 reports and historical archive | **Partial:** genuine dated fund reports, missing full 2015–2026 interval verification | **Restricted/uncertain** for systematic iShares web content extraction |
| Worldwide listed profits | SEC + ESEF + CVM + OpenDART + UK filings | **No:** geographically/issuer incomplete, no global deduplication | Mixed original regulator terms; check issuer rights and data format |
| Global stocks/bonds total returns | MSCI public historic output, VT return export, AGGG 2017+ reporting | **No:** original free global equity + bond index paired complete monthly history unverified | ETF vendor/member-only index limits require rights check |

**Research priorities without application development:** validate SEC 2010–2019 VT full holdings schedules and filing-date chronology; validate 2015/2020/2024/2026 annual/half-yearly iShares schedules and their permitted use; test cross-source GAAP/IFRS net-profit and issuer identities *scientifically*; verify source-legal original monthly global equity/bond benchmark exports and methods. These are **discovery/definition gates**; the developer remains paused, no code or implementation-gap audit is authorized.
