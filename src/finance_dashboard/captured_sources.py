"""Independent selectors for archived native publisher responses.

This module deliberately does not call provider ingestion parsers. A full
source snapshot is required; an overlap response cannot certify old DB rows.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from html.parser import HTMLParser
import csv
from calendar import monthrange
import io
import json
import re

from .catalog import source_contract
from .source_capture import canonical_bytes


def captured_source(root, definition, select_manifest, original_file, *, allow_subset=False):
    from .source_reconciliation import EvidenceError
    definition = source_contract(definition)
    identity = {key: definition[key] for key in ("provider", "source_key")}
    identity["series_id"] = definition["id"]
    retrieved, manifest_hash, path, manifest, method = select_manifest(
        root / "responses" / definition["id"], identity)
    try:
        content = manifest["content_identity"]
        if (manifest.get("schema_version") != 1 or any(manifest.get(k) != v for k, v in identity.items())
                or manifest.get("source_contract") != definition
                or manifest.get("source_contract_sha256") != sha256(canonical_bytes(definition)).hexdigest()
                or path.parent.name != sha256(canonical_bytes(content)).hexdigest()
                or content["source_identity"] != identity):
            raise EvidenceError("source_identity_mismatch")
        scope = ("requested_period_subset", True) if allow_subset else ("full_source_snapshot", False)
        if manifest.get("scope") != scope[0] or (manifest.get("requested_from") is not None) != scope[1]:
            raise EvidenceError("source_snapshot_partial")
        provider = definition["provider"]
        if len(manifest["sources"]) != (2 if provider == "SHILLER" else 1):
            raise EvidenceError("source_response_ambiguous")
        sources=manifest['sources']
        if content["responses"] != [{key: source[key] for key in ("file", "url", "sha256", "bytes")} for source in sources]:
            raise EvidenceError("source_identity_mismatch")
        # Check every raw response before parsing any selected field, including
        # the homepage that independently identifies a downloaded workbook.
        originals=[original_file(path.parent,source,f'response-{index}.bin',binary=True)
                   for index,source in enumerate(sources)]
        source=sources[-1]
        raw,data_hash=originals[-1]
        body=raw.decode('utf-8-sig') if provider not in {'SHILLER','WORLD_BANK_PINK_SHEET'} else None
        dimensions={}
        if provider == "FRED":
            values = _fred(body, definition, source["url"])
        elif provider == "WORLD_BANK":
            values = _world_bank(json.loads(body, parse_float=Decimal), definition)
        elif provider == 'IMF_DATAMAPPER':
            values,dimensions = _imf_mapper(json.loads(body,parse_float=Decimal),definition,source['url'])
        elif provider == 'BEA_Q':
            values = (_bea_table_row(body,definition,source['url']) if definition['source_key'].startswith(('BEA_2026_TABLE_A_','BEA_2026_TABLE_B_'))
                      else _bea_q(body,definition,source['url']))
        elif provider == 'WORLD_BANK_PINK_SHEET':
            values,dimensions = _pink_sheet(raw,definition,source['url'])
        elif provider == 'SHILLER':
            values,dimensions = _shiller(raw,definition,originals[0][0].decode('utf-8-sig'),
                              sources[0]['url'],source['url'], return_metadata=True)
        elif provider == 'ECB':
            values,dimensions = _ecb(body,definition,source['url'],manifest.get('requested_from') if allow_subset else None)
        elif provider == 'FED_G17_DIFFUSION':
            values,dimensions = _g17_diffusion(body,definition,source['url'])
        elif provider == 'OFR_FSI':
            values,dimensions = _ofr_fsi(body,definition,source['url'])
        elif provider == 'BOJ_TSS':
            values,dimensions = _boj(body,definition,source['url'])
        elif provider == 'OECD_CLI':
            values,dimensions = _oecd_cli(body,definition,source['url'])
        elif provider == 'IMF_BOP_IIP':
            values,dimensions = _imf_bop_iip(raw,definition,source['url'])
        elif provider == 'FDIC_BANKFIND':
            values,dimensions = _fdic(json.loads(body,parse_float=Decimal),definition,source['url'])
        else:
            payload=json.loads(body,parse_float=Decimal)
            values = _bis(payload, definition)
            if provider=='BIS': dimensions=_bis_policy_metadata(payload)
            if provider=='BIS_TOTAL_CREDIT': dimensions=_bis_credit_metadata(payload,definition)
        if not values:
            raise EvidenceError("source_empty")
        return values, {"source_sha256": data_hash, "source_manifest_sha256": manifest_hash,
            "evidence_retrieved_at_utc": retrieved.isoformat(), "selection_method": method,
            "source_snapshot_scope": manifest["scope"],**dimensions,
            **({'supporting_source_sha256':{'homepage':originals[0][1]}} if provider=='SHILLER' else {})}
    except EvidenceError:
        raise
    except (KeyError, TypeError, ValueError, IndexError, AttributeError, UnicodeError, csv.Error):
        raise EvidenceError("source_schema_invalid") from None


def _native_period(label, frequency):
    from .source_reconciliation import EvidenceError
    if frequency == "Q" and re.fullmatch(r"\d{4}-?Q[1-4]", label):
        day = date(int(label[:4]), 1 + 3 * (int(label[-1]) - 1), 1)
    elif frequency == "A" and re.fullmatch(r"\d{4}", label):
        day = date(int(label), 1, 1)
    elif frequency == "M" and re.fullmatch(r"\d{4}-\d{2}", label):
        day = date.fromisoformat(label + "-01")
    else:
        day = date.fromisoformat(label)
    if ((frequency == "Q" and (day.month not in (1, 4, 7, 10) or day.day != 1))
            or (frequency == "A" and (day.month, day.day) != (1, 1))
            or (frequency == "M" and day.day != 1) or day > date.today()):
        raise EvidenceError("source_period_invalid")
    return day


def _add(values, seen, period, raw):
    from .source_reconciliation import EvidenceError
    if period in seen:
        raise EvidenceError("source_duplicate_period")
    seen.add(period)
    if raw in (None, "", ".", "NA", "N/A", "NaN", ":"):
        return
    try:
        value = Decimal(str(raw))
        if not value.is_finite():
            raise InvalidOperation
    except (ValueError, InvalidOperation):
        raise EvidenceError("source_value_invalid") from None
    values[period] = value


def _fred(body, definition, url):
    from .source_reconciliation import EvidenceError
    from urllib.parse import urlsplit, parse_qs
    parts = urlsplit(url)
    query = parse_qs(parts.query)
    identifier = definition["source_key"]
    values, seen = {}, set()
    if parts.hostname == "api.stlouisfed.org" and query.get("series_id") == [identifier]:
        payload = json.loads(body, parse_float=Decimal)
        rows = payload["observations"]
        if not isinstance(rows, list) or payload.get("offset", 0) != 0 or payload.get("count", len(rows)) != len(rows):
            raise EvidenceError("source_truncated")
        pairs = [(row["date"], row["value"]) for row in rows]
    elif parts.hostname == "fred.stlouisfed.org" and query.get("id") == [identifier]:
        rows = csv.DictReader(io.StringIO(body))
        if not rows.fieldnames or identifier not in rows.fieldnames:
            raise EvidenceError("source_identity_mismatch")
        time = "observation_date" if "observation_date" in rows.fieldnames else "DATE"
        pairs = [(row[time], row[identifier]) for row in rows]
    elif parts.hostname == "fred.stlouisfed.org" and parts.path == "/data/"+identifier and not query:
        pairs = _fred_public_table_rows(body,identifier)
    else:
        # Unrecognized transports remain archived without an invented selector.
        raise EvidenceError("source_transport_reconciliation_unsupported")
    for label, value in pairs:
        _add(values, seen, _native_period(label, definition["frequency"]), value)
    return values


class _FredOriginalTable(HTMLParser):
    """Independent selector of original semantic tables and hidden native rows."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables=[]
        self.current=None
        self.row=None
        self.cell=None
        self.extra=[]
        self.extra_depth=0
        self.extra_containers=0
        self.caption=None

    def handle_starttag(self,tag,attrs):
        attributes=dict(attrs)
        if tag=='div':
            if attributes.get('id')=='extra-rows':
                if self.extra_depth: raise ValueError('nested hidden observations')
                self.extra_containers+=1
                self.extra_depth=1
            elif self.extra_depth:
                self.extra_depth+=1
        if tag=='table':
            if self.current is not None: raise ValueError('nested source table')
            self.current={'id':attributes.get('id'),'rows':[],'caption':''}
        elif tag=='caption' and self.current is not None:
            self.caption=[]
        elif tag=='tr' and self.current is not None:
            if self.row is not None: raise ValueError('nested source row')
            self.row=[]
        elif tag in ('td','th') and self.row is not None:
            if self.cell is not None: raise ValueError('nested source cell')
            self.cell=[]

    def handle_data(self,value):
        if self.cell is not None: self.cell.append(value)
        if self.caption is not None: self.caption.append(value)
        if self.extra_depth: self.extra.append(value)

    def handle_endtag(self,tag):
        if tag=='div' and self.extra_depth: self.extra_depth-=1
        if tag=='caption' and self.caption is not None:
            self.current['caption']=' '.join(''.join(self.caption).split())
            self.caption=None
        if tag in ('td','th') and self.cell is not None:
            self.row.append(''.join(self.cell).strip())
            self.cell=None
        elif tag=='tr' and self.row is not None:
            if self.cell is not None: raise ValueError('unclosed source cell')
            self.current['rows'].append(self.row)
            self.row=None
        elif tag=='table' and self.current is not None:
            if self.row is not None: raise ValueError('unclosed source row')
            self.tables.append(self.current)
            self.current=None


