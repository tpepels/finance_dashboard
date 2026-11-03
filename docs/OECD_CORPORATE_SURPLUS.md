# OECD corporate gross operating surplus: official-source methodology


> **Technical reference, not a separate development roadmap.** The sole current implementation path and phase acceptance are in [Development plan](DEVELOPMENT_PLAN.md). Historical phase files have been archived.

**Status (2026-11-02): VERIFIED.** [42/42-source historical PostgreSQL/FastAPI ingestion passed](https://github.com/tpepels/finance_dashboard/actions/runs/41503545569), with [42-series full static export](https://github.com/tpepels/finance_dashboard/actions/runs/41503489558). The OECD composite and each quality companion contain **25 annual observations, 2000–2024**. This document does **not** equate an incomplete-country sample to an official OECD-published aggregate.

## Purpose and economic interpretation

Construct a GDP-weighted OECD-member measure of annual corporate **gross operating surplus** as a proportion of national **GDP at market prices**. Corporate sector S11 (nonfinancial) plus S12 (financial), including **unlisted** corporations. This is neither accounting *net profits* of worldwide listed companies nor the OECD's own published aggregate. This is a combined national-accounts panel with source/data completeness gates.

The fixed 38-country membership comes from [OECD members and partners](https://www.oecd.org/en/about/members-partners.html), as of 2026; historical membership changes are **not** modeled. The code stores this precise country set and reports **contributing member count** and **nominal OECD GDP coverage** separately.

## Inputs

| Source | Indicator/dimension | Unit |
|---|---|---|
| [Official OECD annual sector accounts SDMX](https://sdmx.oecd.org/public/rest/dataflow/OECD.SDD.NAD/DSD_NASEC10@DF_TABLE14/1.1?references=all) | `DSD_NASEC10@DF_TABLE14`, S11 `D/B2G` gross operating surplus | Current national currency, millions (XDC; UNIT_MULT 6) |
| Same OECD national accounts | S12 `D/B2G` gross operating surplus | Same |
| Same OECD national accounts | S1 `D/B1G` gross value added and `C/D21X31` net taxes on products | Same |
| [World Bank WDI GDP in current USD](https://data.worldbank.org/indicator/NY.GDP.MKTP.CD) | `NY.GDP.MKTP.CD`, country-year | Current USD, for GDP weighting **only** |
| [World Bank WDI GDP in current LCU](https://data.worldbank.org/indicator/NY.GDP.MKTP.CN) | `NY.GDP.MKTP.CN`, country-year | Current local currency, **denominator fallback only** for USA, JPN and CAN |

Official OECD data API works **without a paid key** with an explicit *annual* source key and `format=csvfile`. Earlier attempts at the **quarterly** dataset with a malformed key/accept header returned 403/406; those responses did not indicate account entitlement.

## Formulas

For each reporting member (i), year (t):

[
GOS_{it} = GOS(S11)_{it} + GOS(S12)_{it}
]

[
GDP^{OECD}_{it} = GVA(S1)_{it} + (taxes\ on\ products - subsidies\ on\ products)_{it}
]

When the OECD S1 product-tax item is unavailable, use WDI **local nominal GDP divided by 1,000,000** only for three stable currencies: **USA/USD, Japan/JPY, Canada/CAD**; the currency observed in the OECD sector record must match, and WDI GDP must be within a bounded plausible ratio of OECD S1 GVA (0.9×–1.35×). The US/Japan/Canada original source gross-surplus numerators must still be observed; there is **no** imputation of sector profits. The controlled fallback recovers economically significant OECD coverage (US, Japan and Canada) missing from the OECD source's GDP decomposition, but **does not** extrapolate any other missing countries. No other geographic fallback is accepted, notably no historical FRF-versus-EUR mix.

Define (r_{it} = GOS_{it} / GDP_{it}), with (0\le r_{it}\le 1). Let (w_{it}) be WDI nominal USD GDP for member (i), year (t). The GDP-weighted OECD-reporting-country aggregate is

[
R_t = 100 \frac{\sum_{i\in E_t} w_{it} r_{it}}{\sum_{i\in E_t} w_{it}}
]

with (E_t) the subset of members whose national corporate numerator, national GDP denominator and nominal USD weighting all pass source validation. Define coverage (C_t=100\sum_{i\in E_t}w_{it}/\sum_{i\in W_t} w_{it}) where (W_t) are the 38 OECD members with valid WDI country GDP in year (t). Member count is \(|E_t|\).

An annual point is only eligible if **35 or more** of the 38 members have WDI GDP weights, **29 or more** members contribute full national ratios, and the included countries represent at least **80%** of the member GDP observed by WDI. Otherwise **all three outputs omit that year**. Zero values are not fabricated.

## Canonical identifiers and integration

- `profit.oecd38.corporate_gross_surplus_gdp` — GDP-weighted surplus share %, not official OECD published national share.
- `profit.oecd38.corporate_gross_surplus_gdp_coverage` — eligible OECD country GDP share %.
- `profit.oecd38.corporate_gross_surplus_member_count` — number of complete contributing country observations.

Source-code ownership: [oecd_corporate.py](../src/finance_dashboard/oecd_corporate.py) for source identity/normalization/computation, [providers.py](../src/finance_dashboard/providers.py) for transport and routing, standard append-only ingestion and API/static export for all three. [Focused offline regression tests](../tests/test_oecd_corporate.py) include malformed source keys, currency mismatch, duplicate inputs, nonfinite values, incomplete coverage, and WDI local GDP fallbacks.

**Provenance and limits:** Source OECD national accounts are revised; WDI weights/LCU denominators may have a different release vintage. OECD's public service limits requests to 60 downloads/hour, so routine extraction should be batched/cached. OECD data reuse rules apply; review publication attribution and licensing before any public deployment.

This expanded OECD data layer is intended to resolve the earlier OECD-versus-EU27 coverage deviation in the [free-source amendment](PHASE_2_FREE_SOURCE_REPLACEMENTS.md). **The existing EU27 indicators remain available and are not relabelled or overwritten.**

## Final 2026-11-02 acceptance record

[Full 42/42 mapped historical PostgreSQL and FastAPI verification](https://github.com/tpepels/finance_dashboard/actions/runs/41503545569) returned **25 years (2000–2024)** for the GDP-weighted OECD member aggregate, GDP share of participating countries and member count, and `PHASE2_ALL_MACRO_POSTGRES=PASS mapped=42 unresolved=0`. [Live complete static export](https://github.com/tpepels/finance_dashboard/actions/runs/41503489558) returned the same **25 + 25 + 25** observations with `STATIC_EXPORT_COMPLETE=42 MARKETS=24`. The full short offline backend/DB suite also passed after the local-GDP fallback fix. The previously open [OECD geographic-scope gate](PHASE_2_FEATURE_CONTRACT.md) is satisfied for the **defined GDP-weighted OECD member reporting coverage**, not for universal 38/38 country accounting completeness. The EU27 indicators remain mapped and independently available.
