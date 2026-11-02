"""Curated, source-grounded economic indicator views for the local research dashboard.

The catalog contains *real, documented* provider series. Research views select
coherent observation sets and apply only explicitly specified transformations.
The 2017=100 BLS output-price productivity/pay comparison is calculated from
BLS series for the SAME nonfarm business sector and identical quarter; the
different CPI pay series is never substituted into this analytical measure.

Geographical scopes are kept distinct: global aggregates, OECD38 member
estimates, US, euro area, EU27 and Japan. Index-weighted "world equities" is
never described as world economic output.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.engine import Engine

from .catalog import load_documents
from .service import current_observations

# Every indicator is source-keyed, and its relationship is explicitly defined.
# 'raw' is for like-for-like measurements only; contextual single series do not
# imply any statistical relationship to an adjacent tile.
SPECS: tuple[dict[str, Any], ...] = (
    # WORLD and OECD contain only corresponding geographic aggregates.
    dict(id="global_growth", region="world", theme="Growth and demand",
         title="World real output growth", sources=["gdp.real_growth.world"],
         kind="raw", question="How fast is the world economy expanding?",
         reading="Annual constant-price GDP growth in the World Bank's world aggregate.",
         caveat="GDP-weighted world growth is not the median country's growth."),
    dict(id="global_labour_share", region="world", theme="Labour and distribution",
         title="Labour's share of world income", sources=["labour.world.income_share"],
         kind="raw", question="What share of output goes to labour?",
         reading="UN SDG 10.4.1 estimated labour income share, accounting for self-employment.",
         caveat="The non-labour remainder includes depreciation, taxes and mixed incomes; it is not an observed Marxian surplus-value rate."),
    dict(id="global_productivity", region="world", theme="Labour and distribution",
         title="World labour productivity growth", sources=["labour.world.productivity_growth"],
         kind="raw", question="Is world output per worker growing?",
         reading="Observed annual world output per employed person growth, separately from the level of labour's income share.",
         caveat="This is output per employed person, not hours-worked productivity or wage growth."),
    dict(id="oecd_corporate_surplus", region="world", theme="Labour and distribution",
         title="OECD corporate operating surplus / GDP", sources=["profit.oecd38.corporate_gross_surplus_gdp"],
         kind="raw", question="What share of member GDP accrues as gross corporate surplus?",
         reading="A GDP-weighted statistic for reporting current OECD38 financial and nonfinancial corporate sectors.",
         caveat="Gross operating surplus includes depreciation and is not net profit, dividends, surplus value or a world corporate share."),
    dict(id="oecd_surplus_coverage", region="world", theme="Data coverage",
         title="GDP coverage of OECD surplus estimate", sources=["profit.oecd38.corporate_gross_surplus_gdp_coverage"],
         kind="raw", question="How complete is the OECD comparison?",
         reading="Coverage share in the underlying OECD corporate-surplus aggregate.",
         caveat="Country coverage can change between years; coverage is not a measure of profits."),
    dict(id="global_credit", region="world", theme="Debt and leverage",
         title="43-economy credit-to-GDP trend gap", sources=["credit.world.private_gdp_gap"],
         kind="raw", question="Is private credit high relative to local trends?",
         reading="Researcher GDP-weighted national BIS credit gaps across 43 reporting economies.",
         caveat="Not a BIS-published world gap; reporting GDP coverage is incomplete and varies."),
    dict(id="global_credit_coverage", region="world", theme="Data coverage",
         title="Coverage of the international credit proxy", sources=["credit.world.private_gdp_gap_coverage"],
         kind="raw", question="How representative is the credit indicator?",
         reading="Proportion of world GDP covered by the country-weighted composite.",
         caveat="Do not interpret this coverage percentage as a credit risk score."),
    dict(id="global_equity_cap", region="world", theme="Capital and equity valuation",
         title="World listed domestic equities / world GDP", sources=["valuation.world.listed_market_cap_world_gdp"],
         kind="raw", question="How large are public equity valuations compared with output?",
         reading="World Bank WFE-listed domestic-company capitalization divided by world GDP in matched years.",
         caveat="A market-cap/GDP ratio does not identify overvaluation; it excludes private enterprise and is sensitive to listing residence."),
    dict(id="global_pe", region="world", theme="Capital and equity valuation",
         title="Global equity-index trailing P/E", sources=["valuation.world.global_trailing_pe"],
         kind="raw", question="How many units of index price per unit of reported earnings?",
         reading="Published Siblis global equity-index trailing price-to-earnings snapshots.",
         caveat="Index universe is capitalization-weighted and US-heavy; observations are sparse, not a continuous monthly global company-profit series."),
    dict(id="global_concentration", region="world", theme="Ownership and concentration",
         title="Largest ten firms' ACWI index weight", sources=["concentration.global.msci_acwi_published_top10"],
         kind="raw", question="How concentrated is the global equity benchmark?",
         reading="MSCI ACWI actual published top-ten company weights at dated snapshots.",
         caveat="The US was 64.21% of MSCI ACWI in the September 30, 2026 factsheet; a capitalization-weighted equity index is NOT a geographically balanced world economy measure."),
    dict(id="global_gold_equity", region="world", theme="Financial conditions",
         title="Gold vs global-equity historical return correlation", sources=["gold.world.equity_correlation"],
         kind="raw", question="Has gold diversified global equity returns?",
         reading="Trailing 36-month return correlation of monthly World Bank gold with MSCI ACWI net total returns.",
         caveat="MSCI ACWI is US-weighted, correlation changes by sample and cannot forecast returns."),
    dict(id="global_public_debt", region="world", theme="Debt and leverage",
         title="World general government gross debt / GDP", sources=["fiscal.world.public_debt"],
         kind="raw", question="How large is the public debt burden globally?",
         reading="IMF aggregate world public gross debt relative to GDP.",
         caveat="A gross debt stock is not annual debt-service costs or an imminent sovereign default signal."),
    # United States: the broad macro environment comes before the distribution detail.
    dict(id="us_growth", region="us", theme="Growth and demand",
         title="US real GDP growth", sources=["gdp.real_growth.us"], kind="raw",
         question="How quickly is real US output expanding?",
         reading="World Bank annual constant-price growth of US GDP.",
         caveat="GDP growth is economy-wide, unlike quarterly BLS nonfarm business productivity."),
    dict(id="us_policy", region="us", theme="Financial conditions",
         title="US harmonized monetary policy rate", sources=["policy_rate.us.bis"], kind="raw",
         question="How has the US monetary policy rate changed?",
         reading="BIS daily harmonized nominal US policy rate.",
         caveat="Nominal policy rates do not account for inflation expectations or household borrowing rates."),
    dict(id="us_real_yield", region="us", theme="Financial conditions",
         title="US 10-year real Treasury yield", sources=["bond.us.real_10y"], kind="raw",
         question="What real return does the inflation-indexed US Treasury curve imply?",
         reading="Daily FRED 10-year constant-maturity TIPS real yield.",
         caveat="A market real yield is distinct from the overnight policy rate and is not a direct equity discount rate."),
    dict(id="us_tobins_q", region="us", theme="Capital and equity valuation",
         title="US nonfinancial corporate market-to-produced-asset replacement ratio",
         sources=["valuation.us.tobins_q"], kind="raw",
         question="What does the market price of US corporate equities imply relative to produced-asset replacement cost?",
         reading="Documented BEA replacement-cost variant of Tobin's Q1; a market-value/produced-assets comparison.",
         caveat="Covers US nonfinancial corporations and produced assets under BEA Q1 definitions; not total global corporate valuation."),
    # United States: exact-sector productivity/pay and distinct GDP-wide labour share.
    dict(id="us_productivity_pay", region="us", theme="Labour and distribution",
         title="Productivity versus output-price-adjusted pay", sources=[
             "labour.us.nonfarm_productivity", "labour.us.nonfarm_hourly_comp", "prices.us.nonfarm_output_deflator"],
         kind="us_productivity_pay", question="Do nonfarm business workers receive a proportional share of productivity gains?",
         reading="BLS output per hour and BLS hourly compensation deflated by the SAME nonfarm-business output price index, both 2017=100. The latest ratio is a baseline-relative distribution measure.",
         caveat="Average total compensation (includes benefits and proprietors), not median wages. The indexed gap is not Marx's rate of exploitation. BLS stresses that CPI deflation answers a different purchasing-power question."),
    dict(id="us_real_pay", region="us", theme="Labour and distribution",
         title="Worker purchasing power: real hourly pay", sources=["labour.us.nonfarm_real_compensation_cpi"],
         kind="raw", question="Is hourly compensation buying more consumer goods?",
         reading="BLS CPI-deflated hourly compensation for nonfarm business, 2017=100.",
         caveat="This consumer-price series uses a different deflator from output-price adjusted compensation. Do not directly overlay it as a labour-share decomposition."),
    dict(id="us_labour_share_gdp", region="us", theme="Labour and distribution",
         title="US labour share of GDP", sources=["labour.us.pwt_labour_share"],
         kind="fraction_percent", question="What share of US national output is attributable to labour?",
         reading="Penn World Table labour-compensation share of GDP in current prices; official FRED series is a fractional ratio and is converted to percentage by multiplying by 100.",
         caveat="Total-economy annual PWT ratio (through 2023) is not the BLS nonfarm business labour share or a surplus-value measure."),
    dict(id="us_labour_share_nonfarm", region="us", theme="Labour and distribution",
         title="US nonfarm business labour share, index", sources=["labour.us.nonfarm_labour_share_index"],
         kind="raw", question="How has the share going to labour moved since 2017?",
         reading="BLS labour share for nonfarm business, index 2017=100.",
         caveat="93 index points is not a 93% share of GDP. It is the relative movement of the sector's labour share."),
    dict(id="us_yield_curve", region="us", theme="Financial conditions",
         title="US Treasury 10-year minus 3-month spread", sources=["rates.us.treasury_10y_3m_spread"],
         kind="raw", question="Is the US Treasury yield curve inverted?",
         reading="Daily difference between 10-year and 3-month Treasury yields; negative values represent inversion.",
         caveat="Yield inversion is associated with past downturns; it does not establish when a recession will occur."),
    dict(id="us_sahm", region="us", theme="Financial conditions",
         title="US Sahm Rule unemployment deterioration", sources=["recession.us.sahm"],
         kind="raw", question="Is the labour market showing recession-like deterioration?",
         reading="FRED real-time Sahm unemployment threshold statistic, a documented recession-onset signal.",
         caveat="Not a leading crash forecast; employment and financial-market turning points can diverge."),
    dict(id="us_cape", region="us", theme="Capital and equity valuation",
         title="US Shiller cyclically adjusted price/earnings", sources=["valuation.us.cape"],
         kind="raw", question="How demanding is the US equity valuation relative to a cycle of earnings?",
         reading="Shiller CAPE based on inflation-adjusted ten-year average earnings.",
         caveat="A valuation multiple does not time near-term market corrections."),
    dict(id="us_credit", region="us", theme="Debt and leverage",
         title="US private credit relative to trend", sources=["credit_gap.us.bis"],
         kind="raw", question="How stretched is nonfinancial credit against its own history?",
         reading="BIS US nonfinancial-sector credit-to-GDP deviation from one-sided trend.",
         caveat="Percentage-point credit gap is not a default rate or complete household balance sheet."),
    dict(id="us_cap_gdp", region="us", theme="Capital and equity valuation",
         title="US domestic listed market cap / GDP", sources=["valuation.domestic_cap_gdp.us"],
         kind="raw", question="How large is the US listed equity sector compared with domestic GDP?",
         reading="World Bank listed domestic-company capitalization relative to US output.",
         caveat="Compare against Japan only on the dedicated like-for-like comparison page."),
    # Euro area and EU27: distinct statistical populations.
    dict(id="ea_growth", region="europe", theme="Growth and demand",
         title="Euro-area real GDP growth", sources=["gdp.real_growth.eu"], kind="raw",
         question="Is euro-area economic activity accelerating?",
         reading="World Bank EMU real annual GDP growth.", caveat="Euro area (EMU), not EU27 or all geographical Europe."),
    dict(id="ea_policy", region="europe", theme="Financial conditions",
         title="Euro-area harmonized policy rate", sources=["policy_rate.ea.bis"], kind="raw",
         question="How restrictive is euro-area nominal monetary policy?",
         reading="BIS euro-area harmonized central bank policy rate.", caveat="Nominal rates alone do not measure real interest rates."),
    dict(id="ea_credit", region="europe", theme="Debt and leverage",
         title="Euro-area private credit gap", sources=["credit_gap.ea.bis"], kind="raw",
         question="Is euro-area private credit above its historical trend?",
         reading="BIS euro-area one-sided credit-to-GDP gap.", caveat="Euro area, not European Union."),
    dict(id="eu27_corporate_surplus", region="europe", theme="Labour and distribution",
         title="EU27 corporate gross operating surplus / GDP",
         sources=["profit.eu27.corporate_operating_surplus_gdp"], kind="raw",
         question="How much EU production accrues as corporate gross surplus?",
         reading="Eurostat EU27 financial and nonfinancial corporate sector gross operating surplus relative to EU GDP.",
         caveat="EU27 membership, not euro area; gross surplus includes depreciation and is not shareholder net profit."),
    dict(id="eu27_nonfinancial_surplus", region="europe", theme="Labour and distribution",
         title="EU27 nonfinancial corporate surplus / sector GVA",
         sources=["profit.eu27.nonfinancial_gross_surplus_value_added"], kind="raw",
         question="What fraction of nonfinancial corporate value added is gross surplus?",
         reading="Eurostat nonfinancial corporate sector surplus relative to the same sector's value added.",
         caveat="Sector GVA denominator differs from EU-wide GDP; do not graph the two surplus percentages as one common variable."),
    # Japan.
    dict(id="jp_growth", region="japan", theme="Growth and demand",
         title="Japan real GDP growth", sources=["gdp.real_growth.jp"], kind="raw",
         question="What is Japan's annual real output growth?",
         reading="World Bank Japanese real GDP growth.", caveat="Annual calendar frequency, revised historically."),
    dict(id="jp_policy", region="japan", theme="Financial conditions",
         title="Japan harmonized policy rate", sources=["policy_rate.jp.bis"], kind="raw",
         question="How has Japan's policy stance changed?",
         reading="BIS Japan central bank harmonized policy-rate series.", caveat="BIS instrument definitions may shift through time."),
    dict(id="jp_credit", region="japan", theme="Debt and leverage",
         title="Japan private credit gap", sources=["credit_gap.jp.bis"], kind="raw",
         question="Where is Japanese private credit relative to trend?",
         reading="BIS Japanese credit-to-GDP trend gap.", caveat="A gap is a statistical deviation, not a crisis probability."),
    dict(id="jp_equity_cap", region="japan", theme="Capital and equity valuation",
         title="Japan listed domestic equity capitalization / GDP",
         sources=["valuation.domestic_cap_gdp.jp"], kind="raw",
         question="How large are Japanese equity listings relative to Japan's GDP?",
         reading="World Bank end-year domestic listed equity capitalization as a share of annual Japanese GDP.",
         caveat="Issuer residency/listings affect country comparisons; it is not a direct cross-country asset valuation."),
    # Cross-country within identical methodology, no 'world' masquerading as an equally weighted country.
    dict(id="compare_growth", region="compare", theme="Growth and demand",
         title="Real growth: US / euro area / Japan / China / India",
         sources=["gdp.real_growth.us", "gdp.real_growth.eu",
                  "gdp.real_growth.jp", "gdp.real_growth.cn", "gdp.real_growth.in"],
         kind="raw", question="Which large economies are expanding fastest?",
         reading="Five World Bank annual real GDP growth rates, displayed on native source years.",
         caveat="World aggregate deliberately excluded; countries have very different economic size and population."),
    dict(id="compare_policy", region="compare", theme="Financial conditions",
         title="Comparable policy rates: US / euro area / Japan",
         sources=["policy_rate.us.bis", "policy_rate.ea.bis", "policy_rate.jp.bis"],
         kind="raw", question="How different are major monetary policy stances?",
         reading="BIS harmonized daily policy rates on the same numeric scale.",
         caveat="Nominal rates; country-specific price inflation and corridor regimes differ."),
    dict(id="compare_credit", region="compare", theme="Debt and leverage",
         title="Comparable credit-to-GDP trend gaps", sources=[
             "credit_gap.us.bis", "credit_gap.ea.bis", "credit_gap.jp.bis"],
         kind="raw", question="Which major economies show credit expansion relative to their trend?",
         reading="Country BIS private nonfinancial credit-to-GDP gaps in percentage points.",
         caveat="A BIS credit gap is not comparable to the level of private debt or default rates."),
    dict(id="compare_market_cap", region="compare", theme="Capital and equity valuation",
         title="Domestic listed capitalization / GDP: US vs Japan",
         sources=["valuation.domestic_cap_gdp.us", "valuation.domestic_cap_gdp.jp"],
         kind="raw", question="How large are domestic listed equity markets against GDP?",
         reading="Identical World Bank indicator CM.MKT.LCAP.GD.ZS for US and Japan.",
         caveat="Capital-market capitalization depends on company listings and cross-border activity."),
)
BY_ID = {spec["id"]: spec for spec in SPECS}
REGIONS = (
    {"id": "world", "title": "World & OECD", "explanation": "World/IMF aggregate series, OECD38 reporting-member composite, and capitalization-weighted global equity benchmarks are identified separately."},
    {"id": "us", "title": "United States", "explanation": "US nonfarm business, total-economy national accounts, and US credit/market indicators with explicit denominator differences."},
    {"id": "europe", "title": "Euro area & EU27", "explanation": "EMU euro-area monetary/credit/GDP series versus EU27 corporate national accounts; the two are not interchangeable."},
    {"id": "japan", "title": "Japan", "explanation": "Japanese GDP, policy stance, private credit and domestic stock-market indicators."},
    {"id": "compare", "title": "Compare regions", "explanation": "Identically defined measures across countries without pretending an equity-weighted world index is an equal-weighted world economy."},
)


def _datum(row: Any) -> tuple[date, Decimal]:
    period, value = ((row[0], row[1]) if isinstance(row, tuple) else (row.period, row.value))
    return period, Decimal(str(value))


def _observed(rows: list[Any]) -> dict[date, Decimal]:
    result = {}
    for row in rows:
        day, number = _datum(row)
        if number.is_finite():
            result[day] = number
    return result


def compile_indicator(spec: dict[str, Any], observed: dict[str, list[Any]],
                      metadata: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Transform only genuine, exact-period source observations."""
    sources = spec["sources"]
    names = [metadata[key] for key in sources]
    values = {key: _observed(observed.get(key, [])) for key in sources}
    kind = spec["kind"]
    used: list[dict[str, Any]] = []

    if kind == "us_productivity_pay":
        p, n, d = (values[source] for source in sources)
        overlap = sorted(set(p) & set(n) & set(d))
        points_output = []
        points_pay = []
        for day in overlap:
            if n[day] <= 0 or d[day] <= 0 or p[day] <= 0:
                continue
            adjusted = Decimal("100") * n[day] / d[day]
            if not adjusted.is_finite() or adjusted <= 0:
                continue
            points_output.append({"date": day.isoformat(), "value": str(p[day])})
            points_pay.append({"date": day.isoformat(), "value": str(adjusted)})
        used = [
            {"id": "derived.us.nonfarm_output", "name": "Output per hour (2017=100)",
             "unit": "index", "frequency": "Q", "points": points_output},
            {"id": "derived.us.output_price_real_pay", "name": "Output-price-adjusted hourly pay (2017=100)",
             "unit": "index", "frequency": "Q", "points": points_pay},
        ]
        if points_output and points_pay:
            last_out = Decimal(points_output[-1]["value"])
            last_pay = Decimal(points_pay[-1]["value"])
            headline = {"date": points_output[-1]["date"],
                        "value": str(Decimal("100") * (last_out / last_pay - 1)),
                        "unit": "percent",
                        "label": "Productivity/pay ratio relative to 2017",
                        "explanation": "100 × (output-per-hour index / output-price-adjusted hourly-compensation index − 1). Baseline 2017 is zero."}
        else:
            headline = None
    else:
        source = sources[0]
        raw = sorted(values[source].items())
        points = [{"date": day.isoformat(),
                   "value": str(value * 100 if kind == "fraction_percent" else value)}
                  for day, value in raw]
        used = [{
            "id": source, "name": names[0]["name"],
            "unit": "percent" if kind == "fraction_percent" else names[0]["unit"],
            "frequency": names[0]["frequency"], "points": points,
        }]
        for source in sources[1:]:
            used.append({
                "id": source, "name": metadata[source]["name"],
                "unit": metadata[source]["unit"], "frequency": metadata[source]["frequency"],
                "points": [{"date": day.isoformat(), "value": str(value)}
                           for day, value in sorted(values[source].items())],
            })
        all_units = {part["unit"] for part in used}
        all_frequencies = {part["frequency"] for part in used}
        if len(all_units) != 1 or len(all_frequencies) != 1:
            raise ValueError("Curated combination has differing unit/frequency")
        newest = [(part["points"][-1], part) for part in used if part["points"]]
        if newest:
            last, corresponding = max(newest, key=lambda pair: pair[0]["date"])
            headline = {"date": last["date"], "value": last["value"],
                        "unit": corresponding["unit"], "label": corresponding["name"],
                        "explanation": "Latest *recorded* observation, no extrapolation."}
        else:
            headline = None

    # Display explicit source-dated changes with each plotted line. The
    # comparison period is the nearest actually observed date about a year
    # earlier, within tolerance for its declared source frequency.
    tolerance = {"D": 40, "M": 55, "Q": 120, "A": 210}
    for series in used:
        recorded = series["points"]
        series["latest"] = recorded[-1] if recorded else None
        series["year_change"] = None
        if len(recorded) < 2:
            continue
        last = recorded[-1]
        target = date.fromisoformat(last["date"]) - timedelta(days=365)
        matches = [(abs((date.fromisoformat(row["date"]) - target).days), row)
                   for row in recorded[:-1]
                   if abs((date.fromisoformat(row["date"]) - target).days)
                       <= tolerance[series["frequency"]]]
        if not matches:
            continue
        prior = min(matches, key=lambda row: (row[0], row[1]["date"]))[1]
        series["year_change"] = {
            "start": prior["date"], "end": last["date"],
            "difference": str(Decimal(last["value"]) - Decimal(prior["value"])),
            "unit": "percentage_points" if series["unit"] == "percent"
                    else "index_points" if series["unit"] == "index"
                    else series["unit"],
        }

    # Country comparisons require an EXACT shared source date. If one of the
    # requested countries has no data, do not silently compare a smaller set.
    if len(used) > 1 and kind == "raw":
        maps = [{row["date"]: Decimal(row["value"]) for row in line["points"]}
                for line in used]
        shared = set.intersection(*(set(row) for row in maps))
        if shared:
            day = max(shared)
            by_value = sorted((values[day], line["name"])
                              for values, line in zip(maps, used))
            headline = {
                "date": day, "value": str(by_value[-1][0] - by_value[0][0]),
                "unit": "percentage_points" if used[0]["unit"] == "percent"
                        else used[0]["unit"],
                "label": "Highest–lowest at exactly shared date",
                "explanation": (f"{by_value[-1][1]} ({by_value[-1][0]}) minus "
                                f"{by_value[0][1]} ({by_value[0][0]}); "
                                "source dates match exactly, no resampling."),
            }
        else:
            headline = None

    return {
        "id": spec["id"], "region": spec["region"], "theme": spec["theme"],
        "title": spec["title"], "question": spec["question"],
        "reading": spec["reading"], "caveat": spec["caveat"],
        "status": "ready" if any(part["points"] for part in used) else "no_data",
        "headline": headline, "series": used,
        "provenance": [{
            "id": meta["id"], "name": meta["name"], "provider": meta["provider"],
            "source_url": meta["source_url"], "frequency": meta["frequency"],
            "geography": meta["geography"], "unit": meta["unit"],
            "measurement": meta.get("measurement"), "notes": meta.get("notes"),
        } for meta in names],
        "method": ("Source-native observations; no interpolation, forward-fill, "
                   "cross-sector aggregation, historical backcasting, or automated causal inference. "
                   "Read the per-indicator caveat before interpreting values."),
    }


