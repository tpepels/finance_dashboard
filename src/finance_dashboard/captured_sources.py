"""Independent selectors for archived native publisher responses.

This module deliberately does not call provider ingestion parsers. A full
source snapshot is required; an overlap response cannot certify old DB rows.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from html.parser import HTMLParser
import csv
import io
import json
import re

from .source_capture import canonical_bytes


def captured_source(root, definition, select_manifest, original_file):
    from .source_reconciliation import EvidenceError
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
        if manifest.get("scope") != "full_source_snapshot" or manifest.get("requested_from") is not None:
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
            values = _bea_q(body,definition,source['url'])
        elif provider == 'WORLD_BANK_PINK_SHEET':
            values,dimensions = _pink_sheet(raw,definition,source['url'])
        elif provider == 'SHILLER':
            values,dimensions = _shiller(raw,definition,originals[0][0].decode('utf-8-sig'),
                              sources[0]['url'],source['url'], return_metadata=True)
        elif provider == 'ECB':
            values,dimensions = _ecb(body,definition,source['url'])
        else:
            payload=json.loads(body,parse_float=Decimal)
            values = _bis(payload, definition)
            if provider=='BIS': dimensions=_bis_policy_metadata(payload)
        if not values:
            raise EvidenceError("source_empty")
        return values, {"source_sha256": data_hash, "source_manifest_sha256": manifest_hash,
            "evidence_retrieved_at_utc": retrieved.isoformat(), "selection_method": method,
            "source_snapshot_scope": "full_source_snapshot",**dimensions,
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
            self.current={'id':attributes.get('id'),'rows':[]}
        elif tag=='tr' and self.current is not None:
            if self.row is not None: raise ValueError('nested source row')
            self.row=[]
        elif tag in ('td','th') and self.row is not None:
            if self.cell is not None: raise ValueError('nested source cell')
            self.cell=[]

    def handle_data(self,value):
        if self.cell is not None: self.cell.append(value)
        if self.extra_depth: self.extra.append(value)

    def handle_endtag(self,tag):
        if tag=='div' and self.extra_depth: self.extra_depth-=1
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


def _ecb(body,definition,url):
    from .source_reconciliation import EvidenceError
    from urllib.parse import urlsplit,parse_qs
    parts=urlsplit(url)
    key=definition['source_key']
    if (parts.scheme!='https' or parts.netloc!='data-api.ecb.europa.eu'
            or parts.path!='/service/data/FM/'+key[3:]
            or parse_qs(parts.query)!={'format':['csvdata']}
            or key!='FM.D.U2.EUR.4F.KR.DFR.LEV'
            or definition['frequency']!='D' or definition['unit']!='percent'):
        raise EvidenceError('source_identity_mismatch')
    rows=csv.DictReader(io.StringIO(body))
    if not rows.fieldnames or not {'KEY','TIME_PERIOD','OBS_VALUE'}<=set(rows.fieldnames):
        raise EvidenceError('source_schema_invalid')
    values,seen={},set()
    native_units=set()
    publisher_metadata={field:set() for field in ('TITLE','TITLE_COMPL','COMPILATION','COVERAGE','SOURCE_AGENCY','SOURCE_PUB')}
    for row in rows:
        if row['KEY']!=key or any(row.get(field,expected)!=expected for field,expected in (
                ('FREQ','D'),('REF_AREA','U2'),('CURRENCY','EUR'),('UNIT_MULT','0'))):
            raise EvidenceError('source_identity_mismatch')
        unit=row.get('UNIT') or row.get('UNIT_MEASURE')
        if unit:
            if unit not in {'PCPA','PC'}: raise EvidenceError('source_identity_mismatch')
            native_units.add(unit)
        for field,reported in publisher_metadata.items():
            if row.get(field): reported.add(row[field])
        _add(values,seen,_native_period(row['TIME_PERIOD'],'D'),row['OBS_VALUE'])
    return values,{'source_native_unit':'percent','source_currency':'EUR',
        'source_native_unit_codes':sorted(native_units),'source_key':key,
        'source_publisher_metadata':{field:sorted(values) for field,values in publisher_metadata.items() if values},
        'individual_observation_first_publication_verified':False}


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
    from .providers import PINK_SHEET_URL
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
                _add(values, seen, _native_period(period, definition["frequency"]), row[0])
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
