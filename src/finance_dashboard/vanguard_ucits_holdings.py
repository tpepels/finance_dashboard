"""Named Vanguard Funds plc annual/semiannual original investment schedules.

The two independently inspected full reports are pinned by their original SHA.
Reported securities reconcile to transferable securities, while derivative market
values, cash, collateral, other assets/liabilities and share classes remain distinct.
"""
from __future__ import annotations

from .source_policy import managed_client, require_managed_client

from datetime import datetime,timezone
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

from .source_evidence import record_acquisition_receipt

FUND="Vanguard FTSE All-World UCITS ETF"
ISIN="IE00B3RBWM25"
REPORTS={
    "annual-2026":{"sha256":"dbf1512a0350742a425930050ffa7218d7ffba6a425a5de5fca42801b65daecf",
        "source_url":"https://fund-docs.vanguard.com/etf-annual-report.pdf",
        "holdings_date":"2026-06-30","date_label":"30 June 2026","pages":(189,226)},
    "semiannual-2025":{"sha256":"6a21e594c4e729e22baf8da7f9df28f7b210edd56a8ef6aae1f6066841e92ccc",
        "source_url":"https://fund-docs.vanguard.com/etf-semiannual-report.pdf",
        "holdings_date":"2025-12-31","date_label":"31 December 2025","pages":(194,230)},
}
_NUMBER=r"(?:\(?[0-9][0-9,]*\)?|—|–|-)"
_POSITION=re.compile(r"^(.+?)\s+([0-9][0-9,]*)\s+("+_NUMBER+r")\s+(\(?[0-9]+\.[0-9]+%\)?)$")


class VanguardUcitsError(ValueError):
    pass


def _decimal(text: str) -> Decimal:
    text=text.replace(",","")
    if text in {"—","–","-"}: return Decimal(0)
    if text.startswith("("):text="-"+text[1:-1]
    return Decimal(text)


def _control(text: str,label: str) -> Decimal:
    text=text.replace("\f","\n")
    matches=re.findall(r"(?m)^\s*"+re.escape(label)+r"\s+("+_NUMBER+r")\s+\(?[0-9]+\.[0-9]+%\)?\s*$",text)
    if len(matches)!=1:raise VanguardUcitsError("Original schedule control absent or ambiguous: "+label)
    return _decimal(matches[0])


def _balance_control(text: str,label: str) -> Decimal:
    matches=re.findall(r"(?m)^\s*"+re.escape(label)+r"[ \t]+((?:"+_NUMBER+r"\s*){2,3})$",text)
    if len(matches)!=1:raise VanguardUcitsError("Original balance-sheet control absent or ambiguous: "+label)
    numbers=re.findall(_NUMBER,matches[0])
    return _decimal(numbers[-2])


