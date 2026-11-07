"""SEC N-PORT dated fund-portfolio holdings, no inferred UCITS look-through.

Import real SEC XML with matching SEC submission accession/acceptance metadata.
The resulting country is the reported issuer/investment country (Form C.5.a),
not the separate confidential economic-risk exposure of C.5.b. Research
eligibility uses the official filing date plus two calendar days; the actual
first-publication instant is unverified and never the holdings observation date.
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
from collections import Counter

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
    # Keep all report dates; amendments use the latest buffered eligibility date
    # on the query date, not a revision filed after the requested cutoff.
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


def _native_node(element) -> dict:
    """Keep repeated contract fields, their attributes and native source hierarchy."""
    return {"tag":_name(element),"attributes":dict(element.attrib),
            "text":element.text.strip() if element.text and element.text.strip() else None,
            "children":[_native_node(child) for child in element]}


def _portfolio_accounting_evidence(positions: list[dict], accounting: dict) -> tuple[dict,dict]:
    """Independent native controls and explicitly unexplained residual accounts.

    The residual decomposition is an arithmetic bridge, not independent proof
    that all portfolio assets or liabilities have been identified. In particular
    neither a NAV residual nor securities-lending collateral is relabelled cash.
    """
    zero=Decimal(0)
    valued=[(p,_decimal(p.get("value_usd"))) for p in positions]
    numeric=[(p,v) for p,v in valued if v is not None]
    signed=sum((v for _,v in numeric),zero)
    positive=sum((v for _,v in numeric if v>0),zero)
    negative=-sum((v for _,v in numeric if v<0),zero)
    derivative=sum((v for p,v in numeric if p["is_derivative"]),zero)
    asset_totals={}
    for p,v in numeric:
        cat=p.get("asset_category") or "UNREPORTED"
        asset_totals[cat]=asset_totals.get(cat,zero)+v
    assets=_decimal(accounting.get("total_assets_usd"))
    liabilities=_decimal(accounting.get("total_liabilities_usd"))
    nav=_decimal(accounting.get("net_assets_usd"))
    cash=_decimal(accounting.get("cash_not_reported_in_parts_c_and_d_usd"))
    other_assets=assets-positive-cash if assets is not None and cash is not None else None
    other_liabilities=liabilities-negative if liabilities is not None else None
    weight_deltas=[]
    missing_weight=0
    for position,value in valued:
        pct=_decimal(position.get("percent_of_fund_nav"))
        if value is None or pct is None or nav is None or nav<=0:
            missing_weight+=1
            continue
        weight_deltas.append(abs(pct-value/nav*100))
    tolerance=Decimal("0.0000000001")
    recon={"position_value_sum_usd":str(signed),"positive_position_value_usd":str(positive),
        "negative_position_value_magnitude_usd":str(negative),
        "derivative_market_value_sum_usd":str(derivative),
        "derivative_positions":sum(p["is_derivative"] for p in positions),
        "positions_with_missing_value":len(valued)-len(numeric),
        "native_asset_category_value_usd":{k:str(v) for k,v in sorted(asset_totals.items())},
        "cash_outside_parts_c_and_d_usd":str(cash) if cash is not None else None,
        "other_assets_residual_usd":str(other_assets) if other_assets is not None else None,
        "other_liabilities_residual_usd":str(other_liabilities) if other_liabilities is not None else None,
        "net_assets_minus_positions_and_reported_cash_usd":str(nav-signed-cash)
            if nav is not None and cash is not None else None,
        "fund_balance_sheet_difference_usd":accounting["assets_less_liabilities_minus_net_assets_usd"],
        "maximum_position_value_nav_weight_difference_pct":str(max(weight_deltas)) if weight_deltas else None,
        "position_value_nav_weight_tolerance_pct":str(tolerance),
        "position_value_nav_weight_mismatches":sum(delta>tolerance for delta in weight_deltas),
        "positions_with_unverified_nav_weight":missing_weight,
        "unreported_residual_composition_verified":False,
        "residual_semantics":"Derived other-asset/liability balance-sheet residuals, not cash; asset residual subtracts positive reported positions and B.2.f cash, liability residual subtracts negative market values. This bridge does not independently identify receivables, payables, collateral or derivative economic exposure."}
    groups={}
    lei_names={}
    ungrouped=zero
    for position,value in numeric:
        if (position["is_derivative"] or value<0 or position.get("asset_category") not in {"EC","EP"}
                or (position.get("payoff_profile") or "").lower() not in {"long",""}):
            continue
        name=" ".join((position.get("name") or "").split())
        if not name:
            ungrouped+=value
            continue
        lei=position.get("lei") or ""
        if not re.fullmatch(r"[A-Z0-9]{20}",lei) or lei=="00000000000000000000": lei=None
        if lei: lei_names.setdefault(lei,set()).add(name)
        # Identical source issuer names consolidate share classes. A reused LEI
        # never joins two differently named reported issuers (seen in 2019 XML).
        group=groups.setdefault(name,{"reported_name":name,"value":zero,"source_rows":[],
            "reported_leis":set(),"security_identifiers":set()})
        group["value"]+=value
        group["source_rows"].append(position["source_row"])
        if lei: group["reported_leis"].add(lei)
        for identifier in position.get("security_identifiers",[]):
            if identifier.get("value"):
                group["security_identifiers"].add((identifier["type"],identifier["value"]))
    ordered=sorted(groups.values(),key=lambda g:(-g["value"],g["reported_name"]))
    equity=sum((g["value"] for g in ordered),zero)+ungrouped
    top=sum((g["value"] for g in ordered[:10]),zero)
    rows=[{"reported_name":g["reported_name"],"value_usd":str(g["value"]),
        "position_count":len(g["source_rows"]),"source_rows":g["source_rows"],
        "reported_leis":sorted(g["reported_leis"]),
        "reported_security_identifiers":[{"type":kind,"value":value}
             for kind,value in sorted(g["security_identifiers"])],
        "share_of_fund_nav_pct":str(g["value"]/nav*100) if nav is not None and nav>0 else None}
        for g in ordered[:10]]
    concentration={"grouping_basis":"Exact whitespace-normalized reported issuer name; source LEIs cross-checked, share classes summed; no inferred aliases or ultimate-parent mapping",
        "issuer_groups":rows,"issuer_groups_count":len(ordered),"reported_ordinary_and_preferred_equity_value_usd":str(equity),
        "unassigned_issuer_name_equity_value_usd":str(ungrouped),"top10_reported_issuer_value_usd":str(top),
        "top10_reported_issuer_share_of_fund_nav_pct":str(top/nav*100) if nav is not None and nav>0 else None,
        "remaining_reported_equity_value_usd":str(equity-top),
        "lei_name_conflicts":[{"reported_lei":lei,"distinct_reported_names":sorted(names)}
              for lei,names in sorted(lei_names.items()) if len(names)>1],
        "name_multiple_lei_conflicts":[{"reported_name":g["reported_name"],"reported_leis":sorted(g["reported_leis"])}
              for g in ordered if len(g["reported_leis"])>1],
        "legal_entity_registry_validation_verified":False,"ultimate_parent_concentration_verified":False,
        "index_constituent_concentration":False,
        "limitations":"Fund-level reported issuer-name concentration only; not MSCI ACWI or FTSE constituents. Native issuer identities can conflict; no unverified parent consolidation or derivative look-through."}
    return recon,concentration


def _native_portfolio_evidence(xml: bytes, *, summary: bool = False) -> dict:
    """Derive current structured evidence from the immutable verified original.

    Direct holding identities must never come from a derivative's reference
    instrument or counterparty. The version-1 positions.json is retained and
    verified as an original archive payload, rather than rewritten by this view.
    """
    root=ET.fromstring(xml)
    investments=_section(root,"invstOrSecs")
    fields={"name":"name","lei":"lei","security_title":"title","cusip":"cusip",
            "quantity":"balance","quantity_unit":"units","currency":"curCd",
            "value_usd":"valUSD","percent_of_fund_nav":"pctVal",
            "asset_category":"assetCat","issuer_category":"issuerCat",
            "issuer_country":"invCountry","payoff_profile":"payoffProfile"}
    def direct(element,tag):
        children=[child for child in element if _name(child)==tag]
        if len(children)>1:
            raise HoldingsError("Ambiguous direct N-PORT native field: "+tag)
        return children[0] if children else None
    def text(element,tag):
        child=direct(element,tag)
        return child.text.strip() if child is not None and child.text and child.text.strip() else None
    positions=[]
    for index,item in enumerate(investments,1):
        if _name(item)!="invstOrSec": continue
        identifiers=direct(item,"identifiers")
        ids=[{"type":_name(child),**dict(child.attrib),
              **({"text":child.text.strip()} if child.text and child.text.strip() else {})}
             for child in identifiers] if identifiers is not None else []
        derivative=direct(item,"derivativeInfo")
        contracts=[_native_node(child) for child in derivative] if derivative is not None and not summary else []
        lending=direct(item,"securityLending")
        position={**{key:text(item,tag) for key,tag in fields.items()},
            "source_row":index,
            "security_identifiers":ids,"isin":next((i.get("value") for i in ids if i["type"]=="isin"),None),
            "is_derivative":(derivative is not None and len(derivative)>0) or (text(item,"assetCat") or "").upper() in {"DE","DCR","DFE","DIR","DO","DCO"},
            "derivative_contracts":contracts,
            "securities_lending":_native_node(lending) if lending is not None and not summary else None,
            "identity_scope":"reported issuer and security only; ultimate-parent identity unverified"}
        conditional=direct(item,"issuerConditional")
        if not summary:
            position["source_xml"]=ET.tostring(item,encoding="unicode")
        if not summary and position["issuer_category"] is None and conditional is not None:
            position["issuer_category"]=conditional.attrib.get("issuerCat")
        positions.append(position)
    fund=_section(root,"fundInfo")
    fund_fields={"total_assets_usd":"totAssets","total_liabilities_usd":"totLiabs",
                 "net_assets_usd":"netAssets","cash_not_reported_in_parts_c_and_d_usd":"cshNotRptdInCorD",
                 "miscellaneous_securities_assets_usd":"assetsAttrMiscSec"}
    accounting={key:text(fund,tag) if fund is not None else None for key,tag in fund_fields.items()}
    a,l,n=(_decimal(accounting[key]) for key in ("total_assets_usd","total_liabilities_usd","net_assets_usd"))
    accounting["assets_less_liabilities_minus_net_assets_usd"]=str(a-l-n) if all(v is not None for v in (a,l,n)) else None
    accounting["cash_semantics"]="B.2.f cash and cash equivalents outside Parts C and D; not total cash or an inferred NAV residual"
    def reported(value):
        return bool(value and value.upper() not in {"N/A","NA","NONE","NOT AVAILABLE","00000000000000000000"})
    coverage={"positions":len(positions),
        "positions_with_reported_issuer_lei":sum(reported(p["lei"]) for p in positions),
        "positions_with_reported_security_identifier":sum(reported(p["cusip"]) or any(reported(i.get("value")) for i in p["security_identifiers"]) for p in positions),
        "derivative_positions":sum(p["is_derivative"] for p in positions),
        "ultimate_parent_mapping_verified":False,
        "identifier_registry_validation_verified":False,
        "derivative_underlying_country_lookthrough_verified":False}
    currencies=Counter(p["currency"] for p in positions if re.fullmatch(r"[A-Z]{3}",p.get("currency") or ""))
    position_coverage={key:coverage[key] for key in ("positions","positions_with_reported_issuer_lei",
        "positions_with_reported_security_identifier","derivative_positions")}
    position_coverage.update(positions_with_reported_currency=sum(currencies.values()),currencies=dict(sorted(currencies.items())))
    reconciliation,concentration=_portfolio_accounting_evidence(positions,accounting)
    return {**({"positions":positions} if not summary else {}),
            "fund_accounting":accounting,"identity_coverage":coverage,"position_coverage":position_coverage,
            "portfolio_reconciliation":reconciliation,"reported_issuer_concentration":concentration,
            "native_evidence_schema_version":1,"native_evidence_xml_sha256":sha256(xml).hexdigest()}


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


def _verify_source_bundle(folder: Path, instrument_id: str|None=None, accession: str|None=None, *,
                          verify_position_payload: bool=True) -> dict:
    try:
        if folder.is_symlink():
            raise ValueError("symlink")
        manifest=json.loads((folder/"manifest.json").read_text())
        if not isinstance(manifest.get("files"),dict) or not {
                "original.xml","metadata.json","positions.json"}.issubset(manifest["files"]):
            raise ValueError("mandatory original source hashes missing")
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
            or verify_position_payload and json.loads((folder/"positions.json").read_text())!=_position_facts(xml)):
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
        name=f"submissions-{index}.{response.get('suffix','json')}"
        payloads[name]=response["body"]
        response_urls.append({"file":name,"url":response["url"]})
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


def read_position_source(root: Path, instrument_id: str, accession: str, *, summary: bool=False) -> dict:
    if instrument_id not in instruments() or not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}",accession):
        raise HoldingsError("Invalid original source identity")
    parent=root/instrument_id/"sources"/accession
    folders=sorted(p for p in parent.glob("*") if re.fullmatch(r"[0-9a-f]{64}",p.name))
    if not folders and not parent.exists():
        return {"instrument_id":instrument_id,"accession":accession,
                "status":"missing_original_positions","positions":[]}
    # A→B→A must select the latest successful acquisition of A, not B's newer
    # immutable creation timestamp. Any corrupt receipt fails the whole read.
    # Summaries are derived directly from original XML. Archived version-1
    # position payloads remain hash-verified, but are not deserialized or used.
    manifests=[(folder,_verify_source_bundle(folder,instrument_id,accession,
        verify_position_payload=not summary)) for folder in folders]
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
    metadata=json.loads((folder/"metadata.json").read_text())
    eligible,acceptance=conservative_eligibility_from_sec_submissions(metadata,accession)
    native=_native_portfolio_evidence((folder/"original.xml").read_bytes(),summary=summary)
    return {"instrument_id":instrument_id,"accession":accession,"status":"ready",
            "manifest":manifest,"bundle_digest":folder.name,"selection_method":selection,
            "acquisition_observed_at_utc":observed.isoformat(),"manifest_sha256":manifest_hash,
            **native,
            "publication_evidence":{"sec_acceptance_timestamp_unverified_timezone":acceptance,
                "eligible_after_conservative_buffer_utc":eligible.isoformat(),
                "first_public_dissemination_verified":False,
                "source_rule":"Form N-PORT General Instruction F: public third-fiscal-month information upon filing; exact dissemination instant is not established by current submissions JSON",
                "source_url":"https://www.sec.gov/files/formn-port.pdf"}}

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
