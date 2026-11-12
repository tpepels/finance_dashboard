"""Independent original selectors and arithmetic for constructed source histories.

No database input or ingestion parser participates in these computations. Every
raw dependency is checked before any field is selected. Source snapshots do not
establish first publication, historical vintages, or complete world populations.
"""
from collections import defaultdict
import csv
from datetime import date
from decimal import Decimal
from hashlib import sha256
import io
import json
import re
from urllib.parse import parse_qs, unquote, urlsplit

from .catalog import source_contract
from .source_capture import canonical_bytes
from .captured_sources import _FredOriginalTable, _add, _native_period, _pink_sheet, _world_bank


CONSTRUCTED_PROVIDERS = frozenset({'MSCI_NETR', 'SIBLIS_WORLD_PE',
    'SIBLIS_WORLD_EARNINGS_YIELD', 'WORLD_LISTED_CAP_SHARE', 'BIS_WORLD_WEIGHTED',
    'EUROSTAT_CORPORATE_GDP', 'EUROSTAT_NFC_PROFIT_GVA', 'OECD_CORPORATE_GDPWEIGHTED', 'GOLD_MSCI_CORR',
    'EUROSTAT_HICP', 'OECD_NFC_ACCOUNTS'})


def _error(code='source_identity_mismatch'):
    from .source_reconciliation import EvidenceError
    raise EvidenceError(code)


def _url(url, expected, query=None):
    parts = urlsplit(url)
    target = urlsplit(expected)
    if (parts.scheme != 'https' or parts.netloc != target.netloc
            or unquote(parts.path) != unquote(target.path)
            or parts.fragment or parts.username or parts.password):
        _error()
    actual = parse_qs(parts.query, keep_blank_values=True)
    if query is not None and actual != {key: [str(value)] for key, value in query.items()}:
        _error()
    return actual


def _json(raw):
    return json.loads(raw.decode('utf-8-sig'), parse_float=Decimal)


