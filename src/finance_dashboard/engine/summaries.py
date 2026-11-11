"""Short findings from each bundle's computed values, with their own dates.

These are descriptive readings, not another acceptance engine. Missing or
withheld values produce no finding. Population and scenario boundaries stay
in the sentences so a summary also makes sense outside its chart.
"""
from __future__ import annotations

import math

NAMES = {"US": "the United States", "JP": "Japan", "DE": "Germany", "FR": "France",
         "GB": "the United Kingdom", "CN": "China", "IN": "India", "EA": "the euro area",
         "PT": "Portugal", "IT": "Italy", "ES": "Spain", "NL": "the Netherlands",
         "G7": "the G7", "G20": "the G20", "WORLD": "the world", "US_BLS": "US BLS nonfarm business"}
NAMES.update({iso: NAMES[short] for iso, short in {
    "USA": "US", "JPN": "JP", "DEU": "DE", "FRA": "FR", "GBR": "GB", "CHN": "CN",
    "IND": "IN", "PRT": "PT", "ITA": "IT", "ESP": "ES", "NLD": "NL"}.items()})
AGGREGATES = {"G7", "G20", "WORLD", "WLD"}


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _quarter(day: str) -> str:
    """Publisher quarterly periods are stored on the quarter's first day."""
    return f"{day[:4]} Q{(int(day[5:7]) - 1) // 3 + 1}"


def _name(code: str, capital: bool = False) -> str:
    name = NAMES.get(code, code)
    return name[0].upper() + name[1:] if capital else name


