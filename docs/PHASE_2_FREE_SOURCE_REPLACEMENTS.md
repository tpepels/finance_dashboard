# Phase 2 source substitution decision — 2026-11-02

**Authority:** Owner approved replacing the two inaccessible original indicators with free macroeconomic indicators after confirming no institutional access. The initial proposed corporate geographic scope was **OECD**; the implemented Eurostat **EU27** fallback is a narrower, separately disclosed implementation deviation, not automatically approved as equivalent. Original measures are preserved in [the superseded-definitions archive](../definitions/superseded_series.json).

## Replacement 1: MSCI ACWI index concentration

- **Original (retired from active catalogue):** `concentration.global.top10`, implied uninterrupted historical *monthly* history of actual MSCI ACWI 892400 free-float-adjusted index constituent weights.
- **New canonical series:** `concentration.global.msci_acwi_published_top10` (monthly-indexed points, **sparse**).
- **Evidence:** 8 dated MSCI ACWI factsheets or independent source publications with verifiable top-ten constituent sum values, 2019, 2020, 2021, 2023, 2024, 2025 (two), 2026. [Dated evidence archive](../data/msci_acwi_published_snapshots.json).
- **Formula:** sum of the **top ten index security/share-class constituent weights** (not ten corporate issuers, and not ETF holdings). Publication figures are already a ten-weight total. The weight is independent of the factsheet presentation currency.
- **Contract:** Preserve exact report as-of day, URL, source type, value and original note per observation. Index `892400` only. Ingest historical month start as a reporting bucket, *not* a claim that the published observation is the first trading day of the month. No interpolation, forward-fill, ETFs, corporate issuer regrouping or inference of missing periods.
- **Limitation:** An irregular 8-snapshot series **does not provide a monthly historical time series**. It shows confirmed long-run markers; a time-axis chart should show disconnected points (or explicitly explain connecting lines do not imply intermediate measurement). This is the agreed freely accessible substitute.
- **Publishing:** MSCI factsheet redistribution terms not yet cleared. Internal/server-side processing and audit do not imply a public commercial redistribution licence.

## Replacement 2: corporation gross operating surplus

- **Original (retired from active catalogue):** `profit.global.corporate_share`, worldwide listed-company consolidated net earnings / world GDP.
- **Targeted free measure:** Corporate **gross operating surplus** as a share of total GDP, from official national/institutional-sector accounts. This includes listed and unlisted companies and differs from accounting net profit.
- **OECD access assessment:** The public OECD SDMX sector-account endpoint `DSD_NASEC1@DF_QSA_TRANSACTIONS_C` returned 403 to CI data requests and 406 to probed metadata requests on 2026-11-02; therefore an OECD-wide implementation cannot honestly be claimed.
- **Implemented fallback, clearly narrower:** Eurostat's **EU27_2020** consolidated geographic aggregate from official annual ESA2010 non-financial transactions `nasa_10_nf_tr`. This is not OECD and not worldwide. **S11 non-financial corporations** plus **S12 financial corporations**, both `B2A3G` gross operating surplus, divided by the same-year **S1 `B1GQ` GDP**, all in current millions EUR, multiplied by 100. `profit.eu27.corporate_operating_surplus_gdp` is the canonical ID and has **24 overlapping annual observations for 2002–2025** in a live 2026-11-02 official source sample.
- **Additional directly published comparator:** `profit.eu27.nonfinancial_gross_surplus_value_added`, Eurostat `nasa_10_ki`, `B2G_B3G_RAT_S11`, gross operating surplus as percent of the **non-financial corporation sector's gross value added**. Not GDP. Independent cross-check of the corporate profit share concept.
- **Geographic/methodology contract:** Never title these as 'world' or 'OECD', never present EU27 values with world GDP and never collapse separate S11/S12 and S1 observations. Missing years are omitted, not invented. Never compare directly against worldwide labour-income share without explaining geographic coverage mismatch.
- **Eurostat licence:** Eurostat reuse and attribution rules apply; before any public site must review and attribute. OECD data could be added later **under a new ID with OECD/country coverage**, not under the EU27 ID.

## Integration and acceptance

