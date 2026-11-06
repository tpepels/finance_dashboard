"""Sparse MSCI ACWI printed totals rebuilt from immutable original factsheets.

A mutable publisher URL is never proof of a formerly cited observation. The
document's own as-of date controls the observation; retrieval and first public
dissemination remain separate. Share classes are the original index constituents.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urlparse

from .source_evidence import record_acquisition_receipt

INDEX_CODE="892400"
SERIES_ID="concentration.global.msci_acwi_published_top10"
APPROVED_HOSTS={"www.msci.com","msci.com","foro.masdividendos.com",
                "schweizerfinanzblog.ch","indexalyzer.com","gestiyon.com"}
MAXIMUM_PDF_BYTES=5_000_000
# Official continuously updated USD ACWI net-return index factsheet. Its
# as-of month is read from the downloaded PDF; never inferred from this URL.
CURRENT_ACWI_FACTSHEET_URL = (
    "https://www.msci.com/documents/10199/255599/msci-acwi-net.pdf"
)
MAX_FACTSHEET_SOURCES = 15
SOURCE="MSCI_ACWI_ORIGINAL_FACTSHEET_PDF"
_DATE=r"(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+[0-9]{1,2},\s+[0-9]{4}"
_ROW=re.compile(r"^\s*(.+?)\s+(?:([A-Z]{2})\s+)?([0-9,]+\.[0-9]+)\s+([0-9]+\.[0-9]+)(?:\s+(.+?))?\s*$")


class MsciOriginalError(ValueError):
    pass


def parse_msci_constituent_count_text(text: str) -> int|None:
    """The left-hand Number of / Constituents source label, never table length."""
    lines=text.replace("\f","\n").splitlines()
    headings=[(i,line.index("TOP 10 CONSTITUENTS")) for i,line in enumerate(lines)
              if "TOP 10 CONSTITUENTS" in line]
    if len(headings)!=1: raise MsciOriginalError("Original constituent-count table ambiguous")
    start,cut=headings[0]
    left="\n".join(line[:cut].rstrip() for line in lines[start+1:start+9])
    matches=re.findall(r"\bNumber of\s+([0-9,]+)\s+Constituents\b",left)
    if not matches: return None
    if len(matches)!=1: raise MsciOriginalError("Original constituent-count label ambiguous")
    count=int(matches[0].replace(",",""))
    if not 10<=count<=100_000: raise MsciOriginalError("Original constituent count implausible")
    return count


def parse_msci_factsheet_text(text: str, *, expected_asof: str|None=None) -> dict:
    """Read the table's printed total, retaining its independent rounding check."""
    text=text.replace("\f","\n")
    titles=set(re.findall(r"(?m)^\s*MSCI (.+?) Index \(([A-Z]{3})\)\s*$",text))
    if not titles or any(title!="ACWI" for title,_ in titles):
        raise MsciOriginalError("Original factsheet index identity mismatch")
    dates=set(re.findall(r"(?m)^[\s\f]*("+_DATE+r")(?:[ \t]+Index Factsheet)?[ \t]*$",text))
    if len(dates)!=1:
        raise MsciOriginalError("Original factsheet as-of date absent or ambiguous")
    asof=datetime.strptime(next(iter(dates)),"%b %d, %Y").date()
    if asof>date.today() or asof.day<27 or expected_asof is not None and asof.isoformat()!=expected_asof:
        raise MsciOriginalError("Original factsheet date does not match observation")
    headings=[(i,line.index("TOP 10 CONSTITUENTS")) for i,line in enumerate(text.splitlines())
              if "TOP 10 CONSTITUENTS" in line]
    if len(headings)!=1:
        raise MsciOriginalError("Original factsheet top-ten table absent or ambiguous")
    start,cut=headings[0]
    constituents=[]
    published=None
    for line in text.splitlines()[start+1:]:
        match=_ROW.match(line[cut:])
        if not match:
            continue
        name,country,capitalization,weight,sector=match.groups()
        value=Decimal(weight)
        if name=="Total":
            published=value
            break
        if not sector or not Decimal(0)<value<Decimal(75):
            raise MsciOriginalError("Original factsheet constituent row invalid")
        constituents.append({"name":name,"reported_country":country,
            "float_adjusted_market_cap_native_billions":capitalization.replace(",",""),
            "index_weight_pct":weight,"sector":sector,"native_table_row":line[cut:].strip()})
    if len(constituents)!=10 or len({p["name"] for p in constituents})!=10 or published is None:
        raise MsciOriginalError("Original factsheet does not contain exactly ten constituents and total")
    summed=sum((Decimal(row["index_weight_pct"]) for row in constituents),Decimal(0))
    # Ten rounded component weights and one rounded total each have half-unit
    # precision. Their sum need not equal the separately rounded published total.
    tolerance=Decimal("0.055")
    if not Decimal(0)<published<Decimal(75) or abs(summed-published)>tolerance:
        raise MsciOriginalError("Original factsheet total differs beyond native rounding")
    return {"schema_version":1,"source":SOURCE,"index_code":INDEX_CODE,"index_name":"MSCI ACWI",
        "as_of":asof.isoformat(),"top10_percent":str(published),"constituents":constituents,
        "sum_rounded_constituent_weights_pct":str(summed),
        "constituent_sum_minus_published_total_pct":str(summed-published),
        "rounding_check_tolerance_pct":str(tolerance),
        "measurement":"printed total weight of ten index constituents; share classes remain distinct",
        "original_first_publication_at":None}


