"""Original named iShares III annual schedules and current SWDA holdings CSV.

Reported fund positions and accounting controls only. No inferred identifiers,
monthly interpolation, index constituents or derivative country look-through.
"""
from __future__ import annotations
from collections import OrderedDict
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from threading import RLock

from .source_evidence import record_acquisition_receipt

FUND="iShares Core MSCI World UCITS ETF"
ISIN="IE00B4L5Y983"
CSV_URL="https://www.ishares.com/uk/professionals/en/products/251882/ishares-core-msci-world-ucits-etf/latest-holdings.csv"
# These full original documents were independently inspected; page numbers are PDF pages, one-based.
ANNUALS={
 2022:("036182d3c2d2ef98e487161c184c516dadc374e662cee774b694e84a53bf9321",686,708),
 2023:("971583b11bbde9c388c72930ccf485572f69fd7e013eb4f2733c40f781e99e63",790,812),
 2024:("0dc76ed1c62520b12f84827a2601a2b35d3d4c36d60d5da02eb07593ee55e075",887,909),
 2025:("4c0e090ffb7e7bcba9826649dfb5a0a835a1c2b816ed80a2ef1951da8973fe80",1047,1062),
 2026:("d889ccc681148e656300fdf3aa849abe9ca0be5c2d9c70ee7fd0c42fc3977051",1227,1242),
}
# Cache only independently rebuilt native selections, never file integrity or
# caller-owned dictionaries. Every read still hashes all original bundle bytes.
_ANNUAL_NATIVE_CACHE=OrderedDict()
_ANNUAL_NATIVE_CACHE_LOCK=RLock()
COUNTRIES=set("Australia|Austria|Belgium|Bermuda|Canada|Cayman Islands|China|Denmark|Finland|France|Germany|Hong Kong|Ireland|Isle of Man|Israel|Italy|Japan|Jersey|Luxembourg|Netherlands|New Zealand|Norway|Portugal|Singapore|Spain|Sweden|Switzerland|United Kingdom|United States|Curacao|Mauritius|Panama|Liberia|Papua New Guinea".split("|"))
NUMBER=r"(?:\(?[0-9][0-9,]*(?:\.[0-9]+)?\)?|-)"
POSITION=re.compile(r"^\s*([A-Z]{3})\s+([0-9][0-9,]*(?:\.[0-9]+)?)\s+(.+?)\s{2,}("+NUMBER+r")\s+("+NUMBER+r")\s*$")

class UcitsHoldingsError(ValueError):
    pass


def _number(raw: str, *, dash_zero: bool=False) -> str|None:
    raw=raw.strip().replace(",","").replace("−","-")
    if raw in ("-",""):
        return "0" if dash_zero else None
    if raw.startswith("(") and raw.endswith(")"):
        raw="-"+raw[1:-1]
    try:
        value=Decimal(raw)
        if not value.is_finite():
            raise InvalidOperation
        return str(value)
    except InvalidOperation as exc:
        raise UcitsHoldingsError("Invalid native holdings numeric value") from exc


def annual_url(year: int) -> str:
    return f"https://www.ishares.com/gls-download/literature/annual-report/ishares-iii-plc-en-annual-report-{year}.pdf"


def _control(text: str, label: str, *, optional: bool=False) -> Decimal:
    match=re.search(label+r"[\s\S]{0,160}?\s+("+NUMBER+r")\s+([0-9]+\.[0-9]+)",text,re.IGNORECASE)
    if not match:
        if optional:
            return Decimal(0)
        raise UcitsHoldingsError("Published annual NAV control missing: "+label)
    return Decimal(_number(match.group(1),dash_zero=True))


def _columns(page: str) -> list[list[str]]:
    lines=page.splitlines()
    for line in lines:
        if "Investment" in line:
            starts=list(re.finditer(r"\b(?:Ccy|Currency)\b",line))
            if len(starts)==2:
                cut=starts[1].start()-10
                return [[line[:cut] for line in lines],[line[cut:] for line in lines]]
    return [lines]


