"""Source-gated five-question Piketty research companion to existing L07.

All quantities come from independently accepted original WID series. Missing
or non-comparable observations remain empty; no GDP, equity-return, estate
proxy, synthetic population denominator or look-ahead substitution.
"""
from __future__ import annotations

from datetime import date
from math import isfinite


AREAS = ("US", "FR", "PT", "CN", "IN", "WORLD")
GROUPS = {"bottom50": .5, "middle40": .4, "top10": .1}
ORIGINAL = "https://wid.world/codes-dictionary/"


def _years(points):
    return {d.year: float(v) for d, v in (points or [])
            if isinstance(d, date) and d.month == 1 and d.day == 1
            and isfinite(float(v))}


def _line(values, scale=1.):
    return [[str(y), round(scale * v, 6)] for y, v in sorted(values.items())]


def _result(status, **values):
    return {"status": status, **values}


# WID group percentiles span the complete adult distribution without
# substituting quantile thresholds for group mean income. Upper tails are
# disjoint from the first nine deciles; a missing original remains absent.
INCIDENCE_GROUPS = (
    ("p00_10", "P0–10", 0.10), ("p10_20", "P10–20", 0.10),
    ("p20_30", "P20–30", 0.10), ("p30_40", "P30–40", 0.10),
    ("p40_50", "P40–50", 0.10), ("p50_60", "P50–60", 0.10),
    ("p60_70", "P60–70", 0.10), ("p70_80", "P70–80", 0.10),
    ("p80_90", "P80–90", 0.10), ("p90_99", "P90–99", 0.09),
    ("p99_99_9", "P99–99.9", 0.009),
    ("p99_9_100", "P99.9–100", 0.001),
)


def _growth_incidence(points, area):
    """Original per-percentile-group growth; no quantile or population inference."""
    originals = {
        key: {year: value for year, value in
              _years(points.get(f"piketty:{area}:income_distribution:{key}", [])).items()
              if year >= 1980 and value > 0}
        for key, _, _ in INCIDENCE_GROUPS
    }
    missing = [key for key, _, _ in INCIDENCE_GROUPS if not originals[key]]
    common = sorted(set.intersection(*(set(originals[key]) for key, _, _
                                       in INCIDENCE_GROUPS))) if not missing else []
    if len(common) < 2:
        return {
            "status": "awaiting_matched_originals",
            "reference_year": None, "comparison_year": None,
            "matched_years": len(common), "rows": [],
            "missing_groups": missing,
            "reason": ("No two original years contain all twelve identical-"
                       "population WID percentile averages. No growth-incidence "
                       "curve can be produced from partial country or percentile series."),
        }
    first, last = common[0], common[-1]
    results = []
    for key, label, weight in INCIDENCE_GROUPS:
        previous, latest = originals[key][first], originals[key][last]
        results.append({
            "group": key, "label": label,
            "population_weight": weight,
            "reference_average": round(previous, 8),
            "latest_average": round(latest, 8),
            "cumulative_real_growth_pct": round(100 * (latest / previous - 1), 6),
            "ratio_of_averages": round(latest / previous, 8),
        })
    return {
        "status": "available",
        "reference_year": first, "comparison_year": last,
        "matched_years": len(common),
        "rows": results, "missing_groups": [],
        "reason": ("Original WID group means for the same area, annual concept "
                   "and constant-price reference unit. Percentile membership "
                   "can change between years; this is not individual lifetime "
                   "income growth or a wealth-inheritance observation."),
    }


