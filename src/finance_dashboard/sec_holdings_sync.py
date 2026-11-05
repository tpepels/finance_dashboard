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
from .source_policy import managed_client

from .market import instruments
from .sec_holdings import (parse_nport, store_snapshot, HoldingsError,
                           store_source_bundle, read_position_source,
                           reconcile_nport_aggregate)

SUBMISSIONS_URL = "https://data.sec.gov/submissions/"
EDGAR_URL = "https://www.sec.gov/Archives/edgar/data/"
CONFIG = Path(os.environ.get("FINANCE_SEC_FUND_MAPPING", "/data/holdings/sec_funds.json"))
CIK = re.compile(r"^[0-9]{1,10}$")
SERIES = re.compile(r"^S[0-9]{9}$")
SEC_FILE = re.compile(r"^[A-Za-z0-9_.-]+\.xml$")
SEC_PRIMARY = re.compile(r"^[A-Za-z0-9_.-]+\.(?:xml|html|htm)$", re.IGNORECASE)
ACCESSION = re.compile(r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
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


def _get_transient_retry(client: httpx.Client, url: str,
                         *, timeout: int) -> httpx.Response:
    """Retry only temporary SEC 502/503/504 errors; preserve other failures.

    SEC access-denial and rate-limit codes must not provoke a retry storm.
    Three attempts maximum, with small bounded backoff and no request logging.
    """
    for attempt in range(3):
        response = client.get(url, timeout=timeout)
        if response.status_code not in (502, 503, 504) or attempt == 2:
            return response
        time.sleep(0.5 * (attempt + 1))
    raise AssertionError("Unreachable")


def _get_json(client: httpx.Client, url: str, evidence: list | None=None) -> dict:
    response = _get_transient_retry(client, url, timeout=25)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data,dict):
        raise HoldingsError("Malformed official SEC submissions page")
    if evidence is not None:
        evidence.append({"url":url,"body":response.content})
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


