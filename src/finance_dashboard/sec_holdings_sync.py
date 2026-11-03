"""Official SEC N-PORT historical filing collection using verified fund mappings.

Network acquisition is opt-in and CLI/refresh driven, not browser-controlled.
SEC submissions give CIK, accession, acceptance metadata and primary document;
the matching source XML must independently confirm SEC fund SERIES ID. No
historical ETF ticker mapping is inferred from today's trading symbol.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import json
from html.parser import HTMLParser
from urllib.parse import urlsplit
import os
from pathlib import Path
import re
import time

import httpx

from .market import instruments
from .sec_holdings import parse_nport, store_snapshot, HoldingsError

SUBMISSIONS_URL = "https://data.sec.gov/submissions/"
EDGAR_URL = "https://www.sec.gov/Archives/edgar/data/"
CONFIG = Path(os.environ.get("FINANCE_SEC_FUND_MAPPING", "/data/holdings/sec_funds.json"))
CIK = re.compile(r"^[0-9]{1,10}$")
SERIES = re.compile(r"^S[0-9]{9}$")
SEC_FILE = re.compile(r"^[A-Za-z0-9_.-]+\.xml$")
SEC_PRIMARY = re.compile(r"^[A-Za-z0-9_.-]+\.(?:xml|html|htm)$", re.IGNORECASE)
SEC_SERIES_IN_INDEX = re.compile(r"\bS[0-9]{9}\b")
PAGE = re.compile(r"^CIK[0-9]{10}-submissions-[0-9]+\.json$")


# Official SEC N-PORT filing indexes confirm both fund and ETF-share identity.
# All other fund mappings require their own SEC source verification.
VERIFIED_DEFAULT_FUNDS = (
    {"instrument_id": "vt", "cik": "857489", "series_id": "S000022482"},
    {"instrument_id": "bnd", "cik": "794105", "series_id": "S000002564"},
)
VERIFICATION_FILINGS = {
    "vt": "https://www.sec.gov/Archives/edgar/data/857489/000085748926000275/0000857489-26-000275-index.htm",
    "bnd": "https://www.sec.gov/Archives/edgar/data/794105/000079410525000080/0000794105-25-000080-index.htm",
}


def read_verified_config(path: Path = CONFIG) -> list[dict]:
    # A user-created file deliberately replaces the built-in verified funds.
    values = (json.loads(path.read_text(encoding="utf-8"))
              if path.is_file() else list(VERIFIED_DEFAULT_FUNDS))
    if not isinstance(values, list) or len(values)>24:
        raise HoldingsError("SEC fund mapping must be an explicit list of at most 24 verified ETFs")
    known = instruments()
    result, ids = [], set()
    for row in values:
        if not isinstance(row,dict):
            raise HoldingsError("Invalid SEC mapping entry")
        fund, cik, series = row.get("instrument_id"), str(row.get("cik","")),row.get("series_id")
        item = known.get(fund)
        if (fund in ids or not item or item["kind"]!="etf"
            or item["domicile"]!="United States"
            or not CIK.fullmatch(cik) or not isinstance(series,str)
            or not SERIES.fullmatch(series)):
            raise HoldingsError("Unverified or inconsistent SEC CIK/series mapping")
        ids.add(fund)
        result.append({"instrument_id":fund,"cik":str(int(cik)),
                       "series_id":series})
    return result


def _get_json(client: httpx.Client, url: str) -> dict:
    response = client.get(url,timeout=25)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data,dict):
        raise HoldingsError("Malformed official SEC submissions page")
    return data


def _rows(metadata: dict) -> list[dict]:
    filings=metadata.get("filings", {}).get("recent",metadata)
    acc=filings.get("accessionNumber",[])
    forms=filings.get("form",[])
    dates=filings.get("filingDate",[])
    docs=filings.get("primaryDocument",[])
    accepted=filings.get("acceptanceDateTime",[])
    if not all(isinstance(x,list) and len(x)==len(acc)
               for x in (forms,dates,docs,accepted)):
        raise HoldingsError("SEC filing metadata columns incomplete")
    return [{"accession":acc[i],"form":forms[i],"date":dates[i],
             "document":docs[i],"acceptance":accepted[i]}
            for i in range(len(acc))]



class _FilingIndex(HTMLParser):
    """Read only SEC filing-index XML filenames and disclosed fund series IDs."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.xml_files: set[str] = set()
        self.series_ids: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        if tag != "a":
            return
        href = dict(attrs).get("href") or ""
        parsed = urlsplit(href)
        if parsed.netloc and parsed.netloc not in {"www.sec.gov", "sec.gov"}:
            return
        name = parsed.path.rsplit("/", 1)[-1]
        if SEC_FILE.fullmatch(name):
            self.xml_files.add(name)

    def handle_data(self, data: str):
        self.series_ids.update(SEC_SERIES_IN_INDEX.findall(data))


def _official_index_url(cik: str, accession: str) -> str:
    return (EDGAR_URL + str(int(cik)) + "/" + accession.replace("-", "") +
            "/" + accession + "-index.htm")