def _shares(points, area):
    """WID percentages are fractions, including legitimately negative net wealth."""
    concepts = {}
    anomalies = {}
    for concept in ("income", "wealth"):
        names = ("top1", "top10", "bottom50")
        originals = {name: _years(points.get(f"piketty:{area}:{concept}:{name}", []))
                     for name in names}
        common = sorted(set.intersection(*(set(v) for v in originals.values())))
        output = {name: {} for name in (*names, "middle40")}
        rejects = []
        for year in common:
            t1, t10, b50 = (originals[name][year] for name in names)
            middle = 1 - t10 - b50
            # Monotonic top groups, without assuming that the bottom half's
            # *net wealth* share must be positive.
            if t1 > t10 + .00001 or t10 > 1.25 or middle < -.05:
                rejects.append(year)
                continue
            for name, v in (("top1", t1), ("top10", t10),
                            ("bottom50", b50), ("middle40", middle)):
                output[name][year] = v
        concepts[concept] = {
            "status": "available" if output["top10"] else "awaiting_originals",
            "percentage_shares": {key: _line(v, 100) for key, v in output.items()},
            "observed_matched_years": len(output["top10"]),
            "first_year": min(output["top10"], default=None),
            "latest_year": max(output["top10"], default=None),
            "derived_middle40": True,
            "source_variables": (
                [("sptincj992" if area == "WORLD" else "sptinc992j"),
                 "p99p100", "p90p100", "p0p50"] if concept == "income"
                else [("shwealj992" if area == "WORLD" else "shweal992j"),
                      "p99p100", "p90p100", "p0p50"]),
            "excluded_inconsistent_years": rejects,
        }
        anomalies[concept] = rejects
    # Only one year common to *both* published concept distributions can
    # support a side-by-side income/wealth comparison. Do not display a 2025
    # wealth share alongside a 2023 income share as if contemporaneous.
    matched = sorted(
        {int(point[0]) for point in concepts["income"]["percentage_shares"]["top10"]}
        & {int(point[0]) for point in concepts["wealth"]["percentage_shares"]["top10"]}
    )
    def ratio(numerator, denominator):
        # Negative/near-zero net wealth at the bottom is economically possible.
        # Dividing by it can produce a meaningless concentration multiple.
        return round(numerator / denominator, 6) if denominator > 0.05 else None
    for concept in ("income", "wealth"):
        original = concepts[concept]["percentage_shares"]
        by_year = {name: {int(y): val for y, val in rows}
                   for name, rows in original.items()}
        concepts[concept]["top_to_bottom_ratios"] = {
            "top10_to_bottom50": [
                [str(year), ratio(by_year["top10"][year], by_year["bottom50"][year])]
                for year in matched
                if year in by_year["top10"] and year in by_year["bottom50"]
            ],
            "top1_to_bottom50": [
                [str(year), ratio(by_year["top1"][year], by_year["bottom50"][year])]
                for year in matched
                if year in by_year["top1"] and year in by_year["bottom50"]
            ],
        }
    return _result("available" if all(
        concepts[c]["status"] == "available" for c in concepts) else "partial",
        compared_years=matched, latest_comparable_year=matched[-1] if matched else None,
        concepts=concepts, notes=[
            "Pre-tax national income and net personal wealth use different WID ranking variables; never rank both by the same households.",
            "Middle 40% is the exact residual of source top 10% and bottom 50% shares, not an independently published observation.",
            "Negative net-wealth shares are valid because liabilities can exceed assets.",
        ])


