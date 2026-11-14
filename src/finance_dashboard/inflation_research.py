"""Observed consumer/asset inflation relationships using exact calendar joins.

No missing-value interpolation, backward-looking publication proxy, artificial
monthly housing prices, or causal claims. Annual overlapping changes are
displayed with their sample period; Fisher bands are only approximate and
do not account for time-series dependence.
"""
from __future__ import annotations

from datetime import date
from math import atanh, exp, isfinite, sqrt, tanh
from statistics import mean


def _clean(points):
    result={}
    for day, value in points or []:
        number=float(value)
        if isfinite(number) and isinstance(day,date) and number>0:
            result[day]=number
    return result


def _month_key(day:date)->int:
    return day.year*12+day.month-1


def _calendar_map(points):
    return {_month_key(day):v for day,v in _clean(points).items()
            if day.day==1}


def _complete_month_ends(points, *, max_date:date|None=None):
    """Last observed trading day in completed months only."""
    by={}
    for day,value in _clean(points).items():
        if max_date is not None and (day.year,day.month)>=(max_date.year,max_date.month):
            continue
        key=_month_key(day)
        if key not in by or day>by[key][0]:
            by[key]=(day,value)
    return {key:value for key,(_,value) in by.items()}


def _annual_change(values, span:int=12):
    return {t:100*(v/values[t-span]-1) for t,v in values.items()
            if t-span in values and values[t-span]>0}


def _monthly_bond_12m(points):
    # Swinkels publishes decimal *simple* monthly returns. No price-index
    # reconstruction or compounding across an unobserved month is allowed.
    values={_month_key(d):float(v) for d,v in points or []
            if isinstance(d,date) and isfinite(float(v)) and float(v)>-1}
    out={}
    for t in sorted(values):
        if all(k in values for k in range(t-11,t+1)):
            wealth=1.
            for k in range(t-11,t+1):
                wealth*=1+values[k]
            out[t]=100*(wealth-1)
    return out


def _quarter_averages(monthly):
    years={}
    for t,value in monthly.items():
        key=t//3
        years.setdefault(key,{})[t%3]=value
    return {q:mean(months.values()) for q,months in years.items()
            if len(months)==3}


def _quarterly_change(points):
    return {_month_key(d)//3:float(v) for d,v in _clean(points).items()
            if d.month in (1,4,7,10)}


def _pearson_pairs(pairs):
    n=len(pairs)
    if n<12:return None
    xs=[x for x,_ in pairs];ys=[y for _,y in pairs]
    mx,my=mean(xs),mean(ys)
    cov=sum((x-mx)*(y-my) for x,y in pairs)
    sx=sum((x-mx)**2 for x in xs);sy=sum((y-my)**2 for y in ys)
    return max(-1.,min(1.,cov/sqrt(sx*sy))) if sx>0 and sy>0 else None


def _ranks(values):
    order=sorted(range(len(values)),key=lambda i:values[i])
    rank=[0.]*len(values)
    j=0
    while j<len(order):
        k=j+1
        while k<len(order) and values[order[k]]==values[order[j]]:
            k+=1
        mid=(j+1+k)/2
        for pos in order[j:k]:rank[pos]=mid
        j=k
    return rank


def _rank_correlation(pairs):
    if len(pairs)<12:return None
    xs=_ranks([p[0] for p in pairs])
    ys=_ranks([p[1] for p in pairs])
    return _pearson_pairs(list(zip(xs,ys)))


def _ci(r, n):
    # Do not present as a formal uncertainty interval for autocorrelated
    # overlapping 12-month returns: flagged as i.i.d. *illustration only*.
    if r is None or n<=24:return None
    z=atanh(max(-.999999,min(.999999,r)))
    half=1.96/sqrt(n-3)
    return [round(tanh(z-half),4),round(tanh(z+half),4)]