def parse_msci_factsheet_pdf(original: bytes) -> dict:
    if len(original)>MAXIMUM_PDF_BYTES or not original.startswith(b"%PDF-"):
        raise MsciOriginalError("Original factsheet is not a bounded PDF")
    from pypdf import PdfReader, __version__
    if __version__!="6.21.4":
        raise MsciOriginalError("Original factsheet extraction requires pinned pypdf 6.21.4")
    try:
        reader=PdfReader(BytesIO(original))
        if not 2<=len(reader.pages)<=6:
            raise MsciOriginalError("Unexpected original factsheet page count")
        text="\f".join(page.extract_text(extraction_mode="layout",layout_mode_space_vertically=False)
                       for page in reader.pages)
        facts=parse_msci_factsheet_text(text)
    except (ValueError,TypeError) as exc:
        raise MsciOriginalError("Original factsheet extraction failed") from exc
    return {**facts,"original_sha256":sha256(original).hexdigest(),
        "extraction":{"tool":"pypdf","version":__version__,"mode":"layout",
                      "text_sha256":sha256(text.encode()).hexdigest()},"_extracted_text":text}


# Internet Archive captures of the official factsheet URL, raw ("id_") form so
# the archived bytes are MSCI's original PDF without Wayback rewriting.
_WAYBACK_FACTSHEET=re.compile(
    r"^/web/[0-9]{14}id_/https?://(?:www\.)?msci\.com/documents/10199/255599/msci-acwi-net\.pdf$")


def _url_identity(source_url: str) -> str:
    address=urlparse(source_url)
    wayback=(address.hostname=="web.archive.org" and not address.query
             and _WAYBACK_FACTSHEET.fullmatch(address.path) is not None)
    if address.scheme!="https" or address.username or (address.hostname not in APPROVED_HOSTS and not wayback):
        raise MsciOriginalError("Unapproved original factsheet URL")
    return sha256(source_url.encode()).hexdigest()[:16]


def store_msci_concentration_original(original: bytes, *, source_url: str, root: Path) -> Path:
    facts=parse_msci_factsheet_pdf(original)
    key=_url_identity(source_url)
    extracted=facts.pop("_extracted_text")
    payloads={"original.pdf":original,"facts.json":json.dumps(facts,sort_keys=True).encode(),
              "extracted.txt":extracted.encode()}
    hashes={name:sha256(body).hexdigest() for name,body in payloads.items()}
    digest=sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    parent=root/"msci-concentration"/INDEX_CODE/facts["as_of"]/key
    folder=parent/digest
    temporary=None
    identity={"publisher":"MSCI","index_code":INDEX_CODE,"as_of":facts["as_of"],"source_url":source_url}
    try:
        parent.mkdir(parents=True,exist_ok=True)
        if not folder.exists():
            temporary=Path(tempfile.mkdtemp(prefix=".msci-",dir=parent))
            for name,body in payloads.items():
                (temporary/name).write_bytes(body)
            manifest={"schema_version":1,"source":SOURCE,**identity,"files":hashes,
                "original_first_publication_at":None,"retrieved_at_utc":datetime.now(timezone.utc).isoformat()}
            (temporary/"manifest.json").write_text(json.dumps(manifest,indent=2))
            try: os.rename(temporary,folder);temporary=None
            except FileExistsError: pass
        _verify_original(folder)
        record_acquisition_receipt(folder,identity)
        return folder
    finally:
        if temporary is not None: shutil.rmtree(temporary,ignore_errors=True)