def _growth(points, area):
    """Real per-adult WID original levels; aggregate gains use fixed percentile weights."""
    levels = {g: _years(points.get(f"piketty:{area}:income_avg:{g}", []))
              for g in (*GROUPS, "top1", "all")}
    common = sorted(set.intersection(*(set(v) for v in levels.values())))
    consistent = {}
    rejected = []
    for year in common:
        total = levels["all"][year]
        groups_sum = sum(weight * levels[group][year]
                         for group, weight in GROUPS.items())
        if total <= 0 or abs(total - groups_sum) / total > .025:
            rejected.append(year)
            continue
        consistent[year] = {group: series[year] for group, series in levels.items()}
    index = {group: {} for group in levels}
    if consistent:
        base = consistent[min(consistent)]
        for year, values in consistent.items():
            for group, value in values.items():
                if base[group] > 0:
                    index[group][year] = 100 * value / base[group]
    captures = []
    for year in sorted(consistent):
        if year - 1 not in consistent:
            continue
        total_change = consistent[year]["all"] - consistent[year-1]["all"]
        if abs(total_change) < 1e-12:
            continue
        group_contrib = {g: 100 * weight *
                         (consistent[year][g] - consistent[year-1][g]) / total_change
                         for g, weight in GROUPS.items()}
        captures.append({
            "year": year,
            "real_income_per_adult_change_pct": round(
                100 * total_change / consistent[year-1]["all"], 5)
                if consistent[year-1]["all"] > 0 else None,
            "contribution_to_change_pct": {
                g: round(value, 5) for g, value in group_contrib.items()},
            "contribution_sum_pct": round(sum(group_contrib.values()), 5),
        })
    return _result("available" if captures else "awaiting_matched_originals",
        real_per_adult_index={g: _line(v) for g, v in index.items()},
        change_contributions=captures,
        accepted_complete_years=sorted(consistent),
        rejected_source_identity_years=rejected,
        note=("WID original per-adult group averages are in a common source "
              "constant-price reference unit. Signed shares of changes use "
              "the same adult population weights; they may be negative or "
              "exceed 100%, especially in contractions. Neither GDP growth "
              "nor total national-income growth is substituted."))


def _ratios(points, area):
    series={kind: _years(points.get(f"piketty:{area}:ratio:{kind}", []))
            for kind in ("national", "private", "public")}
    # WID w-series are source fractions of net national income, NOT percent.
    common=sorted(set.intersection(*(set(x) for x in series.values())))
    out={k:{year:val for year,val in v.items() if isfinite(val)}
         for k,v in series.items()}
    differences={}
    for year in common:
        differences[year]=out["national"][year] - (
            out["private"][year]+out["public"][year])
    return _result("available" if common else "awaiting_matched_originals",
        percent_of_net_national_income={key:_line(val,100) for key,val in out.items()},
        matching_component_years=common,
        national_minus_private_public_pp=_line(differences,100),
        note=("Publisher-defined net national, private and public wealth "
              "relative to NET national income. Stocks divided by annual "
              "flow; 3.0 in WID equals 300%, not 3%. A residual can include "
              "nonprofit/corporate classification differences."))


def _return_vs_growth(points, area):
    income=_years(points.get(f"piketty:{area}:macro:net_national_income", []))
    capital=_years(points.get(f"piketty:{area}:macro:net_capital_income", []))
    wealth=_years(points.get(f"piketty:{area}:macro:net_national_wealth", []))
    capital_share=_years(points.get(f"piketty:{area}:macro:factor_capital_share", []))
    stock_yield, growth, gap = {}, {}, {}
    for year in sorted(set(income) & set(capital) & set(wealth)):
        if (year-1 not in income or year-1 not in wealth or
                income[year-1] <= 0 or income[year] <= 0 or
                wealth[year-1] <= 0 or wealth[year] <= 0):
            continue
        mean_stock=(wealth[year-1]+wealth[year])/2
        r=100*capital[year]/mean_stock
        g=100*(income[year]/income[year-1]-1)
        stock_yield[year], growth[year], gap[year]=r,g,r-g
    return _result("available" if gap else "awaiting_matched_originals",
        net_capital_income_to_mean_national_wealth_pct=_line(stock_yield),
        real_net_national_income_growth_pct=_line(growth),
        accounting_net_income_yield_minus_growth_pp=_line(gap),
        factor_price_capital_share_pct=_line(capital_share,100),
        matched_years=len(gap),
        note=("Net CAPITAL-INCOME FLOW relative to mean prior/current net "
              "national wealth STOCK, compared with real net national-income "
              "growth. WID monetary totals must have the same national "
              "constant-price reference and currency. The yield excludes "
              "capital gains and need not equal an individual investor's r. "
              "r−g does not mechanically imply rising wealth inequality. "
              "The factor-price capital share uses a mixed-income allocation "
              "and is context, not the numerator of this yield."))


