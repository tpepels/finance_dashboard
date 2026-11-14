"""Distribution-aware, source-period-aligned wage research.

No mean can be inferred from percentiles; wage, labour compensation and
profit shares remain separate constructs. OECD full-time employee ratios
must not be combined with BLS CPS nominal weekly amounts as if identical
populations, currencies or statistical methods.
"""
from __future__ import annotations

from datetime import date
from statistics import mean
import math

AREAS = {"us": "United States", "de": "Germany", "fr": "France",
         "pt": "Portugal", "jp": "Japan"}
OECD_MEASURES = ("p90_p10", "p90_p50", "p50_p10", "minimum_median")


def _clean(points):
    return {d: float(v) for d, v in (points or [])
            if isinstance(d, date) and math.isfinite(float(v)) and float(v)>0}


def _annual_cpi(points):
    years = {}
    for d, v in _clean(points).items():
        if d.day != 1:
            continue
        years.setdefault(d.year, {})[d.month] = v
    return {date(y, 1, 1): mean(months.values()) for y, months in years.items()
            if len(months) == 12 and set(months) == set(range(1, 13))}


def _history(values):
    return [[d.isoformat(), round(v, 6)] for d, v in sorted(values.items())]


def _ratio(a, b):
    return {d: a[d]/b[d] for d in sorted(set(a)&set(b))
            if b[d] > 0 and a[d] > 0}


def _index(values):
    if not values:
        return []
    base = min(values)
    first = values[base]
    return _history({d: 100*v/first for d,v in values.items()})