def constructed_source(root, definition, select_manifest, original_file, *, allow_subset=False):
    from .source_reconciliation import EvidenceError
    definition = source_contract(definition)
    identity = {key: definition[key] for key in ('provider', 'source_key')}
    identity['series_id'] = definition['id']
    retrieved, manifest_hash, path, manifest, method = select_manifest(root/'responses'/definition['id'], identity)
    try:
        content = manifest['content_identity']
        contract_hash = sha256(canonical_bytes(definition)).hexdigest()
        sources = manifest['sources']
        if (manifest.get('schema_version') != 1
                or any(manifest.get(key) != value for key, value in identity.items())
                or manifest.get('source_contract') != definition
                or manifest.get('source_contract_sha256') != contract_hash
                or content.get('source_contract_sha256') != contract_hash
                or path.parent.name != sha256(canonical_bytes(content)).hexdigest()
                or content.get('source_identity') != identity
                or content.get('requested_from') != manifest.get('requested_from')
                or content.get('responses') != [{key: source[key] for key in ('file', 'url', 'sha256', 'bytes')} for source in sources]):
            _error()
        scope = ('requested_period_subset', True) if allow_subset else ('full_source_snapshot', False)
        if manifest.get('scope') != scope[0] or (manifest.get('requested_from') is not None) != scope[1]:
            _error('source_snapshot_partial')
        # Only adapters whose reader states its windowed request form accept a
        # requested-period subset; every other reader keeps full snapshots.
        start = date.fromisoformat(manifest['requested_from']) if allow_subset else None
        if start is not None and definition['provider'] != 'MSCI_NETR':
            _error('source_snapshot_partial')
        provider = definition['provider']
        count = {'MSCI_NETR': 1, 'SIBLIS_WORLD_PE': 1, 'SIBLIS_WORLD_EARNINGS_YIELD': 1,
                 'WORLD_LISTED_CAP_SHARE': 2, 'BIS_WORLD_WEIGHTED': 2,
                 'EUROSTAT_CORPORATE_GDP': 3, 'EUROSTAT_NFC_PROFIT_GVA': 1,
                 'OECD_CORPORATE_GDPWEIGHTED': 3, 'GOLD_MSCI_CORR': 2, 'EUROSTAT_HICP': 1, 'OECD_NFC_ACCOUNTS': 1}[provider]
        if len(sources) != count:
            _error('source_response_ambiguous')
        # Verify *all* raw dependencies before parsing any of them.
        raw = [original_file(path.parent, source, f'response-{index}.bin', binary=True)[0]
               for index, source in enumerate(sources)]
        if provider == 'MSCI_NETR':
            if definition['source_key'] != '892400/NETR/USD' or definition['frequency'] != 'D' or definition['unit'] != 'index': _error()
            values = _msci(raw[0], sources[0]['url'], start)
            details = {'source_return_variant': 'NETR', 'source_currency': 'USD', 'source_index_code': '892400'}
        elif provider.startswith('SIBLIS_WORLD_'):
            if definition['source_key'] != 'GLOBAL/PT12M' or definition['frequency'] != 'M' or definition['unit'] != ('ratio' if provider == 'SIBLIS_WORLD_PE' else 'percent'): _error()
            values = _siblis(raw[0], sources[0]['url'])
            if provider == 'SIBLIS_WORLD_EARNINGS_YIELD': values = {day: Decimal(100)/value for day, value in values.items()}
            details = {'source_snapshot_scope': 'sparse_published_snapshots', 'source_population': 'Siblis global index universe'}
        elif provider == 'WORLD_LISTED_CAP_SHARE':
            if definition['source_key'] != 'WLD/CM.MKT.LCAP.CD:WLD/NY.GDP.MKTP.CD' or definition['frequency'] != 'A' or definition['unit'] != 'percent': _error()
            cap = _world_level(raw[0], sources[0]['url'], 'CM.MKT.LCAP.CD')
            gdp = _world_level(raw[1], sources[1]['url'], 'NY.GDP.MKTP.CD')
            if any(value < 0 for value in cap.values()) or any(value <= 0 for value in gdp.values()): _error('source_value_invalid')
            values = {day: cap[day]/gdp[day]*100 for day in cap.keys() & gdp.keys()}
            details = {'source_currency': 'USD', 'source_formula': '100 * WLD listed domestic capitalization / WLD GDP; same annual year'}
        elif provider == 'BIS_WORLD_WEIGHTED':
            values = _world_gap(raw, sources, definition)
            details = {'source_weight_lag_years': 1, 'source_coverage_floor_percent': 80,
                       'source_excluded_overlapping_geographies': ['XM']}
        elif provider == 'OECD_NFC_ACCOUNTS':
            if definition['frequency'] != 'A' or definition['unit'] != 'million_local_currency': _error()
            values = _oecd_nfc(raw[0], sources[0]['url'], definition)
            details = {'source_native_unit': 'million_national_currency', 'source_currency': definition.get('currency'),
                       'source_population': 'Non-financial corporations (S11), national accounts',
                       'source_price_basis': 'current_prices'}
        elif provider == 'EUROSTAT_HICP':
            if definition['source_key'] != 'prc_hicp_minr/M.I25.TOTAL.EA' or definition['frequency'] != 'M' or definition['unit'] != 'index': _error()
            values = _eurostat_hicp(raw[0], sources[0]['url'])
            details = {'source_native_unit': 'index_2025_100', 'source_index_base': '2025=100',
                       'source_classification': 'ECOICOP ver.2 TOTAL',
                       'source_population': 'Euro area changing composition (EA21 from 2026)'}
        elif provider == 'EUROSTAT_NFC_PROFIT_GVA':
            if definition['source_key'] != 'nasa_10_ki/EU27_2020/S11/B2G_B3G_RAT_S11' or definition['frequency'] != 'A' or definition['unit'] != 'percent': _error()
            values = _eurostat(raw[0], sources[0]['url'], 'S11', 'B2G_B3G_RAT_S11',
                               dataset='nasa_10_ki', unit='PC', direct=None)
            if any(value > 100 for value in values.values()): _error('source_value_invalid')
            details = {'source_native_unit': 'percent', 'source_denominator': 'S11 gross value added',
                       'source_population': 'EU27_2020 non-financial corporations S11, listed and unlisted',
                       'source_variable': 'B2G_B3G_RAT_S11'}
        elif provider == 'EUROSTAT_CORPORATE_GDP':
            if definition['source_key'] != 'nasa_10_nf_tr/EU27_2020/S11+S12_B2A3G/S1_B1GQ' or definition['frequency'] != 'A' or definition['unit'] != 'percent': _error()
            selected = [_eurostat(body, source['url'], sector, measure) for body, source, (sector, measure) in zip(raw, sources, [('S11', 'B2A3G'), ('S12', 'B2A3G'), ('S1', 'B1GQ')], strict=True)]
            a, b, gdp = selected
            if any(value <= 0 for value in gdp.values()): _error('source_value_invalid')
            values = {day: (a[day]+b[day])*100/gdp[day] for day in a.keys() & b.keys() & gdp.keys()}
            if any(value > 100 for value in values.values()): _error('source_value_invalid')
            details = {'source_currency': 'EUR', 'source_native_unit': 'current EUR millions', 'source_population': 'EU27_2020 S11 and S12 corporations, listed and unlisted'}
        elif provider == 'OECD_CORPORATE_GDPWEIGHTED':
            values = _oecd(raw, sources, definition)
            details = {'source_population': 'fixed 2026 OECD 38 membership', 'source_coverage_floor_percent': 80,
                       'source_minimum_gdp_weight_members': 35, 'source_minimum_contributing_members': 29}
        else:
            if definition['source_key'] != '36M/PINK_SHEET_GOLD/MSCI_892400_NETR_USD' or definition['frequency'] != 'M' or definition['unit'] != 'ratio': _error()
            gold_definition = {'source_key': 'CMO-Historical-Data-Monthly.xlsx#Monthly Prices:Gold', 'frequency': 'M', 'unit': 'usd_per_oz'}
            gold, _ = _pink_sheet(raw[0], gold_definition, sources[0]['url'])
            index = _msci(raw[1], sources[1]['url'])
            values = _correlation(gold, index)
            details = {'source_currency': 'USD', 'source_correlation_window_months': 36,
                       'source_formula': 'Pearson correlation of arithmetic returns on monthly mean gold and daily NETR index levels; consecutive completed months'}
        if not values: _error('source_empty')
        dependencies = [{key: source[key] for key in ('file', 'url', 'sha256', 'bytes')} for source in sources]
        return values, {'source_sha256': sources[0]['sha256'] if count == 1 else sha256(canonical_bytes(dependencies)).hexdigest(),
            'source_manifest_sha256': manifest_hash, 'evidence_retrieved_at_utc': retrieved.isoformat(),
            'selection_method': method, 'source_dependencies': dependencies,
            'source_value_kind': 'publisher_observations' if provider in {'MSCI_NETR', 'SIBLIS_WORLD_PE', 'EUROSTAT_NFC_PROFIT_GVA'} else 'independently_recomputed_from_originals',
            'individual_observation_first_publication_verified': False, **details}
    except EvidenceError:
        raise
    except (KeyError, TypeError, ValueError, IndexError, AttributeError, UnicodeError, ArithmeticError, csv.Error):
        _error('source_schema_invalid')


