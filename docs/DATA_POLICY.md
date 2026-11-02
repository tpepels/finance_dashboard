# Data integrity and provenance policy

1. **No invented observations.** A catalog entry is a source mapping, not a populated series. The app must distinguish no data, stale data and confirmed zero.
2. **No silent proxies.** US CAPE, domestic listed market-cap/GDP and global Buffett-style metrics are distinct measures. Label each accordingly.
3. **No unsupported world aggregates.** Record constituent coverage, country weights, source conventions and missing-country treatment.
4. **No hidden frequency conversion.** Preserve native observation periods. Missing daily values are not zero. Carry-forward is permitted only when explicitly justified for a state variable such as a policy-rate level.
5. **Revisions are first-class.** Preserve observed historical values, available publication vintages, ingestion timestamps and calculation versions. Do not claim real-time backtests on latest-revised data.
6. **Rights are evaluated per series.** FRED access does not authorize redistribution of third-party content. BIS publication is governed by BIS legal terms. World Bank WDI licenses can vary with indicator ownership; the catalog explicitly records the observed license and a review flag.
7. **Instrument identities matter.** BIS harmonized policy rates may splice policy instruments through history. Fed target corridor edges, ECB deposit facility and BIS rate are different series. Their legends must reflect these definitions.
8. **No false precision.** Historical coverage and publication latency must be inspected from actual provider responses in Phase 2, not inferred from marketing pages.

## Source references

- BIS central bank policy-rate series: https://data.bis.org/topics/CBPOL
- BIS REST documentation: https://stats.bis.org/api-doc/v2/
- ECB deposit facility: https://data.ecb.europa.eu/data/datasets/FM/FM.D.U2.EUR.4F.KR.DFR.LEV
- FRED documentation and terms: https://fred.stlouisfed.org/docs/api/fred/ and https://fred.stlouisfed.org/docs/api/terms_of_use.html
- World Bank indicators/API: https://data.worldbank.org/ and https://datahelpdesk.worldbank.org/knowledgebase/articles/889392
- ILO/UN labour-share SDG 10.4.1: https://unstats.un.org/sdgs/metadata/files/Metadata-10-04-01.pdf
