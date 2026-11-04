"""Independent selection of archived academic returns for DB reconciliation.

This reader does not invoke ingestion parsers or trust their normalized values.
It selects the original CSV columns and ODS cached cells after verifying the
immutable bundle, acquisition receipt and original publisher identities.
"""
from __future__ import annotations

import calendar
import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256, sha1, md5
import io
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

from .research_returns import (
    FRENCH_SERIES, FRENCH_DATASETS, FRENCH_ROOT, SWINKELS_SERIES,
    SWINKELS_METADATA, SWINKELS_SHA256, SWINKELS_README_SHA256,
    SWINKELS_DATA_URL, SWINKELS_README_URL, SWINKELS_METADATA_URL,
    SWINKELS_ORIGINAL_METADATA_URL,
)
from .global_market_returns import GLOBAL_MARKET_SERIES, ORIGINAL_SHA256 as GLOBAL_MARKET_SHA256, SOURCE_URL as GLOBAL_MARKET_URL, SOURCE_IDENTITY as GLOBAL_MARKET_IDENTITY

_NS = {'t': 'urn:oasis:names:tc:opendocument:xmlns:table:1.0',
       'o': 'urn:oasis:names:tc:opendocument:xmlns:office:1.0'}
_T, _O = '{'+_NS['t']+'}', '{'+_NS['o']+'}'


def _error(code):
    # Imported here because the shared dispatcher imports this reader.
    from .source_reconciliation import EvidenceError
    return EvidenceError(code)


def _binary(folder, source, name, url, *, maximum=5_000_000):
    try:
        target = folder / name
        if (source['file'] != name or source['url'] != url or target.is_symlink()
                or not target.is_file() or target.stat().st_size > maximum):
            raise _error('source_identity_mismatch')
        raw = target.read_bytes()
        digest = sha256(raw).hexdigest()
        if len(raw) != source['bytes'] or digest != source['sha256']:
            raise _error('source_hash_mismatch')
        return raw, digest
    except (OSError, KeyError, TypeError):
        raise _error('source_file_invalid') from None


def _members(raw):
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or len(names) > 100 or sum(x.file_size for x in archive.infolist()) > 30_000_000:
                raise ValueError('archive limits')
            return {name: archive.read(name) for name in names}
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile):
        raise _error('source_schema_invalid') from None


def _decimal(raw):
    try:
        result = Decimal(raw)
        if not result.is_finite():
            raise InvalidOperation
        return result
    except (InvalidOperation, ValueError, TypeError):
        raise _error('source_value_invalid') from None


def _manifest(parent, identity, select_manifest):
    retrieved, manifest_hash, path, record, selection = select_manifest(parent, identity)
    try:
        raw = path.read_bytes()
        if (path.is_symlink() or path.parent.is_symlink()
                or sha256(raw).hexdigest() != manifest_hash or json.loads(raw) != record
                or selection != 'acquisition_receipt' or retrieved.utcoffset() is None
                or record.get('schema_version') != 1
                or record.get('source_identity') != identity
                or record.get('original_first_publication_at') is not None):
            raise _error('source_identity_mismatch')
        digest = sha256(json.dumps({key: value['sha256'] for key, value in record['sources'].items()}, sort_keys=True).encode()).hexdigest()
        if path.parent.name != digest:
            raise _error('source_hash_mismatch')
    except (OSError, KeyError, TypeError, ValueError):
        raise _error('source_manifest_invalid') from None
    return record, path.parent, {'source_manifest_sha256': manifest_hash,
        'evidence_retrieved_at_utc': retrieved.isoformat(), 'selection_method': selection}