def _msci(raw, url, start=None):
    from .remaining_sources import MSCI_LEVELS_URL
    query = _url(url, MSCI_LEVELS_URL)
    first = start or date(2000, 1, 1)
    expected = {'index_codes': ['892400'], 'currency_symbol': ['USD'], 'index_variant': ['NETR'],
                'data_frequency': ['DAILY'], 'start_date': [first.strftime('%Y%m%d')]}
    if set(query) != set(expected) | {'end_date'} or any(query.get(key) != value for key, value in expected.items()): _error()
    end = query['end_date']
    if len(end) != 1 or not re.fullmatch(r'[0-9]{8}', end[0]): _error()
    cutoff = date(int(end[0][:4]), int(end[0][4:6]), int(end[0][6:]))
    if cutoff > date.today(): _error('source_period_invalid')
    payload = _json(raw)
    if (str(payload['msci_index_code']) != '892400' or payload['index_variant_type'] != 'NETR'
            or payload['ISO_currency_symbol'] != 'USD' or not isinstance(payload['indexes']['INDEX_LEVELS'], list)): _error()
    values, seen = {}, set()
    for row in payload['indexes']['INDEX_LEVELS']:
        label = str(row['calc_date'])
        if not re.fullmatch(r'[0-9]{8}', label): _error('source_period_invalid')
        day = _native_period(label[:4]+'-'+label[4:6]+'-'+label[6:], 'D')
        if not first <= day <= cutoff: _error('source_period_invalid')
        _add(values, seen, day, row['level_eod'])
    if any(value <= 0 for value in values.values()): _error('source_value_invalid')
    return values