def msci_publisher_factsheet_identity(source_url: str) -> str:
    """A deterministic acquisition ID for one public original PDF endpoint.

    A changed endpoint is a different journal action, even if both ultimately
    publish the same index/month. URL credentials and query secrets are rejected
    before they can enter the provenance report or immutable journal.
    """
    from .source_policy_registry import PolicyRegistry
    if not isinstance(source_url, str) or len(source_url) > 2048:
        raise MsciOriginalError("Invalid MSCI original PDF URL")
    parts = urlparse(source_url)
    if (parts.scheme != "https" or parts.hostname not in {"www.msci.com", "msci.com"}
            or parts.port not in (None, 443)
            or parts.username or parts.password or parts.query or parts.fragment
            or not parts.path.startswith("/") or parts.path == "/"
            or "/../" in parts.path or "/./" in parts.path):
        raise MsciOriginalError("A public MSCI original PDF URL is required")
    if PolicyRegistry().for_url(source_url).id != "msci":
        raise MsciOriginalError("MSCI original PDF host not classified")
    return "pdf-" + sha256(source_url.encode("utf-8")).hexdigest()[:20]


def msci_publisher_factsheet_sources(
        urls: tuple[str, ...] | None = None) -> tuple[tuple[str, str], ...]:
    """Bound the set of original documents; default to the publisher's current PDF."""
    targets = (CURRENT_ACWI_FACTSHEET_URL,) if urls is None else urls
    if (not isinstance(targets, (tuple, list))
            or not 1 <= len(targets) <= MAX_FACTSHEET_SOURCES
            or any(not isinstance(url, str) for url in targets)
            or len(set(targets)) != len(targets)):
        raise MsciOriginalError("Invalid MSCI original PDF source selection")
    identities = tuple((msci_publisher_factsheet_identity(url), url)
                       for url in targets)
    if len({identity for identity, _ in identities}) != len(identities):
        raise MsciOriginalError("Ambiguous MSCI original PDF source identity")
    return identities

def collect_msci_concentration_factsheet(*, root: Path, client,
                                          source_url: str) -> Path:
    """Bounded, publisher-governed fetch into the existing immutable archive.

    The operator provides a concrete original PDF endpoint. An index landing
    page, a mutable citation to an old value, or a failed response does not
    count as an acquired observation. The retained PDF establishes its own
    observed date; first-publication time remains unverified.
    """
    from .source_policy import require_managed_client

    require_managed_client(client)
    msci_publisher_factsheet_identity(source_url)
    _url_identity(source_url)

    payload = bytearray()
    with client.stream("GET", source_url, follow_redirects=False) as response:
        response.raise_for_status()
        size = response.headers.get("content-length")
        if size is not None:
            try:
                bounded = int(size)
            except ValueError as exc:
                raise MsciOriginalError("Invalid factsheet content length") from exc
            if bounded < 1 or bounded > MAXIMUM_PDF_BYTES:
                raise MsciOriginalError("Original factsheet exceeds byte limit")
        for chunk in response.iter_bytes():
            if len(payload) + len(chunk) > MAXIMUM_PDF_BYTES:
                raise MsciOriginalError("Original factsheet exceeds byte limit")
            payload.extend(chunk)
    if not payload.startswith(b"%PDF-"):
        raise MsciOriginalError("Publisher response is not an original PDF")
    return store_msci_concentration_original(
        bytes(payload), source_url=source_url, root=root)