def _fred_public_table_rows(body,identifier):
    """Require exact series metadata and every visible/hidden DATE/VALUE row.

    FRED renders the first 1,000 source rows as a table and keeps the remainder
    in #extra-rows. Reading only the table would silently truncate long series.
    This selector never calls the provider's HTML parser or executes scripts.
    """
    from .source_reconciliation import EvidenceError
    parser=_FredOriginalTable()
    try:
        parser.feed(body)
        parser.close()
        if parser.current is not None or parser.row is not None or parser.cell is not None or parser.extra_depth:
            raise ValueError('unclosed source structure')
        identities=[row for table in parser.tables for row in table['rows']
                    if row and row[0]=='Series ID']
        if identities!=[['Series ID',identifier]]:
            raise EvidenceError('source_identity_mismatch')
        tables=[table['rows'] for table in parser.tables if table['id']=='data-table-observations']
        if (len(tables)!=1 or not tables[0] or tables[0][0]!=['DATE','VALUE']
                or any(len(row)!=2 for row in tables[0]) or parser.extra_containers!=1):
            raise ValueError('native table identity')
        pairs=[tuple(row) for row in tables[0][1:]]
        extra=''.join(parser.extra).strip()
        if extra:
            if not extra.startswith('#'): raise ValueError('hidden native row prefix')
            for chunk in extra.split('#')[1:]:
                match=re.fullmatch(r'(\d{4}-\d{2}-\d{2})\|\s*([^\s|#]+)',chunk.strip())
                if not match: raise ValueError('hidden native row schema')
                pairs.append(match.groups())
        return pairs
    except EvidenceError:
        raise
    except ValueError:
        raise EvidenceError('source_schema_invalid') from None


def _world_bank(payload, definition):
    from .source_reconciliation import EvidenceError
    country, indicator = definition["source_key"].split("/", 1)
    if (not isinstance(payload, list) or len(payload) != 2 or payload[0].get("pages") != 1
            or not isinstance(payload[1], list)):
        raise EvidenceError("source_truncated")
    values, seen = {}, set()
    for row in payload[1]:
        if (row["indicator"]["id"] != indicator
                or (row.get("countryiso3code") or row["country"]["id"]) != country):
            raise EvidenceError("source_identity_mismatch")
        _add(values, seen, _native_period(row["date"], "A"), row["value"])
    return values