def _siblis(raw, url):
    _url(url, 'https://siblisresearch.com/data/global-markets-pe/', {})
    body = raw.decode('utf-8-sig')
    if 'Global stock market valuations' not in body or 'Historical trailing P/E' not in body: _error()
    parser = _FredOriginalTable(); parser.feed(body); parser.close()
    tables = [table['rows'] for table in parser.tables if table['rows'] and len(table['rows'][0]) >= 3
              and [cell.lower() for cell in table['rows'][0]][:2] == ['month', 'global']
              and 'developed' in table['rows'][0][2].lower()]
    if len(tables) != 1: _error()
    months = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
              'jul': 7, 'aug': 8, 'sep': 9, 'sept': 9, 'oct': 10, 'nov': 11, 'dec': 12}
    values, seen = {}, set()
    for row in tables[0][1:]:
        label = ' '.join(row[0].replace(',', '').split())
        match = re.fullmatch(r'([0-9]{4}) ([A-Za-z]+)|([A-Za-z]+) ([0-9]{4})', label)
        if not match: _error('source_period_invalid')
        year, month = (match[1], match[2]) if match[1] else (match[4], match[3])
        day = _native_period(f'{year}-{months[month.lower()]:02d}', 'M')
        _add(values, seen, day, row[1].replace(',', '').strip())
    if any(not 1 <= value <= 300 for value in values.values()): _error('source_value_invalid')
    years = {day.year for day in values if day.month == 12}
    if len(years) < 9 or min(years) > 2017: _error('source_truncated')
    return values


def _world_level(raw, url, indicator):
    _url(url, 'https://api.worldbank.org/v2/country/WLD/indicator/'+indicator, {'format': 'json', 'per_page': 150})
    return _world_bank(_json(raw), {'source_key': 'WLD/'+indicator})


def _wdi_weights(raw, url, indicator, begin, members=None):
    query = _url(url, 'https://api.worldbank.org/v2/country/all/indicator/'+indicator)
    if set(query) != {'format', 'per_page', 'date'} or query['format'] != ['json'] or query['per_page'] != ['20000'] or len(query['date']) != 1: _error()
    window = query['date'][0].split(':')
    if len(window) != 2 or window[0] != str(begin) or not window[1].isdigit() or int(window[1]) > date.today().year: _error()
    payload = _json(raw)
    if not isinstance(payload, list) or len(payload) != 2 or payload[0].get('pages') != 1 or not isinstance(payload[1], list): _error('source_truncated')
    selected, seen = defaultdict(dict), set()
    for row in payload[1]:
        if row['indicator']['id'] != indicator: _error()
        day = _native_period(row['date'], 'A')
        if not begin <= day.year <= int(window[1]): _error('source_period_invalid')
        code = row['countryiso3code'] if members is not None else row.get('country', {}).get('id')
        if members is None and row['countryiso3code'] == 'WLD': code = 'WLD'
        if code not in (members if members is not None else _BIS_COUNTRIES | {'WLD'}): continue
        key = (day.year, code)
        if key in seen: _error('source_duplicate_period')
        seen.add(key)
        if row['value'] is None: continue
        value = Decimal(str(row['value']))
        if not value.is_finite() or value <= 0: _error('source_value_invalid')
        selected[day.year][code] = value
    return selected


_BIS_COUNTRIES = frozenset('PL BR GB MX ZA CN SA US HU JP LU RU CL HK IT NL CZ SG ES IE AU MY AR SE CO TR DK ID IN NZ CA AT FR NO DE TH FI IL BE KR PT CH GR'.split())