def _composition(points, area):
    total=_years(points.get(f"piketty:{area}:macro:net_national_wealth", []))
    housing=_years(points.get(f"piketty:{area}:macro:national_housing_assets", []))
    business=_years(points.get(f"piketty:{area}:macro:national_business_assets", []))
    outputs={"housing":{}, "business_and_other_nonfinancial":{}, "residual":{}}
    for year in sorted(set(total) & set(housing) & set(business)):
        if total[year] <= 0:
            continue
        outputs["housing"][year]=100*housing[year]/total[year]
        outputs["business_and_other_nonfinancial"][year]=100*business[year]/total[year]
        outputs["residual"][year]=100*(total[year]-housing[year]-business[year])/total[year]
    return _result("available" if outputs["housing"] else "awaiting_matched_originals",
        composition_pct_of_national_wealth={k:_line(v) for k,v in outputs.items()},
        matched_years=len(outputs["housing"]),
        note=("National housing and business/non-financial asset stocks are "
              "not household equity portfolios. The algebraic remainder is "
              "shown explicitly; it is not asserted to be all financial "
              "wealth, nor an independently validated net foreign position."))


def piketty_findings(points:dict)->dict:
    """Produce five complete typed research findings with strict missing-data states."""
    rows=[]
    for area in AREAS:
        rows.append({
            "area":area,
            "concentration":_shares(points,area),
            "growth_capture":{**_growth(points,area),
                              "distribution_incidence":_growth_incidence(points,area)},
            "wealth_income":_ratios(points,area),
            "capital_vs_growth":_return_vs_growth(points,area),
            "composition":_composition(points,area),
            "inheritance":{
                "status":"awaiting_comparable_originals",
                "latest_year":None,
                "annual_inheritance_flow_pct":[],
                "reason":("No accepted original bequest/inheritance-flow series with "
                          "comparable national denominator, gift coverage and "
                          "transmission population is registered. The asset "
                          "composition does not measure inherited wealth."),
            },
        })
    return {
        "method_source":"WID.world original annual area bulk data and metadata",
        "methodology_url":ORIGINAL,
        "report_reference":{
            "title":"World Inequality Report 2026",
            "reference_year":2025,
            "world_income_top10_pct":53,
            "world_wealth_top10_pct":75,
            "world_income_bottom50_pct":8,
            "world_wealth_bottom50_pct":2,
            "reconciliation":{
                "state":"report_reference_separate",
                "reason":("The published world report reference is a fixed 2025 "
                          "snapshot with its own definitions. It is not a "
                          "verified observation from the accepted WID annual "
                          "area CSV pair and is never spliced into its histories."),
            },
            "basis":"2025 world PPP report methodology; fixed publication benchmark, not automatically recomputed or necessarily identical to current WID vintage",
            "url":"https://wid.world/document/world-inequality-report-2026/",
        },
        "areas":rows,
        "finding_order":["concentration","growth_capture","wealth_income",
                         "capital_vs_growth","composition","inheritance"],
        "limitations":[
            "Observed WID estimates use a source-published model and can be revised; last recorded year is not a retrieval or first-release vintage.",
            "Share concentration and wealth-to-income ratios are distinct from economic causation; changes in rankings and demographic composition can matter.",
            "Growth-capture observations require five original constant-price income group averages, exact consecutive years, and within 2.5% weighted total reconciliation; missing years are excluded.",
            "Net capital-income accounting flow divided by average national wealth is not a capital-gains-inclusive investment total return or proof of the r>g mechanism.",
            "National asset composition is not the composition of net personal wealth by income or wealth percentiles.",
            "No comparable inheritance original is registered; inheritance trend or contribution to wealth inequality is withheld.",
            "Published WIR 2026 world 2025 figures are an explicitly fixed historical benchmark and are not spliced into later or differently defined WID histories.",
        ],
    }
