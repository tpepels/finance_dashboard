"""Phase 4 EUR/USD multi-asset risk, drawdown and portfolio comparison.

Uses the existing per-instrument validated vendor adjusted close and ECB EUR
translation, not close/price-index or hypothetical licensed ETF NAV histories.
Never aligns price bars by fabricated exchange business days. Global equity and
gold ETFs are investable proxies; issuer domicile is not geographic holdings.
"""
from __future__ import annotations

from datetime import date
from math import sqrt, isfinite
from typing import Any

VALUE_KEYS = {"EUR": "adjusted_close_eur", "USD": "adjusted_close"}


def _month(iso: str) -> int:
    day = date.fromisoformat(iso)
    return day.year * 12 + day.month - 1


def _label(month: int) -> str:
    return f"{month // 12:04d}-{month % 12 + 1:02d}"


def _monthly_prices(history: dict, currency: str) -> dict[int, tuple[float, str]]:
    if currency not in VALUE_KEYS:
        raise ValueError("Unsupported currency")
    if currency == "USD" and history["currency"] != "USD":
        raise ValueError("USD comparisons require USD-quoted instruments; no EUR-to-USD series fabricated")
    values = {}
    for row in sorted(history.get("observations", []), key=lambda record: record["date"]):
        level = row.get(VALUE_KEYS[currency])
        if level is None:
            continue
        number = float(level)
        if not isfinite(number) or number <= 0:
            raise ValueError("Nonpositive or nonfinite adjusted market price")
        values[_month(row["date"])] = (number, row["date"])
    return values


def _drawdown(levels: list[tuple[int, float]]) -> dict[str, Any] | None:
    if not levels:
        return None
    top_month, peak = levels[0]
    max_fraction = 0.0
    peak_at = trough_at = top_month
    for month, value in levels:
        if value > peak:
            peak, top_month = value, month
        decline = (value / peak - 1)
        if decline < max_fraction:
            max_fraction, peak_at, trough_at = decline, top_month, month
    recovered = None
    if max_fraction < 0:
        peak_value = next(value for month, value in levels if month == peak_at)
        for month, value in levels:
            if month > trough_at and value >= peak_value:
                recovered = _label(month)
                break
    return {"max_drawdown_pct": round(max_fraction * 100, 4),
            "peak_month": _label(peak_at), "trough_month": _label(trough_at),
            "recovery_month": recovered}


def _drawdown_path(levels: list[tuple[int, float]]) -> dict[int, float]:
    peak = 0.0
    result = {}
    for month, level in levels:
        peak = max(peak, level)
        result[month] = round((level / peak - 1) * 100, 6)
    return result


def _risk_measure(levels: list[tuple[int, float]]) -> dict[str, Any]:
    if len(levels) < 2:
        return {"annualized_return_pct": None, "annualized_volatility_pct": None,
                "max_drawdown": _drawdown(levels), "monthly_return_count": 0}
    returns = [level / previous - 1
               for (_, previous), (_, level) in zip(levels, levels[1:])]
    annualized = None
    vol = None
    if len(returns) >= 12:
        annualized = (levels[-1][1] / levels[0][1]) ** (12 / len(returns)) - 1
        mean = sum(returns) / len(returns)
        vol = sqrt(12 * sum((x - mean) ** 2 for x in returns) / (len(returns) - 1))
    return {"annualized_return_pct": round(annualized * 100, 4) if annualized is not None else None,
            "annualized_volatility_pct": round(vol * 100, 4) if vol is not None else None,
            "max_drawdown": _drawdown(levels),
            "monthly_return_count": len(returns)}