def parse_vanguard_schedule(text: str, *, report_key: str) -> dict:
    if report_key not in REPORTS:raise VanguardUcitsError("Unverified Vanguard original report")
    report=REPORTS[report_key]
    text=text.replace("\u200c","").replace("\u00a0"," ").replace("\u200b","")
    pages=text.split("\f")
    if (not all(FUND in page for page in pages) or "Statement of Investments" not in pages[0]
            or report["date_label"] not in pages[0] or "US Dollars ($)" not in text
            or "Statement of Assets and Liabilities" not in pages[-1]
            or report["date_label"] not in pages[-1]):
        raise VanguardUcitsError("Original Vanguard legal-fund or reporting-period identity mismatch")
    investment_text,balance=text.rsplit("Statement of Assets and Liabilities",1)
    securities=_control(investment_text,"Total Transferable Securities")
    investments=_control(investment_text,"Total Investments")
    exchange_derivatives=_control(investment_text,"Total Financial Derivative Instruments Dealt in on a Regulated Market")
    otc_derivatives=_control(investment_text,"Total OTC Financial Derivative Instruments")
    other=_control(investment_text,"Other Assets and Liabilities")
    nav=_control(investment_text,"Net Assets")
    assets=_balance_control(balance,"Total Current Assets")
    liabilities=_balance_control(balance,"Total Current Liabilities")
    cash=_balance_control(balance,"Cash")
    margin=_balance_control(balance,"Margin Cash Due from Broker")
    collateral=_balance_control(balance,"Cash Collateral")
    balance_nav_label=next((line.strip().split("  ")[0] for line in balance.splitlines()
                            if line.strip().startswith("Net Assets Attributable to Holders")),None)
    if balance_nav_label is None:raise VanguardUcitsError("Original named subfund NAV control absent")
    # The literal label contains source curly quotes in real reports; locate its
    # final two current/prior numeric columns without normalizing the label.
    nav_line=next(line for line in balance.splitlines() if line.strip().startswith("Net Assets Attributable to Holders"))
    nav_numbers=re.findall(_NUMBER,nav_line)
    balance_nav=_decimal(nav_numbers[-2])
    balance_securities=_balance_control(balance,"Transferable Securities")
    derivative_rows=[line for line in balance.splitlines() if line.strip().startswith("Financial Derivative Instruments")]
    if len(derivative_rows)!=2:raise VanguardUcitsError("Original derivative asset/liability controls absent")
    derivative_assets,derivative_liabilities=(_decimal(re.findall(_NUMBER,line)[-2]) for line in derivative_rows)
    if (securities+exchange_derivatives+otc_derivatives!=investments or investments+other!=nav
            or assets-liabilities!=nav or balance_nav!=nav or balance_securities!=securities
            or derivative_assets-derivative_liabilities!=exchange_derivatives+otc_derivatives or nav<=0):
        raise VanguardUcitsError("Original Vanguard securities, derivatives or NAV controls do not reconcile")
    marker="Financial Derivative Instruments Dealt in on a Regulated Market"
    ordinary,derivative_text=investment_text.split(marker,1)
    positions=[]
    pending=[]
    country=None
    ignored={FUND,"Financial Statements","Statement of Investments",report["date_label"],
             "Number of","Shares","Fair Value","US Dollars ($)","% of Total","Net Assets",".."}
    for page_index,page in enumerate(ordinary.split("\f"),1):
        for raw in page.splitlines():
            line=raw.strip()
            if not line or line in ignored or line.isdigit():continue
            heading=re.match(r"^(.+?)\s+[0-9]+\.[0-9]+%\s+\(",line)
            if heading:
                if heading[1] not in {"Equities","Transferable Securities"}:country=heading[1]
                pending=[]
                continue
            if line.startswith("Total ") or re.match(r"^-\s+-\s",line):pending=[];continue
            match=_POSITION.match(line)
            if match:
                name,quantity,value,weight=match.groups()
                if name.strip("- ")=="":pending=[];continue
                name=" ".join([*pending,name]);pending=[]
                positions.append({"name":name,"quantity":str(_decimal(quantity)),"quantity_unit":"reported shares",
                    "value_usd":str(_decimal(value)),"percent_of_fund_nav":weight.replace("%",""),
                    "native_value":value,"asset_class":"reported transferable equity security",
                    "reported_country_label":country,"source_page_in_extract":page_index,
                    "source_row":line,"isin":None,"lei":None,"cusip":None})
            elif not any(character.isdigit() for character in line) and len(line)<120 and not line.startswith((".","%")):
                pending.append(line)
    if not positions:raise VanguardUcitsError("No original Vanguard security positions parsed")
    parsed=sum((Decimal(row["value_usd"]) for row in positions),Decimal(0))
    difference=parsed-securities
    reconciled=abs(difference)<=Decimal(len(positions))/2
    return {"schema_version":1,"source":"VANGUARD_UCITS_ORIGINAL_REPORT_PDF","report_key":report_key,
        "source_url":report["source_url"],"original_sha256":report["sha256"],"fund_name":FUND,
        "legal_entity":"Vanguard Funds plc","share_class_reference_isin":ISIN,
        "holdings_date":report["holdings_date"],"native_frequency":"annual_report_snapshot" if report_key.startswith("annual") else "semiannual_report_snapshot",
        "original_first_publication_at":None,"positions":positions,"positions_reported_in_extraction":len(positions),
        "complete_security_schedule":reconciled,"individual_share_class_lookthrough_verified":False,
        "valuation_reconciliation":{"published_transferable_security_value_usd":str(securities),
            "parsed_security_value_usd":str(parsed),"security_value_difference_usd":str(difference),
            "security_value_rounding_tolerance_usd":str(Decimal(len(positions))/2),
            "security_values_reconciled":reconciled,"total_investments_usd":str(investments),
            "exchange_derivative_market_value_usd":str(exchange_derivatives),
            "otc_derivative_market_value_usd":str(otc_derivatives),
            "net_derivative_market_value_usd":str(exchange_derivatives+otc_derivatives),
            "derivative_asset_value_usd":str(derivative_assets),"derivative_liability_value_usd":str(derivative_liabilities),
            "other_assets_and_liabilities_usd":str(other),"net_assets_usd":str(nav),
            "total_assets_usd":str(assets),"total_liabilities_usd":str(liabilities),
            "fund_balance_sheet_difference_usd":str(assets-liabilities-nav),
            "cash_usd":str(cash),"margin_cash_due_from_broker_usd":str(margin),"cash_collateral_usd":str(collateral)},
        "original_derivative_schedule_text":marker+derivative_text,
        "limits":"Named subfund assets span accumulating and distributing share classes. Securities have no reported ISIN/LEI here. Native derivative schedule retained separately; notionals are not ordinary security market values or verified country look-through. Cash and collateral remain distinct. No inferred monthly history or index constituents."}