def _xml_in_filing_index(index_html: str, expected_series: str,
                         source_primary: str) -> tuple[str | None, str]:
    """An index's series entry is cheap evidence to avoid unrelated multi-fund
    XML downloads. Actual series identity is still checked inside source XML."""
    if len(index_html) > 2_000_000:
        raise HoldingsError("SEC filing index exceeded size limit")
    found = _FilingIndex()
    found.feed(index_html)
    if found.series_ids and expected_series not in found.series_ids:
        return None, "other_series"
    if SEC_FILE.fullmatch(source_primary) and source_primary in found.xml_files:
        return source_primary, "index_verified"
    if "primary_doc.xml" in found.xml_files:
        return "primary_doc.xml", "index_verified"
    if len(found.xml_files) == 1:
        return next(iter(found.xml_files)), "index_verified"
    # Never guess among multiple XML attachments or transform an HTML
    # filename into an unverified XML path.
    return None, "no_verified_primary_xml"


def _candidate_status(status: int) -> str:
    if status == 429:
        return "sec_rate_limited"
    if status in (401, 403):
        return "sec_access_denied"
    if status >= 500:
        return "sec_server_unavailable"
    if status == 404:
        return "sec_filing_index_missing"
    return "sec_http_failure"


def import_fund(mapping: dict, *, client: httpx.Client,
                root: Path, max_filings: int=12,
                earliest: date=date(2019,10,1)) -> dict:
    if not 1<=max_filings<=50:
        raise HoldingsError("SEC historical sync limited to 1–50 filings per fund")
    fund = mapping["instrument_id"]
    cik = mapping["cik"]
    expected = mapping["series_id"]
    base=_get_json(client,SUBMISSIONS_URL+f"CIK{int(cik):010d}.json")
    if str(int(base.get("cik","0"))) != str(int(cik)):
        raise HoldingsError("SEC registrant identity mismatch")
    rows = _rows(base)
    # SEC may offload historical submissions into separately named page JSON.
    for page in base.get("filings",{}).get("files",[]):
        name = page.get("name","")
        if not PAGE.fullmatch(name):
            continue
        if page.get("filingTo","9999-12-31") < earliest.isoformat():
            continue
        payload=_get_json(client,SUBMISSIONS_URL+name)
        rows.extend(_rows(payload))
        time.sleep(.2)
    candidates = []
    seen = set()
    for item in sorted(rows, key=lambda row: (row["date"], row["accession"]), reverse=True):
        accession, doc = item["accession"], item["document"]
        if (accession in seen or item["form"] not in ("NPORT-P", "NPORT-P/A")
            or item["date"] < earliest.isoformat()
            or not isinstance(doc, str) or not SEC_PRIMARY.fullmatch(doc)):
            continue
        seen.add(accession)
        candidates.append(item)

    # Each accession index is small, while Vanguard multi-series XML can exceed
    # 20 MB. Scan a bounded set of original SEC filing indexes rather than
    # assuming the submissions primaryDocument is itself an XML filename.
    # A verified matching source XML is still required for every stored record.
    index_scan_limit = min(len(candidates), max(120, max_filings * 50))
    xml_download_limit = max(12, max_filings * 3)
    examined = attempted_xml = imported = skipped_series = errors = 0
    missing_xml = 0
    stopped_reason = None
    status_code = None
    for entry in candidates[:index_scan_limit]:
        if imported >= max_filings or attempted_xml >= xml_download_limit:
            break
        accession, primary = entry["accession"], entry["document"]
        xml_name = None
        if SEC_FILE.fullmatch(primary):
            # Some original submissions explicitly designate the XML file.
            xml_name = primary
        else:
            index_url = _official_index_url(cik, accession)
            try:
                response = client.get(index_url, timeout=25)
                response.raise_for_status()
                xml_name, evidence = _xml_in_filing_index(
                    response.text, expected, primary)
            except httpx.HTTPStatusError as exc:
                errors += 1
                status_code = exc.response.status_code
                if status_code in (400, 401, 403, 429) or status_code >= 500:
                    stopped_reason = _candidate_status(status_code)
                    examined += 1
                    break
                examined += 1
                continue
            except (httpx.HTTPError, HoldingsError, ValueError):
                errors += 1
                examined += 1
                continue
            if evidence == "other_series":
                skipped_series += 1
                examined += 1
                time.sleep(.18)
                continue
            if xml_name is None:
                missing_xml += 1
                examined += 1
                time.sleep(.18)
                continue

        examined += 1
        url = (EDGAR_URL + str(int(cik)) + "/" +
               accession.replace("-", "") + "/" + xml_name)
        attempted_xml += 1
        try:
            xml = client.get(url, timeout=45)
            xml.raise_for_status()
            # Validator independently checks official CIK/accession, original
            # reported SEC series, form, holdings-period and issuer countries.
            metadata = {"cik": int(cik), "filings": {"recent": {
                "accessionNumber": [accession], "form": [entry["form"]],
                "filingDate": [entry["date"]],
                "acceptanceDateTime": [entry["acceptance"]]}}}
            filing = parse_nport(xml.content, instrument_id=fund,
                                 accession=accession, filing_url=url,
                                 sec_metadata=metadata,
                                 expected_series_id=expected)
            store_snapshot(filing, root=root)
            imported += 1
        except HoldingsError as exc:
            if "series identity" in str(exc):
                skipped_series += 1
            else:
                errors += 1
        except httpx.HTTPStatusError as exc:
            errors += 1
            status_code = exc.response.status_code
            if status_code in (400, 401, 403, 429) or status_code >= 500:
                stopped_reason = _candidate_status(status_code)
                break
        except (httpx.HTTPError, ValueError, KeyError):
            errors += 1
        time.sleep(.25)

    target_met = imported >= max_filings
    status = ("blocked" if stopped_reason else
              "complete" if target_met and errors == 0 else
              "no_matching_series" if imported == 0 and
              skipped_series + missing_xml == examined and errors == 0 else
              "partial")
    return {
        "instrument_id": fund,
        "status": status,
        "attempted": attempted_xml,
        "index_candidates_examined": examined,
        "source_candidates_found": len(candidates),
        "stored_or_already_present": imported,
        "requested_matching_filings": max_filings,
        "matching_target_reached": target_met,
        "candidate_attempt_cap": index_scan_limit,
        "xml_download_cap": xml_download_limit,
        "unexamined_candidate_filings": max(0, len(candidates) - examined),
        "verification_filing": VERIFICATION_FILINGS.get(fund),
        "other_series_skipped": skipped_series,
        "no_verified_xml_in_index": missing_xml,
        "errors": errors,
        "halted_reason": stopped_reason,
        "http_status": status_code if stopped_reason else None,
        "filing_source": SUBMISSIONS_URL,
        "lookback_from": earliest.isoformat(),
        "note": ("Matching source XML is checked against official fund series and "
                 "original SEC accession; filingDate+2 days is a conservative "
                 "research-eligibility convention, not a public-release timestamp.")
    }

