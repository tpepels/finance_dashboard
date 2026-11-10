"""Evidence summaries for the overview: two dated sentences assembled only from a bundle's own values.

Each summary states the observed comparison with its date, then where the
measures agree or differ (or where a value sits in its own history). No
interpretation, forecast or threshold is added that the values do not carry;
an analysis without a builder, or without values, gets no summary.
"""
from __future__ import annotations

NAMES = {"US": "the United States", "JP": "Japan", "DE": "Germany", "FR": "France", "GB": "the United Kingdom",
         "CN": "China", "IN": "India", "EA": "the euro area", "PT": "Portugal", "IT": "Italy", "ES": "Spain",
         "NL": "the Netherlands", "G7": "the G7", "G20": "the G20"}
AGGREGATES = {"G7", "G20", "WORLD"}
BANKS = {"fed": "the Federal Reserve", "ecb": "the ECB", "boj": "the Bank of Japan"}
SHORT_BANKS = {"fed": "the Fed", "ecb": "the ECB", "boj": "the Bank of Japan"}


def _name(code: str, capital: bool = False) -> str:
    name = NAMES.get(code, code)
    return name[0].upper() + name[1:] if capital else name


def _names(codes: list[str]) -> str:
    names = [_name(c, capital=True).replace("The ", "the ") for c in codes]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _c01(v: dict) -> list[str]:
    rows = [r for r in v.get("clock", []) if r.get("area") not in AGGREGATES]
    if not rows:
        return []
    month = max(r["as_of"] for r in rows)
    order = ("expansion", "slowdown", "recovery", "contraction")
    counts = {p: [r["area"] for r in rows if r["phase"] == p] for p in order}
    parts = [f"{len(counts[p])} in {p}" for p in order if counts[p]]
    first_part, rest = parts[0].replace(" in ", f" of {len(rows)} economies in ", 1), parts[1:]
    listed = first_part + ("".join(f", {p}" for p in rest[:-1]) + f" and {rest[-1]}" if rest else "")
    first = f"In {month} the OECD leading indicators place {listed}"
    first += f" ({_names(counts['contraction'])})." if counts["contraction"] else "."
    g7 = next((r for r in v.get("clock", []) if r.get("area") == "G7"), None)
    diffusion = (v.get("diffusion") or {}).get("6m") or []
    bits = []
    if g7:
        bits.append(f"Across the G7, the indicator is in {g7['phase']}")
    if diffusion:
        d_month, d_value = diffusion[-1]
        bits.append(f"{d_value:.0f}% of US industries grew over the six months to {d_month[:7]}")
    second = "; ".join(bits) + "." if bits else ""
    return [first] + ([second] if second else [])


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _m01(v: dict) -> list[str]:
    ladder = {r["bank"]: r for r in v.get("ladder", []) if r.get("latest") is not None}
    if not ladder:
        return []
    day = max(r["as_of"] for r in ladder.values())
    levels = [f"{BANKS[b]} {'was ' if i == 0 else ''}at {ladder[b]['latest']:.2f}%"
              for i, b in enumerate(b for b in ("fed", "ecb", "boj") if b in ladder)]
    first = f"On {day} {_join(levels)}."
    moves = [f"{SHORT_BANKS[b]} {'moved ' if i == 0 else ''}{ladder[b]['change']:+.2f}{' points' if i == 0 else ''}"
             for i, b in enumerate(b for b in ("ecb", "fed", "boj") if ladder.get(b, {}).get("change") is not None)]
    clauses = [f"over the past year {_join(moves)}"] if moves else []
    gap = (v.get("gaps") or {}).get("eur_minus_usd") or []
    if gap:
        g_month, g_value = gap[-1]
        clauses.append(f"in {g_month} euro cash earned {abs(g_value):.2f} points {'less' if g_value < 0 else 'more'} than dollar cash")
    second = "; ".join(clauses)
    return [first] + ([second[0].upper() + second[1:] + "."] if second else [])