def _world_gap(raw, sources, definition):
    key = definition['source_key']
    if key not in {'GAP/43_COUNTRIES_PRIOR_YEAR_GDP_80PCT', 'COVERAGE/43_COUNTRIES_PRIOR_YEAR_GDP_80PCT'} or definition['frequency'] != 'Q' or definition['unit'] != ('percentage_points' if key.startswith('GAP/') else 'percent'): _error()
    _url(sources[0]['url'], 'https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CREDIT_GAP/1.0/Q..P.A.C', {})
    weights = _wdi_weights(raw[1], sources[1]['url'], 'NY.GDP.MKTP.CD', 1960)
    block = _json(raw[0])['data']; structure = block['structure']; dims = structure['dimensions']
    names = ('FREQ', 'BORROWERS_CTY', 'TC_BORROWERS', 'TC_LENDERS', 'CG_DTYPE')
    if tuple(dim['id'] for dim in dims['series']) != names or [dim['id'] for dim in dims['observation']] != ['TIME_PERIOD'] or len(block['dataSets']) != 1: _error()
    attribute_defs = structure['attributes']['dataset']
    attribute_indices = block['dataSets'][0]['attributes']
    if len(attribute_defs) != len(attribute_indices) or len({item['id'] for item in attribute_defs}) != len(attribute_defs): _error('source_schema_invalid')
    reported = {}
    for attribute, index in zip(attribute_defs, attribute_indices, strict=True):
        if index is None: continue
        if not isinstance(index, int) or index < 0: _error('source_schema_invalid')
        reported[attribute['id']] = attribute['values'][index]['id']
    if reported.get('UNIT_MEASURE') != '770' or reported.get('UNIT_MULT') != '0': _error()
    def decode(dimensions, label):
        indices = label.split(':')
        if len(indices) != len(dimensions) or any(not index.isdigit() for index in indices): _error('source_schema_invalid')
        return [dim['values'][int(index)]['id'] for dim, index in zip(dimensions, indices, strict=True)]
    quarters, seen = defaultdict(dict), set()
    for label, node in block['dataSets'][0]['series'].items():
        freq, country, borrowers, lenders, kind = decode(dims['series'], label)
        if (freq, borrowers, lenders, kind) != ('Q', 'P', 'A', 'C') or country not in _BIS_COUNTRIES | {'XM'}: _error()
        for time, row in node['observations'].items():
            day = _native_period(decode(dims['observation'], time)[0], 'Q')
            if country == 'XM': continue
            pair = (day, country)
            if pair in seen: _error('source_duplicate_period')
            seen.add(pair)
            target = {}; _add(target, set(), day, row[0])
            if target: quarters[day][country] = target[day]
    values = {}
    for day, gaps in quarters.items():
        available = weights.get(day.year-1, {})
        if 'WLD' not in available: continue
        countries = sorted(gaps.keys() & available.keys())
        total = sum((available[country] for country in countries), Decimal(0))
        fraction = total/available['WLD']
        if fraction > Decimal('1.01'): _error('source_value_invalid')
        if fraction < Decimal('0.80'): continue
        values[day] = fraction*100 if key.startswith('COVERAGE/') else sum((available[country]*gaps[country] for country in countries), Decimal(0))/total
    return values


def _eurostat(raw, url, sector, measure, *, dataset='nasa_10_nf_tr', unit='CP_MEUR', direct='RECV'):
    expected = {'freq': 'A', 'unit': unit, 'sector': sector, 'na_item': measure, 'geo': 'EU27_2020'}
    if direct is not None: expected['direct'] = direct
    _url(url, 'https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/'+dataset, expected)
    payload = _json(raw)
    names = ['freq', 'unit']+(['direct'] if direct is not None else [])+['na_item', 'sector', 'geo', 'time']
    if payload['id'] != names or payload['class'] != 'dataset' or payload['source'] != 'ESTAT' or payload['size'][:-1] != [1]*(len(names)-1): _error()
    for name, value in expected.items():
        if payload['dimension'][name]['category']['index'] != {value: 0}: _error()
    times = payload['dimension']['time']['category']['index']
    if len(times) != payload['size'][-1] or set(times.values()) != set(range(len(times))) or set(payload['value']) - {str(index) for index in times.values()}: _error('source_schema_invalid')
    values, seen = {}, set()
    for label, index in times.items(): _add(values, seen, _native_period(label, 'A'), payload['value'].get(str(index)))
    if any(value < 0 for value in values.values()): _error('source_value_invalid')
    return values