def _date_label(t, quarter):
    year=(t//4 if quarter else t//12)
    period=(t%4 if quarter else t%12)
    return f"{year:04d}-" + (f"Q{period+1}" if quarter else f"{period+1:02d}")


def _joined(asset, inflation, *, lag=0):
    """Positive lag means asset leads inflation by that many periods."""
    keys=sorted(t for t in asset if t+lag in inflation)
    return [(t,asset[t],inflation[t+lag]) for t in keys]


def _analysis(asset, inflation, quarter:bool=False):
    pairs=_joined(asset,inflation)
    values=[(a,b) for _,a,b in pairs]
    coefficient=_pearson_pairs(values)
    valid=coefficient is not None
    lag_limit=8 if quarter else 12
    lagged=[]
    for lag in range(-lag_limit,lag_limit+1):
        rows=_joined(asset,inflation,lag=lag)
        corr=_pearson_pairs([(a,b) for _,a,b in rows])
        lagged.append({"lag":lag,"asset_leads_if_positive":True,
                       "pearson":round(corr,4) if corr is not None else None,
                       "n":len(rows)})
    rolling={}
    for years in (3,5,10):
        width=years*(4 if quarter else 12)
        points=[]
        for t in sorted(asset):
            rows=[(asset[k],inflation[k]) for k in range(t-width+1,t+1)
                  if k in asset and k in inflation]
            if len(rows)!=width:continue
            value=_pearson_pairs(rows)
            if value is not None:points.append([_date_label(t,quarter),round(value,4)])
        rolling[f"{years}y"]=points
    def regime(start,end):
        filt=[(a,b) for t,a,b in pairs if start <= t//(4 if quarter else 12) <= end]
        v=_pearson_pairs(filt)
        return {"start":start,"end":end,"n":len(filt),
                "pearson":round(v,4) if v is not None else None}
    return {
        "n":len(pairs),
        "first":_date_label(pairs[0][0],quarter) if pairs else None,
        "last":_date_label(pairs[-1][0],quarter) if pairs else None,
        "frequency":"Q" if quarter else "M",
        "pearson":round(coefficient,4) if valid else None,
        "spearman":round(_rank_correlation(values),4) if valid else None,
        "illustrative_independent_sample_95pct_ci":_ci(coefficient,len(pairs)),
        "rolling":rolling,
        "lead_lag":lagged,
        "regimes":[regime(1980,1999),regime(2000,2019),regime(2020,9999)],
        "scatter":[{"period":_date_label(t,quarter),"asset_change_pct":round(a,4),
                    "inflation_pct":round(b,4)} for t,a,b in pairs],
        "unverified_due_to_insufficient_coverage":not valid,
        "lag_definition":"positive lag k: correlate asset yoy[t] with consumer yoy[t+k]; not a causal test",
        "confidence_interval_note":"Fisher-z i.i.d. illustration; not HAC/bootstrap robust to overlapping annual changes or serial dependence",
    }


def inflation_assets(points:dict, *,today:date|None=None)->dict:
    cutoff=today or date.today()
    cpi=_calendar_map(points.get("us_cpi",[]))
    hicp=_calendar_map(points.get("ea_hicp",[]))
    cpi_yoy=_annual_change(cpi)
    hicp_yoy=_annual_change(hicp)
    fx=_complete_month_ends(points.get("usd_per_eur",[]),max_date=cutoff)
    equity=_complete_month_ends(points.get("equity_usd",[]),max_date=cutoff)
    gold=_calendar_map(points.get("gold_usd",[]))
    commodity={name:_calendar_map(points.get(name,[]))
               for name in ("brent","gas","maize","copper")}
    assets={}
    for name, series in [("equity_total_return_usd",equity),
                         ("gold_usd",gold),*commodity.items()]:
        changes=_annual_change(series)
        assets[name]={"asset_class":name,
                      "measurement":"total_return" if name.startswith("equity") else "reference_price",
                      "quote_currency":"USD",
                      "calendar_yoy":changes,
                      "inflation_denominator":"US_CPI_U",
                      "correlation":_analysis(changes,cpi_yoy),
                      "real_yoy":{t:100*((1+changes[t]/100)/(1+cpi_yoy[t]/100)-1)
                                   for t in changes if t in cpi_yoy and cpi_yoy[t]>-100},
                     }
    bond=_monthly_bond_12m(points.get("us_bond_returns",[]))
    assets["us_treasury_hypothetical_total_return_usd"]={
        "asset_class":"sovereign_hypothetical_10y","measurement":"compounded_yield_modelled_monthly_simple_return",
        "quote_currency":"USD","calendar_yoy":bond,
        "inflation_denominator":"US_CPI_U",
        "correlation":_analysis(bond,cpi_yoy),
        "real_yoy":{t:100*((1+bond[t]/100)/(1+cpi_yoy[t]/100)-1)
                     for t in bond if t in cpi_yoy and cpi_yoy[t]>-100},
    }
    for name, series in [("equity_total_return_eur",equity),
                         ("gold_eur",gold),*[(n+"_eur",v) for n,v in commodity.items()]]:
        converted={t:value/fx[t] for t,value in series.items()
                   if t in fx and fx[t]>0}
        changes=_annual_change(converted)
        assets[name]={"asset_class":name,"measurement":"total_return" if name.startswith("equity") else "reference_price",
                      "quote_currency":"EUR","calendar_yoy":changes,
                      "inflation_denominator":"EA_HICP",
                      "correlation":_analysis(changes,hicp_yoy),
                      "real_yoy":{t:100*((1+changes[t]/100)/(1+hicp_yoy[t]/100)-1)
                                   for t in changes if t in hicp_yoy and hicp_yoy[t]>-100}}
    housing={}
    for country,denominator in (("us",cpi),("ea",hicp),("de",None),("pt",None),("jp",None)):
        source=_quarterly_change(points.get(f"housing:{country}",[]))
        yoy=_annual_change(source,4)
        inflation=_annual_change(_quarter_averages(denominator),4) if denominator else {}
        housing[country]={
            "nominal_yoy":[[_date_label(t,True),round(v,4)] for t,v in sorted(yoy.items())],
            "consumer_inflation_matched":bool(denominator),
            "correlation":_analysis(yoy,inflation,quarter=True) if denominator else None,
            "excluded_reason":None if denominator else "Matching national CPI/HICP original not yet registered; no substitute inflation geography",
            "real_yoy":[[_date_label(t,True),
                         round(100*((1+yoy[t]/100)/(1+inflation[t]/100)-1),4)]
                        for t in sorted(yoy) if t in inflation and inflation[t]>-100],
        }
    # Serialize large intermediate arrays only when useful for charting. The
    # derived return/level histories share exact canonical month/quarter keys.
    clean_assets={}
    for name,row in assets.items():
        clean_assets[name]={**{k:v for k,v in row.items() if k not in ("calendar_yoy","real_yoy")},
            "nominal_yoy":[[_date_label(t,False),round(v,4)]
                           for t,v in sorted(row["calendar_yoy"].items())],
            "real_yoy":[[_date_label(t,False),round(v,4)]
                        for t,v in sorted(row["real_yoy"].items())]}
    return {
        "consumer_inflation":{
            "us_cpi_yoy":[[_date_label(t,False),round(v,4)] for t,v in sorted(cpi_yoy.items())],
            "ea_hicp_yoy":[[_date_label(t,False),round(v,4)] for t,v in sorted(hicp_yoy.items())],
        },
        "assets":clean_assets,"housing":housing,
        "limitations":[
            "Monthly rolling and contemporaneous 12-month changes overlap and are serially dependent; naïve Fisher confidence intervals overstate precision.",
            "Lag correlations are observational and are not evidence of exogenous shocks, causal pass-through, or market timing.",
            "World Bank named commodity benchmarks are not a diversified commodity total-return basket.",
            "Swinkels US sovereign monthly returns are hypothetical yield-modelled returns ending at the pinned source observation, not an investable bond fund.",
            "Gold is a monthly average; MSCI ACWI is a daily net total return index converted at month-end FX; mixed conventions can affect correlations.",
            "BIS country property price coverage and definitions differ; DE/PT/JP consumer matching is withheld until national CPI series are validated.",
            "EUR investor results use euro-area HICP and ECB USD/EUR reference values; returns are not hedged and do not reflect taxes or costs.",
        ],
    }