def _corr(x: list[float], y: list[float]) -> float | None:
    if len(x) < 12 or len(x) != len(y):
        return None
    mx, my = sum(x) / len(x), sum(y) / len(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    denx = sum((a - mx) ** 2 for a in x)
    deny = sum((b - my) ** 2 for b in y)
    return round(num / sqrt(denx * deny), 6) if denx > 0 and deny > 0 else None


def compare_market_histories(histories: dict[str, dict], definitions: dict[str, dict],
                             *, currency: str = "EUR",
                             weights: dict[str, float] | None = None) -> dict[str, Any]:
    """Last contiguous common calendar-month segment, never missing month fill.

    If weights are supplied the synthetic portfolio assumes fixed-weight
    monthly rebalancing. Its first and subsequent observations use only the
    same aligned monthly returns; no prices or returns are interpolated.
    """
    if currency not in VALUE_KEYS or len(histories) < 2 or len(histories) > 5:
        raise ValueError("Select 2–5 instruments and EUR or USD")
    keys = list(histories)
    if len(keys) != len(set(keys)) or any(k not in definitions for k in keys):
        raise ValueError("Unknown or duplicate asset IDs")
    if weights is not None:
        if set(weights) != set(keys):
            raise ValueError("Portfolio weights must cover every selected asset")
        if any(not isfinite(w) or w < 0 or w > 1 for w in weights.values()):
            raise ValueError("Invalid portfolio weights")
        if abs(sum(weights.values()) - 1.0) > 1e-8:
            raise ValueError("Portfolio weights must total exactly 100 percent")
    monthly = {}
    missing = []
    for sid in keys:
        history = histories[sid]
        if history.get("status") != "ready":
            monthly[sid] = {}
            missing.append(sid)
        else:
            monthly[sid] = _monthly_prices(history, currency)
            if not monthly[sid]:
                missing.append(sid)
    base = {
        "currency": currency,
        "source_instruments": keys,
        "status": "no_data" if missing else "ready",
        "missing_instruments": missing,
        "portfolio_rebalance": "end_of_month_fixed_weights" if weights is not None else None,
        "method": ("Last recorded trading close of each calendar month; Yahoo vendor adjusted "
                   "closes in native trading currency, or USD/GBP/CHF converted to EUR "
                   "using prior five calendar-day ECB EUR reference. All assets must "
                   "have actual prices within every shared month; the most recent "
                   "contiguous common monthly segment is used. Normalized at 100. "
                   "Returns are gross of transaction costs and portfolio taxes."),
        "historical_as_of": "app_ingestion_snapshot_not_source_publication_vintage",
        "caveats": ("Yahoo adjusted closes are vendor-defined, may be retrospectively revised, "
                    "and are not independently verified fund NAV or official index total "
                    "returns. The last trading date in one month may differ across venues. "
                    "ETF trading domicile, asset class and quoted currency are not "
                    "look-through country/sector holdings or regional concentration."),
        "instruments": [],
        "portfolio": None,
        "aligned_months": [],
        "excluded_common_months": 0,
        "correlations": [],
    }
    if missing:
        return base
    months = sorted(set.intersection(*(set(monthly[sid]) for sid in keys)))
    if not months:
        base["status"] = "insufficient_overlap"
        return base
    # Retain the most recent unbroken run, rather than bridging missing months.
    chain = [months[-1]]
    for m in reversed(months[:-1]):
        if m != chain[-1] - 1:
            break
        chain.append(m)
    chain.reverse()
    base["excluded_common_months"] = len(months) - len(chain)
    base["aligned_months"] = [_label(m) for m in chain]
    if len(chain) < 2:
        base["status"] = "insufficient_overlap"
        return base

    series_returns: dict[str, list[float]] = {}
    holdings = {}
    for sid in keys:
        definition = definitions[sid]
        price = monthly[sid]
        begin = price[chain[0]][0]
        levels = [(m, 100 * price[m][0] / begin) for m in chain]
        rets = [price[b][0] / price[a][0] - 1 for a, b in zip(chain, chain[1:])]
        series_returns[sid] = rets
        drawdowns = _drawdown_path(levels)
        asset = {
            "id": sid, "name": definition["name"],
            "asset_class": definition["asset_class"],
            "instrument_kind": definition["kind"],
            "benchmark": definition.get("benchmark"),
            "domicile": definition["domicile"],
            "trading_currency": definition["trading_currency"],
            "fund_base_currency": definition["fund_base_currency"],
            "index_method": "vendor_adjusted_close",
            "geographic_holdings_status": "not_verified",
            "observations": [
                {"month": _label(m), "last_trade_date": price[m][1],
                 "index_100": round(value, 6), "drawdown_pct": drawdowns[m]}
                for m, value in levels],
            **_risk_measure(levels),
        }
        base["instruments"].append(asset)
        holdings[sid] = {"asset_class": definition["asset_class"],
                         "trading_currency": definition["trading_currency"],
                         "domicile": definition["domicile"],
                         "weight_pct": round(weights[sid] * 100, 4) if weights else None}
    if weights is not None:
        values = [(chain[0], 100.0)]
        for i, month in enumerate(chain[1:]):
            monthly_portfolio_return = sum(weights[sid] * series_returns[sid][i]
                                           for sid in keys)
            values.append((month, values[-1][1] * (1 + monthly_portfolio_return)))
        portfolio_drawdowns = _drawdown_path(values)
        base["portfolio"] = {
            "weights_pct": {sid: round(weights[sid] * 100, 4) for sid in keys},
            "exposure_metadata": holdings,
            "holdings_country_weights": "not_available_without_verified_holdings_history",
            "observations": [{"month": _label(month), "index_100": round(value, 6),
                              "drawdown_pct": portfolio_drawdowns[month]}
                             for month, value in values],
            **_risk_measure(values),
        }
    for i, left in enumerate(keys):
        for right in keys[i+1:]:
            base["correlations"].append({
                "left": left, "right": right,
                "monthly_return_pearson": _corr(series_returns[left], series_returns[right]),
                "sample_monthly_returns": len(series_returns[left]),
            })
    return base