def collect_configured(*, config: Path=CONFIG, root: Path|None=None,
                       user_agent: str|None=None,
                       max_filings_per_fund: int=12) -> dict:
    mappings=read_verified_config(config)
    if not mappings:
        return {"status":"unconfigured","funds":[]}
    agent=user_agent or os.environ.get("SEC_USER_AGENT","")
    # SEC requests require a descriptive organization+contact address.
    if not agent or "@" not in agent or len(agent)<10:
        return {"status":"disabled_missing_SEC_USER_AGENT","funds":[]}
    folder = root or Path(os.environ.get("FINANCE_HOLDINGS_DIR","/data/holdings"))
    reports=[]
    with httpx.Client(headers={"User-Agent":agent,"Accept-Encoding":"gzip, deflate"},
                      timeout=45,follow_redirects=False) as client:
        for mapping in mappings:
            try:
                reports.append(import_fund(mapping,client=client,root=folder,
                                           max_filings=max_filings_per_fund))
            except (HoldingsError,httpx.HTTPError,ValueError):
                reports.append({"instrument_id":mapping["instrument_id"],
                                "status":"failed","errors":1})
    return {"status":("complete" if all(x.get("status") == "complete" for x in reports)
                      else "partial"),"funds":reports}


def collect_if_due(*, config: Path = CONFIG, root: Path | None = None,
                   today: date | None = None) -> dict:
    """Do not re-download the same SEC submissions on every daily refresh."""
    target = root or Path(os.environ.get("FINANCE_HOLDINGS_DIR","/data/holdings"))
    day = today or datetime.now(timezone.utc).date()
    # Built-in SEC identities can be used without local mapping files.
    # Network activity is still guarded by the opt-in refresh flag and a
    # real SEC_USER_AGENT contact, never an invented address.
    marker = target / ".sec-refresh-state.json"
    if marker.exists():
        try:
            recorded = date.fromisoformat(json.loads(marker.read_text())["date"])
            if 0 <= (day-recorded).days < 28:
                return {"status":"not_due","last_success":recorded.isoformat(),"funds":[]}
        except (ValueError,KeyError,OSError,json.JSONDecodeError):
            pass
    result = collect_configured(config=config,root=target,max_filings_per_fund=12)
    if result["status"] == "complete":
        target.mkdir(parents=True,exist_ok=True)
        temporary = target / ".sec-refresh-state.pending"
        temporary.write_text(json.dumps({"date":day.isoformat()}),encoding="utf-8")
        os.replace(temporary,marker)
    return result


def main() -> int:
    import argparse
    parser=argparse.ArgumentParser(description="Collect SEC N-PORT dated holdings for verified mapped funds")
    parser.add_argument("--config",type=Path,default=CONFIG)
    parser.add_argument("--root",type=Path,default=Path(os.environ.get("FINANCE_HOLDINGS_DIR","/data/holdings")))
    parser.add_argument("--limit",type=int,default=12)
    args=parser.parse_args()
    result=collect_configured(config=args.config,root=args.root,
                              max_filings_per_fund=args.limit)
    print(json.dumps(result,indent=2))
    return 0 if result["status"]=="complete" else 1


if __name__=="__main__":
    raise SystemExit(main())
