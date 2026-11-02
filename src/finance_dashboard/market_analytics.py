"""Investment-proxy analytics with explicit return, calendar and currency conventions."""
from __future__ import annotations

from datetime import date
from math import sqrt
from typing import Any


def _month_id(iso_day: str) -> int:
    day=date.fromisoformat(iso_day)
    return day.year*12+day.month


def monthly_returns(observations: list[dict], value_key: str) -> dict[int, float]:
    """Consecutive calendar-month ETF *adjusted-close returns*, no look-ahead."""
    last={}
    for row in observations:
        value=row.get(value_key)
        if value is None:
            continue
        month=_month_id(row["date"])
        # Data are ordered daily, so the last trading close is retained.
        last[month]=float(value)
    out={}
    for month in sorted(last):
        if month-1 in last and last[month-1] > 0 and last[month] > 0:
            out[month]=last[month]/last[month-1]-1
    return out


def rolling_gold_vs_global_etf(
    gold: dict, world: dict, *,
    months: int = 36, currency: str = "USD",
) -> dict[str, Any]:
    """Trailing Pearson correlation of *returns*, not price levels.

    SPDR Gold Shares (GLD) and Vanguard Total World Stock ETF (VT) are
    investable US-domiciled proxies. This is NOT the original requested
    licensed global-index/spot-gold correlation series.
    """
    if months < 12 or months > 120:
        raise ValueError("Rolling window must have 12–120 months")
    if currency not in ("USD","EUR"):
        raise ValueError("Only USD and EUR return conventions supported")
    key="adjusted_close" if currency=="USD" else "adjusted_close_eur"
    if gold.get("symbol")!="GLD" or world.get("symbol")!="VT":
        raise ValueError("Gold/world proxy identities must be GLD and VT")
    r1=monthly_returns(gold["observations"],key)
    r2=monthly_returns(world["observations"],key)
    common=sorted(set(r1)&set(r2))
    result=[]
    for i in range(months-1,len(common)):
        sequence=common[i-months+1:i+1]
        if any(b-a!=1 for a,b in zip(sequence,sequence[1:])):
            continue  # Never bridge missing month/FX history.
        x=[r1[m] for m in sequence]
        y=[r2[m] for m in sequence]
        mx=sum(x)/months
        my=sum(y)/months
        numerator=sum((a-mx)*(b-my) for a,b in zip(x,y))
        dx=sum((a-mx)**2 for a in x)
        dy=sum((b-my)**2 for b in y)
        value=numerator/sqrt(dx*dy) if dx>0 and dy>0 else None
        yr=(sequence[-1]-1)//12
        mo=(sequence[-1]-1)%12+1
        result.append({"month":f"{yr:04d}-{mo:02d}",
                       "correlation":round(max(-1,min(1,value)),8) if value is not None else None,
                       "observations":months})
    return {
        "id":f"proxy.gold_etf_world_etf_correlation_{months}m_{currency.lower()}",
        "status":"proxy_not_global_index",
        "title":f"GLD versus VT rolling {months}-month {currency} adjusted-return correlation",
        "source_instruments":["gld","vt"],
        "price_method":"Monthly last-trading-day vendor-adjusted closes; arithmetic monthly returns; trailing Pearson; full calendar months only",
        "currency":currency,
        "window_months":months,
        "caveats":"Gold ETF has fees, premium/discount and tracking differences from physical spot. VT is a fund, not a licensed global equity index total-return series. Foreign-exchange conversion changes EUR correlations. Source adjusted-close conventions may differ from issuer NAV.",
        "observations":result,
    }
