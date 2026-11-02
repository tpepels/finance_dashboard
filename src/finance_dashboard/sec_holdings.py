"""SEC N-PORT dated fund-portfolio holdings, no inferred UCITS look-through.

Import real SEC XML with matching SEC submission accession/acceptance metadata.
The resulting country is the reported issuer/investment country (Form C.5.a),
not the separate confidential economic-risk exposure of C.5.b. Source
availability begins on filing acceptance, NOT at the month of holdings.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import argparse
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
import os
import xml.etree.ElementTree as ET

from .market import instruments

ROOT = Path(os.environ.get("FINANCE_HOLDINGS_DIR", "/data/holdings"))
MAX_XML_BYTES = 30_000_000
SEC_ARCHIVE = re.compile(r"^https://www\.sec\.gov/Archives/edgar/data/(\d+)/(\d+)/([A-Za-z0-9_.-]+\.xml)$")
NPORT_FORMS = {"NPORT-P", "NPORT-P/A"}
ISO_COUNTRY = re.compile(r"^[A-Z]{2}$")


class HoldingsError(ValueError):
    pass


def _name(element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _find_first(element, name: str) -> str | None:
    for part in element.iter():
        if _name(part) == name and part.text and part.text.strip():
            return part.text.strip()
    return None


def _section(element, name: str):
    for part in element.iter():
        if _name(part) == name:
            return part
    return None


def _decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        number = Decimal(value)
    except (ValueError, InvalidOperation):
        return None
    return number if number.is_finite() else None


def accepted_at_from_sec_submissions(meta: dict, accession: str) -> datetime:
    """Verify accession against the exact official SEC submissions JSON rows."""
    filings = meta.get("filings", {}).get("recent", {})
    numbers = filings.get("accessionNumber", [])
    forms = filings.get("form", [])
    accepted = filings.get("acceptanceDateTime", [])
    if not (len(numbers) == len(forms) == len(accepted)):
        raise HoldingsError("Incomplete SEC submissions metadata columns")
    hits = [i for i, number in enumerate(numbers) if number == accession]
    if len(hits) != 1 or forms[hits[0]] not in NPORT_FORMS:
        raise HoldingsError("Accession not uniquely confirmed as NPORT-P/A by SEC metadata")
    raw = accepted[hits[0]]
    if not isinstance(raw, str):
        raise HoldingsError("SEC acceptance timestamp absent")
    # SEC submission API uses US Eastern-local wall clock; do not silently
    # call an unzoned timestamp UTC. Retain the exact SEC time as source text.
    timestamp = datetime.fromisoformat(raw.replace("Z","+00:00"))
    if timestamp.tzinfo is None:
        from zoneinfo import ZoneInfo
        timestamp = timestamp.replace(tzinfo=ZoneInfo("America/New_York"))
    return timestamp.astimezone(timezone.utc)


def parse_nport(xml: bytes, *, instrument_id: str, accession: str,
                filing_url: str, sec_metadata: dict,
                expected_series_id: str) -> dict:
    """Parse only the fund matching the registered instrument + SEC series.

    Country weights are exposure to an issuer's country of organization,
    *not* the fund's ultimate operating-country or revenue distribution.
    """
    registry = instruments()
    item = registry.get(instrument_id)
    if item is None or item["kind"] != "etf" or item["domicile"] != "United States":
        raise HoldingsError("Official SEC N-PORT is only for registered US ETFs")
    archive = SEC_ARCHIVE.fullmatch(filing_url)
    if not archive or archive.group(2) != accession.replace("-", ""):
        raise HoldingsError("Filing URL/accession must match official SEC archives")
    cik = str(int(archive.group(1)))
    if str(int(sec_metadata.get("cik","0"))) != cik:
        raise HoldingsError("SEC submissions CIK does not match filing")
    if len(xml) > MAX_XML_BYTES or not xml.strip().startswith(b"<"):
        raise HoldingsError("XML too large or malformed")
    if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
        raise HoldingsError("External entity or DTD is not supported")
    accepted_at = accepted_at_from_sec_submissions(sec_metadata,accession)
    root = ET.fromstring(xml)
    if _name(root) != "edgarSubmission":
        raise HoldingsError("Not SEC EDGAR N-PORT XML")
    filer = _section(root,"filerInfo")
    report = _section(root,"genInfo")
    if filer is None or report is None:
        raise HoldingsError("N-PORT filing metadata missing")
    series_id = _find_first(filer,"seriesId")
    if not expected_series_id or series_id != expected_series_id:
        raise HoldingsError("Fund series identity unverified; a ticker alone is insufficient")
    form = _find_first(root,"submissionType")
    if form not in NPORT_FORMS:
        raise HoldingsError("Form does not match N-PORT")
    raw_period = _find_first(report,"repPdDate") or _find_first(report,"repPdEnd")
    if not raw_period:
        raise HoldingsError("Missing reported holdings period")
    period = date.fromisoformat(raw_period.replace("/","-"))
    if period > accepted_at.date():
        raise HoldingsError("Holding observation cannot follow public filing date")
    investments = _section(root,"invstOrSecs")
    if investments is None:
        raise HoldingsError("Missing SEC investment schedule")
    groups: dict[str, Decimal] = {}
    classified = Decimal("0")
    total_long = Decimal("0")
    missing = 0
    excluded = 0
    positions = 0
    for security in investments:
        if _name(security) != "invstOrSec":
            continue
        positions += 1
        pct = _decimal(_find_first(security,"pctVal"))
        value = _decimal(_find_first(security,"valUSD"))
        if pct is None or value is None:
            missing += 1
            continue
        if abs(pct) > Decimal("500") or abs(value) > Decimal("1e15"):
            raise HoldingsError("Implausible SEC investment value/percentage")
        payoff = (_find_first(security,"payoffProfile") or "").lower()
        if pct < 0 or payoff not in ("long", "") or value < 0:
            excluded += 1
            continue
        total_long += pct
        issuer_country = (_find_first(security,"invCountry") or "").upper()
        if ISO_COUNTRY.fullmatch(issuer_country):
            groups[issuer_country] = groups.get(issuer_country, Decimal("0")) + pct
            classified += pct
        else:
            missing += 1
    if positions == 0:
        raise HoldingsError("No SEC holdings rows")
    if classified <= 0:
        raise HoldingsError("No issuer-country holdings evidence")
    results = [{"country":country, "share_of_fund_nav_pct":str(weight)}
               for country,weight in sorted(groups.items(),key=lambda x:(-x[1],x[0]))]
    return {
        "schema_version":1,"source":"SEC_NPORT_PRIMARY_XML",
        "instrument_id":instrument_id,"fund_name":item["name"],
        "sec_cik":cik,"sec_series_id":series_id,"accession":accession,
        "source_url":filing_url, "holdings_date":period.isoformat(),
        "available_at_utc":accepted_at.isoformat(),
        "reporting_semantics":("N-PORT fund holdings as of holdings_date; public "
                               "availability begins at SEC filing acceptance date."),
        "country_semantics":("N-PORT C.5.a issuer country of organization; NOT "
                             "confidential C.5.b ultimate risk/economic exposure. "
                             "Fund-of-funds is not recursively look-through."),
        "positions_reported":positions,"positions_unclassified":missing,
        "positions_excluded_short_or_derivative":excluded,
        "reported_long_nav_percent":str(total_long),
        "classified_long_nav_percent":str(classified),
        "unclassified_long_nav_percent":str(total_long-classified),
        "classified_fraction_of_reported_long":str(classified/total_long)
             if total_long>0 else None,
        "complete_share_of_nav": bool(
             excluded == 0 and missing == 0 and
             Decimal("98")<=classified<=Decimal("102")),
        "countries":results,
        "xml_sha256":sha256(xml).hexdigest(),
        "source_metadata_sha256":sha256(json.dumps(
            sec_metadata,sort_keys=True).encode("utf-8")).hexdigest(),
        "rights":"SEC public disseminated filings; third-party filing information subject to source terms",
    }


def store_snapshot(record: dict, *, root: Path=ROOT) -> Path:
    fund = record["instrument_id"]
    if fund not in instruments() or ".." in fund or "/" in fund:
        raise HoldingsError("Invalid fund")
    # Original accession and dated public availability distinguish amendments.
    name = record["holdings_date"]+"--"+record["accession"].replace("-","")+".json"
    folder = root / fund
    folder.mkdir(parents=True,exist_ok=True)
    target = folder / name
    if target.exists():
        previous = json.loads(target.read_text(encoding="utf-8"))
        if previous != record:
            raise HoldingsError("Existing SEC accession differs: never overwrite source filings")
        return target
    with NamedTemporaryFile("w",dir=folder,encoding="utf-8",
                            prefix=".nport-",delete=False) as output:
        json.dump(record,output,indent=2)
        temp = Path(output.name)
    try:
        os.replace(temp,target)
    finally:
        temp.unlink(missing_ok=True)
    return target


def list_holdings(root: Path, instrument_id: str, *,
                  asof: date | None=None) -> dict:
    item = instruments().get(instrument_id)
    if item is None or item["kind"] != "etf":
        raise HoldingsError("Unknown or non-ETF instrument")
    entries = []
    folder = root / instrument_id
    for file in sorted(folder.glob("????-??-??--*.json")) if folder.exists() else []:
        try:
            record = json.loads(file.read_text(encoding="utf-8"))
            if (record.get("instrument_id") != instrument_id
                or record.get("source") != "SEC_NPORT_PRIMARY_XML"
                or record.get("schema_version") != 1):
                continue
            accepted = datetime.fromisoformat(record["available_at_utc"]).date()
            if asof and accepted > asof:
                continue
            entries.append(record)
        except (ValueError, KeyError, OSError):
            continue
    # Keep ALL report dates; for amendments use latest SEC accepted revision
    # actually available on the query date, not a revision filed after query.
    by_period = {}
    for record in entries:
        period=record["holdings_date"]
        if period not in by_period or (
            record["available_at_utc"] > by_period[period]["available_at_utc"]):
            by_period[period] = record
    return {
        "instrument_id":instrument_id,
        "status":"ready" if by_period else "no_dated_holdings",
        "country_semantics":"issuer_organization_not_verified_end_market_revenue",
        "coverage":"SEC filings only for US-domiciled registered ETFs, as imported locally",
        "records":sorted(by_period.values(),key=lambda x:x["holdings_date"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import original SEC N-PORT XML with SEC verified accession")
    parser.add_argument("--instrument",required=True)
    parser.add_argument("--xml",type=Path,required=True)
    parser.add_argument("--sec-submissions-json",type=Path,required=True)
    parser.add_argument("--accession",required=True)
    parser.add_argument("--filing-url",required=True)
    parser.add_argument("--series-id",required=True,
                        help="The fund's verified SEC Series ID S#########")
    parser.add_argument("--root",type=Path,default=ROOT)
    args=parser.parse_args()
    data=parse_nport(args.xml.read_bytes(),instrument_id=args.instrument,
                     accession=args.accession,filing_url=args.filing_url,
                     sec_metadata=json.loads(args.sec_submissions_json.read_text()),
                     expected_series_id=args.series_id)
    path=store_snapshot(data,root=args.root)
    print(json.dumps({"stored":str(path),"holdings_date":data["holdings_date"],
                      "publicly_available_from":data["available_at_utc"],
                      "issuer_country_coverage_pct":data["classified_long_nav_percent"],
                      "complete":data["complete_share_of_nav"]},indent=2))


if __name__ == "__main__":
    main()