# Approved ECB data-portal series: dataset, native frequency, catalogue unit,
# expected SDMX dimension columns, permitted native unit codes, currency.
_ECB_SERIES = {
    'FM.D.U2.EUR.4F.KR.DFR.LEV': ('FM', 'D', 'percent',
        {'FREQ': 'D', 'REF_AREA': 'U2', 'CURRENCY': 'EUR', 'UNIT_MULT': '0'}, {'PCPA', 'PC'}, 'EUR'),
    'ICP.M.U2.N.000000.4.INX': ('ICP', 'M', 'index',
        {'FREQ': 'M', 'REF_AREA': 'U2', 'ADJUSTMENT': 'N', 'ICP_ITEM': '000000',
         'STS_INSTITUTION': '4', 'ICP_SUFFIX': 'INX'}, None, None),
    'YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y': ('YC', 'D', 'percent',
        {'FREQ': 'B', 'REF_AREA': 'U2', 'CURRENCY': 'EUR', 'DATA_TYPE_FM': 'SR_10Y'}, None, 'EUR'),
    **{f'EXR.D.{cur}.EUR.SP00.A': ('EXR', 'D', 'currency_per_eur',
        {'FREQ': 'D', 'CURRENCY': cur, 'CURRENCY_DENOM': 'EUR', 'EXR_TYPE': 'SP00', 'EXR_SUFFIX': 'A'},
        None, None) for cur in ('USD', 'JPY', 'GBP', 'CHF')},
}
ECB_DATASETS = frozenset(item[0] for item in _ECB_SERIES.values())


def _ecb(body,definition,url,start=None):
    from .source_reconciliation import EvidenceError
    from urllib.parse import urlsplit,parse_qs
    parts=urlsplit(url)
    key=definition['source_key']
    if key not in _ECB_SERIES:
        raise EvidenceError('source_identity_mismatch')
    dataset,frequency,unit_name,dimensions,unit_codes,currency=_ECB_SERIES[key]
    if (parts.scheme!='https' or parts.netloc!='data-api.ecb.europa.eu'
            or parts.path!='/service/data/'+dataset+'/'+key[len(dataset)+1:]
            or parse_qs(parts.query)!={'format':['csvdata'],**({'startPeriod':[start]} if start else {})}
            or definition['frequency']!=frequency or definition['unit']!=unit_name):
        raise EvidenceError('source_identity_mismatch')
    rows=csv.DictReader(io.StringIO(body))
    if not rows.fieldnames or not {'KEY','TIME_PERIOD','OBS_VALUE'}<=set(rows.fieldnames):
        raise EvidenceError('source_schema_invalid')
    values,seen={},set()
    native_units=set()
    publisher_metadata={field:set() for field in ('TITLE','TITLE_COMPL','COMPILATION','COVERAGE','SOURCE_AGENCY','SOURCE_PUB')}
    for row in rows:
        if row['KEY']!=key or any(row.get(field,expected)!=expected for field,expected in dimensions.items()):
            raise EvidenceError('source_identity_mismatch')
        unit=row.get('UNIT') or row.get('UNIT_MEASURE')
        if unit:
            if unit_codes is not None and unit not in unit_codes: raise EvidenceError('source_identity_mismatch')
            native_units.add(unit)
        for field,reported in publisher_metadata.items():
            if row.get(field): reported.add(row[field])
        _add(values,seen,_native_period(row['TIME_PERIOD'],frequency),row['OBS_VALUE'])
    metadata={'source_native_unit':unit_name,
        'source_native_unit_codes':sorted(native_units),'source_key':key,
        'source_publisher_metadata':{field:sorted(values) for field,values in publisher_metadata.items() if values},
        'individual_observation_first_publication_verified':False}
    if currency is not None:
        metadata['source_currency']=currency
    return values,metadata


def _imf_mapper(payload,definition,url):
    from .source_reconciliation import EvidenceError
    area,indicator=definition['source_key'].split('/',1)
    if (url!='https://www.imf.org/external/datamapper/api/v2/'+indicator
            or definition['frequency']!='A' or definition['unit']!='percent'
            or set(payload['values'])-{indicator,''}
            or ('' in payload['values'] and payload['values'][''] is not None)
            or not isinstance(payload['values'][indicator][area],dict)):
        raise EvidenceError('source_identity_mismatch')
    metadata=payload['indicators'][indicator]
    expected_units={'BCA_NGDPD':'Percent of GDP','GGXWDG_NGDP':'Percent of GDP','PCPIPCH':'Annual percent change',
                    'NGDP_RPCH':'Annual percent change'}
    projection=metadata['projection-year']
    if (indicator not in expected_units or metadata['unit']!=expected_units[indicator]
            or metadata['dataset']!='WEO' or not isinstance(projection,int)
            or not 1980<=projection<=date.today().year+1):
        raise EvidenceError('source_identity_mismatch')
    values,seen={},set()
    for year,value in payload['values'][indicator][area].items():
        if not re.fullmatch(r'[0-9]{4}',year): raise EvidenceError('source_period_invalid')
        # WEO's endpoint does not give a final/estimate flag for each point.
        # Prior calendar years remain published estimates; current/projection
        # years are excluded without calling them first-release observations.
        if int(year)>=min(date.today().year,projection): continue
        _add(values,seen,_native_period(year,'A'),value)
    return values,{'source_native_unit':'percent','source_native_unit_label':metadata['unit'],
        'source_database_vintage':metadata['source'],'source_dataset':'WEO',
        'source_projection_start_year':projection,'source_metadata_last_modified':metadata['last-modified'],
        'individual_observation_first_publication_verified':False}