def parse_annual_schedule(text: str, *, year: int, pdf_sha256: str, source_url: str) -> dict:
    if year not in ANNUALS or pdf_sha256!=ANNUALS[year][0] or source_url!=annual_url(year):
        raise UcitsHoldingsError("Unverified original annual document identity")
    pages=text.split("\f")
    for page in pages:
        if (FUND.upper() not in page.upper() or "SCHEDULE OF INVESTMENTS" not in page
            or f"As at 30 June {year}" not in page):
            raise UcitsHoldingsError("Annual named fund/date/page identity mismatch")
    if "USD'000" not in text and "USD’000" not in text:
        raise UcitsHoldingsError("Annual native reporting currency/unit missing")
    # Table columns are read top-to-bottom before accounting controls are matched.
    ordered_text="\n".join(line for page in pages for column in _columns(page) for line in column)
    nav=_control(ordered_text,r"Net asset value attributable to redeemable")
    if year<=2024:
        terms={"investments":_control(ordered_text,r"Total value of investments"),
               "cash_equivalents":_control(ordered_text,r"BlackRock ICS US Dollar Liquidity Fund[~^]?(?:\s+)",optional=True),
               "cash":_control(ordered_text,r"(?m)^\s*Cash[†]?(?=\s+[0-9])"),
               "other_net_assets":_control(ordered_text,r"Other net assets")}
        # Money-market security row has a quantity before its name; control begins after its name.
        mm=re.search(r"BlackRock ICS US Dollar Liquidity Fund[~^]?\s+("+NUMBER+r")\s+[0-9]+\.[0-9]+",ordered_text)
        terms["cash_equivalents"]=Decimal(_number(mm.group(1),dash_zero=True)) if mm else Decimal(0)
    else:
        terms={"financial_assets":_control(ordered_text,r"Total financial assets at fair value through profit or loss"),
               "financial_liabilities":_control(ordered_text,r"Total financial liabilities at fair value through profit or loss"),
               "cash_and_margin_cash":_control(ordered_text,r"Cash and margin cash"),
               "cash_equivalents":_control(ordered_text,r"Total cash equivalents",optional=True),
               "other_assets_and_liabilities":_control(ordered_text,r"Other assets and liabilities")}
    difference=sum(terms.values())-nav
    if difference!=0 or nav<=0:
        raise UcitsHoldingsError("Published annual NAV identity does not reconcile")
    positions=[]
    country=None
    asset_class="Equity"
    derivative_lines=[]
    for page_no,page in enumerate(pages,1):
        derivative_page=bool(re.search(r"(?:Forward currency contracts|forward currency contracts|Futures contracts|futures contracts)",page))
        if derivative_page:
            derivative_lines.extend({"source_page_in_extract":page_no,"source_row":line,
                                     "semantics":"unparsed original derivative schedule; not ordinary security quantity or country exposure"}
                                    for line in page.splitlines() if re.match(r"\s*[A-Z]{3}\s+[0-9]",line))
        for column in _columns(page):
            for line_index,line in enumerate(column):
                kind=re.match(r"^\s*(Equities|Rights|Warrants)\s+\(",line)
                if kind:
                    asset_class={"Equities":"Equity","Rights":"Rights","Warrants":"Warrants"}[kind.group(1)]
                head=re.match(r"^\s*(.*?)\s+\((?:30 June|continued)",line)
                if head and head.group(1) in COUNTRIES:
                    country=head.group(1)
                match=POSITION.match(line)
                source_row=line
                if not match and re.match(r"\s*[A-Z]{3}\s+[0-9]",line) and line_index+1<len(column):
                    continuation=column[line_index+1]
                    if not re.match(r"\s*[A-Z]{3}\s+[0-9]",continuation):
                        match=POSITION.match(line.rstrip()+" "+continuation.strip())
                        source_row=line+"\n"+continuation
                if not match and asset_class=="Warrants":
                    match=re.match(r"^\s*([A-Z]{3})\s+([0-9,]+)\s+(.+?)\s+(-)(0\.00)\s*$",line)
                if not match:
                    continue
                ccy,quantity,name,value,weight=match.groups()
                if re.fullmatch(r"[A-Z]{3}",name) or "Futures" in name or re.search(r"[0-9]{2}/[0-9]{2}/[0-9]{4}",name) or re.match(r"[A-Z]{3}\s+[0-9]",name):
                    continue
                if name.lower().startswith(("total ","cash ")):
                    continue
                positions.append({"source_row":source_row.strip(),"source_page_in_extract":page_no,
                    "name":name,"currency":ccy,"quantity":_number(quantity),
                    "quantity_unit":"reported holding quantity; unit not separately specified",
                    "value_usd_thousands":_number(value),"percent_of_fund_nav":_number(weight),
                    "asset_class":"Money Market" if "Liquidity Fund" in name else asset_class,
                    "reported_country_label":country,"country_semantics":"issuer incorporation where source explicitly states; not revenue exposure",
                    "isin":None,"lei":None,"cusip":None})
    if not positions:
        raise UcitsHoldingsError("No original annual security position rows parsed")
    equity_total=None
    m=re.search(r"Total (?:investments in )?equities\s+("+NUMBER+r")\s+[0-9]+\.[0-9]+",ordered_text,re.IGNORECASE)
    if m:
        equity_total=Decimal(_number(m.group(1),dash_zero=True))
    else:
        m=re.search(r"Total transferable securities admitted to an official stock exchange[\s\S]{0,200}?\s+("+NUMBER+r")\s+[0-9]+\.[0-9]+",ordered_text,re.IGNORECASE)
        if m: equity_total=Decimal(_number(m.group(1),dash_zero=True))
    equity_sum=sum((Decimal(p["value_usd_thousands"] or "0") for p in positions if p["asset_class"]=="Equity"),Decimal(0))
    # Rounding may explain only at most half one native USD-thousand per published row.
    complete=equity_total is not None and abs(equity_sum-equity_total)<=Decimal(len(positions))/2
    return {"schema_version":1,"source":"ISHARES_UCITS_ANNUAL_PRIMARY_PDF","fund_name":FUND,
        "legal_entity":"iShares III plc","share_class_reference_isin":ISIN,
        "holdings_date":f"{year}-06-30","native_frequency":"annual_report_snapshot",
        "source_url":source_url,"original_sha256":pdf_sha256,"original_first_publication_at":None,
        "positions":positions,"positions_reported_in_extraction":len(positions),
        "complete_security_schedule":False,"equity_value_reconciled":complete,"equity_value_usd_thousands_parsed":str(equity_sum),
        "published_equity_value_usd_thousands":str(equity_total) if equity_total is not None else None,
        "derivative_schedule_lines":derivative_lines,
        "nav_reconciliation":{"net_assets_usd_thousands":str(nav),
            "terms_usd_thousands":{k:str(v) for k,v in terms.items()},
            "difference_usd_thousands":str(difference)},
        "limits":"Subfund assets include multiple share classes. Derivative rows remain original unparsed schedule lines; hedging is not ordinary share holdings. No individual share-class or revenue-country look-through."}


