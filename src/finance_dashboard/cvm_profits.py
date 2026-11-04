"""Original CVM consolidated annual-income evidence, never worldwide profits.

Keep issuer, fiscal period, report revision, native scale and parent attribution
separate. A received date is authority metadata, not proved public availability.
"""
from __future__ import annotations
import csv
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import unicodedata
import zipfile

import httpx

from .bis import ProviderError
from .research_returns import _number
from .source_evidence import record_acquisition_receipt

DRE_FIELDS=("CNPJ_CIA","DT_REFER","VERSAO","DENOM_CIA","CD_CVM","GRUPO_DFP","MOEDA",
    "ESCALA_MOEDA","ORDEM_EXERC","DT_INI_EXERC","DT_FIM_EXERC","CD_CONTA","DS_CONTA","VL_CONTA","ST_CONTA_FIXA")
FILING_FIELDS=("CNPJ_CIA","DT_REFER","VERSAO","DENOM_CIA","CD_CVM","CATEG_DOC","ID_DOC","DT_RECEB","LINK_DOC")
BASE="https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/"


def _rows(raw,expected):
    if len(raw)>50_000_000:
        raise ProviderError("CVM source CSV exceeds bounded size")
    reader=csv.DictReader(io.StringIO(raw.decode("latin1")),delimiter=";")
    if tuple(reader.fieldnames or ())!=expected:
        raise ProviderError("Original CVM CSV column identity mismatch")
    rows=list(reader)
    if any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ProviderError("Original CVM CSV row width invalid")
    return rows


def _label(raw):
    return "".join(c for c in unicodedata.normalize("NFKD",raw.lower()) if not unicodedata.combining(c))


