"""Wisesheets SEC-reporting listed company profit dataset (not world profits).

The free tier covers SEC EDGAR filers, not all world exchanges. This
collector retrieves the complete entitled company universe and annual net
income in bounded API batches, collapses multiple tickers per issuer CIK,
converts reported currencies to USD using historical ECB cross-rates, and
compares results to World Bank world nominal GDP. The result is explicitly
a US-SEC-REPORTER numerator, never the global listed-company numerator.

No provider token, complete raw API body or account data is serialized.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from collections import defaultdict
import csv
from io import StringIO
import json
import os
from pathlib import Path
import time
from typing import Any

import httpx

BASE = "https://api.wisesheets.io/v1"
ECB = "https://data-api.ecb.europa.eu/service/data/EXR"
WDI = "https://api.worldbank.org/v2/country/WLD/indicator/NY.GDP.MKTP.CD"
CURRENCIES = frozenset({
    "USD", "EUR", "GBP", "CHF", "CAD", "JPY", "AUD", "HKD", "SEK", "NOK",
    "DKK", "CNY", "SGD", "KRW", "INR", "BRL", "MXN", "NZD", "ZAR", "ILS",
    "TRY", "PLN", "CZK", "HUF", "RON", "IDR", "MYR", "THB", "PHP",
})
BATCH_SIZE = 100
MAX_COMPANY_PAGES = 400
MAX_COMPANIES = 40000


class WisesheetsError(ValueError):
    pass


def _decimal(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
    except (ValueError, InvalidOperation, TypeError) as exc:
        raise WisesheetsError("Invalid financial value") from exc
    if not result.is_finite():
        raise WisesheetsError("Nonfinite financial value")
    return result


def parse_companies(payload: dict) -> tuple[list[dict], str | None]:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise WisesheetsError("Company discovery response missing data")
    meta = payload.get("meta")
    if not isinstance(meta, dict) or "nextCursor" not in meta:
        raise WisesheetsError("Company pagination cursor missing")
    companies = []
    for item in payload["data"]:
        if not isinstance(item, dict):
            raise WisesheetsError("Invalid filer row")
        cik = str(item.get("cik") or "").lstrip("0")
        ticker = str(item.get("ticker") or "").strip().upper()
        if not cik.isdigit() or not ticker or len(ticker) > 24:
            raise WisesheetsError("Invalid SEC issuer CIK or ticker")
        companies.append({
            "cik": cik, "ticker": ticker,
            "has_financials": item.get("hasFinancials") is True,
            "status": str(item.get("status") or "unknown"),
        })
    cursor = meta["nextCursor"]
    if cursor is not None and (not isinstance(cursor, str) or not cursor):
        raise WisesheetsError("Invalid company pagination cursor")
    return companies, cursor


def unique_issuers(rows: list[dict]) -> dict[str, dict]:
    """Deduplicate share classes/aliases by SEC CIK, with stable ticker choice."""
    issuers = {}
    for row in rows:
        key = row["cik"]
        if key not in issuers or (
            row["has_financials"] and not issuers[key]["has_financials"]
        ) or (
            row["has_financials"] == issuers[key]["has_financials"]
            and row["ticker"] < issuers[key]["ticker"]
        ):
            issuers[key] = row
    return issuers


def parse_financials(payload: dict, requested: dict[str, str]) -> dict[tuple[str, int], dict]:
    """Fiscal-year net income; retain losses and SEC XBRL provenance."""
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise WisesheetsError("Financial response missing observations")
    meta = payload.get("meta") or {}
    if not isinstance(meta, dict) or meta.get("layout") not in (None, "long"):
        raise WisesheetsError("Unsupported financial response layout")
    records = {}
    for row in payload["data"]:
        if not isinstance(row, dict):
            raise WisesheetsError("Malformed financial row")
        symbol = str(row.get("ticker") or "").upper()
        cik = str(row.get("cik") or "").lstrip("0")
        if requested.get(symbol) != cik:
            raise WisesheetsError("Returned financial company identity mismatch")
        if row.get("metric") != "net_income" or row.get("fiscalPeriod") != "FY":
            raise WisesheetsError("Nonannual or wrong financial metric")
        year = row.get("fiscalYear")
        if not isinstance(year, int) or not 2000 <= year <= date.today().year:
            raise WisesheetsError("Invalid fiscal year")
        try:
            period_end = date.fromisoformat(str(row.get("periodEnd")))
        except (ValueError, TypeError) as exc:
            raise WisesheetsError("Invalid fiscal end date") from exc
        if abs(period_end.year - year) > 1 or period_end > date.today():
            raise WisesheetsError("Fiscal period unexpectedly distant or future")
        unit = str(row.get("unit") or "").strip().upper()
        if not unit or len(unit) > 24:
            raise WisesheetsError("Financial currency is missing")
        source = row.get("source")
        source = source if isinstance(source, dict) else {}
        if source.get("isSuperseded") is True:
            continue
        verifiable = bool(source.get("accession") and source.get("filingDate")
                          and source.get("kind") == "reported")
        if verifiable:
            try:
                filed = date.fromisoformat(str(source["filingDate"]))
            except ValueError as exc:
                raise WisesheetsError("Invalid source filing date") from exc
        else:
            # Some free-tier rows have no SEC accession. Preserve as a
            # coverage diagnostic but exclude them from verified totals.
            filed = date.min
        record = {
            "cik": cik, "year": year, "period_end": period_end,
            "unit": unit, "amount": _decimal(row.get("value")),
            "filing_date": filed, "accession": str(source.get("accession") or ""),
            "source_is_verifiable": verifiable,
        }
        key = (cik, year)
        older = records.get(key)
        if older is None or (verifiable, record["period_end"], filed, record["accession"]) > (
            older["source_is_verifiable"], older["period_end"],
            older["filing_date"], older["accession"]
        ):
            records[key] = record
    return records


def parse_ecb_currency(payload: str, currency: str) -> dict[date, Decimal]:
    reader = csv.DictReader(StringIO(payload.lstrip("\\ufeff")))
    if not reader.fieldnames or not {"KEY", "TIME_PERIOD", "OBS_VALUE"}.issubset(reader.fieldnames):
        raise WisesheetsError("ECB cross-rate CSV schema missing")
    expected = f"EXR.D.{currency}.EUR.SP00.A"
    observations = {}
    for row in reader:
        if row["KEY"] != expected:
            raise WisesheetsError("ECB currency series mismatch")
        if row["OBS_VALUE"] in ("", "."):
            continue
        day = date.fromisoformat(row["TIME_PERIOD"])
        if day in observations:
            raise WisesheetsError("Duplicate ECB FX observation")
        value = _decimal(row["OBS_VALUE"])
        if value <= 0:
            raise WisesheetsError("Invalid ECB FX value")
        observations[day] = value
    if not observations:
        raise WisesheetsError("ECB currency source has no data")
    return observations


def parse_world_gdp(payload: Any) -> dict[int, Decimal]:
    if not isinstance(payload, list) or len(payload) != 2 or not isinstance(payload[1], list):
        raise WisesheetsError("Malformed WDI GDP response")
    if payload[0].get("pages") != 1:
        raise WisesheetsError("World GDP history is incomplete or paged")
    result = {}
    for row in payload[1]:
        if row.get("indicator", {}).get("id") != "NY.GDP.MKTP.CD" or row.get("countryiso3code") != "WLD":
            raise WisesheetsError("World GDP indicator/geography mismatch")
        if row.get("value") is None:
            continue
        year = int(row["date"])
        if year in result:
            raise WisesheetsError("Duplicate world GDP year")
        value = _decimal(row["value"])
        if value <= 0:
            raise WisesheetsError("Invalid world nominal GDP")
        result[year] = value
    if not result:
        raise WisesheetsError("No world GDP")
    return result


class WisesheetsClient:
    def __init__(self, key: str | None = None, client: httpx.Client | None = None,
                 min_request_spacing: float = 0.34):
        key = key or os.environ.get("WISESHEETS_API_KEY")
        if not key:
            raise WisesheetsError("WISESHEETS_API_KEY is required")
        self._own = client is None
        self.client = client or httpx.Client(timeout=30)
        self.headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
        self.spacing = min_request_spacing
        self.last_request = 0.0
        self.requests_made = 0

    def close(self):
        if self._own:
            self.client.close()

    def _request(self, url: str, *, params: dict | None = None, authenticated: bool = True) -> Any:
        if authenticated:
            wait = self.spacing - (time.monotonic() - self.last_request)
            if wait > 0:
                time.sleep(wait)
        try:
            response = self.client.get(url, params=params,
                                       headers=self.headers if authenticated else {"Accept": "application/json"})
        except httpx.HTTPError as exc:
            raise WisesheetsError("Provider transport error; details redacted") from None
        if authenticated:
            self.last_request = time.monotonic()
            self.requests_made += 1
        if response.status_code != 200:
            raise WisesheetsError(f"Provider refused request with status {response.status_code}")
        try:
            return response.json() if authenticated or "/indicator/" in url else response.text
        except ValueError as exc:
            raise WisesheetsError("Invalid provider JSON") from exc

    def plan(self) -> dict:
        row = self._request(f"{BASE}/me/")
        plan = row.get("plan") if isinstance(row, dict) else None
        if not isinstance(plan, dict):
            raise WisesheetsError("Key entitlement information unavailable")
        features = plan.get("features") or []
        if not {"fundamentals"}.issubset(set(features)):
            raise WisesheetsError("Key lacks annual fundamentals entitlement")
        return {
            "code": str(plan.get("planCode") or "unknown"),
            "history_years": int(plan.get("limits", {}).get("historyYears", 0)),
            "requests_per_minute": int(plan.get("limits", {}).get("requestsPerMinute", 0)),
            "monthly_requests": int(plan.get("limits", {}).get("monthlyRequests", 0)),
        }

    def companies(self) -> dict[str, dict]:
        rows, seen_cursors = [], set()
        cursor = None
        for page in range(MAX_COMPANY_PAGES):
            params = {"limit": 100}
            if cursor:
                params["cursor"] = cursor
            data = self._request(f"{BASE}/companies/", params=params)
            items, cursor = parse_companies(data)
            if not items:
                if cursor is not None:
                    raise WisesheetsError("Empty company page with next cursor")
                break
            rows.extend(items)
            if len(rows) > MAX_COMPANIES:
                raise WisesheetsError("Issuer universe exceeds configured safety cap")
            if cursor is None:
                break
            if cursor in seen_cursors:
                raise WisesheetsError("Repeated company cursor")
            seen_cursors.add(cursor)
        else:
            raise WisesheetsError("Incomplete company-pagination traversal")
        if not rows:
            raise WisesheetsError("No issuer rows")
        return unique_issuers(rows)

    def earnings(self, issuer_lookup: dict[str, dict], *, batch_size: int = BATCH_SIZE) -> dict:
        if not 1 <= batch_size <= 100:
            raise ValueError("Invalid financial batch size")
        chosen = sorted(
            (x for x in issuer_lookup.values() if x["has_financials"]),
            key=lambda x: x["ticker"],
        )
        records = {}
        for index in range(0, len(chosen), batch_size):
            batch = chosen[index:index+batch_size]
            ticker_to_cik = {r["ticker"]: r["cik"] for r in batch}
            response = self._request(f"{BASE}/financials/", params={
                "tickers": ",".join(ticker_to_cik), "metrics": "net_income",
                "period": "last5y", "frequency": "annual",
                "layout": "long", "include": "source",
            })
            got = parse_financials(response, ticker_to_cik)
            for key, record in got.items():
                if key in records:
                    raise WisesheetsError("Issuer unexpectedly appears in multiple financial batches")
                records[key] = record
        if not records:
            raise WisesheetsError("No SEC net income financial data")
        return records

    def fx_history(self, currency: str, start: str) -> dict[date, Decimal]:
        if currency not in CURRENCIES or currency == "EUR":
            raise WisesheetsError("Unsupported ECB reporting currency")
        # ECB public endpoint, not charged against Wisesheets quotas.
        url = f"{ECB}/D.{currency}.EUR.SP00.A"
        try:
            response = self.client.get(url, params={"format": "csvdata", "startPeriod": start},
                                       headers={"Accept": "text/csv"}, timeout=30)
        except httpx.HTTPError:
            raise WisesheetsError("ECB FX request error") from None
        if response.status_code != 200:
            raise WisesheetsError(f"ECB has no quote for {currency}")
        return parse_ecb_currency(response.text, currency)

    def world_gdp(self) -> dict[int, Decimal]:
        data = self._request(WDI, params={"format": "json", "per_page": 100},
                             authenticated=False)
        return parse_world_gdp(data)


def _fiscal_fx_multiplier(currency: str, period_end: date,
                          fx: dict[str, dict[date, Decimal]]) -> Decimal | None:
    """Mean paired daily USD/foreign exchange rate over 365 days ending FY."""
    if currency == "USD":
        return Decimal(1)
    usd = fx.get("USD")
    if not usd:
        return None
    begin = period_end - timedelta(days=365)
    days = sorted(d for d in usd if begin <= d <= period_end)
    if currency == "EUR":
        ratios = [usd[d] for d in days]
    else:
        foreign = fx.get(currency)
        if not foreign:
            return None
        ratios = [usd[d] / foreign[d] for d in days if d in foreign]
    if len(ratios) < 120:
        return None
    return sum(ratios, Decimal(0)) / Decimal(len(ratios))


def calculate_sec_earnings(
    issuers: dict[str, dict],
    financials: dict[tuple[str, int], dict],
    fx: dict[str, dict[date, Decimal]],
    world_gdp: dict[int, Decimal],
) -> dict:
    """Aggregate current SEC-reporting issuer universe, never claim world coverage."""
    totals = defaultdict(Decimal)
    included = defaultdict(set)
    excluded_units = defaultdict(lambda: defaultdict(int))
    missing_financials = defaultdict(int)
    untraceable = defaultdict(int)
    historical_filers = defaultdict(set)
    fx_cache = {}
    for (cik, year), row in financials.items():
        if cik not in issuers or year < date.today().year - 6:
            raise WisesheetsError("Unexpected issuer or historical period")
        historical_filers[year].add(cik)
        if row.get("source_is_verifiable") is False:
            untraceable[year] += 1
            continue
        unit = row["unit"]
        if unit not in CURRENCIES:
            excluded_units[year][unit] += 1
            continue
        key = (unit, row["period_end"])
        if key not in fx_cache:
            fx_cache[key] = _fiscal_fx_multiplier(unit, row["period_end"], fx)
        rate = fx_cache[key]
        if rate is None:
            excluded_units[year][unit] += 1
            continue
        totals[year] += row["amount"] * rate
        included[year].add(cik)
    output = []
    universe = len(issuers)
    for year in sorted(world_gdp):
        if year not in historical_filers:
            continue
        earnings = totals[year]
        gdp = world_gdp[year]
        if gdp <= 0:
            raise WisesheetsError("Invalid GDP denominator")
        output.append({
            "year": year,
            "sec_filer_net_income_usd": str(earnings),
            "world_gdp_usd": str(gdp),
            "sec_filer_income_as_pct_of_world_gdp": str(earnings / gdp * Decimal(100)),
            "reporting_issuers": len(historical_filers[year]),
            "usd_converted_issuers": len(included[year]),
            "unconvertible_issuers_by_currency": dict(sorted(excluded_units[year].items())),
            "untraceable_earnings_issuers": untraceable[year],
            "usd_conversion_coverage_pct_of_reporting_issuers": str(
                Decimal(100) * len(included[year]) / len(historical_filers[year])
            ),
            "current_universe_issuer_count": universe,
        })
    if not output:
        raise WisesheetsError("No fiscal years matched world GDP history")
    return {
        "schema_version": 1,
        "id": "profit.us_sec_filers.world_gdp_share",
        "status": "partial_us_sec_reporter_coverage",
        "description": "SEC-reporting US-listed issuer net income divided by nominal world GDP. NOT a global listed-company profit share.",
        "currency": "USD",
        "frequency": "A",
        "source": "Wisesheets SEC EDGAR XBRL, ECB FX, World Bank GDP",
        "source_urls": [
            "https://www.wisesheets.io/api/docs",
            "https://data.ecb.europa.eu/data/datasets/EXR",
            "https://data.worldbank.org/indicator/NY.GDP.MKTP.CD",
        ],
        "methodology": (
            "Current SEC filer universe, one issuer per CIK and fiscal year. "
            "Use annual net_income including negative values and zeroes. "
            "Convert each annual reported-currency flow to USD at mean daily ECB USD/currency "
            "cross rate over the fiscal period ending on periodEnd. "
            "Divide by corresponding calendar-year world nominal GDP. "
            "Issuer fiscal years may not match calendar GDP exactly. "
            "No historical delisting adjustment; universe has survivorship bias. "
            "Unconvertible currency rows excluded and counted. "
            "This does not measure complete global listed-company profits."
        ),
        "observations": output,
    }


def collect_wisesheets(
    client: WisesheetsClient, *, max_requests: int = 800,
    min_issuers: int = 5000,
) -> dict:
    plan = client.plan()
    if plan["history_years"] < 5 or plan["requests_per_minute"] < 1:
        raise WisesheetsError("Insufficient history or throttling entitlement")
    companies = client.companies()
    if len(companies) < min_issuers:
        raise WisesheetsError("Insufficient SEC filer universe coverage")
    expected_financial_batches = (sum(r["has_financials"] for r in companies.values()) + BATCH_SIZE-1) // BATCH_SIZE
    if client.requests_made + expected_financial_batches > max_requests:
        raise WisesheetsError("Expected financial query count exceeds safe monthly request budget")
    records = client.earnings(companies)
    currencies = {r["unit"] for r in records.values()}
    earliest = min(r["period_end"] for r in records.values()) - timedelta(days=365)
    fx = {}
    for currency in sorted(currencies | {"USD"}):
        if currency == "EUR":
            continue
        if currency not in CURRENCIES:
            continue
        try:
            fx[currency] = client.fx_history(currency, earliest.isoformat())
        except WisesheetsError:
            # Not all currencies have an ECB daily reference series. Report
            # omitted reporting-currency rows instead of inventing FX.
            continue
    gdp = client.world_gdp()
    result = calculate_sec_earnings(companies, records, fx, gdp)
    result["source_snapshot_at_utc"] = datetime.now(timezone.utc).isoformat()
    result["wisesheets_plan_code"] = plan["code"]
    result["history_years_entitlement"] = plan["history_years"]
    result["wisesheets_requests_used_this_run"] = client.requests_made
    result["unique_issuers_with_financials"] = len({cik for (cik, _), r in records.items() if r["source_is_verifiable"]})
    result["unique_issuers_with_any_earnings_row"] = len({cik for cik, _ in records})
    return result



def load_sec_profit_snapshot(path: Path | None = None) -> dict | None:
    """Read validated local aggregate; never fall back to a live API fetch."""
    from .catalog import DEFAULT_ROOT
    path = Path(path) if path is not None else DEFAULT_ROOT / "data" / "wisesheets" / "sec_filer_profit.json"
    if not path.is_file():
        return None
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        if (result.get("schema_version") != 1
            or result.get("id") != "profit.us_sec_filers.world_gdp_share"
            or result.get("status") != "partial_us_sec_reporter_coverage"
            or result.get("currency") != "USD"):
            raise ValueError("Incorrect SEC aggregate identity")
        years = set()
        for row in result["observations"]:
            year = row["year"]
            if year in years:
                raise ValueError("Duplicate SEC net income year")
            years.add(year)
            if not Decimal(str(row["world_gdp_usd"])).is_finite():
                raise ValueError("Invalid GDP")
            if not Decimal(str(row["sec_filer_income_as_pct_of_world_gdp"])).is_finite():
                raise ValueError("Invalid SEC profit/GDP ratio")
        timestamp = datetime.fromisoformat(result["source_snapshot_at_utc"])
        if timestamp.tzinfo is None:
            raise ValueError("Missing snapshot timezone")
        result["snapshot_age_days"] = max(0, (
            datetime.now(timezone.utc) - timestamp
        ).days)
        result["snapshot_status"] = (
            "stale" if result["snapshot_age_days"] > 45 else "current"
        )
        return result
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise WisesheetsError("Invalid SEC annual earnings snapshot") from exc

def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="build/wisesheets/sec_filer_profit.json")
    parser.add_argument("--min-issuers", type=int, default=5000)
    parser.add_argument("--max-requests", type=int, default=800)
    args = parser.parse_args()
    client = WisesheetsClient()
    try:
        result = collect_wisesheets(
            client, max_requests=args.max_requests,
            min_issuers=args.min_issuers,
        )
    finally:
        client.close()
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                   encoding="utf-8")
    tmp.replace(destination)
    print("WISESHEETS_US_SEC_EARNINGS=PASS "
          f"years={len(result['observations'])} "
          f"issuers={result['unique_issuers_with_financials']} "
          f"requests={result['wisesheets_requests_used_this_run']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