def _french_original(raw, dataset):
    files = _members(raw)
    if set(files) != {dataset+'.csv'}:
        raise _error('source_identity_mismatch')
    try:
        body = files[dataset+'.csv'].decode('utf-8-sig')
        vintage = re.search(r'^This file was created using the ([0-9]{6}) Bloomberg database\.', body)
        if not vintage or 'Missing data are indicated by -99.99.' not in body:
            raise _error('source_identity_mismatch')
        source_vintage = datetime.strptime(vintage[1], '%Y%m').date()
        columns = ['', 'Mkt-RF', 'SMB', 'HML'] + (['RMW', 'CMA'] if dataset=='Emerging_5_Factors' else []) + ['RF']
        rows = list(csv.reader(io.StringIO(body)))
        first = next(i for i, row in enumerate(rows) if [x.strip() for x in row] == columns)
    except (UnicodeError, ValueError, StopIteration, csv.Error):
        raise _error('source_schema_invalid') from None
    output, periods, inputs, missing = {}, {}, {}, {key: 0 for key in columns[1:]}
    for row in rows[first+1:]:
        if not row or not any(x.strip() for x in row):
            if output:
                break
            continue
        try:
            raw_period = row[0].strip()
            if not re.fullmatch(r'[0-9]{6}', raw_period) or len(row) != len(columns):
                raise ValueError('period/column identity')
            period = datetime.strptime(raw_period, '%Y%m').date()
            if period in output or period > date.today() or period > source_vintage:
                raise ValueError('period bounds or duplicate')
        except (TypeError, ValueError):
            raise _error('source_period_invalid') from None
        values = {}
        for variable, raw_value in zip(columns[1:], row[1:]):
            value = _decimal(raw_value.strip())
            if value == Decimal('-99.99'):
                missing[variable] += 1
                value = None
            values[variable] = value
        output[period] = {key: values[key] for key in ('Mkt-RF', 'RF')}
        inputs[period.isoformat()] = {key: str(values[key]) if values[key] is not None else None for key in ('Mkt-RF', 'RF')}
        periods[period.isoformat()] = date(period.year, period.month, calendar.monthrange(period.year, period.month)[1]).isoformat()
    if not output:
        raise _error('source_empty')
    return output, periods, inputs, missing, vintage[1]


def _french(root, ids, area, dataset, select_manifest):
    identity = {'publisher': 'Kenneth French Data Library', 'dataset': dataset}
    record, folder, proof = _manifest(root/'research-returns/french'/area, identity, select_manifest)
    try:
        if set(record['sources']) != {'data'}:
            raise _error('source_identity_mismatch')
        raw, digest = _binary(folder, record['sources']['data'], 'source.zip', f'{FRENCH_ROOT}/{dataset}_CSV.zip')
        native, periods, inputs, missing, vintage = _french_original(raw, dataset)
        metadata = record['data_metadata']
        if (metadata['dataset'] != dataset or metadata['native_frequency'] != 'M'
                or metadata['native_unit'] != 'percent' or metadata['currency'] != 'USD'
                or metadata['original_first_publication_at'] is not None
                or metadata['source_database_vintage'] != vintage
                or metadata['transformation_inputs'] != inputs
                or metadata['missing_values_by_variable'] != missing):
            raise _error('source_identity_mismatch')
        values, evidence = {}, {}
        for sid in ids:
            _name, variable = FRENCH_SERIES[sid]
            contract = metadata['series'][sid]
            if (contract['source_periods'] != periods
                    or contract['source_variables'] != (['Mkt-RF','RF'] if variable=='Mkt-RF+RF' else [variable])
                    or contract['transformation'] != ('Mkt-RF + RF' if variable=='Mkt-RF+RF' else None)):
                raise _error('source_identity_mismatch')
            result = {}
            for period, row in native.items():
                if variable == 'Mkt-RF+RF':
                    value = row['Mkt-RF']+row['RF'] if row['Mkt-RF'] is not None and row['RF'] is not None else None
                else:
                    value = row[variable]
                if value is not None:
                    result[period] = value
            if not result:
                raise _error('source_empty')
            values[sid] = dict(sorted(result.items()))
            evidence[sid] = {**proof, 'source_sha256': digest, 'source_native_unit': 'percent',
                             'source_currency': 'USD', 'source_identity': identity,
                             'source_database_vintage': vintage}
        return values, evidence
    except (KeyError, TypeError):
        raise _error('source_schema_invalid') from None


def _native_cells(row, needed):
    cells = []
    for cell in row:
        if cell.tag not in (_T+'table-cell', _T+'covered-table-cell'):
            continue
        try:
            count = int(cell.get(_T+'number-columns-repeated', '1'))
            if count < 1:
                raise ValueError('repeat')
        except ValueError:
            raise _error('source_schema_invalid') from None
        cells.extend([cell]*min(count, needed-len(cells)))
        if len(cells) >= needed:
            break
    return cells