def parse_annual_pdf(original: bytes, *, year: int) -> dict:
    """Reproducible bounded extraction of hash-identified primary PDF schedule pages."""
    if year not in ANNUALS or sha256(original).hexdigest()!=ANNUALS[year][0]:
        raise UcitsHoldingsError("Unverified full annual PDF SHA")
    from pypdf import PdfReader, __version__
    if __version__!="6.21.4":
        raise UcitsHoldingsError("Annual PDF extraction requires pinned pypdf 6.21.4")
    reader=PdfReader(BytesIO(original))
    _,first,last=ANNUALS[year]
    texts=[]
    for number in range(first,last+1):
        page=reader.pages[number-1]
        if len(page.get_contents().get_data())>10_000_000:
            raise UcitsHoldingsError("Annual PDF page content exceeded bounded extraction")
        texts.append(page.extract_text(extraction_mode="layout",layout_mode_space_vertically=False))
    text="\f".join(texts)
    facts=parse_annual_schedule(text,year=year,pdf_sha256=sha256(original).hexdigest(),source_url=annual_url(year))
    if not facts["equity_value_reconciled"]:
        raise UcitsHoldingsError("Complete original annual equity values do not reconcile")
    facts["extraction"]={"tool":"pypdf","version":__version__,"mode":"layout",
        "pdf_pages":[first,last],"text_sha256":sha256(text.encode()).hexdigest()}
    facts["_extracted_text"]=text
    return facts