def _cached_verified_accessions(root: Path, instrument_id: str,
                                series_id: str) -> set[str]:
    """Only previously validated, identity-consistent original XML imports count."""
    folder = root / instrument_id
    existing = set()
    if not folder.is_dir():
        return existing
    for file in folder.glob("????-??-??--*.json"):
        if not file.is_file() or file.is_symlink():
            continue
        try:
            stored = json.loads(file.read_text(encoding="utf-8"))
            accession = stored.get("accession")
            if (stored.get("schema_version") == 1
                and stored.get("source") == "SEC_NPORT_PRIMARY_XML"
                and stored.get("instrument_id") == instrument_id
                and stored.get("sec_series_id") == series_id
                and isinstance(accession, str)
                and file.name.endswith("--" + accession.replace("-", "") + ".json")
                and re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession)
                and re.fullmatch(r"[0-9a-f]{64}", stored.get("xml_sha256", ""))):
                existing.add(accession)
        except (ValueError, OSError, TypeError):
            continue
    return existing


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
    metadata_responses=[]
    base=_get_json(client,SUBMISSIONS_URL+f"CIK{int(cik):010d}.json", metadata_responses)
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
        payload=_get_json(client,SUBMISSIONS_URL+name, metadata_responses)
        rows.extend(_rows(payload))
        time.sleep(.2)
    candidates = []
    seen = set()
    for item in sorted(rows, key=lambda row: (row["date"], row["accession"]), reverse=True):
        accession, doc = item["accession"], item["document"]
        if (not isinstance(accession, str) or not ACCESSION.fullmatch(accession)
            or accession in seen or item["form"] not in ("NPORT-P", "NPORT-P/A")
            or item["date"] < earliest.isoformat()):
            continue
        # The submission's primaryDocument can be HTML or missing; the actual
        # downloadable XML filename is discovered from the official index.
        if not isinstance(doc, str) or not SEC_PRIMARY.fullmatch(doc):
            item = {**item, "document": ""}
        seen.add(accession)
        candidates.append(item)

    # Each accession index is small, while Vanguard multi-series XML can exceed
    # 20 MB. Scan a bounded set of original SEC filing indexes rather than
    # assuming the submissions primaryDocument is itself an XML filename.
    # A verified matching source XML is still required for every stored record.
    index_scan_limit = min(len(candidates), max(120, max_filings * 50))
    xml_download_limit = max(12, max_filings * 3)
    examined = attempted_xml = imported = skipped_series = errors = 0
    cached_reused = 0
    known_accessions = _cached_verified_accessions(root, fund, expected)
    missing_xml = 0
    stopped_reason = None
    first_error_reason = None
    status_code = None
    for entry in candidates[:index_scan_limit]:
        if imported >= max_filings or attempted_xml >= xml_download_limit:
            break
        accession, primary = entry["accession"], entry["document"]
        if accession in known_accessions:
            examined += 1
            imported += 1
            cached_reused += 1
            continue
        xml_name = None
        if SEC_FILE.fullmatch(primary):
            # Some original submissions explicitly designate the XML file.
            xml_name = primary
        else:
            index_url = _official_index_url(cik, accession)
            try:
                response = _get_transient_retry(client, index_url, timeout=25)
                if response.status_code == 404:
                    # EDGAR accepts either -index.htm or -index.html depending
                    # on submission era. Never follow arbitrary redirects.
                    response = _get_transient_retry(
                        client, index_url[:-3] + "html", timeout=25)
                response.raise_for_status()
                xml_name, evidence = _xml_in_filing_index(
                    response.text, expected, primary)
            except httpx.HTTPStatusError as exc:
                errors += 1
                status_code = exc.response.status_code
                first_error_reason = (first_error_reason or
                                      _candidate_status(status_code))
                if status_code in (400, 401, 403, 429) or status_code >= 500:
                    stopped_reason = _candidate_status(status_code)
                    examined += 1
                    break
                examined += 1
                continue
            except (httpx.HTTPError, HoldingsError, ValueError) as exc:
                errors += 1
                first_error_reason = (first_error_reason or
                    ("sec_index_network_failed" if isinstance(exc, httpx.HTTPError)
                     else "sec_index_schema_invalid"))
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
            xml = _get_transient_retry(client, url, timeout=45)
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
            store_source_bundle(xml.content,sec_metadata=metadata,aggregate=filing,
                                root=root,metadata_responses=metadata_responses)
            store_snapshot(filing, root=root)
            imported += 1
        except HoldingsError as exc:
            if "series identity" in str(exc):
                skipped_series += 1
            else:
                errors += 1
                first_error_reason = (first_error_reason or
                                      "sec_holdings_xml_invalid")
        except httpx.HTTPStatusError as exc:
            errors += 1
            status_code = exc.response.status_code
            first_error_reason = (first_error_reason or
                                  _candidate_status(status_code))
            if status_code in (400, 401, 403, 429) or status_code >= 500:
                stopped_reason = _candidate_status(status_code)
                break
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            errors += 1
            first_error_reason = (first_error_reason or
                ("sec_filing_network_failed" if isinstance(exc, httpx.HTTPError)
                 else "sec_filing_response_invalid"))
        time.sleep(.25)

    target_met = imported >= max_filings
    # Fewer than 50 verified source filings can still be complete when all
    # eligible original candidate indexes were examined with no unresolved
    # download/validation failures. Never call a capped incomplete scan full.
    all_candidates_examined = examined == len(candidates)
    source_exhausted = all_candidates_examined and missing_xml == 0
    status = ("blocked" if stopped_reason else
              "complete" if imported > 0 and errors == 0 and
              (target_met or source_exhausted) else
              "no_eligible_submissions" if not candidates else
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
        "already_cached_in_selection": cached_reused,
        "requested_matching_filings": max_filings,
        "matching_target_reached": target_met,
        "all_candidates_examined": all_candidates_examined,
        "candidate_attempt_cap": index_scan_limit,
        "xml_download_cap": xml_download_limit,
        "unexamined_candidate_filings": max(0, len(candidates) - examined),
        "verification_filing": VERIFICATION_FILINGS.get(fund),
        "other_series_skipped": skipped_series,
        "no_verified_xml_in_index": missing_xml,
        "errors": errors,
        "first_error_reason": first_error_reason,
        "halted_reason": stopped_reason,
        "http_status": status_code if stopped_reason else None,
        "filing_source": SUBMISSIONS_URL,
        "lookback_from": earliest.isoformat(),
        "note": ("Matching source XML is checked against official fund series and "
                 "original SEC accession; filingDate+2 days is a conservative "
                 "research-eligibility convention, not a public-release timestamp.")
    }