def _swinkels_original(raw, ids):
    files = _members(raw)
    if files.get('mimetype') != b'application/vnd.oasis.opendocument.spreadsheet':
        raise _error('source_identity_mismatch')
    try:
        body = files['content.xml']
        if b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper():
            raise ValueError('XML declaration')
        tree = ET.fromstring(body)
    except (KeyError, ValueError, ET.ParseError):
        raise _error('source_schema_invalid') from None
    values, periods, formulas = {}, {}, {}
    for sid in ids:
        sheet, column = SWINKELS_SERIES[sid]
        tables = [x for x in tree.findall('.//t:table', _NS) if x.get(_T+'name') == sheet]
        if len(tables) != 1:
            raise _error('source_identity_mismatch')
        rows = tables[0].findall('t:table-row', _NS)
        headers = _native_cells(rows[0], column+1) if rows else []
        if (len(headers) <= column or ''.join(headers[0].itertext()).strip() != 'observation_date'
                or ''.join(headers[column].itertext()).strip() != 'Return M'):
            raise _error('source_identity_mismatch')
        selected, native_periods, native_formulas, seen = {}, {}, {}, set()
        for row in rows[1:]:
            cells = _native_cells(row, column+1)
            if not cells or cells[0].get(_O+'value-type') != 'date':
                continue
            try:
                day = date.fromisoformat(cells[0].get(_O+'date-value', '')[:10])
                if (day in seen or day.day != calendar.monthrange(day.year, day.month)[1]
                        or day > date.today() or int(row.get(_T+'number-rows-repeated', '1')) != 1):
                    raise ValueError('month identity')
            except ValueError:
                raise _error('source_period_invalid') from None
            seen.add(day)
            cell = cells[column] if len(cells)>column else None
            if cell is None or cell.get(_O+'value') is None:
                if selected:
                    raise _error('source_value_invalid')
                continue
            if cell.get(_O+'value-type') != 'percentage' or not cell.get(_T+'formula'):
                raise _error('source_identity_mismatch')
            period = day.replace(day=1)
            selected[period] = _decimal(cell.get(_O+'value'))
            native_periods[period.isoformat()] = day.isoformat()
            native_formulas[period.isoformat()] = cell.get(_T+'formula')
        if not selected:
            raise _error('source_empty')
        values[sid], periods[sid], formulas[sid] = dict(sorted(selected.items())), native_periods, native_formulas
    return values, periods, formulas


def _swinkels(root, ids, select_manifest, original_file):
    identity = {'publisher': 'Laurens Swinkels', 'doi': '10.25397/eur.8152748.v6', 'version': 6}
    record, folder, proof = _manifest(root/'research-returns/swinkels', identity, select_manifest)
    try:
        sources = record['sources']
        if set(sources) != {'data','readme','repository_metadata','original_metadata'}:
            raise _error('source_identity_mismatch')
        raw, digest = _binary(folder, sources['data'], 'source.ods', SWINKELS_DATA_URL)
        readme, readme_hash = _binary(folder, sources['readme'], 'readme.pdf', SWINKELS_README_URL)
        if digest != SWINKELS_SHA256 or readme_hash != SWINKELS_README_SHA256:
            raise _error('source_hash_mismatch')
        for kind, url in [('repository_metadata',SWINKELS_METADATA_URL), ('original_metadata',SWINKELS_ORIGINAL_METADATA_URL)]:
            if sources[kind]['url'] != url:
                raise _error('source_identity_mismatch')
        repo_text, _ = original_file(folder, sources['repository_metadata'], 'repository_metadata.json')
        original_text, _ = original_file(folder, sources['original_metadata'], 'original_v6_metadata.json')
        repository = json.loads(repo_text)['data']['latestVersion']
        original = json.loads(original_text)
        repo_file = next(x['dataFile'] for x in repository['files'] if x['dataFile']['id']==512630)
        original_file_record = next(x for x in original['files'] if x['name'].endswith('.ods'))
        metadata = record['data_metadata']
        if (repository['datasetPersistentId'] != 'doi:10.34894/YWT2IX'
                or repository['license']['name'] != 'CC-BY-4.0'
                or repo_file['checksum'] != {'type':'SHA-1','value':sha1(raw).hexdigest()}
                or original['doi'] != '10.25397/eur.8152748.v6' or original['version'] != 6
                or original['license']['name'] != 'CC BY 4.0'
                or original['published_date'] != '2023-01-10T08:58:37Z'
                or original_file_record['computed_md5'] != md5(raw).hexdigest()
                or metadata['dataset_doi'] != original['doi'] or metadata['dataset_version'] != 6
                or metadata['dataset_release_at'] != original['published_date']
                or metadata['native_frequency'] != 'M' or metadata['native_unit'] != 'ratio'
                or metadata['original_first_publication_at'] is not None):
            raise _error('source_identity_mismatch')
        values, periods, formulas = _swinkels_original(raw, ids)
        evidence = {}
        for sid in ids:
            contract = metadata['series'][sid]
            sheet, column = SWINKELS_SERIES[sid]
            if (contract['source_sheet'] != sheet or contract['return_column_zero_based'] != column
                    or contract['currency'] != SWINKELS_METADATA[sid]['currency']
                    or contract['source_periods'] != periods[sid] or contract['source_formulas'] != formulas[sid]):
                raise _error('source_identity_mismatch')
            evidence[sid] = {**proof, 'source_sha256': digest, 'source_native_unit': 'ratio',
                             'source_currency': contract['currency'], 'source_identity': identity,
                             'dataset_release_at': original['published_date']}
        return values, evidence
    except (KeyError, TypeError, StopIteration, json.JSONDecodeError):
        raise _error('source_schema_invalid') from None