def parse_cvm_consolidated_income(dre_csv: bytes,filings_csv: bytes,*,authority_receipt_cutoff: date|None=None) -> dict:
    rows=_rows(dre_csv,DRE_FIELDS)
    filings=_rows(filings_csv,FILING_FIELDS)
    versions={}
    for row in filings:
        if row["CATEG_DOC"]!="DFP":
            raise ProviderError("Original CVM filing category mismatch")
        if authority_receipt_cutoff is not None and date.fromisoformat(row["DT_RECEB"])>authority_receipt_cutoff:
            continue
        key=(row["CNPJ_CIA"],row["DT_REFER"])
        versions.setdefault(key,[]).append(row)
    groups={}
    for rowno,row in enumerate(rows,2):
        if row["GRUPO_DFP"]!="DF Consolidado - Demonstração do Resultado":
            raise ProviderError("Consolidated CVM income scope mismatch")
        if row["ORDEM_EXERC"]!="ÚLTIMO": continue
        key=(row["CNPJ_CIA"],row["DT_REFER"])
        groups.setdefault(key,[]).append((rowno,row))
    records=[]
    unavailable_revisions=[]
    for key,source_rows in sorted(groups.items()):
        if key not in versions:
            if authority_receipt_cutoff is not None:
                continue
            raise ProviderError("CVM income lacks matching filing metadata")
        current=max(int(f["VERSAO"]) for f in versions[key])
        selected=[(i,r) for i,r in source_rows if int(r["VERSAO"])==current]
        metadata=[f for f in versions[key] if int(f["VERSAO"])==current]
        if len(metadata)!=1:
            raise ProviderError("Latest CVM filing/income version not uniquely matched")
        if not selected:
            if authority_receipt_cutoff is None:
                raise ProviderError("Latest CVM filing/income version not uniquely matched")
            unavailable_revisions.append({'cnpj':key[0],'report_reference_date':key[1],
                'filing_version':current,'authority_received_date':metadata[0]['DT_RECEB'],
                'reason':'Receipt-eligible filing revision is absent from this current original DRE package; later revision not substituted.'})
            continue
        # Identical rows occur in the source CSV. Retain their exact row numbers,
        # but count a reported fact once; conflicting duplicates remain blocked.
        unique={}
        for i,r in selected:
            unique.setdefault(tuple(r.items()),[]).append(i)
        facts=[dict(items) for items in unique]
        one=facts[0]
        if metadata[0]['CD_CVM']!=one['CD_CVM']:
            raise ProviderError('CVM filing/income issuer identity mismatch')
        dimensions=("CD_CVM","MOEDA","ESCALA_MOEDA","DT_INI_EXERC","DT_FIM_EXERC")
        if any(any(r[d]!=one[d] for d in dimensions) for r in facts):
            raise ProviderError("CVM fiscal/currency/issuer dimensions conflict")
        if one["MOEDA"]!="REAL" or one["ESCALA_MOEDA"] not in {"MIL","UNIDADE"}:
            raise ProviderError("Unverified CVM native currency or scale")
        start,end=(date.fromisoformat(one[d]) for d in ("DT_INI_EXERC","DT_FIM_EXERC"))
        if start>end:
            raise ProviderError("CVM fiscal period reversed")
        received=date.fromisoformat(metadata[0]["DT_RECEB"])
        candidates=[r for r in facts if r["CD_CONTA"] in {"3.09.01","3.11.01","3.13.01"}
            and r["ST_CONTA_FIXA"]=="S" and _label(r["DS_CONTA"]).startswith("atribuido")
            and "controladora" in _label(r["DS_CONTA"])]
        parent=total=minority=None
        residual=None
        state="missing_parent_income" if not candidates else "ambiguous_parent_income" if len(candidates)>1 else "reported_profit_partition_missing"
        parent_row=candidates[0] if len(candidates)==1 else None
        if parent_row:
            parent=_number(parent_row["VL_CONTA"])
            prefix=parent_row["CD_CONTA"].rsplit(".",1)[0]
            totals=[r for r in facts if r["CD_CONTA"]==prefix and r["ST_CONTA_FIXA"]=="S"
                    and "consolidado" in _label(r["DS_CONTA"]) and any(s in _label(r["DS_CONTA"]) for s in ("lucro","prejuizo"))]
            minorities=[r for r in facts if r["CD_CONTA"]==prefix+".02" and r["ST_CONTA_FIXA"]=="S"
                        and "nao controladores" in _label(r["DS_CONTA"])]
            if len(totals)==len(minorities)==1:
                total,minority=(_number(r["VL_CONTA"]) for r in (totals[0],minorities[0]))
                residual=parent+minority-total
                state="exact_reported_profit_partition_passed" if residual==0 else "reported_profit_partition_mismatch"
        scale=Decimal(1000) if one["ESCALA_MOEDA"]=="MIL" else Decimal(1)
        records.append({"cnpj":key[0],"cvm_company_code":one["CD_CVM"],"issuer_name":one["DENOM_CIA"],
            "report_reference_date":key[1],"filing_version":current,
            "available_filing_versions":[{"version":int(f["VERSAO"]),"authority_received_date":f["DT_RECEB"],"document_id":f["ID_DOC"]} for f in sorted(versions[key],key=lambda f:int(f["VERSAO"]))],
            "authority_received_date":received.isoformat(),"filing_document_id":metadata[0]["ID_DOC"],
            "original_document_url":metadata[0]["LINK_DOC"],"first_publication_verified":False,
            "authority_receipt_is_first_publication":False,
            "fiscal_start":start.isoformat(),"fiscal_end":end.isoformat(),
            "calendar_year_aligned":start==date(end.year,1,1) and end==date(end.year,12,31),
            "reported_consolidation_scope":one["GRUPO_DFP"],"native_currency":one["MOEDA"],"native_scale":one["ESCALA_MOEDA"],
            "parent_income_account":parent_row["CD_CONTA"] if parent_row else None,
            "parent_income_label":parent_row["DS_CONTA"] if parent_row else None,
            "parent_attributable_income_native":str(parent) if parent is not None else None,
            "parent_attributable_income_brl":str(parent*scale) if parent is not None else None,
            "consolidated_income_native":str(total) if total is not None else None,
            "noncontrolling_income_native":str(minority) if minority is not None else None,
            "parent_plus_noncontrolling_minus_total_native":str(residual) if residual is not None else None,
            "state":state,"source_csv_rows":[i for i,_ in selected],
            "duplicate_identical_source_rows":len(selected)-len(unique)})
    return {"schema_version":1,"source":"CVM_ORIGINAL_CONSOLIDATED_DRE",
        "publisher":"Comissão de Valores Mobiliários (CVM)",
        "authority_receipt_cutoff":authority_receipt_cutoff.isoformat() if authority_receipt_cutoff else None,
        "selection":"Latest available matching annual filing revision by authority receipt date; not a public-release vintage",
        "status":"regional_source_partial" if not records or unavailable_revisions or any(r["state"]!="exact_reported_profit_partition_passed" for r in records) else "regional_source_accounting_checked",
        "population":{"filing_issuers":len({f["CNPJ_CIA"] for f in filings}),
            "filing_versions":len(filings),"consolidated_income_issuers":len({r["cnpj"] for r in records})},
        "records":records,"unavailable_historical_revisions":unavailable_revisions,
        "worldwide_population_verified":False,"listed_population_verified":False,
        "ultimate_parent_deduplication_verified":False,"fx_conversion_performed":False,
        "source_csv_sha256":{"consolidated_dre":sha256(dre_csv).hexdigest(),"filing_metadata":sha256(filings_csv).hexdigest()},
        "limits":"CVM reporting companies are not a proved worldwide or listed-parent universe. Consolidated parent profit remains issuer-specific; corporate cross-holdings, issuer domicile, fiscal-calendar alignment, FX and publication instants are unverified. Exact reported partition residuals are disclosed without modifying values or fitting a tolerance. No worldwide or regional profit aggregate is produced."}