def _bea_q(body,definition,url):
    from .source_reconciliation import EvidenceError
    from .remaining_sources import BEA_Q_URL
    keys={'BEA_2026_TABLE_E_Q1':1,'BEA_2026_TABLE_E_Q2':2,'BEA_2026_TABLE_E_Q3':3}
    if (url!=BEA_Q_URL or definition['source_key'] not in keys
            or definition['frequency']!='A' or definition['unit']!='ratio'
            or 'Q-Type Ratios' not in body or 'produced assets' not in body):
        raise EvidenceError('source_identity_mismatch')
    parser=_FredOriginalTable();parser.feed(body);parser.close()
    tables=[]
    for table in parser.tables:
        rows=table['rows']
        if (rows and len(rows[0])==4 and all(rows[0][column].upper().startswith('Q'+str(column)) for column in (1,2,3))
                and any(row and row[0]=='1960' for row in rows[1:])):
            tables.append(rows)
    if len(tables)!=1: raise EvidenceError('source_identity_mismatch')
    values,seen={},set()
    column=keys[definition['source_key']]
    for row in tables[0][1:]:
        if len(row)!=4 or not re.fullmatch(r'[0-9]{4}',row[0]): raise EvidenceError('source_schema_invalid')
        # The three different published ratios are selected, never recomputed.
        try:
            numbers=[Decimal(value.replace(',','')) for value in row[1:]]
        except InvalidOperation:
            raise EvidenceError('source_value_invalid') from None
        if any(not number.is_finite() or number<=0 for number in numbers): raise EvidenceError('source_value_invalid')
        _add(values,seen,_native_period(row[0],'A'),numbers[column-1])
    if not values or min(values)!=date(1960,1,1) or len(values)!=max(values).year-1959:
        raise EvidenceError('source_truncated')
    return values


def _bea_table_row(body,definition,url):
    """One published row of BEA's returns article Tables A/B (2004-2014 and 2015-2024 parts)."""
    from .source_reconciliation import EvidenceError
    from .remaining_sources import BEA_Q_URL
    selectors={'BEA_2026_TABLE_B_NFC_PRODUCED_ASSETS':('Table B. Produced Assets of Domestic Nonfinancial Corporations','Nonfinancial corporations'),
               'BEA_2026_TABLE_A_NFC_NET_OPERATING_SURPLUS':('Table A. Net Operating Surplus of Domestic Nonfinancial Corporations','Nonfinancial corporations')}
    if (url!=BEA_Q_URL or definition['source_key'] not in selectors or definition['frequency']!='A'
            or definition['unit']!='billion_usd'):
        raise EvidenceError('source_identity_mismatch')
    caption,label=selectors[definition['source_key']]
    parser=_FredOriginalTable();parser.feed(body);parser.close()
    parts=[t['rows'] for t in parser.tables if t['caption'].startswith(caption) and '[Billions of dollars]' in body]
    if len(parts)!=2: raise EvidenceError('source_identity_mismatch')
    values,seen={},set()
    for rows in parts:
        header=rows[0]
        if not header or header[0]!='' or not all(re.fullmatch(r'[0-9]{4}',year) for year in header[1:]):
            raise EvidenceError('source_schema_invalid')
        matches=[row for row in rows[1:] if row and row[0]==label]
        if len(matches)!=1 or len(matches[0])!=len(header): raise EvidenceError('source_schema_invalid')
        for year,cell in zip(header[1:],matches[0][1:]):
            try:
                number=Decimal(cell.replace(',','').replace('\u2212','-'))
            except InvalidOperation:
                raise EvidenceError('source_value_invalid') from None
            _add(values,seen,_native_period(year,'A'),number)
    years=sorted(day.year for day in values)
    if years!=list(range(years[0],years[-1]+1)): raise EvidenceError('source_truncated')
    return values


def _workbook_rows(raw,sheet):
    from .source_reconciliation import EvidenceError
    from python_calamine import CalamineWorkbook
    if len(raw)>15_000_000 or not raw.startswith((b'PK\x03\x04',bytes.fromhex('D0CF11E0A1B11AE1'))):
        raise EvidenceError('source_schema_invalid')
    try:
        # Calamine reads cached native workbook cells. No provider selector,
        # spreadsheet recalculation, scripts or external links are invoked.
        return CalamineWorkbook.from_filelike(io.BytesIO(raw)).get_sheet_by_name(sheet).to_python()
    except Exception:
        raise EvidenceError('source_schema_invalid') from None


def _pink_sheet(raw,definition,url):
    from .source_reconciliation import EvidenceError
    from .provider_parsers import PINK_SHEET_URL
    selectors={
        'CMO-Historical-Data-Monthly.xlsx#Monthly Prices:Gold':('Gold','troy oz','usd_per_oz'),
        'CMO-Historical-Data-Monthly.xlsx#Monthly Prices:Crude oil, Brent':('Crude oil, Brent','bbl','usd_per_barrel'),
        'CMO-Historical-Data-Monthly.xlsx#Monthly Prices:Natural gas, US':('Natural gas, US','mmbtu','usd_per_mmbtu'),
        'CMO-Historical-Data-Monthly.xlsx#Monthly Prices:Maize':('Maize','mt','usd_per_metric_ton')}
    if url!=PINK_SHEET_URL or definition['source_key'] not in selectors or definition['frequency']!='M':
        raise EvidenceError('source_identity_mismatch')
    label,unit,native_unit=selectors[definition['source_key']]
    if definition['unit']!=native_unit: raise EvidenceError('source_identity_mismatch')
    rows=_workbook_rows(raw,'Monthly Prices')
    headers=[(r,c) for r,row in enumerate(rows[:15]) for c,value in enumerate(row) if str(value).strip()==label]
    if len(headers)!=1: raise EvidenceError('source_identity_mismatch')
    header,column=headers[0]
    unit_label=str(rows[header+1][column]).strip()
    if unit_label.lower() != f'($/{unit})': raise EvidenceError('source_identity_mismatch')
    values,seen={},set()
    for row in rows[header+2:]:
        period=str(row[0]).strip() if row else ''
        if not re.fullmatch(r'[0-9]{4}M(?:0[1-9]|1[0-2])',period): continue
        day=_native_period(period[:4]+'-'+period[-2:],'M')
        _add(values,seen,day,row[column] if len(row)>column else None)
        if day in values and values[day]<=0: raise EvidenceError('source_value_invalid')
    return values,{'source_native_unit':native_unit,'source_native_unit_label':unit_label,
                   'source_currency':'USD','source_sheet':'Monthly Prices','source_variable':label}