def _global_multiasset(root, ids, select_manifest):
    """Select original cached XLSX cells independently of the ingestion parser."""
    record,folder,proof=_manifest(root/'research-returns/doeswijk-swinkels/global-multiasset',
                                 GLOBAL_MARKET_IDENTITY,select_manifest)
    try:
        if set(record['sources'])!={'data'}:
            raise _error('source_identity_mismatch')
        raw,digest=_binary(folder,record['sources']['data'],'source.xlsx',GLOBAL_MARKET_URL)
        if digest!=GLOBAL_MARKET_SHA256:
            raise _error('source_hash_mismatch')
        files=_members(raw)
        namespace={'x':'http://purl.oclc.org/ooxml/spreadsheetml/main'}
        strings=[''.join(part.text or '' for part in node.iter('{'+namespace['x']+'}t'))
                 for node in ET.fromstring(files['xl/sharedStrings.xml'])]
        book=ET.fromstring(files['xl/workbook.xml'])
        if [node.attrib['name'] for node in book.findall('x:sheets/x:sheet',namespace)]!=['GMP JIMF']:
            raise _error('source_identity_mismatch')
        cells={}
        for cell in ET.fromstring(files['xl/worksheets/sheet1.xml']).findall('x:sheetData/x:row/x:c',namespace):
            node=cell.find('x:v',namespace)
            if node is not None:
                cells[cell.attrib['r']]=strings[int(node.text)] if cell.attrib.get('t')=='s' else node.text
        # Literal columns establish an independent selector, not ingestion's map.
        columns={'AUD':('A',('B','C','D'),('E','F','G')),
            'CAD':('I',('J','K','L'),('M','N','O')),
            'EUR':('Q',('R','S','T'),('U','V','W')),
            'JPY':('Y',('Z','AA','AB'),('AC','AD','AE')),
            'NZD':('AG',('AH','AI','AJ'),('AK','AL','AM')),
            'NOK':('AO',('AP','AQ','AR'),('AS','AT','AU')),
            'SEK':('AW',('AX','AY','AZ'),('BA','BB','BC')),
            'CHF':('BE',('BF','BG','BH'),('BI','BJ','BK')),
            'GBP':('BM',('BN','BO','BP'),('BQ','BR','BS')),
            'USD':('BU',('BV','BW','BX'),('BY','BZ','CA'))}
        metadata=record['data_metadata']
        if (metadata['publisher']!='Doeswijk and Swinkels'
                or metadata['research_doi']!='10.1016/j.jimonfin.2025.103453'
                or metadata['native_frequency']!='M' or metadata['native_unit']!='percent'
                or metadata['original_first_publication_at'] is not None
                or metadata['dataset_release_at'] is not None
                or metadata['original_sha256']!=GLOBAL_MARKET_SHA256
                or metadata['source_values_modified'] is not False
                or metadata['original_equity_or_bond_benchmark'] is not False
                or metadata['release_vintages_verified'] is not False
                or metadata['source_workbook_audit_status']!='original_index_return_identity_failed'
                or metadata['excluded_source_pairs']!=[{'currency':'EUR','return_type':'NOMINAL','identity_failures':579}]):
            raise _error('source_identity_mismatch')
        values,evidence={},{}
        for sid in ids:
            currency,kind=GLOBAL_MARKET_SERIES[sid]
            column,index_columns,return_columns=columns[currency]
            kind_position=('NOMINAL','REAL','EXCESS').index(kind)
            index_col,return_col=index_columns[kind_position],return_columns[kind_position]
            if cells[column+'3']!=currency or cells[return_col+'4']!=kind or cells[index_col+'4']!=kind:
                raise _error('source_identity_mismatch')
            result,periods,windows,controls={},{},{},{}
            for row in range(6,642):
                day=date.fromisoformat(cells[column+str(row)])
                period=day.replace(day=1)
                if period in result:
                    raise _error('source_period_invalid')
                result[period]=_decimal(cells[return_col+str(row)])
                periods[period.isoformat()]=day.isoformat()
                windows[period.isoformat()]={'start_exclusive':cells[column+str(row-1)],'end_inclusive':day.isoformat()}
                controls[period.isoformat()]={'previous':cells[index_col+str(row-1)],'current':cells[index_col+str(row)]}
            contract=metadata['series'][sid]
            if (contract['currency']!=currency or contract['return_type']!=kind
                    or contract['source_sheet']!='GMP JIMF' or contract['source_date_column']!=column
                    or contract['source_index_column']!=index_col or contract['source_return_column']!=return_col
                    or contract['source_periods']!=periods or contract['source_return_windows']!=windows
                    or contract['native_index_controls']!=controls
                    or contract['index_return_identity_checks']!=636 or contract['index_return_identity_failures']!=0):
                raise _error('source_identity_mismatch')
            values[sid]=result
            evidence[sid]={**proof,'source_sha256':digest,'source_native_unit':'percent',
                'source_currency':currency,'source_identity':GLOBAL_MARKET_IDENTITY,
                'source_edition':'Pinned original workbook; individual observation first releases unverified',
                'source_workbook_audit_status':'original_index_return_identity_failed',
                'selected_pair_index_return_identity_failures':0,'original_equity_or_bond_benchmark':False}
        return values,evidence
    except (KeyError,TypeError,ValueError,IndexError,ET.ParseError):
        raise _error('source_schema_invalid') from None