def parse_holdings_csv(original: bytes, *, expected_asof: str|None=None) -> dict:
    if len(original)>10_000_000:
        raise UcitsHoldingsError("Holdings CSV exceeded bounded size")
    try:
        rows=list(csv.reader(StringIO(original.decode("utf-8-sig"))))
        if rows[0][0]!="Fund Holdings as of": raise ValueError("date header")
        asof=datetime.strptime(rows[0][1],"%d/%b/%Y").date().isoformat()
        if expected_asof is not None and asof!=expected_asof:
            raise ValueError("asof mismatch")
        start=next(i for i,r in enumerate(rows) if r and r[0]=="Ticker")
        columns=["Ticker","Name","Sector","Asset Class","Market Value","Weight (%)",
                 "Notional Value","Shares","Price","Location","Exchange","Market Currency"]
        if rows[start]!=columns: raise ValueError("schema")
        positions=[]
        for row in rows[start+1:]:
            if not row or all(not item.strip() for item in row): continue
            if len(row)!=len(columns): raise ValueError("row width")
            item=dict(zip(columns,row))
            positions.append({"ticker":item["Ticker"],"name":item["Name"],"sector":item["Sector"],
                "asset_class":item["Asset Class"],"market_value":_number(item["Market Value"]),
                "percent_of_fund_nav":_number(item["Weight (%)"]),"notional_value":_number(item["Notional Value"]),
                "quantity":_number(item["Shares"]),"price":_number(item["Price"]),
                "reported_location":item["Location"],"exchange":item["Exchange"],"currency":item["Market Currency"],
                "isin":None,"lei":None,"cusip":None,"native_row":item,
                "quantity_semantics":"native Shares column; FX/futures/cash not interpreted as ordinary equity shares"})
        if not positions: raise ValueError("empty")
    except (ValueError,IndexError,StopIteration,csv.Error,UnicodeError) as exc:
        raise UcitsHoldingsError("Original UCITS CSV schema or requested asof mismatch") from exc
    return {"schema_version":1,"source":"ISHARES_UCITS_PRIMARY_CSV","fund_name":FUND,
        "share_class_reference_isin":ISIN,"holdings_date":asof,"native_frequency":"dated_published_snapshot",
        "source_url":CSV_URL,"original_sha256":sha256(original).hexdigest(),"original_first_publication_at":None,
        "positions":positions,"positions_reported_in_extraction":len(positions),
        "rounded_weights_sum_pct":str(sum((Decimal(p["percent_of_fund_nav"] or "0") for p in positions),Decimal(0))),
        "market_value_currency":"USD, fund base currency; Market Currency remains native security currency",
        "limits":"Rounded weights preserved without forcing 100 percent. Location is publisher label, not verified revenue country. No historical date inferred from requested URL."}


def _annual_native_facts(original: bytes, year: int) -> dict:
    digest=sha256(original).hexdigest()
    if year not in ANNUALS or digest!=ANNUALS[year][0]:
        raise UcitsHoldingsError("Unverified full annual PDF SHA")
    with _ANNUAL_NATIVE_CACHE_LOCK:
        cached=_ANNUAL_NATIVE_CACHE.get(digest)
        if cached is None:
            cached=json.dumps(parse_annual_pdf(original,year=year),sort_keys=True).encode()
            _ANNUAL_NATIVE_CACHE[digest]=cached
            if len(_ANNUAL_NATIVE_CACHE)>5:
                _ANNUAL_NATIVE_CACHE.popitem(last=False)
        else:
            _ANNUAL_NATIVE_CACHE.move_to_end(digest)
    return json.loads(cached)