def check_sec_sources(*, config: Path = CONFIG,
                      user_agent: str | None = None,
                      client: httpx.Client | None = None) -> dict:
    """One index request per verified default fund; never downloads or persists XML."""
    mappings = read_verified_config(config)
    agent = user_agent if user_agent is not None else os.environ.get("SEC_USER_AGENT", "")
    if not agent or "@" not in agent or len(agent) < 10:
        return {"status": "blocked", "reason": "missing_SEC_USER_AGENT",
                "funds": [], "requests": 0}
    owns = client is None
    source = client or managed_client(
        headers={"User-Agent": agent, "Accept-Encoding": "gzip, deflate"},
        timeout=25, follow_redirects=False)
    funds = []
    try:
        for mapping in mappings:
            fund = mapping["instrument_id"]
            index_url = VERIFICATION_FILINGS.get(fund)
            if index_url is None:
                funds.append({"instrument_id": fund, "status": "needs_source_index",
                              "requests": 0})
                continue
            try:
                response = source.get(index_url, timeout=25)
                if response.status_code == 404 and index_url.endswith("-index.htm"):
                    response = source.get(index_url[:-3] + "html", timeout=25)
                response.raise_for_status()
                xml, method = _xml_in_filing_index(
                    response.text, mapping["series_id"], "primary_doc.html")
                funds.append({
                    "instrument_id": fund, "status": "ready" if xml else "blocked",
                    "index_series_verified": bool(xml),
                    "xml_filename": xml,
                    "reason": method, "requests": 1,
                })
            except httpx.HTTPStatusError as exc:
                funds.append({"instrument_id": fund, "status": "blocked",
                              "http_status": exc.response.status_code,
                              "reason": _candidate_status(exc.response.status_code),
                              "requests": 1})
            except (httpx.RequestError, HoldingsError, ValueError):
                funds.append({"instrument_id": fund, "status": "blocked",
                              "reason": "sec_index_unavailable", "requests": 1})
            if owns:
                time.sleep(.2)
    finally:
        if owns:
            source.close()
    return {
        "provider": "SEC_NPORT", "status": (
            "ready" if funds and all(f["status"] == "ready" for f in funds)
            else "partial"),
        "funds": funds, "requests": sum(f["requests"] for f in funds),
        "note": "Official index and expected series verified; original XML holdings not imported.",
    }


def collect_configured(*, config: Path=CONFIG, root: Path|None=None,
                       user_agent: str|None=None,
                       max_filings_per_fund: int=12, progress=None, stopped=None) -> dict:
    mappings=read_verified_config(config)
    if not mappings:
        return {"status":"unconfigured","funds":[]}
    agent=user_agent or os.environ.get("SEC_USER_AGENT","")
    # SEC requests require a descriptive organization+contact address.
    if not agent or "@" not in agent or len(agent)<10:
        return {"status":"disabled_missing_SEC_USER_AGENT","funds":[]}
    folder = root or Path(os.environ.get("FINANCE_HOLDINGS_DIR","/data/holdings"))
    reports=[]
    with managed_client(headers={"User-Agent":agent,"Accept-Encoding":"gzip, deflate"},
                      timeout=45,follow_redirects=False) as client:
        for index, mapping in enumerate(mappings, 1):
            if stopped is not None and stopped.is_set():
                break
            try:
                reports.append(import_fund(mapping,client=client,root=folder,
                                           max_filings=max_filings_per_fund))
            except httpx.HTTPStatusError as exc:
                reports.append({"instrument_id":mapping["instrument_id"],
                                "status":"blocked","errors":1,
                                "http_status":exc.response.status_code,
                                "halted_reason":_candidate_status(exc.response.status_code)})
            except (HoldingsError,httpx.HTTPError,ValueError):
                reports.append({"instrument_id":mapping["instrument_id"],
                                "status":"failed","errors":1})
            finally:
                if progress is not None:
                    progress(index, len(mappings), mapping["instrument_id"])
    return {"status":("complete" if all(x.get("status") == "complete" for x in reports)
                      else "partial"),"funds":reports}