def read_return_originals(root, series_ids, select_manifest, original_file):
    """Return independently selected native source values and cryptographic proof.

    ``select_manifest`` verifies the append-only receipt chain. ``original_file``
    verifies the textual metadata files. Binary ZIP/ODS/PDF originals are checked
    here without attempting UTF-8 decoding or calling ingestion parsers.
    """
    ids = list(dict.fromkeys(series_ids))
    if set(ids) - (set(FRENCH_SERIES)|set(SWINKELS_SERIES)|set(GLOBAL_MARKET_SERIES)):
        raise _error('source_identity_mismatch')
    root = Path(root)
    values, proof = {}, {}
    for area, dataset in FRENCH_DATASETS.items():
        selected = [sid for sid in ids if sid in FRENCH_SERIES and FRENCH_SERIES[sid][0]==dataset]
        if selected:
            native, evidence = _french(root, selected, area, dataset, select_manifest)
            values.update(native); proof.update(evidence)
    selected = [sid for sid in ids if sid in SWINKELS_SERIES]
    if selected:
        native, evidence = _swinkels(root, selected, select_manifest, original_file)
        values.update(native); proof.update(evidence)
    selected=[sid for sid in ids if sid in GLOBAL_MARKET_SERIES]
    if selected:
        native,evidence=_global_multiasset(root,selected,select_manifest)
        values.update(native);proof.update(evidence)
    return values, proof