def _verify_archive(folder: Path) -> dict:
    try:
        if folder.is_symlink() or (folder/"manifest.json").is_symlink(): raise ValueError("symlink")
        manifest=json.loads((folder/"manifest.json").read_text())
        if (manifest["schema_version"]!=1 or manifest["publisher"]!="iShares / BlackRock"
                or manifest["fund_name"]!=FUND or manifest["share_class_reference_isin"]!=ISIN
                or manifest["original_first_publication_at"] is not None
                or folder.parent.name!=manifest["holdings_date"] or folder.parent.parent.name!=ISIN
                or folder.parent.parent.parent.name!="ucits"
                or datetime.fromisoformat(manifest["retrieved_at_utc"]).utcoffset() is None):
            raise ValueError("native source identity mismatch")
        source=manifest["source"]
        if source=="ISHARES_UCITS_ANNUAL_PRIMARY_PDF":
            expected={"original.pdf","facts.json","extracted.txt"}
        elif source=="ISHARES_UCITS_PRIMARY_CSV":
            expected={"original.csv","facts.json"}
        else:
            raise ValueError("unsupported native source")
        if set(manifest["files"])!=expected:
            raise ValueError("native original files missing")
        if sha256(json.dumps(manifest["files"],sort_keys=True).encode()).hexdigest()!=folder.name:
            raise ValueError("bundle digest mismatch")
        bodies={}
        for name,digest in manifest["files"].items():
            path=folder/name
            if path.parent!=folder or path.is_symlink() or path.stat().st_size>30_000_000:
                raise ValueError("original source size or symlink invalid")
            bodies[name]=path.read_bytes()
            if sha256(bodies[name]).hexdigest()!=digest:
                raise ValueError("hash mismatch")
        if source=="ISHARES_UCITS_ANNUAL_PRIMARY_PDF":
            native=_annual_native_facts(bodies["original.pdf"],int(manifest["holdings_date"][:4]))
            if native.pop("_extracted_text").encode()!=bodies["extracted.txt"]:
                raise ValueError("original PDF text extraction mismatch")
        else:
            native=parse_holdings_csv(bodies["original.csv"],expected_asof=manifest["holdings_date"])
        if (native!=json.loads(bodies["facts.json"])
                or any(native[key]!=manifest[key] for key in
                       ("source","fund_name","share_class_reference_isin","holdings_date","source_url"))):
            raise ValueError("native original facts mismatch")
        return manifest
    except (OSError,ValueError,KeyError,TypeError) as exc:
        raise UcitsHoldingsError("Immutable UCITS original source archive inconsistent") from exc


def store_ucits_source(original: bytes, *, facts: dict, root: Path) -> Path:
    if sha256(original).hexdigest()!=facts["original_sha256"]:
        raise UcitsHoldingsError("Original UCITS source SHA mismatch")
    if facts["source"]=="ISHARES_UCITS_ANNUAL_PRIMARY_PDF":
        validated=parse_annual_pdf(original,year=int(facts["holdings_date"][:4]))
        suffix="pdf"
    elif facts["source"]=="ISHARES_UCITS_PRIMARY_CSV":
        validated=parse_holdings_csv(original,expected_asof=facts["holdings_date"])
        suffix="csv"
    else:
        raise UcitsHoldingsError("Unsupported original UCITS source")
    if validated!=facts:
        raise UcitsHoldingsError("UCITS source facts differ from original content")
    record={key:value for key,value in facts.items() if key!="_extracted_text"}
    payloads={"original."+suffix:original,"facts.json":json.dumps(record,sort_keys=True).encode()}
    if "_extracted_text" in facts: payloads["extracted.txt"]=facts["_extracted_text"].encode()
    hashes={name:sha256(body).hexdigest() for name,body in payloads.items()}
    digest=sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    parent=root/"ucits"/ISIN/facts["holdings_date"]
    folder=parent/digest
    temporary=None
    try:
        parent.mkdir(parents=True,exist_ok=True)
        if not folder.exists():
            temporary=Path(tempfile.mkdtemp(prefix=".ucits-",dir=parent))
            for name,body in payloads.items():
                with (temporary/name).open("wb") as stream:
                    stream.write(body);stream.flush();os.fsync(stream.fileno())
            manifest={"schema_version":1,"publisher":"iShares / BlackRock","fund_name":FUND,
                "source":facts["source"],"source_url":facts["source_url"],"holdings_date":facts["holdings_date"],
                "original_first_publication_at":None,"retrieved_at_utc":datetime.now(timezone.utc).isoformat(),
                "share_class_reference_isin":ISIN,"files":hashes}
            (temporary/"manifest.json").write_text(json.dumps(manifest,indent=2))
            try: os.rename(temporary,folder);temporary=None
            except FileExistsError: pass
        manifest=_verify_archive(folder)
        if manifest["files"]!=hashes: raise UcitsHoldingsError("UCITS immutable source mismatch")
        record_acquisition_receipt(folder,{"publisher":"iShares / BlackRock","isin":ISIN,
            "holdings_date":facts["holdings_date"],"source_url":facts["source_url"]})
        return folder
    finally:
        if temporary is not None: shutil.rmtree(temporary,ignore_errors=True)