def _oecd_nfc(raw, url, definition):
    """Verify exact source dimensions for both original and shared OECD S11 documents.

    Older single-transaction acquisition receipts are still valid and must
    remain independently re-verifiable. New country-scoped Table 14 originals
    are verified against their declared multi-code request key and all
    returned source-row identities; only the requested target is extracted.
    """
    country, _, transaction = definition['source_key'].partition('/')
    entries = {'B1G': 'D', 'D1': 'D', 'B2G': 'D',
               'P51C': 'D', 'D29': 'D', 'D39': 'C'}
    stocks = {'N11N'}
    if not re.fullmatch('[A-Z]{3}', country) or transaction not in set(entries) | stocks:
        _error()
    query = parse_qs(urlsplit(url).query)
    if (set(query) - {'format', 'startPeriod'}
            or query.get('format') != ['csvfile'] or 'startPeriod' in query):
        _error('source_snapshot_partial')
    legacy = False
    if transaction in stocks:
        key = f'A.{country}.S11.S1.A._Z.{transaction}._Z.XDC._Z.V.N.T2600'
        _url(url, 'https://sdmx.oecd.org/public/rest/data/OECD.SDD.NAD,DSD_NASEC10@DF_TABLE9B,1.1/'+key)
        fixed = {'DATAFLOW': 'OECD.SDD.NAD:DSD_NASEC10@DF_TABLE9B(1.1)',
                 'FREQ': 'A', 'REF_AREA': country,
                 'SECTOR': 'S11', 'COUNTERPART_SECTOR': 'S1',
                 'ACCOUNTING_ENTRY': 'A', 'TRANSACTION': '_Z',
                 'INSTR_ASSET': transaction, 'EXPENDITURE': '_Z',
                 'UNIT_MEASURE': 'XDC', 'VALUATION': '_Z', 'PRICE_BASE': 'V',
                 'TRANSFORMATION': 'N', 'TABLE_IDENTIFIER': 'T2600',
                 'UNIT_MULT': '6'}
    else:
        old_key = f'A.{country}.S11.S1.{entries[transaction]}.{transaction}._Z._Z.XDC.S.V.N.T0800'
        batched_key = (f'A.{country}.S11.S1.C+D.'
                       'B1G+B2G+D1+D29+D39+P51C._Z._Z.XDC.S.V.N.T0800')
        root = 'https://sdmx.oecd.org/public/rest/data/OECD.SDD.NAD,DSD_NASEC10@DF_TABLE14,1.1/'
        if urlsplit(url).path == urlsplit(root + old_key).path:
            _url(url, root + old_key)
            legacy = True
        else:
            _url(url, root + batched_key)
        fixed = {'DATAFLOW': 'OECD.SDD.NAD:DSD_NASEC10@DF_TABLE14(1.1)',
                 'FREQ': 'A', 'REF_AREA': country,
                 'SECTOR': 'S11', 'COUNTERPART_SECTOR': 'S1',
                 'INSTR_ASSET': '_Z', 'EXPENDITURE': '_Z',
                 'UNIT_MEASURE': 'XDC', 'VALUATION': 'S', 'PRICE_BASE': 'V',
                 'TRANSFORMATION': 'N', 'TABLE_IDENTIFIER': 'T0800',
                 'UNIT_MULT': '6'}
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    required = set(fixed) | {'CURRENCY', 'TIME_PERIOD', 'OBS_VALUE',
                             'ACCOUNTING_ENTRY', 'TRANSACTION'}
    if not reader.fieldnames or not required <= set(reader.fieldnames) or len(reader.fieldnames) != len(set(reader.fieldnames)):
        _error('source_schema_invalid')
    values, seen = {}, set()
    for row in reader:
        if any(row.get(name) != value for name, value in fixed.items()):
            _error()
        if definition.get('currency') and row['CURRENCY'] != definition['currency']:
            _error()
        if transaction in stocks:
            include = True
        else:
            code = row.get('TRANSACTION')
            # A many-series original cannot smuggle another economic series
            # under a permissive wildcard: every returned role must belong
            # to the exact audited key with the correct uses/resources entry.
            if (code not in entries
                    or row.get('ACCOUNTING_ENTRY') != entries[code]
                    or (legacy and code != transaction)):
                _error()
            include = code == transaction
        if include:
            _add(values, seen, _native_period(row['TIME_PERIOD'], 'A'), row['OBS_VALUE'])
    if transaction != 'B2G' and any(value < 0 for value in values.values()):
        _error('source_value_invalid')
    return values