def _verify_original(folder: Path) -> tuple[dict,dict]:
    try:
        manifest=json.loads((folder/"manifest.json").read_text())
        files=manifest["files"]
        if (folder.is_symlink() or (folder/"manifest.json").is_symlink()
                or set(files)!={"original.pdf","facts.json","extracted.txt"}
                or sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()!=folder.name
                or manifest["schema_version"]!=1 or manifest["source"]!=SOURCE
                or manifest["publisher"]!="MSCI" or manifest["index_code"]!=INDEX_CODE
                or manifest["original_first_publication_at"] is not None
                or folder.parent.name!=_url_identity(manifest["source_url"])
                or folder.parent.parent.name!=manifest["as_of"]):
            raise ValueError("manifest identity")
        bodies={}
        for name,digest in files.items():
            path=folder/name
            if path.is_symlink() or path.stat().st_size>MAXIMUM_PDF_BYTES:
                raise ValueError("original file")
            bodies[name]=path.read_bytes()
            if sha256(bodies[name]).hexdigest()!=digest: raise ValueError("hash")
        native=parse_msci_factsheet_pdf(bodies["original.pdf"])
        if native.pop("_extracted_text").encode()!=bodies["extracted.txt"]:
            raise ValueError("extraction")
        if native!=json.loads(bodies["facts.json"]) or native["as_of"]!=manifest["as_of"]:
            raise ValueError("native facts")
        return manifest,native
    except (OSError,ValueError,TypeError,KeyError) as exc:
        raise MsciOriginalError("Immutable original MSCI factsheet inconsistent") from exc


def monthly_msci_values(records: list[dict]) -> dict[date,Decimal]:
    result={}
    for record in records:
        asof=date.fromisoformat(record["as_of"])
        month=asof.replace(day=1)
        value=Decimal(record["top10_percent"])
        if month in result and result[month]!=value:
            raise MsciOriginalError("Original factsheets have conflicting observations")
        result[month]=value
    return dict(sorted(result.items()))


def read_msci_concentration_originals(root: Path) -> tuple[dict[date,Decimal],dict]:
    from .source_reconciliation import _selected_manifest
    records=[]
    proofs=[]
    for parent in sorted((root/"msci-concentration"/INDEX_CODE).glob("????-??-??/*")):
        if not parent.is_dir() or not re.fullmatch(r"[0-9a-f]{16}",parent.name): continue
        manifests=[_verify_original(folder) for folder in sorted(parent.glob("*"))
                   if re.fullmatch(r"[0-9a-f]{64}",folder.name)]
        if not manifests: raise MsciOriginalError("Original MSCI archive has no immutable documents")
        urls={manifest["source_url"] for manifest,_ in manifests}
        if len(urls)!=1: raise MsciOriginalError("Original MSCI source URL identity ambiguous")
        identity={"publisher":"MSCI","index_code":INDEX_CODE,"as_of":parent.parent.name,
                  "source_url":next(iter(urls))}
        observed,manifest_hash,path,manifest,selection=_selected_manifest(parent,identity)
        if selection!="acquisition_receipt":
            raise MsciOriginalError("Original MSCI archive requires an acquisition receipt")
        verified,facts=_verify_original(path.parent)
        if verified!=manifest: raise MsciOriginalError("Original MSCI receipt identity differs")
        count=parse_msci_constituent_count_text((path.parent/"extracted.txt").read_text())
        records.append({**facts,"constituent_count":count})
        proofs.append({"as_of":facts["as_of"],"period":facts["as_of"][:7]+"-01",
            "top10_percent":facts["top10_percent"],"constituent_count":count,"source_url":manifest["source_url"],
            "source_file_sha256":facts["original_sha256"],"source_manifest_sha256":manifest_hash,
            "bundle_digest":path.parent.name,"acquisition_observed_at_utc":observed.isoformat(),
            "selection_method":selection,"original_first_publication_at":None})
    if not records: raise MsciOriginalError("Missing original MSCI ACWI factsheet documents")
    values=monthly_msci_values(records)
    return values,{"source":"MSCI_ACWI_ORIGINAL_FACTSHEET_PDF","source_snapshot_scope":"partial_original_documents",
        "source_first_publication_at":None,"source_observation_dates":[r["as_of"] for r in records],
        "original_covered_periods":[d.isoformat() for d in values],"original_document_proofs":proofs,
        "constituent_count_values":{r["as_of"][:7]+"-01":str(r["constituent_count"])
                                   for r in records if r["constituent_count"] is not None},
        "source_sha256":sha256(json.dumps(proofs,sort_keys=True).encode()).hexdigest(),
        "source_periods":len(values),"source_first_observation":min(values).isoformat(),
        "source_last_observation":max(values).isoformat(),
        "limitations":"Sparse original factsheets only; secondary research excluded; mutable URLs cannot verify former document dates; no interpolation or issuer consolidation"}