def parse_vanguard_pdf(original: bytes, *, report_key: str) -> dict:
    report=REPORTS.get(report_key)
    if report is None or len(original)>30_000_000 or sha256(original).hexdigest()!=report["sha256"]:
        raise VanguardUcitsError("Unverified full Vanguard original report SHA")
    from pypdf import PdfReader,__version__
    if __version__!="6.21.4":raise VanguardUcitsError("Vanguard original extraction requires pinned pypdf 6.21.4")
    reader=PdfReader(BytesIO(original))
    first,last=report["pages"]
    text="\f".join(reader.pages[i-1].extract_text(extraction_mode="plain") for i in range(first,last+1))
    facts=parse_vanguard_schedule(text,report_key=report_key)
    if not facts["complete_security_schedule"]:
        raise VanguardUcitsError("Original Vanguard security values do not reconcile: "+facts["valuation_reconciliation"]["security_value_difference_usd"])
    return {**facts,"extraction":{"tool":"pypdf","version":__version__,"mode":"plain","pdf_pages":[first,last],
        "text_sha256":sha256(text.encode()).hexdigest()},"_extracted_text":text}


def _verify_archive(folder: Path) -> tuple[dict,dict]:
    try:
        manifest=json.loads((folder/"manifest.json").read_text())
        files=manifest["files"]
        if (folder.is_symlink() or (folder/"manifest.json").is_symlink()
                or set(files)!={"original.pdf","facts.json","extracted.txt"}
                or sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()!=folder.name
                or manifest["schema_version"]!=1 or manifest["publisher"]!="Vanguard"
                or manifest["fund_name"]!=FUND or manifest["share_class_reference_isin"]!=ISIN
                or manifest["original_first_publication_at"] is not None):raise ValueError("manifest")
        bodies={}
        for name,digest in files.items():
            path=folder/name
            if path.is_symlink() or path.stat().st_size>30_000_000:raise ValueError("original source")
            bodies[name]=path.read_bytes()
            if sha256(bodies[name]).hexdigest()!=digest:raise ValueError("original SHA")
        facts=parse_vanguard_pdf(bodies["original.pdf"],report_key=manifest["report_key"])
        if facts.pop("_extracted_text").encode()!=bodies["extracted.txt"] or facts!=json.loads(bodies["facts.json"]):
            raise ValueError("native facts")
        if any(manifest[k]!=facts[k] for k in ("source","source_url","holdings_date","report_key")):
            raise ValueError("identity")
        if folder.parent.name!=facts["holdings_date"] or folder.parent.parent.name!=ISIN:raise ValueError("path identity")
        return manifest,facts
    except (OSError,ValueError,KeyError,TypeError) as exc:
        raise VanguardUcitsError("Immutable original Vanguard UCITS archive inconsistent") from exc


def store_vanguard_ucits_source(original: bytes, *, report_key: str, root: Path) -> Path:
    facts=parse_vanguard_pdf(original,report_key=report_key)
    text=facts.pop("_extracted_text")
    payloads={"original.pdf":original,"facts.json":json.dumps(facts,sort_keys=True).encode(),"extracted.txt":text.encode()}
    files={name:sha256(body).hexdigest() for name,body in payloads.items()}
    digest=sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
    parent=root/"ucits"/ISIN/facts["holdings_date"]
    folder=parent/digest
    temporary=None
    identity={"publisher":"Vanguard","isin":ISIN,"holdings_date":facts["holdings_date"],"source_url":facts["source_url"]}
    try:
        parent.mkdir(parents=True,exist_ok=True)
        if not folder.exists():
            temporary=Path(tempfile.mkdtemp(prefix=".vanguard-",dir=parent))
            for name,body in payloads.items():(temporary/name).write_bytes(body)
            manifest={"schema_version":1,"publisher":"Vanguard","source":facts["source"],"fund_name":FUND,
                "share_class_reference_isin":ISIN,"report_key":report_key,"source_url":facts["source_url"],
                "holdings_date":facts["holdings_date"],"original_first_publication_at":None,
                "retrieved_at_utc":datetime.now(timezone.utc).isoformat(),"files":files}
            (temporary/"manifest.json").write_text(json.dumps(manifest,indent=2))
            try:os.rename(temporary,folder);temporary=None
            except FileExistsError:pass
        _verify_archive(folder)
        record_acquisition_receipt(folder,identity)
        return folder
    finally:
        if temporary is not None:shutil.rmtree(temporary,ignore_errors=True)