def _eurostat_hicp(raw, url):
    expected = {'freq': 'M', 'unit': 'I25', 'coicop18': 'TOTAL', 'geo': 'EA'}
    _url(url, 'https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_minr', expected)
    payload = _json(raw)
    names = ['freq', 'unit', 'coicop18', 'geo', 'time']
    if payload['id'] != names or payload['class'] != 'dataset' or payload['source'] != 'ESTAT' or payload['size'][:-1] != [1, 1, 1, 1]: _error()
    for name, value in expected.items():
        if payload['dimension'][name]['category']['index'] != {value: 0}: _error()
    times = payload['dimension']['time']['category']['index']
    if len(times) != payload['size'][-1] or set(times.values()) != set(range(len(times))) or set(payload['value']) - {str(index) for index in times.values()}: _error('source_schema_invalid')
    values, seen = {}, set()
    for label, index in times.items(): _add(values, seen, _native_period(label, 'M'), payload['value'].get(str(index)))
    if any(value <= 0 for value in values.values()): _error('source_value_invalid')
    return values


_OECD_MEMBERS = frozenset('AUS AUT BEL CAN CHL COL CRI CZE DNK EST FIN FRA DEU GRC HUN ISL IRL ISR ITA JPN KOR LVA LTU LUX MEX NLD NZL NOR POL PRT SVK SVN ESP SWE CHE TUR GBR USA'.split())