class _OriginalWorkbookLinks(HTMLParser):
    def __init__(self):
        super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':
            href=dict(attrs).get('href','')
            if 'ie_data.xls' in href.lower(): self.links.append(href)


def _shiller(raw,definition,homepage,homepage_url,workbook_url, *, return_metadata=False):
    from .source_reconciliation import EvidenceError
    from .source_capture import safe_url
    from urllib.parse import urljoin,urlsplit
    selectors = {'ie_data.xls#Data:CAPE': ('CAPE', 'ratio'),
                 'ie_data.xls#Data:P': ('S&P COMP. P', 'index'),
                 'ie_data.xls#Data:D': ('DIVIDEND D', 'index'),
                 'ie_data.xls#Data:E': ('EARNINGS E', 'index'),
                 'ie_data.xls#Data:CPI': ('CONSUMER PRICE INDEX CPI', 'index'),
                 'ie_data.xls#Data:REAL_TR_PRICE': ('REAL TOTAL RETURN PRICE', 'index')}
    key = definition['source_key']
    if (key not in selectors or definition['unit']!=selectors[key][1]
            or definition['frequency']!='M' or homepage_url not in {'https://shillerdata.com/','https://www.shillerdata.com/'}):
        raise EvidenceError('source_identity_mismatch')
    links=_OriginalWorkbookLinks();links.feed(homepage);links.close()
    if (len(links.links)!=1 or safe_url(urljoin(homepage_url,links.links[0]))!=workbook_url
            or urlsplit(workbook_url).hostname not in {'img1.wsimg.com','shillerdata.com','www.econ.yale.edu'}):
        raise EvidenceError('source_identity_mismatch')
    rows=_workbook_rows(raw,'Data')
    width=max(len(row) for row in rows[:20])
    headings=[' '.join(str(row[column]).strip() for row in rows[:20]
                      if len(row)>column and isinstance(row[column],str) and row[column].strip()).upper()
              for column in range(width)]
    dates=[column for column,label in enumerate(headings) if re.search(r'\bDATE\b',label) and 'FRACTION' not in label]
    capes=[column for column,label in enumerate(headings) if 'CYCLICALLY ADJUSTED' in label
           and 'CAPE' in label and not any(excluded in label for excluded in ('TOTAL RETURN','TR CAPE','EXCESS'))]
    if key != 'ie_data.xls#Data:CAPE':
        capes=[column for column,label in enumerate(headings) if label == selectors[key][0]]
    if len(dates)!=1 or len(capes)!=1: raise EvidenceError('source_identity_mismatch')
    date_col,cape_col=dates[0],capes[0]
    values,seen={},set()
    for row in rows:
        if len(row)<=date_col or not isinstance(row[date_col],(int,float,Decimal)): continue
        stamp=Decimal(str(row[date_col]));year=int(stamp)
        if not 1870<=year<=date.today().year: continue
        month_value=(stamp-year)*100;month=int(month_value.to_integral_value())
        if abs(month_value-month)>Decimal('0.000001') or not 1<=month<=12:
            raise EvidenceError('source_period_invalid')
        day=_native_period(f'{year:04d}-{month:02d}','M')
        _add(values,seen,day,row[cape_col] if len(row)>cape_col else None)
        if day in values and values[day]<=0 and key not in {'ie_data.xls#Data:E', 'ie_data.xls#Data:D'}:
            raise EvidenceError('source_value_invalid')
    if not values or min(values)>date(1882,1,1): raise EvidenceError('source_truncated')
    expected=(max(values).year-min(values).year)*12+max(values).month-min(values).month+1
    if len(values)<expected*Decimal('0.9'): raise EvidenceError('source_truncated')
    variable = key.split(':')[-1]
    basis = {'CAPE': 'ratio_to_trailing_real_earnings', 'P': 'nominal',
             'D': 'nominal_annual_per_index_unit', 'E': 'nominal_annual_per_index_unit',
             'CPI': 'consumer_price_index', 'REAL_TR_PRICE': 'real_cpi_deflated'}
    metadata = {'source_sheet': 'Data', 'source_variable': variable,
        'source_population': ('US consumer-price basket and source historical extensions' if variable == 'CPI'
                              else 'Shiller US S&P Composite historical sample'),
        'source_price_basis': basis[variable],
        **({'source_author_constructed': True} if variable in {'CAPE', 'D', 'E', 'REAL_TR_PRICE'} else {}),
        'source_workbook_notes': [str(cell).strip() for row in rows for cell in row
                                  if isinstance(cell,str) and any(word in cell.lower()
                                  for word in ('estimated', 'close', 'value'))],
        'individual_observation_first_publication_verified': False}
    return (values, metadata) if return_metadata else values