def load_indicator(engine: Engine, indicator_id: str, *, start: date | None = None,
                   end: date | None = None) -> dict[str, Any]:
    spec = BY_ID[indicator_id]
    source_catalog, _ = load_documents()
    metadata = {s["id"]: s for s in source_catalog["series"]}
    with Session(engine) as session:
        data = {sid: current_observations(session, sid, start, end)
                for sid in spec["sources"]}
        # Materialize exact observations before closing the DB session.
        converted = {sid: list(data[sid]) for sid in spec["sources"]}
    return compile_indicator(spec, converted, metadata)


def list_research() -> dict[str, Any]:
    return {
        "regions": list(REGIONS),
        "indicators": [{k: value for k, value in spec.items()
                        if k != "kind"}
                       for spec in SPECS],
        "periods": [
            {"start": "2001-04-01", "end": "2001-11-30", "source": "NBER"},
            {"start": "2008-01-01", "end": "2009-06-30", "source": "NBER"},
            {"start": "2020-03-01", "end": "2020-04-30", "source": "NBER"},
        ],
        "periods_note": ("Shaded intervals are the US NBER recession months "
                         "associated with the dot-com crash, financial crisis and COVID-19. "
                         "They do not define recessions for other countries."),
        "reference": "https://www.nber.org/research/data/us-business-cycle-expansions-and-contractions",
    }