def audit_cvm_annual_archive(original: bytes,*,year: int,authority_receipt_cutoff: date|None=None) -> dict:
    if year<2010 or year>2026:
        raise ProviderError("CVM annual archive year outside reviewed source range")
    try:
        # Annual packages also contain large, unrelated equity-change schedules.
        # Bound and read only the two original income/filing members required.
        with zipfile.ZipFile(io.BytesIO(original)) as archive:
            names=archive.namelist()
            if len(names)>100 or len(names)!=len(set(names)):
                raise ValueError("duplicate or excess archive members")
            selected=(f"dfp_cia_aberta_DRE_con_{year}.csv",f"dfp_cia_aberta_{year}.csv")
            if any(archive.getinfo(name).file_size>50_000_000 for name in selected):
                raise ValueError("selected member size")
            report=parse_cvm_consolidated_income(*(archive.read(name) for name in selected),
                authority_receipt_cutoff=authority_receipt_cutoff)
            if any(int(r['report_reference_date'][:4])!=year for r in report['records']):
                raise ValueError('archive fiscal reference year mismatch')
    except (KeyError,ValueError,zipfile.BadZipFile) as exc:
        raise ProviderError("Original CVM annual archive members invalid") from exc
    return {**report,"source_url":BASE+f"dfp_cia_aberta_{year}.zip","original_archive_sha256":sha256(original).hexdigest()}


def _source_identity(year: int) -> dict:
    return {"publisher":"Comissão de Valores Mobiliários (CVM)","dataset":"DFP consolidated DRE",
            "year":year,"source_url":BASE+f"dfp_cia_aberta_{year}.zip"}


def _verified_bundle(folder: Path,*,year: int) -> tuple[dict,dict]:
    """Rebuild issuer facts from original ZIP, rather than trusting an audit JSON."""
    try:
        if folder.is_symlink() or (folder/'manifest.json').is_symlink():
            raise ValueError('symlink')
        manifest=json.loads((folder/'manifest.json').read_text())
        expected={"original.zip","facts.json"}
        if (manifest['schema_version']!=1 or manifest['source_identity']!=_source_identity(year)
                or manifest['original_first_publication_at'] is not None
                or set(manifest['files'])!=expected
                or sha256(json.dumps(manifest['files'],sort_keys=True).encode()).hexdigest()!=folder.name):
            raise ValueError('identity')
        bodies={}
        for name in expected:
            path=folder/name
            if path.is_symlink() or path.stat().st_size>50_000_000:
                raise ValueError('source size or symlink')
            bodies[name]=path.read_bytes()
            if sha256(bodies[name]).hexdigest()!=manifest['files'][name]:
                raise ValueError('source hash')
        report=audit_cvm_annual_archive(bodies['original.zip'],year=year)
        if report!=json.loads(bodies['facts.json']):
            raise ValueError('source selection')
        return manifest,report
    except (OSError,ValueError,KeyError,TypeError) as exc:
        raise ProviderError('Immutable original CVM evidence inconsistent') from exc