def _join(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _latest(series):
    rows = [row for row in series if len(row) == 2 and row[0] and _number(row[1])]
    return max(rows, key=lambda r: r[0]) if rows else None


def _focus(rows, key="area"):
    """A named comparator, never a claimed cross-country aggregate."""
    return next((r for r in rows if r.get(key) in {"US", "USA"}), rows[0] if rows else None)


def _ends(rows, key):
    lo, hi = min(rows, key=key), max(rows, key=key)
    return [lo] if lo is hi else [lo, hi]


def _c01(v):
    rows = [r for r in v.get("clock", []) if r.get("area") not in AGGREGATES and r.get("as_of") and r.get("phase")]
    if not rows:
        return []
    groups = {}
    for r in rows:
        groups.setdefault((r["phase"], r["as_of"]), []).append(_name(r["area"]))
    first = "OECD leading-indicator phases: " + "; ".join(
        f"{_join(names)} in {phase} ({day})" for (phase, day), names in groups.items()) + "."
    bits = []
    g7 = next((r for r in v.get("clock", []) if r.get("area") == "G7" and r.get("as_of")), None)
    if g7:
        bits.append(f"the G7 indicator is in {g7['phase']} ({g7['as_of']})")
    diffusion = _latest((v.get("diffusion") or {}).get("6m", []))
    if diffusion:
        bits.append(f"{diffusion[1]:.0f}% of US industries grew over the six months to {diffusion[0][:7]}")
    second = "; ".join(bits)
    return [first] + ([second[0].upper() + second[1:] + "."] if second else [])


def _c02(v):
    now = v.get("now") or {}
    spread, sahm = now.get("spread"), now.get("sahm")
    bits = []
    if spread and _number(spread.get("value")):
        bits.append(f"the 10-year minus 3-month Treasury spread was {spread['value']:.2f} percentage points ({spread['month']})")
    if sahm and _number(sahm.get("value")) and _number(now.get("threshold")):
        bits.append(f"Sahm was {sahm['value']:.2f} against its {now['threshold']:.2f}-point threshold ({sahm['month']})")
    if not bits:
        return []
    observed = [r for r in v.get("recessions", []) if r.get("curve_observed") and r.get("sahm_observed")]
    second = (f"Only {len(observed)} recession starts have both signal histories in this comparison; fixed warning windows do not establish predictive reliability."
              if observed else "These are observed indicators, not a recession probability or a timing instruction.")
    return ["Observed recession indicators: " + "; ".join(bits) + ".", second]


def _c03(v):
    rows = [r for r in v.get("strip", []) if r.get("area") not in AGGREGATES and _number(r.get("latest")) and r.get("year")]
    if not rows:
        return []
    chosen = _ends(rows, lambda r: r["latest"])
    return ["Latest actual real GDP growth ranged across the economies shown: " + "; ".join(
        f"{_name(r['area'])} {r['latest']:.1f}% ({r['year']})" for r in chosen) + ".",
        "These latest observations have their own years; they do not establish convergence over a common historical window."]


def _c05(v):
    episodes = [e for e in v.get("episodes", []) if any(e.get("measures", {}).values())]
    if not episodes:
        return []
    e = max(episodes, key=lambda r: r["start"])
    key = next(k for k in ("gdp", "payrolls", "industrial_production") if e.get("measures", {}).get(k))
    m = e["measures"][key]
    label = {"gdp": "Real GDP", "payrolls": "Payroll jobs", "industrial_production": "Industrial production"}[key]
    recovered = (f"regained its peak {m['months_to_recover']} months after the low" if m.get("months_to_recover") is not None
                 else "had not regained its peak within the observed history")
    peak, trough = (_quarter(m["peak"]), _quarter(m["trough"])) if key == "gdp" else (m["peak"], m["trough"])
    return [f"{label} fell {abs(m['depth']) * 100:.1f}% from {peak} to {trough} around the US recession starting {e['start']}, and {recovered}.",
            "Recovery lengths differ by activity measure; this retrospective episode does not identify the cause of the shock."]


def _c06(v):
    rows = [r for r in v.get("commodities", []) if _number(r.get("latest")) and r.get("as_of")]
    if not rows:
        return []
    chosen = _ends(rows, lambda r: r["latest"])
    return ["Commodity price changes over 12 months: " + "; ".join(
        f"{r['name']} {r['latest'] * 100:+.1f}% ({r['as_of']})" for r in chosen) + ".",
        "The inflation and growth comparisons describe coincidence across different frequencies, not a causal commodity effect."]


def _m01(v):
    labels = {"fed": "US EFFR", "ecb": "ECB deposit setting", "boj": "BoJ overnight call rate"}
    rows = [r for r in v.get("ladder", []) if r.get("bank") in labels and _number(r.get("latest")) and r.get("as_of")]
    if not rows:
        return []
    first = "Latest short rates: " + "; ".join(f"{labels[r['bank']]} {r['latest']:.2f}% ({r['as_of']})" for r in rows) + "."
    gap = _latest((v.get("gaps") or {}).get("eur_minus_usd", []))
    second = (f"ECB deposit setting minus US EFFR was {gap[1]:+.2f} percentage points in {gap[0]}; this compares a policy setting with a realized overnight rate."
              if gap else "A policy setting and realized overnight market rates are distinct measures.")
    return [first, second]


def _m02(v):
    now = (v.get("split") or {}).get("now")
    if not now:
        return []
    return [f"On {now['date']}, the US 10-year nominal yield was {now['nominal']:.2f}% and real yield {now['real']:.2f}%, a {now['breakeven']:.2f}-point breakeven.",
            "Breakeven compensation includes inflation risk and liquidity premia; it is not a pure expected-inflation forecast."]


def _m04(v):
    rows = [r for r in v.get("currencies", []) if _number(r.get("move_12m")) and r.get("move_as_of")]
    if not rows:
        return []
    r = next((r for r in rows if r["currency"] == "USD"), rows[0])
    first = f"The euro's 12-month log change against {r['currency']} was {r['move_12m']:+.1f}% ({r['move_as_of']})."
    second = (f"The euro-minus-{r['currency']} short-rate gap was {r['gap']:+.2f} percentage points ({r['gap_as_of']}); this is co-movement, not a causal FX estimate."
              if _number(r.get("gap")) and r.get("gap_as_of") else "Rate and currency co-movement does not establish causation.")
    return [first, second]


def _f01(v):
    rows = [r for r in v.get("economies", []) if _number(r.get("ratio")) and r.get("as_of")]
    r = _focus(rows)
    if not r:
        return []
    first = f"BIS private non-financial credit in {_name(r['area'])} was {r['ratio']:.1f}% of GDP ({_quarter(r['as_of'])})."
    second = (f"That ratio changed {r['ratio_change_5y']:+.1f} percentage points since {_quarter(r['ratio_5y_ago_as_of'])}; the published BIS denominator is retained."
              if _number(r.get("ratio_change_5y")) and r.get("ratio_5y_ago_as_of") else "The published ratio describes credit quantity, not lending quality or a world credit gap.")
    return [first, second]


def _f02(v):
    rows = [r for r in v.get("rows", []) if r.get("series") == "private" and _number(r.get("latest")) and r.get("as_of")]
    r = _focus(rows)
    if not r:
        return []
    first = f"Private-sector debt service in {_name(r['area'])} took {r['latest']:.1f}% of income ({_quarter(r['as_of'])})."
    second = (f"The burden changed {r['change']:+.1f} percentage points since {_quarter(r['back_as_of'])}; national household and corporate series have different income denominators."
              if _number(r.get("change")) and r.get("back_as_of") else "National household and corporate burdens use their own income denominators; they are not added.")
    return [first, second]


def _f03(v):
    rows = [r for r in v.get("rows", []) if _number((r.get("credit_gap") or {}).get("latest"))]
    r = _focus(rows)
    if not r:
        return []
    gap = r["credit_gap"]
    out = [f"In {_name(r['area'])}, credit/GDP minus its BIS trend was {gap['latest']:+.1f} percentage points ({_quarter(gap['as_of'])})."]
    dsr = r.get("private_dsr") or {}
    if _number(dsr.get("latest")) and _number(dsr.get("deviation_from_own_mean")):
        direction = "above" if dsr["deviation_from_own_mean"] > 0 else "below" if dsr["deviation_from_own_mean"] < 0 else "at"
        out.append(f"Private debt service was {dsr['latest']:.1f}% of income ({_quarter(dsr['as_of'])}), {direction} its own historical mean; joint readings are not a crisis probability.")
    return out


def _f04(v):
    rows = [r for r in v.get("gauges", []) if _number(r.get("latest")) and r.get("as_of")]
    if not rows:
        return []
    selected = [r for r in rows if r.get("key") in {"nfci", "ofr_fsi"}] or rows[:1]
    def reading(r):
        unit = "%" if r.get("key") == "high_yield" else ""
        relation = (f", {'above' if r['latest'] > r['own_mean'] else 'below' if r['latest'] < r['own_mean'] else 'at'} its own historical mean"
                    if _number(r.get("own_mean")) else "")
        return f"{r['name']} was {r['latest']:.2f}{unit} ({r['as_of']}){relation}"
    return ["; ".join(reading(r) for r in selected) + ".", "Each stress measure retains its own scale; these observations do not prescribe an exit trade."]


def _f05(v):
    rows = [r for r in v.get("economies", []) if _number(r.get("household")) and _number(r.get("corporate"))]
    r = _focus(rows)
    if not r:
        return []
    out = [f"In {_name(r['area'])}, household credit was {r['household']:.1f}% and non-financial corporate credit {r['corporate']:.1f}% of GDP ({_quarter(r['as_of'])})."]
    if _number(r.get("government")) and r.get("government_year"):
        out.append(f"Government debt was {r['government']:.1f}% of GDP ({r['government_year']}); annual public debt and quarterly private credit are separate exposures.")
    else:
        out.append("Sector stocks describe where debt sits; they do not identify creditors, debt quality or a single consolidated leverage ratio.")
    return out


def _f06(v):
    rows = [r for r in v.get("residential", []) if _number(r.get("change_5y_pct")) and r.get("back_as_of") and r.get("as_of")]
    if not rows:
        return []
    selected = _ends(rows, lambda r: r["change_5y_pct"])
    return ["Real residential property price changes: " + "; ".join(
        f"{_name(r['area'])} {r['change_5y_pct']:+.1f}% from {_quarter(r['back_as_of'])} to {_quarter(r['as_of'])}" for r in selected) + ".",
        "Price growth is not a price-to-income valuation or an estimate of default risk; commercial-property coverage differs."]


def _f07(v):
    r = v.get("latest") or {}
    if not _number(r.get("broker_leverage")):
        return []
    first = f"US broker-dealer financial assets were {r['broker_leverage']:.1f} times book equity"
    if _number(r.get("repo_share")):
        first += f", with repo at {r['repo_share']:.1f}% of liabilities"
    first += f" ({_quarter(r['as_of'])})."
    second = (f"Money-market fund financial assets were ${r['mmf_assets'] / 1e6:.1f} trillion ({_quarter(r['mmf_as_of'])}); asset size does not measure liquidity mismatch or run risk."
              if _number(r.get("mmf_assets")) and r.get("mmf_as_of") else "These sector totals do not measure fund liquidity mismatch or individual run risk.")
    return [first, second]


def _v01(v):
    gauges = {g["key"]: g for g in v.get("gauges", []) if _number(g.get("latest"))}
    cape = gauges.get("cape")
    if not cape or not _number(cape.get("own_percentile")):
        return []
    first = f"US CAPE was {cape['latest']:.1f} in {cape['as_of'][:7]}, above about {cape['own_percentile'] * 100:.0f}% of observed months since {cape['history_start'][:4]}."
    parts = []
    for key, label, unit in (("pe", "Trailing P/E", ""), ("excess_cape_yield", "Excess CAPE yield", " percentage points")):
        r = gauges.get(key)
        if r:
            parts.append(f"{label} was {r['latest']:.1f}{unit} ({r['as_of'][:7]})")
    return [first] + (["; ".join(parts) + "; valuation levels are not a timing signal."] if parts else [])


def _v02(v):
    rows = [r for r in v.get("gauges", []) if r.get("key") != "cape" and _number(r.get("latest")) and r.get("as_of")]
    if not rows:
        return []
    return ["Replacement-cost comparisons: " + "; ".join(f"{r['name']} {r['latest']:.2f} times ({r['as_of'][:4]})" for r in rows[:2]) + ".",
            "BEA measures use distinct asset and liability perimeters; a high ratio is descriptive valuation context."]


def _v03(v):
    rows = [r for r in v.get("regions", []) if _number(r.get("trailing")) and r.get("as_of")]
    if not rows:
        return []
    selected = _ends(rows, lambda r: r["trailing"])
    return ["Archived MSCI trailing P/E: " + "; ".join(f"{r['region']} {r['trailing']:.1f} times ({r['as_of'][:7]})" for r in selected) + ".",
            "These are captured factsheet months with different sector mixes; forward P/E depends on analyst earnings estimates."]


def _v05(v):
    cells = [r for r in v.get("cells", []) if _number(r.get("rho")) and r.get("first_start") and r.get("last_start")]
    if not cells:
        return []
    r = next((r for r in cells if r.get("era") == "All years" and r.get("horizon_years") == 10), cells[-1])
    return [f"Starting earnings yield and subsequent {r['horizon_years']}-year real stock returns had rank correlation {r['rho']:.2f} for starts {r['first_start']} to {r['last_start']} ({r['era']}).",
            f"The {r['windows']} overlapping windows represent about {r['effective_windows']:.1f} horizon-length blocks; overlap and regime changes limit predictive interpretation."]


def _l01(v):
    rows = [r for r in v.get("economies", []) if _number(r.get("productivity")) and _number(r.get("pay"))]
    r = _focus(rows)
    if not r:
        return []
    return [f"From {r['base_year']} to {r['latest_year']} in {_name(r['area'])}, indexed productivity rose {r['productivity'] - 100:.1f}% and real hourly compensation {r['pay'] - 100:.1f}%.",
            "This matches average compensation and productivity within the named sector and deflator convention; it is not median take-home pay."]


def _l02(v):
    rows = [r for r in v.get("economies", []) if r.get("parts")]
    r = _focus(rows)
    if not r:
        return []
    parts = {p["key"]: p["share"] for p in r["parts"] if _number(p.get("share"))}
    out = []
    if "compensation" in parts:
        out.append(f"Employee compensation accounted for {parts['compensation']:.0f}% of non-financial corporate value added in {_name(r['area'])} ({r['year']}).")
    if "net_operating_surplus" in parts:
        out.append(f"Net operating surplus was {parts['net_operating_surplus']:.0f}% of value added ({r['year']}), after depreciation but before property-income flows and corporation tax.")
    return out


def _l03(v):
    rows = [r for r in v.get("economies", []) if _number(r.get("latest")) and _number(r.get("first"))]
    r = _focus(rows)
    if not r:
        return []
    return [f"In {_name(r['area'])}, corporate net operating surplus / net fixed assets moved from {r['first']:.1f}% ({r['first_year']}) to {r['latest']:.1f}% ({r['latest_year']}).",
            "This national-accounts operating return is before property-income flows and corporation tax, not listed-company net profit."]


def _l04(v):
    rows = [r for r in v.get("countries", []) if any(m.get("surplus_value") for m in r.get("methods", {}).values())]
    r = _focus(rows, "country")
    if not r:
        return []
    methods = r["methods"]
    key = next((k for k in ("io", "sea", "klems_io", "klems") if methods.get(k, {}).get("surplus_value")), None)
    m = methods[key]
    spread = m["surplus_value"]
    label = {"io": "WIOD full input-output method", "sea": "WIOD value-added method", "klems_io": "EU KLEMS/ICIO extension", "klems": "EU KLEMS extension"}[key]
    first = f"For {_name(r['country'])} ({m['year']}), the {label} gives surplus-to-wage ratios of {spread['min'] * 100:.0f}% to {spread['max'] * 100:.0f}% across classification and wage assumptions."
    extension = methods.get("klems_io")
    second = (f"The EU KLEMS/ICIO extension reaches {extension['year']}; its merged-industry bounds and source changes are separate from the WIOD replication."
              if extension and key != "klems_io" else "The spread reflects theoretical classification, wage and gross-surplus conventions; it is not an identified measure of unpaid labour.")
    return [first, second]


def _l05(v):
    groups = {r["key"]: r for r in v.get("groups", []) if _number(r.get("latest"))}
    day = v.get("latest_date")
    if not groups or not day:
        return []
    parts = []
    if "top_point1" in groups and "next_point9" in groups:
        top = groups["top_point1"]["latest"] + groups["next_point9"]["latest"]
        parts.append(f"the top 1% held {top:.1f}%")
    elif "top_point1" in groups:
        parts.append(f"the top 0.1% held {groups['top_point1']['latest']:.1f}%")
    if "bottom50" in groups:
        parts.append(f"the bottom half held {groups['bottom50']['latest']:.1f}%")
    return [f"In the US DFA for {_quarter(day)}, " + _join(parts) + " of household net worth.",
            "Net worth includes assets and liabilities; these are not shares of income or corporate ownership."] if parts else []


def _l07(v):
    rows = [r for r in v.get("economies", []) if _number(r.get("top1_latest")) and _number(r.get("bottom50_latest"))]
    r = next((r for r in rows if r.get("area") == "WORLD"), _focus(rows))
    if not r:
        return []
    return [f"In {_name(r['area'])} ({r['latest_year']}), the top 1% income share was {r['top1_latest']:.1f}% and the bottom-half share {r['bottom50_latest']:.1f}%.",
            "These WID income shares are distinct from the US DFA wealth shares; country definitions and latest years differ."]


def _g01(v):
    r = v.get("latest") or {}
    if not _number(r.get("top10_pct")):
        return []
    first = f"The ten largest reported issuers in the ACWI ETF held {r['top10_pct']:.1f}% of fund NAV ({r['date']})."
    printed = _latest(v.get("published_top10", []))
    second = (f"MSCI's published top-ten security weights totaled {printed[1]:.1f}% ({printed[0][:7]}); index security weights and ETF issuer groups are different populations."
              if printed else "ETF issuer-name grouping is not a complete MSCI index or ultimate-parent crosswalk.")
    return [first, second]


def _g02(v):
    rows = [r for r in v.get("countries", []) if _number(r.get("index_weight")) and _number(r.get("gdp_share"))]
    r = _focus(rows)
    if not r or not v.get("date"):
        return []
    return [f"{_name(r['area'], True)} had {r['index_weight']:.1f}% of ACWI ETF NAV by reported investment country ({v['date']}), versus {r['gdp_share']:.1f}% of world nominal GDP ({r['gdp_year']}).",
            "Fund investment-country assignment differs from MSCI country classification and companies' revenue geography; GDP weights are not a portfolio target."]


def _g03(v):
    proxy = (v.get("listed_earnings") or {}).get("latest")
    alternatives = [r for r in v.get("alternatives", []) if _number(r.get("latest")) and r.get("as_of")]
    samples = (v.get("listed_profit_coverage") or {}).get("sources", [])
    if not alternatives and not proxy and not samples:
        return []
    bits = []
    if proxy and _number(proxy.get("earnings_usd_bn")):
        bits.append(f"the implied index earnings proxy was ${proxy['earnings_usd_bn'] / 1000:.1f} trillion ({proxy['month'][:7]})")
    for r in alternatives:
        label, denominator = (("EU27 non-financial gross surplus", "sector value added") if r["key"] == "eu27_profit_share"
                              else ("reporting OECD corporate gross surplus", "GDP"))
        bits.append(f"{label} was {r['latest']:.1f}% of {denominator} ({r['as_of'][:4]})")
    for sample in samples:
        bits.append(f"Brazil CVM {sample['year']} has {sample['consolidated_income_issuers']} consolidated-income reporters among {sample['filing_issuers']} filing issuers; listing/ultimate-parent/global coverage remains unverified")
    return ["The original worldwide listed-parent profit/GDP answer remains withheld: the complete income/universe/FX panel is missing.",
            "Bounded alternatives: " + "; ".join(bits) + "; none is reported worldwide listed-company net profit."] if bits else []


def _g05(v):
    rows = [r for r in v.get("economies", []) if _number(r.get("current_account_gdp")) or _number(r.get("net_position_gdp"))]
    r = _focus(rows)
    if not r:
        return []
    bits = []
    if _number(r.get("current_account_gdp")):
        bits.append(f"current account {r['current_account_gdp']:+.1f}% of GDP ({r['current_account_year']})")
    if _number(r.get("net_position_gdp")):
        bits.append(f"net international investment position {r['net_position_gdp']:+.1f}% of GDP ({r['net_position_year']})")
    return [f"{_name(r['area'], True)}: " + "; ".join(bits) + ".",
            "An external flow and a net asset stock are distinct; their co-movement with credit does not establish causation."]


def _g06(v):
    rows = [r for r in v.get("economies", []) if _number(r.get("latest")) and _number(r.get("first"))]
    if not rows:
        return []
    r = max(rows, key=lambda r: r["latest"])
    return [f"In {_name(r['area'])}, value added serving foreign final demand changed from {r['first']:.1f}% ({r['first_year']}) to {r['latest']:.1f}% ({r['latest_year']}).".replace("rose from", "changed from"),
            "This is a value-added supply-chain exposure, not gross exports, issuer domicile or a company's foreign revenue share."]


def _p01(v):
    owner = v.get("owner_portfolio") or {}
    summary = owner.get("summary") or {}
    if owner.get("positions") and summary.get("position_count"):
        total = summary.get("total_value_eur")
        value = f"€{total:,.0f}" if _number(total) else "total value not supplied"
        count, accounts, funds = summary["position_count"], len(summary.get("accounts", [])), summary.get("funds", [])
        noun = lambda n, word: f"{n} {word}" + ("s" if n != 1 else "")
        dated = f"valuation date {owner['as_of']}" if owner.get("as_of") else "valuation date not supplied"
        first = f"Supplied positions: {value} across {noun(count, 'position')}, {noun(accounts, 'account')} and {noun(len(funds), 'fund')}; {dated}."
        weighted = [r for r in funds if _number(r.get("weight"))]
        top = max(weighted, key=lambda r: r["weight"]) if weighted else None
        second = (f"Largest supplied fund: {top['name']}, {top['weight'] * 100:.1f}% of declared value; "
                  if top else "Fund weights are unavailable; ")
        return [first, second + "issuer-country/sector look-through remains unverified."]
    rows = [r for r in v.get("funds", []) if r.get("countries") and r.get("date")]
    if not rows:
        return []
    bits = []
    for r in rows[:3]:
        largest = max(r["countries"], key=lambda c: c["share"])
        bits.append(f"{r['name']}: {_name(largest['key'])} {largest['share']:.1f}% ({r['date']})")
    return ["Largest reported country weights by fund: " + "; ".join(bits) + ".",
            "These are separate fund snapshots; actual dated portfolio fund weights are needed to combine them."]


def _p02(v):
    cells = [r for r in v.get("cells", []) if _number(r.get("rho"))]
    r = next((r for r in cells if r.get("pair") == "stocks_bonds" and r.get("period") == "All years"), None)
    if not r:
        return []
    return [f"Monthly world-equity/US sovereign-bond return correlation was {r['rho']:.2f} over {r['months']} matched months ({r['from']} to {r['to']}).",
            "The bond leg is US sovereign returns, not a global aggregate; gold uses monthly average prices and correlations vary by regime."]


def _p03(v):
    point = _latest(v.get("underwater", []))
    if not point:
        return []
    month, value = point
    first = f"At the end of {month} world equities (MSCI ACWI, US dollars) were " + (f"{abs(value) * 100:.1f}% below their previous peak." if value < 0 else "at their observed peak.")
    episodes = [e for e in v.get("episodes", []) if _number(e.get("depth"))]
    if not episodes:
        return [first]
    worst = min(episodes, key=lambda e: e["depth"])
    regained = (f"regained {worst['months_to_recover']} months after the low" if worst.get("months_to_recover") is not None else "not regained within the observed history")
    return [first, f"The deepest observed fall was {abs(worst['depth']) * 100:.0f}% ({worst['peak']} to {worst['trough']}), {regained}; this is an equity benchmark, not your actual portfolio."]


def _p04(v):
    rows = [r for r in v.get("shocks", []) if _number(r.get("impact_pct"))]
    if not rows:
        return []
    r = next((r for r in rows if r.get("key") == "rates_up"), rows[0])
    label = "Example" if v.get("is_example", True) else "Saved-input"
    return [f"{label} scenario — {r['label']}: modeled impact {r['impact_pct']:+.1f}% of portfolio value.",
            "This is a first-order, separate shock with assumed weights and duration, not a probability or a joint-shock forecast."]


def _p05(v):
    rows = [r for r in v.get("rules", []) if _number(r.get("final"))]
    r = next((r for r in rows if r.get("key") == v.get("chosen")), None)
    period = v.get("period") or {}
    if not r or not period.get("from") or not period.get("to"):
        return []
    label = "Example" if v.get("is_example", True) else "Saved-input"
    return [f"{label} {r['label']} replay ({period['from']} to {period['to']}) ended at €{r['final']:,.0f}, with a {abs(r['max_drawdown']) * 100:.1f}% wealth drawdown.",
            "Wealth includes cash flows and simplified costs/taxes; the bond leg is a sovereign surrogate, and this path does not establish future resilience."]


def _p06(v):
    bits = []
    equity = v.get("equity_world_snapshot") or {}
    if _number(equity.get("earnings_yield")) and equity.get("as_of"):
        bits.append(f"Siblis global equity earnings yield {equity['earnings_yield'] * 100:.1f}% ({equity['as_of'][:7]})")
    nominal = (v.get("bonds") or {}).get("us_nominal_10y") or {}
    if _number(nominal.get("yield")) and nominal.get("as_of"):
        bits.append(f"US 10-year nominal yield {nominal['yield'] * 100:.2f}% ({nominal['as_of']})")
    return ["Current return-calibration inputs: " + "; ".join(bits) + ".",
            "Earnings yields and bond yields are distinct valuation inputs, not promised returns or a forecast with known precision."] if bits else []


def _p07(v):
    nominal = v.get("nominal") or {}
    unhedged, hedged = nominal.get("eur_unhedged") or {}, nominal.get("eur_hedged") or {}
    rows = v.get("rows") or []
    if not rows or not _number(unhedged.get("annualized_return")) or not _number(hedged.get("annualized_return")):
        return []
    return [f"From {rows[0]['month']} to {rows[-1]['month']}, nominal EUR world-equity returns annualized at {unhedged['annualized_return'] * 100:.1f}% unhedged versus {hedged['annualized_return'] * 100:.1f}% with the modeled hedge.",
            "The hedge uses short-rate carry assumptions and omits trading frictions; it is not an observed hedged fund return."]


BUILDERS = {"C01": _c01, "C02": _c02, "C03": _c03, "C05": _c05, "C06": _c06,
            "M01": _m01, "M02": _m02, "M04": _m04,
            "F01": _f01, "F02": _f02, "F03": _f03, "F04": _f04, "F05": _f05, "F06": _f06, "F07": _f07,
            "V01": _v01, "V02": _v02, "V03": _v03, "V05": _v05,
            "L01": _l01, "L02": _l02, "L03": _l03, "L04": _l04, "L05": _l05, "L07": _l07,
            "G01": _g01, "G02": _g02, "G03": _g03, "G05": _g05, "G06": _g06,
            "P01": _p01, "P02": _p02, "P03": _p03, "P04": _p04, "P05": _p05, "P06": _p06, "P07": _p07}


def summarize(analysis_id: str, values: dict | None) -> list[str]:
    builder = BUILDERS.get(analysis_id)
    if builder is None or not isinstance(values, dict) or not values:
        return []
    try:
        return builder(values)
    except (KeyError, TypeError, ValueError, IndexError, StopIteration, AttributeError):
        return []