def read_vanguard_ucits_sources(root: Path, *, summary: bool=False) -> dict:
    from .source_reconciliation import _selected_manifest
    records=[]
    for parent in sorted((root/"ucits"/ISIN).glob("????-??-??")):
        folders=[f for f in sorted(parent.glob("*")) if re.fullmatch(r"[0-9a-f]{64}",f.name)]
        if not folders:continue
        manifests=[_verify_archive(folder)[0] for folder in folders]
        urls={m["source_url"] for m in manifests}
        if len(urls)!=1:raise VanguardUcitsError("Original Vanguard URL identity ambiguous")
        identity={"publisher":"Vanguard","isin":ISIN,"holdings_date":parent.name,"source_url":next(iter(urls))}
        observed,manifest_hash,path,manifest,selection=_selected_manifest(parent,identity)
        if selection!="acquisition_receipt":raise VanguardUcitsError("Original Vanguard archive requires an acquisition receipt")
        verified,facts=_verify_archive(path.parent)
        if verified!=manifest:raise VanguardUcitsError("Original Vanguard receipt identity mismatch")
        record={**facts,"bundle_digest":path.parent.name,"source_manifest_sha256":manifest_hash,
            "manifest":manifest,"acquisition_observed_at_utc":observed.isoformat(),"selection_method":selection}
        record.update(complete_transferable_security_schedule=facts["complete_security_schedule"],
                      complete_derivative_contract_extraction=False,derivative_accounting_controls_reconciled=True)
        if summary:
            record.pop("positions")
            record.pop("original_derivative_schedule_text")
        records.append(record)
    return {"fund_name":FUND,"legal_entity":"Vanguard Funds plc","share_class_reference_isin":ISIN,
            "status":"ready" if records else "missing_original_ucits_positions","records":records}


def collect_vanguard_ucits_sources(*, root: Path, report_keys=("annual-2026","semiannual-2025"),client=None) -> dict:
    """Acquire only the exact named official reports already independently inspected."""
    import httpx
    if len(report_keys)>2 or len(set(report_keys))!=len(report_keys) or any(key not in REPORTS for key in report_keys):
        raise VanguardUcitsError("Only the independently verified original Vanguard reports may be acquired")
    owns=client is None
    connection=require_managed_client(client) if client is not None else managed_client(timeout=60,follow_redirects=False)
    reports=[]
    try:
        cached=read_vanguard_ucits_sources(root,summary=True)["records"]
        for key in report_keys:
            source=REPORTS[key]
            if any(r["report_key"]==key and r["original_sha256"]==source["sha256"] for r in cached):
                reports.append({"report_key":key,"status":"already_archived","holdings_date":source["holdings_date"]})
                continue
            try:
                response=connection.get(source["source_url"],timeout=60)
                response.raise_for_status()
                folder=store_vanguard_ucits_source(response.content,report_key=key,root=root)
                reports.append({"report_key":key,"status":"acquired","holdings_date":source["holdings_date"],"bundle_digest":folder.name})
            except httpx.HTTPStatusError as exc:
                reports.append({"report_key":key,"status":"blocked","http_status":exc.response.status_code,"reason":"original_publisher_access_unavailable"})
                break
            except (httpx.HTTPError,VanguardUcitsError) as exc:
                reports.append({"report_key":key,"status":"failed","reason":type(exc).__name__+": "+str(exc)})
    finally:
        if owns:connection.close()
    complete=len(reports)==len(report_keys) and all(r["status"] in {"acquired","already_archived"} for r in reports)
    return {"status":"complete" if complete else "partial","fund_name":FUND,"reports":reports,
            "original_index_constituents":False,"original_first_publication_verified":False}
