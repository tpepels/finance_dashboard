"""Independent, exact-original reconciliation for ECB DWA, Eurostat HPI and SEC N-MFP.

Every observation originates in response bytes already hash-verified by the
canonical receipt/archive gateway. Never use an ingestion adapter here.
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
import csv
import json
import re
from urllib.parse import urlsplit, parse_qs
from zipfile import ZipFile

from .source_reconciliation import EvidenceError


def _decimal(value):
    try:
        output = Decimal(str(value).strip())
        if not output.is_finite():
            raise InvalidOperation
        return output
    except (ValueError, TypeError, InvalidOperation):
        raise EvidenceError("source_numeric_invalid") from None


def _quarter(label):
    if not re.fullmatch(r"\d{4}-?Q[1-4]", str(label)):
        raise EvidenceError("source_period_invalid")
    return date(int(label[:4]), 3*(int(label[-1])-1)+1, 1)


def _ecb_dwa(raw, source, definition, start):
    key = definition["source_key"]
    path = "https://data-api.ecb.europa.eu/service/data/DWA/" + key[4:]
    url = urlsplit(source["url"])
    expected = {"format":["csvdata"]}
    if start:
        expected["startPeriod"] = [f"{int(start[:4])}-Q{(int(start[5:7])-1)//3+1}"]
    if url._replace(query="",fragment="").geturl() != path or parse_qs(url.query) != expected:
        raise EvidenceError("source_identity_mismatch")
    reader = csv.DictReader(StringIO(raw.decode("utf-8-sig")))
    if not reader.fieldnames or not {"KEY","TIME_PERIOD","OBS_VALUE"} <= set(reader.fieldnames):
        raise EvidenceError("source_schema_invalid")
    values={}
    for row in reader:
        if row["KEY"]!=key:raise EvidenceError("source_identity_mismatch")
        if row["OBS_VALUE"].strip() in ("","."):
            continue
        day=_quarter(row["TIME_PERIOD"])
        value=_decimal(row["OBS_VALUE"])
        if not 0 <= value <= 100 or day in values:
            raise EvidenceError("source_value_or_period_invalid")
        values[day]=value
    return values, {"source_native_unit":"percent","source_scope":"ECB S14 household adjusted net wealth"}


def _eurostat(raw, source, definition, start):
    from urllib.parse import parse_qs
    key=definition["source_key"].split("/")
    if len(key)!=4 or key[0]!="prc_hpi_q":
        raise EvidenceError("source_identity_mismatch")
    area,purchase,unit=key[1:]
    url=urlsplit(source["url"])
    params={"freq":["Q"],"geo":[area],"purchase":[purchase],"unit":[unit]}
    if start:params["sinceTimePeriod"]=[f"{int(start[:4])}-Q{(int(start[5:7])-1)//3+1}"]
    if (url._replace(query="",fragment="").geturl() !=
            "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hpi_q"
            or parse_qs(url.query)!=params):
        raise EvidenceError("source_identity_mismatch")
    payload=json.loads(raw,parse_float=Decimal)
    if payload.get("class")!="dataset":raise EvidenceError("source_schema_invalid")
    ids=payload.get("id"); sizes=payload.get("size")
    if not isinstance(ids,list) or not isinstance(sizes,list) or set(ids)!={"freq","geo","purchase","unit","time"} or len(sizes)!=5:
        raise EvidenceError("source_schema_invalid")
    idx={}
    for i,name in enumerate(ids):
        idx[name]=payload["dimension"][name]["category"]["index"]
        if len(idx[name])!=sizes[i]:raise EvidenceError("source_schema_invalid")
    req={"geo":area,"purchase":purchase,"unit":unit,"freq":"Q"}
    if any(sizes[ids.index(k)]!=1 or kcode not in idx[k] for k,kcode in req.items()):
        raise EvidenceError("source_identity_mismatch")
    time_map={v:k for k,v in idx["time"].items()}
    values={}
    for item,value in payload["value"].items():
        offset=int(item); positions={}
        if str(offset)!=str(item) or offset <0:raise EvidenceError("source_schema_invalid")
        for name,size in reversed(list(zip(ids,sizes))):
            positions[name]=offset%size
            offset//=size
        if offset or any(positions[k]!=idx[k][v] for k,v in req.items()):
            raise EvidenceError("source_identity_mismatch")
        period=time_map.get(positions["time"])
        day=_quarter(period)
        val=_decimal(value)
        if val<=0 or day in values:raise EvidenceError("source_value_or_period_invalid")
        values[day]=val
    return values, {"source_native_unit":"2015_base_index","source_scope":"Eurostat dwelling purchases"}


def _tsv(zf, name):
    matches=[r for r in zf.infolist() if not r.is_dir() and r.filename.upper().split("/")[-1]==name+".TSV"]
    if len(matches)!=1 or matches[0].file_size>35_000_000:
        raise EvidenceError("source_schema_invalid")
    rows=csv.DictReader(StringIO(zf.read(matches[0]).decode("utf-8-sig")),delimiter="\t")
    if not rows.fieldnames or "ACCESSION_NUMBER" not in rows.fieldnames:
        raise EvidenceError("source_schema_invalid")
    return list(rows)


def _month_zip(raw, month):
    # Independent keyed joins, choosing latest amendment per fund series.
    with ZipFile(BytesIO(raw)) as zf:
        submission=_tsv(zf,"SUBMISSION")
        series=_tsv(zf,"SERIESLEVELINFO")
        liquidity=_tsv(zf,"LIQUIDASSETSDETAILS")
    reports={}
    for row in submission:
        if row.get("SUBMISSIONTYPE") not in ("N-MFP3","N-MFP3/A"):continue
        report=datetime.strptime(row["REPORTDATE"],"%Y-%m-%d").date()
        if report.year!=month.year or report.month!=month.month:continue
        accession=row["ACCESSION_NUMBER"]
        if accession in reports:raise EvidenceError("source_duplicate_identity")
        reports[accession]=(row["SERIESID"],row["FILING_DATE"])
    rows={}
    for row in series:
        a=row["ACCESSION_NUMBER"]
        if a in reports:
            if a in rows:raise EvidenceError("source_duplicate_identity")
            rows[a]=row
    latest={}
    for accession,(fund,filing) in reports.items():
        if accession not in rows or not fund:continue
        if fund not in latest or (filing,accession)>latest[fund][0]:
            latest[fund]=((filing,accession),accession)
    holdings={}
    for _,accession in latest.values():
        row=rows[accession]
        if row["FEEDERFUNDFLAG"]=="Y":continue
        value=_decimal(row["NETASSETSOFSERIES"])
        if value>0:holdings[accession]=(value,row)
    if not holdings:raise EvidenceError("source_empty")
    assets=sum((v[0] for v in holdings.values()),Decimal(0))
    result={"NET_ASSETS_MUSD":assets/Decimal(1000000)}
    for key,field in (("WAM_DAYS","AVERAGEPORTFOLIOMATURITY"),
                      ("WAL_DAYS","AVERAGELIFEMATURITY")):
        pairs=[(size,_decimal(row[field])) for size,row in holdings.values() if row.get(field)]
        if pairs:
            result[key]=sum((size*value for size,value in pairs),Decimal(0))/sum((size for size,_ in pairs),Decimal(0))
    by_fund={}
    for row in liquidity:
        accession=row["ACCESSION_NUMBER"]
        if accession not in holdings or not row.get("PCTWEEKLYLIQUIDASSETS"):continue
        day=datetime.strptime(row["TOTLIQUIDASSETSNEARPCTDATE"],"%Y-%m-%d").date()
        if (day.year,day.month)!=(month.year,month.month):continue
        fraction=_decimal(row["PCTWEEKLYLIQUIDASSETS"])
        if not 0<=fraction<=1:raise EvidenceError("source_numeric_invalid")
        if accession not in by_fund or day>by_fund[accession][0]:
            by_fund[accession]=(day,fraction*100)
        elif day==by_fund[accession][0]:raise EvidenceError("source_duplicate_identity")
    if by_fund:
        weight=sum((holdings[a][0] for a in by_fund),Decimal(0))
        result["WEEKLY_LIQUIDITY_PCT"]=sum((holdings[a][0]*v[1] for a,v in by_fund.items()),Decimal(0))/weight
    return result


def _sec_nmfp(originals, sources, definition):
    if len(sources)<2 or sources[0]["url"]!="https://www.sec.gov/data-research/sec-markets-data/dera-form-n-mfp-data-sets":
        raise EvidenceError("source_identity_mismatch")
    # Each ZIP must be linked from the exact first archived publisher index.
    from html.parser import HTMLParser
    from urllib.parse import urljoin
    class Links(HTMLParser):
        def __init__(self):
            super().__init__();self.links=[]
        def handle_starttag(self, tag, attrs):
            if tag=="a":
                href=dict(attrs).get("href")
                if href:self.links.append(urljoin(sources[0]["url"],href))
    links=Links();links.feed(originals[0][0].decode("utf-8-sig"))
    allowed=set(links.links)
    metric=definition["source_key"]
    if metric not in ("NET_ASSETS_MUSD","WAM_DAYS","WAL_DAYS","WEEKLY_LIQUIDITY_PCT"):
        raise EvidenceError("source_identity_mismatch")
    values={}
    for (raw,_),source in zip(originals[1:],sources[1:]):
        url=source["url"]
        if url not in allowed:raise EvidenceError("source_identity_mismatch")
        matched=re.fullmatch(
            r"https://www\.sec\.gov/files/dera/data/form-n-mfp-data-sets/(\d{8})-(\d{8})_nmfp\.zip",url,re.I)
        if not matched:raise EvidenceError("source_identity_mismatch")
        # Filing windows are not reporting months. Obtain report month from
        # the verified SEC link label, never from ZIP acquisition dates.
        # Each monthly archive includes the prior-month reporting forms.
        end=datetime.strptime(matched.group(2),"%Y%m%d").date()
        month=(date(end.year if end.month>1 else end.year-1,
                    end.month-1 if end.month>1 else 12,1))
        sample=_month_zip(raw,month)
        if metric in sample:
            if month in values:raise EvidenceError("source_duplicate_identity")
            values[month]=sample[metric]
    return values, {"source_native_unit":definition["unit"],"individual_observation_first_publication_verified":False}


def independent_values(provider, originals, sources, definition, start):
    if provider=="ECB_DWA":
        return _ecb_dwa(originals[0][0],sources[0],definition,start)
    if provider=="EUROSTAT_HPI":
        return _eurostat(originals[0][0],sources[0],definition,start)
    if provider=="SEC_NMFP":
        return _sec_nmfp(originals,sources,definition)
    raise EvidenceError("unsupported_independent_source")