The replacement source registrations, three mapped charts and source-specific parsers are:
- [Canonical series](../definitions/series.json) and [charts](../definitions/charts.json).
- [MSCI documented snapshots](../src/finance_dashboard/concentration_snapshots.py) and [Eurostat official sector accounts](../src/finance_dashboard/eurostat_corporate.py).
- The existing [provider router](../src/finance_dashboard/providers.py), append-only PostgreSQL worker, FastAPI query/status routes and static browser-data export; no separate legacy pipeline.
- Negative tests for wrong index, missing evidence, wrong sector, currency, direction, geography, nonfinite measurements, duplicate periods and unmatched years.
- Full reproducible acceptance requires **39/39 mapped catalogue series**, **zero unresolved active definitions**, PostgreSQL/API readback, complete static export with rights metadata, and verified new-source observation counts.

**Completion boundary:** Once integrated full acceptance is green, the **implemented 39-series technical data pipeline** is verified. The OECD-vs-EU27 geographic scope deviation remains **open for owner acceptance or further OECD/UN source work**; do not claim that the proposed wider corporate geographic coverage is complete. This does **not** claim the unavailable original global listed-company earnings/GDP, a complete MSCI monthly index-constituent history, or full OECD geographic coverage.

This decision amends the previously locked [feature](PHASE_2_FEATURE_CONTRACT.md), [architecture](PHASE_2_ARCHITECTURE_CONTRACT.md) and [implementation](PHASE_2_IMPLEMENTATION_CONTRACT.md) contracts. Reverting to the original definitions requires a new, explicit source/scope decision.

## Geographic acceptance qualification (separate from technical CI)

The owner's `Ok, go ahead` followed a proposal for **OECD** corporate operating surplus/GDP as the initial geographical measure, with wider UN coverage only when defensible. The working **EU27 Eurostat** series was selected during implementation only after the OECD SDMX service was inaccessible from GitHub CI. **This EU27-only interim coverage was subsequently superseded by the verified official OECD38 GDP-weighted reporting-country aggregate.** The 39/39 mapped-source CI acceptance proves the **implemented EU27 data path**; it does not discharge the separate question of extending to OECD or UN-supported multi-economy geography. Do not call the originally proposed OECD corporate-data coverage implemented or fully close all Phase 2 scope requirements on the basis of a green CI run. The original unavailable global listed-company earnings/GDP and full historical monthly MSCI concentration series remain correctly archived as superseded, not reconstructed.

## Resolution of the OECD geographic gap — verified 2026-11-02

The preceding EU27-only restriction is **no longer the final source coverage**. A corrected request against the **official OECD annual** sector-account flow `OECD.SDD.NAD,DSD_NASEC10@DF_TABLE14,1.1`, with `format=csvfile`, returned actual no-key country S11 and S12 gross operating surplus. The first attempts against the OECD **quarterly** source returned 403/406 due to an inappropriate endpoint and request, not an institutional access requirement. [OECD source documentation](https://www.oecd.org/en/data/insights/data-explainers/2024/09/api.html).

The constructed `profit.oecd38.corporate_gross_surplus_gdp` uses OECD 2026's **38 member countries** (fixed retrospectively), per-country official S11 and S12 B2G gross operating surplus, and GDP from OECD GVA+net product taxes where the balance is reported. For **USA, Japan, Canada**, which supply corporate numerators but omit that GDP tax component, same-year nominal World Bank **local-currency** GDP is used only when its USD/JPY/CAD identity and value scale are verified. Country ratios are GDP-weighted using same-year WDI nominal USD GDP; years below 80% included-member GDP coverage, 29 contributing countries or 35/38 available GDP weights are omitted. Two companion series report GDP coverage % and member count, not hidden.

**[42/42 full historical PostgreSQL and FastAPI acceptance passed](https://github.com/tpepels/finance_dashboard/actions/runs/41503545569)** and **[42/42 full static source export passed](https://github.com/tpepels/finance_dashboard/actions/runs/41503489558)**, with **25 annual observations (2000–2024)** each for OECD surplus/GDP, OECD member-GDP coverage and contributing-member counts. Detailed source/formula/quality contract: [OECD_CORPORATE_SURPLUS.md](OECD_CORPORATE_SURPLUS.md). The EU27 series remains separately charted. The [locked geographic feature gate](PHASE_2_FEATURE_CONTRACT.md) is closed for the **GDP-weighted OECD reporting-country scope**, not for a fictitious official OECD all-member aggregate or worldwide listed-company net profits.
