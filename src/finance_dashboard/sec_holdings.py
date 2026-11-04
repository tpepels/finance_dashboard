"""SEC N-PORT dated fund-portfolio holdings, no inferred UCITS look-through.

Import real SEC XML with matching SEC submission accession/acceptance metadata.
The resulting country is the reported issuer/investment country (Form C.5.a),
not the separate confidential economic-risk exposure of C.5.b. Source
availability begins on filing acceptance, NOT at the month of holdings.
"""
from __future__ import annotations

from datetime import date, datetime, timezone, timedelta
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


def conservative_eligibility_from_sec_submissions(meta: dict, accession: str) -> tuple[datetime, str]:
    """SEC filing DATE is dependable; acceptance JSON timezone may not be.

    SEC does NOT guarantee a publication timestamp. We delay source eligibility
    by two calendar dates beyond the official filing date to avoid treating an
    acceptance timestamp as exact public visibility. This is a conservative
    research rule, NOT proof of the actual dissemination instant.
    """
    filings = meta.get("filings", {}).get("recent", {})
    numbers = filings.get("accessionNumber", [])
    forms = filings.get("form", [])
    accepted = filings.get("acceptanceDateTime", [])
    filed = filings.get("filingDate", [])
    if not (len(numbers) == len(forms) == len(accepted) == len(filed)):
        raise HoldingsError("Incomplete official SEC submissions metadata columns")
    hits = [i for i, number in enumerate(numbers) if number == accession]
    if len(hits) != 1 or forms[hits[0]] not in NPORT_FORMS:
        raise HoldingsError("Accession not uniquely confirmed as NPORT-P/A by SEC metadata")
    if not isinstance(accepted[hits[0]], str) or not accepted[hits[0]]:
        raise HoldingsError("SEC raw acceptance audit timestamp absent")
    filed_day = date.fromisoformat(filed[hits[0]])
    eligible = datetime.combine(filed_day + timedelta(days=2),
                                datetime.min.time(), tzinfo=timezone.utc)
    return eligible, accepted[hits[0]]


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
    eligible_at, raw_acceptance = conservative_eligibility_from_sec_submissions(sec_metadata,accession)
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
    if period > eligible_at.date():
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
        # SEC derivative market values are not equivalent to look-through
        # underlying economic exposure; exclude them from issuer-country bars.
        asset_cat = (_find_first(security,"assetCat") or "").upper()
        derivative = asset_cat in {"DE", "DCR", "DFE", "DIR", "DO", "DCO"}
        if derivative or pct < 0 or payoff not in ("long", "") or value < 0:
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
        "eligible_after_buffer_utc":eligible_at.isoformat(),
        "available_at_utc":eligible_at.isoformat(),
        "sec_acceptance_timestamp_unverified_timezone":raw_acceptance,
        "availability_time_quality":"conservative_filing_date_plus_two_days_not_actual_public_dissemination",
        "reporting_semantics":("N-PORT fund holdings as of holdings_date; public "
                               "actual public dissemination time is NOT verified; eligibility "
                               "uses official filingDate plus two calendar days."),
        "country_semantics":("N-PORT C.5.a issuer country of organization for non-derivative "
                             "long investments; derivative market value/issuer does not "
                             "identify the underlying country exposure. NOT "
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



def _position_facts(xml: bytes) -> list[dict]:
    """Native security fields; no issuer consolidation or derivative look-through."""
    fields = {"name":"name", "lei":"lei", "security_title":"title", "cusip":"cusip",
              "quantity":"balance", "quantity_unit":"units", "currency":"curCd",
              "value_usd":"valUSD", "percent_of_fund_nav":"pctVal",
              "asset_category":"assetCat", "issuer_category":"issuerCat",
              "issuer_country":"invCountry", "payoff_profile":"payoffProfile"}
    investments = _section(ET.fromstring(xml), "invstOrSecs")
    return [{**{key:_find_first(item, tag) for key,tag in fields.items()},
             "source_row":index, "source_xml":ET.tostring(item, encoding="unicode")}
            for index,item in enumerate(investments,1) if _name(item)=="invstOrSec"]


def reconcile_nport_aggregate(current: dict, original: dict) -> None:
    """New metadata bytes cannot replace old metadata hashes or stored capture facts."""
    if current.get("xml_sha256") != original.get("xml_sha256"):
        raise HoldingsError("Recovered original XML SHA does not match stored filing")
    keys = ("instrument_id", "sec_cik", "sec_series_id", "accession", "source_url",
            "holdings_date", "available_at_utc", "eligible_after_buffer_utc",
            "positions_reported", "positions_unclassified", "positions_excluded_short_or_derivative",
            "reported_long_nav_percent", "classified_long_nav_percent",
            "unclassified_long_nav_percent", "countries", "complete_share_of_nav")
    if any(current.get(key) != original.get(key) for key in keys):
        raise HoldingsError("Recovered original country aggregate does not reconcile")


def _verify_source_bundle(folder: Path, instrument_id: str|None=None, accession: str|None=None) -> dict:
    try:
        if folder.is_symlink():
            raise ValueError("symlink")
        manifest=json.loads((folder/"manifest.json").read_text())
        if sha256(json.dumps(manifest["files"],sort_keys=True).encode()).hexdigest()!=folder.name:
            raise ValueError("bundle digest mismatch")
        for name, digest in manifest["files"].items():
            path=folder/name
            if path.is_symlink() or path.parent != folder or sha256(path.read_bytes()).hexdigest()!=digest:
                raise ValueError("hash mismatch")
        if (manifest.get("schema_version")!=1 or manifest["source"] != "SEC_NPORT_PRIMARY_XML"
            or (instrument_id is not None and manifest["instrument_id"]!=instrument_id)
            or (accession is not None and manifest["accession"]!=accession)
            or folder.parent.name!=manifest["accession"]
            or folder.parent.parent.name!="sources"
            or folder.parent.parent.parent.name!=manifest["instrument_id"]):
            raise ValueError("source identity")
        xml=(folder/"original.xml").read_bytes()
        parsed=parse_nport(xml,instrument_id=manifest["instrument_id"],accession=manifest["accession"],
            filing_url=manifest["source_url"],sec_metadata=json.loads((folder/"metadata.json").read_text()),
            expected_series_id=manifest["sec_series_id"])
        if (parsed["holdings_date"]!=manifest["holdings_date"]
            or json.loads((folder/"positions.json").read_text())!=_position_facts(xml)):
            raise ValueError("original source facts identity")
        return manifest
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HoldingsError("SEC immutable original source bundle inconsistent") from exc


def store_source_bundle(xml: bytes, *, sec_metadata: dict, aggregate: dict,
                        root: Path=ROOT, metadata_responses: list[dict]|None=None) -> Path:
    """Archive original bytes separately; never rewrite an existing aggregate record."""
    import shutil
    import tempfile
    from .source_evidence import record_acquisition_receipt
    current=parse_nport(xml,instrument_id=aggregate["instrument_id"],
        accession=aggregate["accession"],filing_url=aggregate["source_url"],
        sec_metadata=sec_metadata,expected_series_id=aggregate["sec_series_id"])
    reconcile_nport_aggregate(current,aggregate)
    payloads={"original.xml":xml,
              "metadata.json":json.dumps(sec_metadata,sort_keys=True).encode(),
              "positions.json":json.dumps(_position_facts(xml),sort_keys=True).encode()}
    response_urls=[]
    for index,response in enumerate(metadata_responses or []):
        payloads[f"submissions-{index}.json"]=response["body"]
        response_urls.append({"file":f"submissions-{index}.json","url":response["url"]})
    hashes={name:sha256(body).hexdigest() for name,body in payloads.items()}
    digest=sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    parent=root/aggregate["instrument_id"] / "sources" / aggregate["accession"]
    folder=parent/digest
    temporary=None
    try:
        parent.mkdir(parents=True,exist_ok=True)
        if not folder.exists():
            temporary=Path(tempfile.mkdtemp(prefix=".sec-",dir=parent))
            for name,body in payloads.items():
                with (temporary/name).open("wb") as stream:
                    stream.write(body);stream.flush();os.fsync(stream.fileno())
            manifest={"schema_version":1,"source":"SEC_NPORT_PRIMARY_XML",
                "instrument_id":aggregate["instrument_id"],"accession":aggregate["accession"],
                "source_url":aggregate["source_url"],"holdings_date":aggregate["holdings_date"],
                "sec_series_id":aggregate["sec_series_id"],"files":hashes,
                "metadata_responses":response_urls,
                "retrieved_at_utc":datetime.now(timezone.utc).isoformat(),
                "original_first_publication_at":None,
                "metadata_note":"Current verified metadata archived independently; original stored aggregate metadata hash is preserved",
                "stored_aggregate_source_metadata_sha256":aggregate["source_metadata_sha256"],
                "country_semantics":aggregate["country_semantics"]}
            (temporary/"manifest.json").write_text(json.dumps(manifest,indent=2))
            try:
                os.rename(temporary,folder)
                temporary=None
            except FileExistsError:
                pass
        manifest=_verify_source_bundle(folder)
        if manifest["files"]!=hashes:
            raise HoldingsError("SEC immutable original source bundle inconsistent")
        record_acquisition_receipt(folder,{"publisher":"SEC", "instrument_id":aggregate["instrument_id"],
            "accession":aggregate["accession"],"source_url":aggregate["source_url"]})
        return folder
    finally:
        if temporary is not None:
            shutil.rmtree(temporary,ignore_errors=True)


def read_position_source(root: Path, instrument_id: str, accession: str) -> dict:
    if instrument_id not in instruments() or not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}",accession):
        raise HoldingsError("Invalid original source identity")
    parent=root/instrument_id/"sources"/accession
    folders=sorted(p for p in parent.glob("*") if re.fullmatch(r"[0-9a-f]{64}",p.name))
    if not folders and not parent.exists():
        return {"instrument_id":instrument_id,"accession":accession,
                "status":"missing_original_positions","positions":[]}
    # A→B→A must select the latest successful acquisition of A, not B's newer
    # immutable creation timestamp. Any corrupt receipt fails the whole read.
    manifests=[(folder,_verify_source_bundle(folder,instrument_id,accession)) for folder in folders]
    urls={manifest["source_url"] for _,manifest in manifests}
    if len(urls)!=1 or not (parent/"retrievals").is_dir():
        raise HoldingsError("SEC original source receipt identity invalid")
    from .source_reconciliation import _selected_manifest, EvidenceError
    try:
        observed,manifest_hash,path,manifest,selection=_selected_manifest(parent,
            {"publisher":"SEC","instrument_id":instrument_id,"accession":accession,"source_url":next(iter(urls))})
    except EvidenceError as exc:
        raise HoldingsError("SEC original source receipt invalid") from exc
    folder=path.parent
    return {"instrument_id":instrument_id,"accession":accession,"status":"ready",
            "manifest":manifest,"bundle_digest":folder.name,"selection_method":selection,
            "acquisition_observed_at_utc":observed.isoformat(),"manifest_sha256":manifest_hash,
            "positions":json.loads((folder/"positions.json").read_text())}

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
                      "eligible_after_conservative_buffer":data["available_at_utc"],
                      "issuer_country_coverage_pct":data["classified_long_nav_percent"],
                      "complete":data["complete_share_of_nav"]},indent=2))


if __name__ == "__main__":
    main()