def _f03(v: dict) -> list[str]:
    rows = v.get("rows", [])
    gaps = [r for r in rows if r.get("credit_gap")]
    if not gaps:
        return []
    month = max(r["credit_gap"]["as_of"] for r in gaps)[:7]
    above = [r["area"] for r in gaps if r.get("gap_guide_band") == "above_10pp"]
    below = [r["area"] for r in gaps if r.get("gap_guide_band") == "below_2pp"]
    first = (f"In the BIS data to {month} private credit is more than 10 points of GDP above its trend in {_names(above)}"
             if above else f"In the BIS data to {month} no economy shown has private credit more than 10 points of GDP above its trend")
    first += f"; it is below trend or less than 2 points above it in {_names(below)}." if below else "."
    dsr = [r for r in rows if r.get("private_dsr")]
    high = [r["area"] for r in dsr if r["private_dsr"]["deviation_from_own_mean"] > 0]
    low = [r["area"] for r in dsr if r["private_dsr"]["deviation_from_own_mean"] <= 0]
    second = ""
    if dsr:
        second = "Debt service takes a larger share of income than its own long-run average in " + \
            (_names(high) if high else "none of them") + (f", and a smaller share in {_names(low)}." if low else ".")
    return [first] + ([second] if second else [])


def _v01(v: dict) -> list[str]:
    gauges = {g["key"]: g for g in v.get("gauges", [])}
    cape = gauges.get("cape")
    if not cape:
        return []
    pct = lambda g: round(100 * g["own_percentile"]) if g.get("own_percentile") is not None else None

    def position(g):
        p = pct(g)
        since = g["history_start"][:4]
        return (f"the highest reading since {since}" if p == 100 else f"the lowest reading since {since}" if p == 0
                else f"higher than {p}% of its history since {since}")
    first = (f"In {cape['as_of'][:7]} the US CAPE was {cape['latest']:.1f}, higher than {pct(cape)}% of months since "
             f"{cape['history_start'][:4]} (long-run mean {cape['own_mean']:.1f}).")
    parts = []
    if "pe" in gauges:
        parts.append(f"the trailing P/E was {gauges['pe']['latest']:.1f} ({position(gauges['pe'])})")
    if "excess_cape_yield" in gauges:
        e = gauges["excess_cape_yield"]
        parts.append(f"the excess CAPE yield was {e['latest']:.1f} points ({position(e)})")
    second = ("In the same month " + " and ".join(parts) + ".") if parts else ""
    return [first] + ([second] if second else [])


def _l02(v: dict) -> list[str]:
    rows = [r for r in v.get("economies", []) if r.get("parts")]
    if not rows:
        return []
    def share(r, key):
        return next((p["share"] for p in r["parts"] if p["key"] == key), None)
    wages = [(share(r, "compensation"), r["area"], r["year"]) for r in rows if share(r, "compensation") is not None]
    profit = [(share(r, "net_operating_surplus"), r["area"], r["year"]) for r in rows if share(r, "net_operating_surplus") is not None]
    out = []
    if wages:
        lo, hi = min(wages), max(wages)
        out.append(f"In the latest year published, wages took between {lo[0]:.0f}% of non-financial companies' value added "
                   f"({_name(lo[1])}, {lo[2]}) and {hi[0]:.0f}% ({_name(hi[1])}, {hi[2]}).")
    if profit:
        lo, hi = min(profit), max(profit)
        out.append(f"Net profit after depreciation took between {lo[0]:.0f}% ({_name(lo[1])}) and {hi[0]:.0f}% ({_name(hi[1])}).")
    return out


def _p03(v: dict) -> list[str]:
    under = v.get("underwater") or []
    if not under:
        return []
    month, value = under[-1]
    first = (f"At the end of {month} world equities (MSCI ACWI, US dollars) were " +
             (f"{abs(value) * 100:.1f}% below their previous peak." if value < 0 else "at a new high."))
    episodes = v.get("episodes") or []
    if not episodes:
        return [first]
    worst = min(episodes, key=lambda e: e["depth"])
    regained = (f"regained {worst['months_to_recover']} months after the low" if worst.get("months_to_recover") is not None
                else "not yet regained")
    return [first, f"The deepest fall in the data was {abs(worst['depth']) * 100:.0f}% ({worst['peak']} to {worst['trough']}), {regained}."]


BUILDERS = {"C01": _c01, "M01": _m01, "F03": _f03, "V01": _v01, "L02": _l02, "P03": _p03}


def summarize(analysis_id: str, values: dict | None) -> list[str]:
    builder = BUILDERS.get(analysis_id)
    if builder is None or not values:
        return []
    try:
        return builder(values)
    except (KeyError, TypeError, ValueError, IndexError):
        return []