def _oecd(raw, sources, definition):
    key = definition['source_key']
    if key not in {kind+'/OECD38_S11_S12_B2G_GDP_WDIWEIGHT' for kind in ('RATIO', 'COVERAGE', 'COUNT')} or definition['frequency'] != 'A' or definition['unit'] != ('count' if key.startswith('COUNT/') else 'percent'): _error()
    members = '+'.join(sorted(_OECD_MEMBERS))
    source_key = f'A.{members}.S11+S12+S1.S1.C+D.B2G+B1G+D21X31._Z._Z.XDC.S.V.N.T0800'
    _url(sources[0]['url'], 'https://sdmx.oecd.org/public/rest/data/OECD.SDD.NAD,DSD_NASEC10@DF_TABLE14,1.1/'+source_key, {'format': 'csvfile', 'startPeriod': 1990})
    usd = _wdi_weights(raw[1], sources[1]['url'], 'NY.GDP.MKTP.CD', 1990, _OECD_MEMBERS)
    local = _wdi_weights(raw[2], sources[2]['url'], 'NY.GDP.MKTP.CN', 1990, _OECD_MEMBERS)
    reader = csv.DictReader(io.StringIO(raw[0].decode('utf-8-sig')))
    fixed = {'DATAFLOW': 'OECD.SDD.NAD:DSD_NASEC10@DF_TABLE14(1.1)', 'FREQ': 'A',
             'COUNTERPART_SECTOR': 'S1', 'INSTR_ASSET': '_Z', 'EXPENDITURE': '_Z',
             'UNIT_MEASURE': 'XDC', 'VALUATION': 'S', 'PRICE_BASE': 'V',
             'TRANSFORMATION': 'N', 'TABLE_IDENTIFIER': 'T0800', 'UNIT_MULT': '6'}
    required = set(fixed) | {'REF_AREA', 'CURRENCY', 'SECTOR', 'ACCOUNTING_ENTRY', 'TRANSACTION', 'TIME_PERIOD', 'OBS_VALUE'}
    if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)) or not required <= set(reader.fieldnames): _error('source_schema_invalid')
    accounts, currencies, seen = defaultdict(dict), {}, set()
    selectors = {('S11', 'D', 'B2G'): 'nfc', ('S12', 'D', 'B2G'): 'fc', ('S1', 'D', 'B1G'): 'gva', ('S1', 'C', 'D21X31'): 'tax'}
    for row in reader:
        if any(row.get(name) != value for name, value in fixed.items()) or row['REF_AREA'] not in _OECD_MEMBERS: _error()
        day = _native_period(row['TIME_PERIOD'], 'A')
        if day.year < 1990: _error('source_period_invalid')
        pair = (day.year, row['REF_AREA']); currency = row['CURRENCY']
        if not re.fullmatch('[A-Z]{3}', currency) or currencies.setdefault(pair, currency) != currency: _error()
        component = selectors.get((row['SECTOR'], row['ACCOUNTING_ENTRY'], row['TRANSACTION']))
        if component is None: continue
        unique = (*pair, component)
        if unique in seen: _error('source_duplicate_period')
        seen.add(unique)
        if row['OBS_VALUE'] in ('', None): continue
        value = Decimal(row['OBS_VALUE'])
        if not value.is_finite() or (component != 'tax' and value < 0): _error('source_value_invalid')
        accounts[pair][component] = value
    results = {}
    for year, weights in usd.items():
        if len(weights) < 35: continue
        eligible = []
        for country, weight in weights.items():
            components = accounts.get((year, country), {})
            if not {'nfc', 'fc', 'gva'} <= components.keys(): continue
            if 'tax' in components:
                gdp = components['gva']+components['tax']
            elif currencies[(year, country)] == {'USA': 'USD', 'JPN': 'JPY', 'CAN': 'CAD'}.get(country) and country in local.get(year, {}):
                gdp = local[year][country]/Decimal(1_000_000)
                if not components['gva']*Decimal('.90') <= gdp <= components['gva']*Decimal('1.35'): _error('source_value_invalid')
            else: continue
            if gdp <= 0: _error('source_value_invalid')
            ratio = (components['nfc']+components['fc'])/gdp
            if not 0 <= ratio <= 1: _error('source_value_invalid')
            eligible.append((weight, ratio))
        included = sum((weight for weight, _ in eligible), Decimal(0))
        fraction = included/sum(weights.values(), Decimal(0))
        if len(eligible) < 29 or fraction < Decimal('.80'): continue
        kind = key.split('/')[0]
        results[date(year, 1, 1)] = (Decimal(len(eligible)) if kind == 'COUNT' else fraction*100 if kind == 'COVERAGE'
            else sum((weight*ratio for weight, ratio in eligible), Decimal(0))/included*100)
    return results


def _previous_month(day):
    return date(day.year-1, 12, 1) if day.month == 1 else date(day.year, day.month-1, 1)


def _correlation(gold, daily):
    groups = defaultdict(list)
    for day, value in daily.items(): groups[day.replace(day=1)].append(value)
    means = {day: sum(values, Decimal(0))/len(values) for day, values in groups.items()}
    returns = {}
    for day in sorted(gold.keys() & means.keys()):
        previous = _previous_month(day)
        if day >= date.today().replace(day=1) or previous not in gold or previous not in means: continue
        if any(value <= 0 for value in (gold[previous], means[previous], gold[day], means[day])): _error('source_value_invalid')
        returns[day] = (gold[day]/gold[previous]-1, means[day]/means[previous]-1)
    values = {}
    for day in sorted(returns):
        months = [day]
        for _ in range(35): months.append(_previous_month(months[-1]))
        if any(month not in returns for month in months): continue
        sample = [returns[month] for month in reversed(months)]
        xmean = sum((x for x, _ in sample), Decimal(0))/36
        ymean = sum((y for _, y in sample), Decimal(0))/36
        numerator = sum(((x-xmean)*(y-ymean) for x, y in sample), Decimal(0))
        xvar = sum(((x-xmean)**2 for x, _ in sample), Decimal(0))
        yvar = sum(((y-ymean)**2 for _, y in sample), Decimal(0))
        if xvar == 0 or yvar == 0: continue
        value = numerator/(xvar*yvar).sqrt()
        if abs(value) > Decimal('1.00000001'): _error('source_value_invalid')
        values[day] = max(Decimal(-1), min(Decimal(1), value))
    return values