def _bis(payload, definition):
    from .source_reconciliation import EvidenceError
    provider = definition["provider"]
    source_key = definition["source_key"].split("/", 1)[-1]
    if provider == 'BIS':
        names=('FREQ','REF_AREA')
        if (definition['frequency']!='D' or definition['unit']!='percent'
                or definition['source_key'] not in {'BIS,WS_CBPOL,1.0/D.US','BIS,WS_CBPOL,1.0/D.XM','BIS,WS_CBPOL,1.0/D.JP'}):
            raise EvidenceError('source_identity_mismatch')
    elif provider == "BIS_DSR":
        names = ("FREQ", "BORROWERS_CTY", "DSR_BORROWERS")
    elif provider == "BIS_TOTAL_CREDIT":
        names = ("FREQ", "BORROWERS_CTY", "TC_BORROWERS", "TC_LENDERS", "VALUATION", "UNIT_TYPE", "TC_ADJUST")
    elif provider == "BIS_CREDIT_GAP":
        names = ("FREQ", "BORROWERS_CTY", "TC_BORROWERS", "TC_LENDERS", "CG_DTYPE")
    elif provider == "BIS_PROPERTY":
        names = (("FREQ", "REF_AREA", "VALUE", "UNIT_MEASURE") if len(source_key.split(".")) == 4 else
                 ("FREQ", "REF_AREA", "COVERED_AREA", "RE_TYPE", "RE_VINTAGE", "COMPILING_ORG", "PRICED_UNIT", "ADJUST_CODED"))
    else:
        raise EvidenceError("source_reconciliation_unsupported")
    expected = dict(zip(names, source_key.split("."), strict=True))
    block = payload["data"]
    structure = block.get("structure", block.get("structures"))
    if isinstance(structure, list):
        if len(structure) != 1:
            raise EvidenceError("source_identity_mismatch")
        structure = structure[0]
    dims = structure["dimensions"]
    if (tuple(d["id"] for d in dims["series"]) != names
            or [d["id"] for d in dims["observation"]] != ["TIME_PERIOD"]):
        raise EvidenceError("source_identity_mismatch")
    def decode(dimensions, key):
        parts = key.split(":")
        if len(parts) != len(dimensions) or any(not part.isdigit() for part in parts):
            raise EvidenceError("source_schema_invalid")
        return {dim["id"]: dim["values"][int(index)]["id"] for dim, index in zip(dimensions, parts)}
    values, seen, matched = {}, set(), 0
    for dataset in block["dataSets"]:
        for key, node in dataset["series"].items():
            actual = decode(dims["series"], key)
            if actual != expected:
                if provider == "BIS_CREDIT_GAP" and all(actual[k] == expected[k] for k in names[:-1]):
                    continue
                raise EvidenceError("source_identity_mismatch")
            matched += 1
            for index, row in node["observations"].items():
                period = decode(dims["observation"], index)["TIME_PERIOD"]
                native_date = _native_period(period, definition["frequency"])
                if not isinstance(row, (list, tuple)) or not row:
                    raise EvidenceError("source_schema_invalid")
                if provider == "BIS_TOTAL_CREDIT" and row[0] not in (None, "", "NaN", "NA", "N/A"):
                    last_month = native_date.month + 2
                    if date(native_date.year, last_month, monthrange(native_date.year, last_month)[1]) > date.today():
                        raise EvidenceError("source_period_invalid")
                _add(values, seen, native_date, row[0])
    if matched != 1:
        raise EvidenceError("source_identity_mismatch")
    return values


def _bis_policy_metadata(payload):
    """Resolve reported units and instrument-splice notes from native attributes."""
    from .source_reconciliation import EvidenceError
    block=payload['data'];structure=block.get('structure',block.get('structures'))
    if isinstance(structure,list):
        if len(structure)!=1: raise EvidenceError('source_identity_mismatch')
        structure=structure[0]
    attributes=structure['attributes']
    if len(block['dataSets'])!=1: raise EvidenceError('source_identity_mismatch')
    dataset=block['dataSets'][0]
    def selected(definitions,indices):
        if len(definitions)!=len(indices): raise EvidenceError('source_schema_invalid')
        output={}
        for definition,index in zip(definitions,indices):
            if index is None: continue
            if not isinstance(index,int) or index<0: raise EvidenceError('source_schema_invalid')
            if definition['id'] in output: raise EvidenceError('source_identity_mismatch')
            output[definition['id']]=definition['values'][index]
        return output
    native=selected(attributes['dataset'],dataset['attributes'])
    if native['UNIT_MEASURE']['id']!='368' or native['UNIT_MULT']['id']!='0':
        raise EvidenceError('source_identity_mismatch')
    if len(dataset['series'])!=1: raise EvidenceError('source_identity_mismatch')
    node=next(iter(dataset['series'].values()))
    details=selected(attributes['series'],node['attributes'])
    return {'source_native_unit':'percent','source_native_unit_code':'368',
        'source_native_unit_label':native['UNIT_MEASURE']['name'],'source_unit_multiplier':'0',
        'source_publisher_metadata':{key:value['id'] for key,value in details.items()
                                     if key in {'COMPILATION','SOURCE_REF','TITLE','SUPP_INFO_BREAKS'}},
        'source_response_prepared_at':payload.get('meta',{}).get('prepared'),
        'individual_observation_first_publication_verified':False}


def _bis_credit_metadata(payload,definition):
    """Check the reported unit and multiplier of the one selected total-credit series."""
    from .source_reconciliation import EvidenceError
    block=payload['data'];structure=block.get('structure',block.get('structures'))
    if isinstance(structure,list):
        if len(structure)!=1: raise EvidenceError('source_identity_mismatch')
        structure=structure[0]
    nodes=list(block['dataSets'][0]['series'].values())
    if len(nodes)!=1: raise EvidenceError('source_identity_mismatch')
    declarations=structure['attributes']['series']
    indexes=nodes[0]['attributes']
    if len(declarations)!=len(indexes): raise EvidenceError('source_schema_invalid')
    selected={}
    for attribute,index in zip(declarations,indexes):
        if index is None: continue
        if type(index) is not int or index<0 or attribute['id'] in selected:
            raise EvidenceError('source_schema_invalid')
        try:
            selected[attribute['id']]=attribute['values'][index]['id']
        except (IndexError,KeyError,TypeError,ValueError) as exc:
            raise EvidenceError('source_schema_invalid') from exc
    stock=definition['source_key'].split('.')[-2]=='XDC'
    if (selected.get('UNIT_MEASURE')!=(definition.get('currency') if stock else '367')
            or selected.get('UNIT_MULT')!=('9' if stock else '0')):
        raise EvidenceError('source_identity_mismatch')
    return {'source_native_unit':definition['unit'],'source_native_unit_code':selected['UNIT_MEASURE'],
        'source_unit_multiplier':selected['UNIT_MULT'],'source_decimals':selected.get('DECIMALS'),
        **({'source_currency':selected['UNIT_MEASURE']} if stock else {}),
        'source_response_prepared_at':payload.get('meta',{}).get('prepared'),
        'individual_observation_first_publication_verified':False}