def recover_fund_raw(mapping: dict, *, client: httpx.Client, root: Path,
                     max_filings: int=50, stopped=None) -> dict:
    """Recover exactly the stored original URLs, reconciling their immutable hashes."""
    if not 1<=max_filings<=50:
        raise HoldingsError("SEC raw recovery limited to 1–50 filings per fund")
    fund=mapping["instrument_id"]
    records=[]
    for file in sorted((root/fund).glob("????-??-??--*.json")):
        record=json.loads(file.read_text())
        if (record.get("source")=="SEC_NPORT_PRIMARY_XML"
            and record.get("sec_series_id")==mapping["series_id"]
            and str(record.get("sec_cik"))==str(int(mapping["cik"]))):
            records.append(record)
    recovered=present=errors=0
    halted=None
    metadata_responses=[]
    rows=None
    for old in records[:max_filings]:
        if stopped is not None and stopped.is_set():
            break
        try:
            if read_position_source(root,fund,old["accession"])["status"]=="ready":
                present+=1
                continue
            if rows is None:
                base=_get_json(client,SUBMISSIONS_URL+f"CIK{int(mapping['cik']):010d}.json",metadata_responses)
                if str(int(base.get("cik","0")))!=str(int(mapping["cik"])):
                    raise HoldingsError("SEC registrant identity mismatch")
                rows=_rows(base)
                for page in base.get("filings",{}).get("files",[]):
                    name=page.get("name","")
                    if PAGE.fullmatch(name):
                        rows.extend(_rows(_get_json(client,SUBMISSIONS_URL+name,metadata_responses)))
                        time.sleep(.2)
            found=[r for r in rows if r["accession"]==old["accession"]]
            if len(found)!=1:
                raise HoldingsError("Stored accession not uniquely verified by SEC metadata")
            entry=found[0]
            metadata={"cik":int(mapping["cik"]),"filings":{"recent":{
                "accessionNumber":[entry["accession"]],"form":[entry["form"]],
                "filingDate":[entry["date"]],"acceptanceDateTime":[entry["acceptance"]]}}}
            # The parser checks SEC URL/CIK/accession and series before any file publication.
            from .sec_holdings import SEC_ARCHIVE
            match=SEC_ARCHIVE.fullmatch(old["source_url"])
            if (not match or match.group(2)!=old["accession"].replace("-","")
                or str(int(match.group(1)))!=str(int(mapping["cik"]))):
                raise HoldingsError("Stored original SEC URL identity invalid")
            response=_get_transient_retry(client,old["source_url"],timeout=45)
            response.raise_for_status()
            current=parse_nport(response.content,instrument_id=fund,accession=old["accession"],
                filing_url=old["source_url"],sec_metadata=metadata,
                expected_series_id=mapping["series_id"])
            reconcile_nport_aggregate(current,old)
            store_source_bundle(response.content,sec_metadata=metadata,aggregate=old,
                                root=root,metadata_responses=metadata_responses)
            recovered+=1
            time.sleep(.25)
        except httpx.HTTPStatusError as exc:
            errors+=1
            if exc.response.status_code in (400,401,403,429) or exc.response.status_code>=500:
                halted=_candidate_status(exc.response.status_code)
                break
        except (HoldingsError,httpx.HTTPError,ValueError,KeyError):
            errors+=1
    return {"instrument_id":fund,"status":"blocked" if halted else
            "complete" if errors==0 and recovered+present==len(records) else "partial",
            "recovered":recovered,"already_present":present,"errors":errors,
            "stored_filings":len(records),"unexamined":max(0,len(records)-max_filings),
            "halted_reason":halted,"aggregate_records_modified":0}


def recover_configured_raw(*, config: Path=CONFIG, root: Path|None=None,
                           user_agent: str|None=None, max_filings_per_fund: int=50,
                           progress=None, stopped=None) -> dict:
    agent=user_agent or os.environ.get("SEC_USER_AGENT","")
    if not agent or "@" not in agent or len(agent)<10:
        return {"status":"disabled_missing_SEC_USER_AGENT","funds":[]}
    mappings=read_verified_config(config)
    target=root or Path(os.environ.get("FINANCE_HOLDINGS_DIR","/data/holdings"))
    reports=[]
    with managed_client(headers={"User-Agent":agent,"Accept-Encoding":"gzip, deflate"},
                      timeout=45,follow_redirects=False) as client:
        for index,mapping in enumerate(mappings,1):
            if stopped is not None and stopped.is_set():
                break
            reports.append(recover_fund_raw(mapping,client=client,root=target,
                max_filings=max_filings_per_fund,stopped=stopped))
            if progress is not None:
                progress(index,len(mappings),mapping["instrument_id"])
    return {"status":"complete" if len(reports)==len(mappings) and
            all(r["status"]=="complete" for r in reports) else "partial","funds":reports}

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
    parser.add_argument("--check", action="store_true",
                        help="Verify official SEC fund indexes and XML links without downloading holdings")
    parser.add_argument("--recover-raw",action="store_true",help="Recover original XML for existing immutable aggregates")
    args=parser.parse_args()
    if args.recover_raw:
        result=recover_configured_raw(config=args.config,root=args.root,max_filings_per_fund=args.limit)
        print(json.dumps(result,indent=2))
        return 0 if result["status"]=="complete" else 1
    if args.check:
        result=check_sec_sources(config=args.config)
        print(json.dumps(result,indent=2))
        return 0 if result["status"]=="ready" else 1
    result=collect_configured(config=args.config,root=args.root,
                              max_filings_per_fund=args.limit)
    print(json.dumps(result,indent=2))
    return 0 if result["status"]=="complete" else 1


if __name__=="__main__":
    raise SystemExit(main())