def read_ucits_sources(root: Path) -> dict:
    records=[]
    for folder in sorted((root/"ucits"/ISIN).glob("????-??-??/*")):
        if not re.fullmatch(r"[0-9a-f]{64}",folder.name): continue
        manifest=_verify_archive(folder)
        facts=json.loads((folder/"facts.json").read_text())
        records.append({**facts,"bundle_digest":folder.name,"manifest":manifest,
            "source_manifest_sha256":sha256((folder/"manifest.json").read_bytes()).hexdigest(),
            "immutable_manifest_retrieved_at_utc":manifest["retrieved_at_utc"]})
    return {"fund_name":FUND,"share_class_reference_isin":ISIN,
            "status":"ready" if records else "missing_original_ucits_positions","records":records}



def collect_ucits_sources(*, root: Path, years=(2022,2023,2024,2025,2026),
                         include_current: bool=True, client=None,
                         progress=None, stopped=None) -> dict:
    """Acquire fixed public originals; respect redirects, denial and source identity."""
    import httpx
from .source_policy import managed_client
    if len(years)>5 or any(year not in ANNUALS for year in years) or len(set(years))!=len(years):
        raise UcitsHoldingsError("Only the five independently verified annual documents may be acquired")
    owns=client is None
    source=client or managed_client(timeout=60,follow_redirects=False)
    jobs=[(year,annual_url(year)) for year in years]
    if include_current: jobs.append((None,CSV_URL))
    reports=[]
    halted=False
    try:
        cached=read_ucits_sources(root)["records"]
        for index,(year,url) in enumerate(jobs,1):
            if stopped is not None and stopped.is_set(): break
            if year is not None and any(r["source_url"]==url and r["original_sha256"]==ANNUALS[year][0] for r in cached):
                reports.append({"source_url":url,"status":"already_archived","holdings_date":f"{year}-06-30"})
                if progress is not None: progress(index,len(jobs),f"ucits-{year}")
                continue
            try:
                response=source.get(url,timeout=60)
                response.raise_for_status()
                original=response.content
                if len(original)>30_000_000: raise UcitsHoldingsError("Original document exceeds bounded source size")
                facts=parse_annual_pdf(original,year=year) if year else parse_holdings_csv(original)
                bundle=store_ucits_source(original,facts=facts,root=root)
                reports.append({"source_url":url,"status":"acquired","holdings_date":facts["holdings_date"],
                    "bundle_digest":bundle.name,"positions":facts["positions_reported_in_extraction"],
                    "equity_value_reconciled":facts.get("equity_value_reconciled"),
                    "original_first_publication_at":None})
            except httpx.HTTPStatusError as exc:
                status=exc.response.status_code
                halted=status in (400,401,403,429) or status>=500 or 300<=status<400
                reports.append({"source_url":url,"status":"blocked" if halted else "failed",
                                "http_status":status,"reason":"original_publisher_access_unavailable"})
            except (UcitsHoldingsError,httpx.HTTPError,ValueError):
                reports.append({"source_url":url,"status":"failed","reason":"original_content_identity_or_accounting_validation_failed"})
            finally:
                if progress is not None: progress(index,len(jobs),f"ucits-{year or 'current'}")
            if halted: break
    finally:
        if owns: source.close()
    complete=len(reports)==len(jobs) and all(r["status"] in ("acquired","already_archived") for r in reports)
    return {"status":"blocked" if halted else "complete" if complete else "partial",
            "fund_name":FUND,"reports":reports,"original_index_constituents":False,
            "original_first_publication_verified":False}

def main() -> int:
    import argparse
    parser=argparse.ArgumentParser(description="Import original named iShares annual PDF or actual dated holdings CSV")
    parser.add_argument("--file",type=Path,required=True)
    parser.add_argument("--year",type=int,choices=list(ANNUALS))
    parser.add_argument("--asof")
    parser.add_argument("--root",type=Path,default=Path(os.environ.get("FINANCE_HOLDINGS_DIR","/data/holdings")))
    args=parser.parse_args()
    original=args.file.read_bytes()
    facts=parse_annual_pdf(original,year=args.year) if args.year else parse_holdings_csv(original,expected_asof=args.asof)
    folder=store_ucits_source(original,facts=facts,root=args.root)
    print(json.dumps({"bundle":str(folder),"source":facts["source"],"holdings_date":facts["holdings_date"],
                      "positions":facts["positions_reported_in_extraction"]}))
    return 0

if __name__=="__main__": raise SystemExit(main())