def _g17_diffusion(body,definition,url):
    """Fixed-width column slicing; a blank cell is a missing month, never shifted."""
    from .source_reconciliation import EvidenceError
    spans={'DIFFUSION_1':'one month earlier','DIFFUSION_3':'three months earlier','DIFFUSION_6':'six months earlier'}
    block=definition['source_key'].rsplit('#',1)[-1]
    if (url!='https://www.federalreserve.gov/Releases/G17/Current/ipdisk/diff_sa.txt' or block not in spans
            or definition['source_key']!='diff_sa.txt#'+block or definition['frequency']!='M'
            or definition['unit']!='index'):
        raise EvidenceError('source_identity_mismatch')
    lines=body.splitlines()
    starts=[i for i,line in enumerate(lines) if line.strip()=='"%s: Diffusion index of industrial production, %s"'%(block,spans[block])]
    if len(starts)!=1: raise EvidenceError('source_identity_mismatch')
    values,seen,rows=({},set(),0)
    for line in lines[starts[0]+1:]:
        if not line.strip(): continue
        if line.strip().startswith('"DIFFUSION_') and ':' in line: break
        year=line[13:23].strip()
        if line[:13]!='"%s"'%block or len(line.rstrip())>143 or not re.fullmatch(r'\d{4}',year):
            raise EvidenceError('source_schema_invalid')
        rows+=1
        for month in range(12):
            cell=line[23+10*month:33+10*month].strip()
            if not cell: continue
            day=date(int(year),month+1,1)
            if day>date.today(): raise EvidenceError('source_period_invalid')
            _add(values,seen,day,cell)
            if day in values and not 0<=values[day]<=100: raise EvidenceError('source_value_invalid')
    if not rows: raise EvidenceError('source_empty')
    return values,{'source_native_unit':'index','source_publisher_metadata':{
        'definition':'percentage of series that increased over the span plus one-half of the unchanged','span':spans[block]},
        'source_seasonal_adjustment':'seasonally adjusted','individual_observation_first_publication_verified':False}


def _ofr_fsi(body,definition,url):
    from .source_reconciliation import EvidenceError
    columns=['OFR FSI','Credit','Equity valuation','Safe assets','Funding','Volatility',
             'United States','Other advanced economies','Emerging markets']
    column=definition['source_key'].partition('#')[2]
    if (url!='https://www.financialresearch.gov/financial-stress-index/data/fsi.csv'
            or definition['source_key']!='fsi.csv#'+column or column not in columns
            or definition['frequency']!='D' or definition['unit']!='index'):
        raise EvidenceError('source_identity_mismatch')
    rows=list(csv.reader(io.StringIO(body)))
    if not rows or rows[0]!=['Date']+columns: raise EvidenceError('source_identity_mismatch')
    position=rows[0].index(column)
    values,seen=({},set())
    categories=regions=0
    for row in rows[1:]:
        if len(row)!=len(rows[0]): raise EvidenceError('source_schema_invalid')
        _add(values,seen,_native_period(row[0],'D'),row[position])
        total=Decimal(row[1])
        categories+=abs(sum(Decimal(v) for v in row[2:7])-total)>Decimal('0.003')
        regions+=abs(sum(Decimal(v) for v in row[7:10])-total)>Decimal('0.002')
    return values,{'source_native_unit':'standardized_index','source_publisher_metadata':{
        'scale':'zero is average stress; positive above average','frequency':'business days',
        'published_decimals':3,'category_partition_rows_beyond_rounding':categories,
        'region_partition_rows_beyond_rounding':regions},
        'individual_observation_first_publication_verified':False}


def _boj(body,definition,url):
    from .source_reconciliation import EvidenceError
    codes={"FM01'STRDCLUCON":('fm01_d_1_en',0,'D'),"FM02'STRECLUCON":('fm02_m_1_en',0,'M'),
           "FM02'STRACLUCON":('fm02_m_1_en',1,'M')}
    spec=codes.get(definition['source_key'])
    if (spec is None or url!='https://www.stat-search.boj.or.jp/ssi/mtshtml/csv/%s.csv'%spec[0]
            or definition['frequency']!=spec[2] or definition['unit']!='percent'):
        raise EvidenceError('source_identity_mismatch')
    rows=list(csv.reader(io.StringIO(body)))
    named={row[0]:row for row in rows if row and row[0] in ('Series code','Unit','Name of time-series')}
    column=spec[1]+1
    if (len(named)!=3 or named['Series code'][column]!=definition['source_key']
            or named['Unit'][column]!='percent per annum'):
        raise EvidenceError('source_identity_mismatch')
    pattern=r'\d{4}/\d{2}/\d{2}' if spec[2]=='D' else r'\d{4}/\d{2}'
    values,seen=({},set())
    for row in rows:
        if row and re.fullmatch(pattern,row[0]):
            if len(row)!=len(named['Series code']): raise EvidenceError('source_schema_invalid')
            _add(values,seen,_native_period(row[0].replace('/','-'),spec[2]),row[column])
    return values,{'source_native_unit':'percent','source_native_unit_label':named['Unit'][column],
        'source_publisher_metadata':{'series_code':definition['source_key'],'name':named['Name of time-series'][column]},
        'individual_observation_first_publication_verified':False}