def store_cvm_source(original: bytes,*,year: int,root: Path,http_metadata: dict|None=None) -> Path:
    """Archive native issuer evidence atomically; repeat captures append receipts."""
    report=audit_cvm_annual_archive(original,year=year)
    payloads={'original.zip':original,'facts.json':json.dumps(report,sort_keys=True).encode()}
    hashes={name:sha256(body).hexdigest() for name,body in payloads.items()}
    digest=sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
    parent=Path(root)/'corporate-profits/cvm'/str(year)
    folder=parent/digest
    temporary=None
    try:
        parent.mkdir(parents=True,exist_ok=True)
        if not folder.exists():
            temporary=Path(tempfile.mkdtemp(prefix='.cvm-',dir=parent))
            for name,body in payloads.items():
                with (temporary/name).open('wb') as stream:
                    stream.write(body);stream.flush();os.fsync(stream.fileno())
            manifest={'schema_version':1,'source_identity':_source_identity(year),'files':hashes,
                'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),'original_first_publication_at':None,
                'acquisition_method':'publisher_http' if http_metadata is not None else 'imported_original_bytes',
                'http_metadata':http_metadata,
                'publication_note':'Annual ZIP is a revisable current package. Local acquisition, HTTP modification, authority receipt and first public release are distinct.'}
            with (temporary/'manifest.json').open('w') as stream:
                json.dump(manifest,stream,indent=2);stream.flush();os.fsync(stream.fileno())
            try:
                os.rename(temporary,folder)
            except OSError:
                if not folder.exists(): raise
        _verified_bundle(folder,year=year)
        record_acquisition_receipt(folder,_source_identity(year))
        return folder
    finally:
        if temporary is not None: shutil.rmtree(temporary,ignore_errors=True)


def read_cvm_sources(root: Path) -> dict:
    """Read the latest receipt-selected original edition independently per year."""
    from .source_reconciliation import _selected_manifest
    records=[]
    for parent in sorted((Path(root)/'corporate-profits/cvm').glob('????')):
        if not re.fullmatch(r'20[0-9]{2}',parent.name): continue
        year=int(parent.name)
        retrieved,manifest_hash,path,_record,selection=_selected_manifest(parent,_source_identity(year))
        manifest,report=_verified_bundle(path.parent,year=year)
        if selection!='acquisition_receipt' or sha256(path.read_bytes()).hexdigest()!=manifest_hash:
            raise ProviderError('Original CVM acquisition receipt missing')
        records.append({**report,'archive_year':year,'bundle_digest':path.parent.name,
            'source_manifest_sha256':manifest_hash,'evidence_retrieved_at_utc':retrieved.isoformat(),
            'selection_method':selection,'acquisition_method':manifest['acquisition_method']})
    return {'status':'regional_source_partial' if records else 'missing_original_cvm_evidence',
        'publisher':'Comissão de Valores Mobiliários (CVM)','records':records,
        'worldwide_population_verified':False,'listed_population_verified':False,
        'first_publication_verified':False,'aggregate_produced':False}


def collect_cvm_annual_source(*,root: Path,year: int,client: httpx.Client) -> dict:
    """Canonical bounded publisher acquisition; no database or aggregate writes."""
    if not 2010<=year<=date.today().year:
        raise ProviderError('CVM annual archive year outside reviewed source range')
    url=BASE+f'dfp_cia_aberta_{year}.zip'
    response=client.get(url,follow_redirects=False)
    if response.status_code>=400: response.raise_for_status()
    if response.status_code!=200 or len(response.content)>50_000_000:
        raise ProviderError('Original CVM annual response status or size invalid')
    folder=store_cvm_source(response.content,year=year,root=root,http_metadata={
        'last_modified':response.headers.get('last-modified'),'etag':response.headers.get('etag'),
        'content_type':response.headers.get('content-type')})
    return {'archive_year':year,'source_url':url,'bundle_digest':folder.name,
        'status':'regional_source_partial','worldwide_population_verified':False,'database_writes':0}


def main() -> int:
    import argparse
    parser=argparse.ArgumentParser(description="Read-only original CVM consolidated profit evidence audit")
    parser.add_argument("--file",type=Path,required=True)
    parser.add_argument("--year",type=int,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    report=audit_cvm_annual_archive(args.file.read_bytes(),year=args.year)
    with args.output.open("x",encoding="utf-8") as stream:
        json.dump(report,stream,indent=2)
    print(json.dumps({k:v for k,v in report.items() if k!="records"},indent=2))
    return 0


if __name__=="__main__": raise SystemExit(main())
