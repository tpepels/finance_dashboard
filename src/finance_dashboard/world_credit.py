"""GDP-weighted international credit gap across BIS reporting countries.

This is the GDP-weighted average of 43 *national* BIS country gap
indicators, explicitly NOT the one-sided HP trend of a hypothetical world
credit/GDP ratio. Excludes BIS euro-area aggregate XM to avoid double-counting
member economies. GDP weights are nominal USD at prior calendar year.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from .bis import _dimension_code

BIS_COVERAGE_COUNTRIES = frozenset((
    "PL","BR","GB","MX","ZA","CN","SA","US","HU","JP","LU","RU","CL","HK",
    "IT","NL","CZ","SG","ES","IE","AU","MY","AR","SE","CO","TR","DK",
    "ID","IN","NZ","CA","AT","FR","NO","DE","TH","FI","IL","BE","KR",
    "PT","CH","GR",
))
BIS_COMPOSITE_URL = "https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CREDIT_GAP/1.0/Q..P.A.C"
WORLD_GDP_URL = "https://api.worldbank.org/v2/country/all/indicator/NY.GDP.MKTP.CD"
COVERAGE_THRESHOLD = Decimal("0.80")


class GlobalCreditError(ValueError):
    pass


def parse_bis_national_credit_gaps(payload: Any, *,
                                  country_codes=BIS_COVERAGE_COUNTRIES) -> dict[date,dict[str,Decimal]]:
    try:
        block=payload["data"]
        series_dims=block["structure"]["dimensions"]["series"]
        obs_dims=block["structure"]["dimensions"]["observation"]
        series=block["dataSets"][0]["series"]
    except (KeyError,TypeError,IndexError) as exc:
        raise GlobalCreditError("BIS national gaps response malformed") from exc
    if len(obs_dims)!=1 or obs_dims[0].get("id")!="TIME_PERIOD":
        raise GlobalCreditError("BIS quarterly time dimension missing")
    output={}
    for key,node in series.items():
        dims=_dimension_code(series_dims,key)
        if any(dims.get(field)!=value for field,value in
               (("FREQ","Q"),("TC_BORROWERS","P"),("TC_LENDERS","A"),("CG_DTYPE","C"))):
            raise GlobalCreditError("Unexpected BIS national gap dimension")
        country=dims.get("BORROWERS_CTY")
        if country=="XM": # euro-area group overlaps countries; exclude.
            continue
        if country not in country_codes:
            raise GlobalCreditError("Unexpected geography in BIS gap query")
        for k,row in node.get("observations",{}).items():
            label=_dimension_code(obs_dims,k)["TIME_PERIOD"]
            from .provider_parsers import _date, _value
            day=_date(label,"Q")
            value=_value(row[0])
            if value is None:
                continue
            bucket=output.setdefault(day,{})
            if country in bucket:
                raise GlobalCreditError("Duplicate country and quarter")
            bucket[country]=value
    if not output:
        raise GlobalCreditError("No BIS quarterly national credit gaps")
    return dict(sorted(output.items()))


def parse_wdi_gdp_all(payload: Any, *,
                      country_codes=BIS_COVERAGE_COUNTRIES
                     ) -> tuple[dict[int,dict[str,Decimal]],dict[int,Decimal]]:
    if (not isinstance(payload,list) or len(payload)!=2
        or not isinstance(payload[0],dict) or payload[0].get("pages")!=1
        or not isinstance(payload[1],list)):
        raise GlobalCreditError("Unpaginated or malformed World Bank GDP dataset")
    country_gdp={}
    world={}
    for row in payload[1]:
        if row.get("indicator",{}).get("id")!="NY.GDP.MKTP.CD":
            raise GlobalCreditError("World Bank GDP indicator mismatch")
        try:
            year=int(row["date"])
        except (TypeError,ValueError,KeyError) as exc:
            raise GlobalCreditError("World Bank GDP year invalid") from exc
        value=row.get("value")
        if value is None:
            continue
        try:
            amount=Decimal(str(value))
        except (InvalidOperation,TypeError) as exc:
            raise GlobalCreditError("World Bank GDP numeric invalid") from exc
        if not amount.is_finite() or amount<=0:
            raise GlobalCreditError("World Bank GDP must be positive USD")
        if row.get("countryiso3code")=="WLD":
            if year in world:
                raise GlobalCreditError("Duplicate world GDP")
            world[year]=amount
            continue
        code=row.get("country",{}).get("id")
        if code not in country_codes:
            continue
        bucket=country_gdp.setdefault(year,{})
        if code in bucket:
            raise GlobalCreditError("Duplicate World Bank national GDP year")
        bucket[code]=amount
    if not world or not country_gdp:
        raise GlobalCreditError("Missing world or national GDP totals")
    return country_gdp,world


def country_weighted_bis_gap(
    country_gaps: dict[date,dict[str,Decimal]],
    country_gdp: dict[int,dict[str,Decimal]],
    world_gdp: dict[int,Decimal],
    *,
    start: date | None = None,
    min_coverage: Decimal = COVERAGE_THRESHOLD,
) -> tuple[dict[date,Decimal],dict[date,Decimal]]:
    """Annual prior-year nominal-USD GDP weights; quarter coverage>=80%.

    Return (weighted national gap composite, coverage as % of world GDP).
    Coverage for every quarter uses *only countries with published country
    gaps in that quarter*. Early periods below the threshold are excluded.
    """
    result={}
    coverage={}
    for quarter, gaps in sorted(country_gaps.items()):
        if start and quarter<start:
            continue
        yr=quarter.year-1
        if yr not in country_gdp or yr not in world_gdp:
            continue
        weights=country_gdp[yr]
        pairs=[(weight,gaps[code]) for code,weight in weights.items()
               if code in gaps and code in BIS_COVERAGE_COUNTRIES]
        if not pairs:
            continue
        total=sum((weight for weight,_ in pairs),Decimal(0))
        fraction=total/world_gdp[yr]
        if fraction < min_coverage:
            continue
        if fraction>Decimal("1.01"):
            raise GlobalCreditError("BIS reporting GDP exceeds total world GDP")
        result[quarter]=sum((weight*value for weight,value in pairs),Decimal(0))/total
        coverage[quarter]=fraction*Decimal(100)
    if not result:
        raise GlobalCreditError("No quarters meet BIS-country world-GDP coverage threshold")
    return result,coverage