def _oecd_cli(body,definition,url):
    from .source_reconciliation import EvidenceError
    key=definition['source_key']
    flow,_,series=key.partition('/')
    if (flow!='OECD.SDD.STES,DSD_STES@DF_CLI,4.1'
            or url!='https://sdmx.oecd.org/public/rest/data/%s/%s?format=csvfile'%(flow,series)
            or definition['frequency']!='M' or definition['unit']!='index'):
        raise EvidenceError('source_identity_mismatch')
    names=('REF_AREA','FREQ','MEASURE','UNIT_MEASURE','ACTIVITY','ADJUSTMENT','TRANSFORMATION','TIME_HORIZ','METHODOLOGY')
    expected=dict(zip(names,series.split('.'),strict=True))
    if expected['MEASURE']!='LI' or expected['ADJUSTMENT'] not in ('AA','TR'): raise EvidenceError('source_identity_mismatch')
    rows=csv.DictReader(io.StringIO(body))
    values,seen=({},set())
    decimals=set()
    for row in rows:
        if (row['DATAFLOW']!='OECD.SDD.STES:DSD_STES@DF_CLI(4.1)' or row['UNIT_MULT']!='0'
                or any(row[name]!=value for name,value in expected.items()) or row['OBS_STATUS']!='A'):
            raise EvidenceError('source_identity_mismatch')
        decimals.add(row['DECIMALS'])
        _add(values,seen,_native_period(row['TIME_PERIOD'],'M'),row['OBS_VALUE'])
    return values,{'source_native_unit':'index','source_dataset':'OECD DSD_STES@DF_CLI',
        'source_database_vintage':'dataflow version 4.1','source_decimals':sorted(decimals),
        'source_publisher_metadata':{'adjustment':{'AA':'amplitude adjusted (average 100)','TR':'trend restored'}[expected['ADJUSTMENT']],
            'methodology':'OECD harmonised'},'individual_observation_first_publication_verified':False}


def _imf_bop_iip(raw,definition,url):
    """Regex attribute scan of the structure-specific XML, independent of the ElementTree provider."""
    from .source_reconciliation import EvidenceError
    key=definition['source_key']
    flow_id,_,series=key.partition('/')
    agency,flow,version=flow_id.split(',')
    country,_,rest=series.partition('..')
    indicator,unit,frequency=rest.split('.')
    entries={'CAB':'NETCD_T','NIIP':'NETAL_P'}
    if (agency!='IMF.STA' or (flow,indicator) not in (('BOP','CAB'),('IIP','NIIP')) or unit!='USD' or frequency!='A'
            or url!='https://api.imf.org/external/sdmx/2.1/data/%s/%s'%(flow_id,series)
            or definition['frequency']!='A' or definition['unit']!='usd'):
        raise EvidenceError('source_identity_mismatch')
    text=raw.decode('utf-8-sig')
    blocks=re.findall(r'<Series\s([^>]*)>(.*?)</Series>',text,flags=re.S)
    if len(blocks)!=1: raise EvidenceError('source_identity_mismatch')
    attributes=dict(re.findall(r'(\w+)="([^"]*)"',blocks[0][0]))
    if (attributes.get('COUNTRY')!=country or attributes.get('BOP_ACCOUNTING_ENTRY')!=entries[indicator]
            or attributes.get('INDICATOR')!=indicator or attributes.get('UNIT')!='USD'
            or attributes.get('FREQUENCY')!='A' or attributes.get('METHODOLOGY')!='BPM6'):
        raise EvidenceError('source_identity_mismatch')
    values,seen=({},set())
    derivations=set()
    for observation in re.findall(r'<Obs\s([^>]*?)/>',blocks[0][1]):
        fields=dict(re.findall(r'(\w+)="([^"]*)"',observation))
        derivations.add(fields.get('DERIVATION_TYPE'))
        _add(values,seen,_native_period(fields['TIME_PERIOD'],'A'),fields.get('OBS_VALUE'))
    return values,{'source_native_unit':'usd','source_currency':'USD','source_variable':indicator,
        'source_price_basis':'flow' if indicator=='CAB' else 'end_period_stock',
        'source_publisher_metadata':{'methodology':'BPM6','accounting_entry':attributes['BOP_ACCOUNTING_ENTRY'],
            'overlap':attributes.get('OVERLAP'),'scale':attributes.get('SCALE'),
            'derivation_types':sorted(item for item in derivations if item)},
        'source_dataset':flow_id,'individual_observation_first_publication_verified':False}


def _fdic(payload,definition,url):
    from .source_reconciliation import EvidenceError
    from urllib.parse import urlsplit,parse_qs
    field=definition['source_key'].partition('#')[2]
    parts=urlsplit(url)
    query=parse_qs(parts.query)
    if (parts.scheme!='https' or parts.netloc!='api.fdic.gov' or parts.path!='/banks/financials'
            or definition['source_key']!='financials?agg_by=REPDTE#'+field or field not in ('sum_ASSET','sum_EQ','count')
            or query.get('agg_by')!=['REPDTE'] or query.get('agg_sum_fields')!=['ASSET,EQ']
            or definition['frequency']!='Q' or definition['unit']!=('count' if field=='count' else 'thousand_usd')):
        raise EvidenceError('source_identity_mismatch')
    meta=payload['meta']['parameters']['aggsMetaData']
    rows=payload['data']
    if meta['by']!='REPDTE' or not rows or len(rows)>=int(query['agg_limit'][0]): raise EvidenceError('source_truncated')
    values,seen=({},set())
    counts=[]
    for row in rows:
        match=re.fullmatch(r'(\d{4})(03|06|09|12)(30|31)',row['data']['REPDTE'])
        if not match: raise EvidenceError('source_period_invalid')
        year, month, reported_day = map(int, match.groups())
        if reported_day != monthrange(year, month)[1]:
            raise EvidenceError('source_period_invalid')
        if date(year, month, reported_day) > date.today():
            raise EvidenceError('source_period_invalid')
        counts.append(int(row['data']['count']))
        _add(values,seen,date(year,month-2,1),row['data'][field])
    return values,{'source_native_unit':definition['unit'],'source_currency':None if field=='count' else 'USD',
        'source_publisher_metadata':{'perimeter':'all institutions reporting financials at each report date',
            'reporting_institutions_first':counts[0],'reporting_institutions_last':counts[-1],
            'reporting_institutions_minimum':min(counts),'reporting_institutions_maximum':max(counts)},
        'individual_observation_first_publication_verified':False}