def wage_distribution(points:dict) -> dict:
    """Return only source-supported historical comparisons.

    * US annual P10/P50/P90 are nominal BLS CPS weekly earnings;
    * CPI-real series use calendar-year averages of twelve monthly CPI-U NSA
      observations (missing any month withholds that year's real amount);
    * OECD source ratios already have consistent native denominator metadata;
    * the federal hourly minimum is not divided by a weekly wage. OECD
      minimum/median ratios are shown separately, for the OECD population.
    """
    wages = {q:_clean(points.get(q, [])) for q in ("p10","p50","p90")}
    cpi = _annual_cpi(points.get("us_cpi", []))
    years = sorted(set.intersection(*(set(v) for v in wages.values()))) if all(wages.values()) else []
    all_years=sorted(set().union(*(set(v) for v in wages.values())))
    excluded={q:[d.isoformat() for d in all_years if d not in wages[q]]
              for q in wages}
    if years:
        valid = [d for d in years if wages["p10"][d] <= wages["p50"][d] <= wages["p90"][d]]
        if len(valid) != len(years):
            raise ValueError("wage_percentile_order_violation")
    nominal = {q:{d:wages[q][d] for d in years} for q in wages}
    real = {q:{d:100*wages[q][d]/cpi[d] for d in years if d in cpi} for q in wages}
    ratios = {
        "p90_p10":_ratio(nominal["p90"],nominal["p10"]),
        "p90_p50":_ratio(nominal["p90"],nominal["p50"]),
        "p50_p10":_ratio(nominal["p50"],nominal["p10"]),
    }
    # Both series have explicitly different wage units. CPI adjustment
    # preserves USD/hour and never creates a min-to-weekly-median ratio.
    minimum_hourly = _clean(points.get("us_federal_min", []))
    real_minimum_hourly = {
        d: 100*rate/cpi[d] for d,rate in minimum_hourly.items() if d in cpi
    }
    published_real_median = _clean(points.get("p50_publisher_real", []))
    real_comparison = _ratio(real["p50"], published_real_median)
    # Publisher nominal/real CPS series and annual NSA CPI can differ by
    # index definition or vintage. Do not silently force their equality.
    unverified = [
        d.isoformat() for d, ratio in real_comparison.items()
        if not .98 <= ratio <= 1.02
    ]
    # This separate employer-establishment survey is the only observed
    # mean/median pair in this panel. Both figures must originate from
    # the identical OEWS all-occupations row for the identical May year.
    oews_means=_clean(points.get("oews_mean",[]))
    oews_medians=_clean(points.get("oews_median",[]))
    shared=sorted(set(oews_means)&set(oews_medians))
    missing_mean=sorted(set(oews_medians)-set(oews_means))
    missing_median=sorted(set(oews_means)-set(oews_medians))
    may_cpi=_clean(points.get("us_cpi",[]))
    oews_real={key:{
        d:100*source[d]/may_cpi[date(d.year,5,1)]
        for d in shared if date(d.year,5,1) in may_cpi
    } for key,source in (("mean",oews_means),("median",oews_medians))}
    oews={
        "population":"US OEWS all-occupations (SOC 00-0000) covered nonfarm wage and salary employment, full-time and part-time; excludes self-employed",
        "reference_period":"May of source year",
        "unit":"nominal USD/hour and CPI-U May 1982-84 purchasing-power USD/hour",
        "matched_years":len(shared),
        "first_year":shared[0].year if shared else None,
        "latest_year":shared[-1].year if shared else None,
        "nominal_hourly_usd":{
            "mean":_history({d:oews_means[d] for d in shared}),
            "median":_history({d:oews_medians[d] for d in shared}),
        },
        "mean_to_median_ratio":_history({
            d:oews_means[d]/oews_medians[d] for d in shared
        }),
        "mean_minus_median_hourly_usd":_history({
            d:oews_means[d]-oews_medians[d] for d in shared
        }),
        "real_hourly_1982_84_usd":{key:_history(values)
                                  for key,values in oews_real.items()},
        "real_index":{key:_index(values) for key,values in oews_real.items()},
        "withheld_source_years":{
            "mean":[d.isoformat() for d in missing_mean],
            "median":[d.isoformat() for d in missing_median],
            "may_cpi":[d.isoformat() for d in shared
                       if date(d.year,5,1) not in may_cpi],
        },
        "comparable_to_cps_weekly":False,
        "comparable_to_nonfarm_business_productivity":False,
        "no_top_income_share_or_causal_attribution":True,
    }
    us = {
        "population":"US CPS full-time wage and salary employees aged 16+; excludes self-employed; nominal usual weekly gross earnings",
        "nominal_weekly_usd":{q:_history(nominal[q]) for q in nominal},
        "real_weekly_1982_84_usd":{q:_history(real[q]) for q in real},
        "nominal_index":{q:_index(nominal[q]) for q in nominal},
        "real_index":{q:_index(real[q]) for q in real},
        "dispersion":{q:_history(ratios[q]) for q in ratios},
        "published_real_p50":_history(published_real_median),
        "cpi_annual_averages":_history(cpi),
        "real_median_reconciliation": {
            "compared_years":len(real_comparison),
            "outside_2_percent_years":unverified,
            "not_a_scientific_identity":True,
        },
        "nominal_federal_minimum_hourly":_history(minimum_hourly),
        "real_federal_minimum_hourly_1982_84_usd":_history(real_minimum_hourly),
        "real_federal_minimum_unit":"1982-84 purchasing-power USD per hour",
        "matched_years":len(years),
        "unmatched_percentile_years":excluded,
        "first_year":years[0].year if years else None,
        "latest_year":years[-1].year if years else None,
        "mean_wage_observed":False,
        "p99_wage_observed":False,
        "federal_minimum_to_weekly_median_computable":False,
    }
    countries=[]
    for area, name in AREAS.items():
        values={kind:_clean(points.get(f"oecd:{area}:{kind}", []))
                for kind in OECD_MEASURES}
        # All OECD ratios are already within full-time employee populations
        # and do not justify reconstructing any absolute wage percentile.
        latest={kind:({"year":max(v).year,"value":v[max(v)]} if v else None)
                for kind,v in values.items()}
        deciles=("p90_p10","p90_p50","p50_p10")
        comparable=(sorted(set.intersection(*(set(values[k]) for k in deciles)))
                    if all(values[k] for k in deciles) else [])
        errors={d:abs(values["p90_p10"][d]-
                      values["p90_p50"][d]*values["p50_p10"][d])/
                      values["p90_p10"][d]
                for d in comparable}
        countries.append({
            "area":area.upper(), "name":name,
            "population":"OECD full-time employees; national earnings definition, see original",
            "measures":{kind:_history(v) for kind,v in values.items()},
            "latest":latest,
            "minimum_median_unit":"percent_of_median_full_time_earnings",
            "decile_ratio_consistency":{
                "compared_years":len(comparable),
                "outside_3_percent_years":[d.isoformat() for d in comparable
                                           if errors[d]>.03],
                "max_relative_error_pct":round(100*max(errors.values()),3)
                                         if errors else None,
                "source_rounding_tolerance_pct":3,
            },
            "median_wage_level_available":False,
            "percentile_levels_available":False,
        })
    return {
        "us":us, "oecd":countries, "oews":oews,
        "limitations":[
            "Wage percentiles are employee earnings, not average compensation of all persons engaged.",
            "CPS weekly US levels and OECD ratios have different sampling and earnings definitions; no absolute cross-country wage comparisons.",
            "Matched US percentile histories exclude dates with a missing percentile, and OECD published ratio consistency is separately audited with a 3% relative tolerance; disagreements are displayed, not corrected.",
            "Annual CPI real purchasing power and output-price-deflated factor compensation must remain distinct.",
            "A US federal statutory minimum is not every worker's effective minimum; no 40-hour conversion is assumed.",
            "Mean earnings within CPS, P99 compensation, low-pay incidence and occupation decomposition require distinct publisher evidence.",
            "OEWS employer-based mean and median hourly wages are paired only with each other in the same May all-occupations survey year; never divide an OEWS mean by a CPS weekly median.",
            "OEWS annual estimates incorporate multiple survey panels and can change in coverage and occupation classifications; compare years descriptively rather than treating occupational reweighting as causal evidence.",
        ],
        "research_follow_ups":[
            "How did real P10/P50/P90 purchasing power diverge?",
            "Did minimum-to-median earnings change together with wage dispersion?",
            "How do labour's aggregate value-added share and the typical employee's earnings diverge?",
            "Can verified occupation-level data explain top-tail mean-to-median divergence?",
        ],
    }
