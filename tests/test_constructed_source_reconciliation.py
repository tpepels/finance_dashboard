"""Original-input proof for constructed series, independent of ingestion code."""
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from finance_dashboard.catalog import load_documents
from finance_dashboard.source_capture import canonical_bytes, CapturedProvider
from finance_dashboard.source_reconciliation import _reconcile_values
from finance_dashboard.providers import ProviderRouter
from test_macro_aggregates import published_html
from test_world_credit import bis_fixture
from test_eurostat_corporate import payload as eurostat_payload
from test_oecd_corporate import input_rows, csv_text, wdi_payload


REGISTRY = {row['id']: row for row in load_documents()[0]['series']}
WDI = 'https://api.worldbank.org/v2/country/'
MSCI = 'https://app2.msci.com/products/service/index/indexmaster/getLevelDataForGraph'


def archive(root, sid, responses):
    definition = REGISTRY[sid]
    identity = {key: definition[key] for key in ('provider', 'source_key')}
    identity['series_id'] = sid
    contract_hash = sha256(canonical_bytes(definition)).hexdigest()
    files = []
    for index, (url, payload) in enumerate(responses):
        raw = payload if isinstance(payload, bytes) else payload.encode() if isinstance(payload, str) else canonical_bytes(payload)
        files.append((raw, {'file': f'response-{index}.bin', 'url': url,
                           'sha256': sha256(raw).hexdigest(), 'bytes': len(raw)}))
    content = {'source_identity': identity, 'source_contract_sha256': contract_hash,
               'requested_from': None, 'responses': [record for _, record in files]}
    folder = root / 'responses' / sid / sha256(canonical_bytes(content)).hexdigest()
    folder.mkdir(parents=True)
    for raw, record in files:
        (folder / record['file']).write_bytes(raw)
    manifest = {'schema_version': 1, **identity, 'source_contract': definition,
                'source_contract_sha256': contract_hash, 'scope': 'full_source_snapshot',
                'requested_from': None, 'retrieved_at_utc': '2026-11-04T10:00:00+00:00',
                'content_identity': content, 'sources': [record for _, record in files]}
    (folder / 'manifest.json').write_bytes(canonical_bytes(manifest))
    return folder


def wdi(indicator, rows):
    return [{'pages': 1}, [{'indicator': {'id': indicator}, **row} for row in rows]]


def audit(root, sid, values):
    # Supply the values as actual Numeric(32,10) database rows would return.
    stored = {day: value.quantize(Decimal('0.0000000001')) for day, value in values.items()}
    return _reconcile_values({sid: stored}, 'postgresql', root)['series'][0]


class ConstructedSourceTests(unittest.TestCase):
    def test_msci_capture_keeps_exact_query_and_native_original_identity(self):
        sid = 'equity.world.msci_acwi_netr_usd'
        original = {'msci_index_code': '892400', 'index_variant_type': 'NETR',
                    'ISO_currency_symbol': 'USD', 'indexes': {'INDEX_LEVELS': [
                        {'calc_date': '20240102', 'level_eod': '310.25'}]}}
        with TemporaryDirectory() as temp:
            root = Path(temp)
            with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=original))) as client:
                CapturedProvider(ProviderRouter(client), root).fetch(sid)
            item = audit(root, sid, {date(2024, 1, 2): Decimal('310.25')})
            self.assertTrue(item['source_values_match'], item)
            self.assertEqual(item['source_return_variant'], 'NETR')
            manifest = json.loads(next(root.glob('responses/*/*/manifest.json')).read_bytes())
            self.assertIn('index_codes=892400', manifest['sources'][0]['url'])
            # A source identity change remains invalid even with updated raw hashes.
            wrong = json.loads(json.dumps(original)); wrong['ISO_currency_symbol'] = 'EUR'
            other = Path(temp) / 'wrong'
            archive(other, sid, [(manifest['sources'][0]['url'], wrong)])
            self.assertEqual(audit(other, sid, {})['failure_code'], 'source_identity_mismatch')
            with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=original))) as client:
                CapturedProvider(ProviderRouter(client), root).fetch(sid, date(2024, 1, 1))
            self.assertEqual(audit(root, sid, {})['failure_code'], 'source_snapshot_partial')

    def test_siblis_sparse_snapshots_and_same_universe_inverse_are_independent(self):
        for sid, expected in [('valuation.world.global_trailing_pe', Decimal(20)),
                              ('valuation.world.global_earnings_yield', Decimal(5))]:
            with self.subTest(sid=sid), TemporaryDirectory() as temp:
                root = Path(temp)
                archive(root, sid, [('https://siblisresearch.com/data/global-markets-pe/', published_html())])
                values = {date(year, 12, 1): expected for year in range(2016, 2026)}
                values[date(2026, 9, 1)] = Decimal('21.60') if expected == 20 else Decimal(100) / Decimal('21.60')
                with patch('finance_dashboard.macro_aggregates.parse_siblis_world_pe', side_effect=AssertionError('ingestion parser used')):
                    item = audit(root, sid, values)
                self.assertTrue(item['source_values_match'], item)
                self.assertEqual(item['source_periods'], 11)

    def test_world_listed_ratio_requires_both_originals_and_preserves_intersection(self):
        sid = 'valuation.world.listed_market_cap_world_gdp'
        responses = [(WDI+'WLD/indicator/CM.MKT.LCAP.CD?format=json&per_page=150',
                      wdi('CM.MKT.LCAP.CD', [{'date': '2024', 'countryiso3code': 'WLD', 'value': '150'},
                                               {'date': '2025', 'countryiso3code': 'WLD', 'value': '170'}])),
                     (WDI+'WLD/indicator/NY.GDP.MKTP.CD?format=json&per_page=150',
                      wdi('NY.GDP.MKTP.CD', [{'date': '2024', 'countryiso3code': 'WLD', 'value': '100'}]))]
        with TemporaryDirectory() as temp:
            root = Path(temp); folder = archive(root, sid, responses)
            item = audit(root, sid, {date(2024, 1, 1): Decimal(150)})
            self.assertTrue(item['source_values_match'], item)
            self.assertEqual(len(item['source_dependencies']), 2)
            # Rehash every dependency before attempting to parse even the first.
            other = root/'broken'
            folder = archive(other, sid, [(responses[0][0], 'not JSON'), responses[1]])
            (folder/'response-1.bin').write_text('corrupt denominator')
            self.assertEqual(audit(other, sid, {})['failure_code'], 'source_hash_mismatch')

    def test_world_credit_uses_prior_year_gdp_and_excludes_overlapping_euro_area(self):
        native = bis_fixture()
        native['data']['structure']['attributes'] = {'dataset': [
            {'id': 'UNIT_MEASURE', 'values': [{'id': '770'}]},
            {'id': 'UNIT_MULT', 'values': [{'id': '0'}]}]}
        native['data']['dataSets'][0]['attributes'] = [0, 0]
        responses = [('https://stats.bis.org/api/v2/data/dataflow/BIS/WS_CREDIT_GAP/1.0/Q..P.A.C', native),
                     (WDI+'all/indicator/NY.GDP.MKTP.CD?format=json&per_page=20000&date=1960:2026',
                      wdi('NY.GDP.MKTP.CD', [
                          {'date': '2024', 'countryiso3code': 'USA', 'country': {'id': 'US'}, 'value': 60},
                          {'date': '2024', 'countryiso3code': 'JPN', 'country': {'id': 'JP'}, 'value': 30},
                          {'date': '2024', 'countryiso3code': 'WLD', 'country': {'id': '1W'}, 'value': 100},
                          {'date': '2025', 'countryiso3code': 'USA', 'country': {'id': 'US'}, 'value': 900}]))]
        for sid, expected in [('credit.world.private_gdp_gap', -5), ('credit.world.private_gdp_gap_coverage', 90)]:
            with self.subTest(sid=sid), TemporaryDirectory() as temp:
                root = Path(temp); archive(root, sid, responses)
                item = audit(root, sid, {date(2025, 1, 1): Decimal(expected)})
                self.assertTrue(item['source_values_match'], item)
                self.assertEqual(item['source_weight_lag_years'], 1)
                native['data']['structure']['attributes']['dataset'][1]['values'][0]['id'] = '6'
                other = root/'wrong-units'; archive(other, sid, responses)
                self.assertEqual(audit(other, sid, {}).get('failure_code'), 'source_identity_mismatch')
                native['data']['structure']['attributes']['dataset'][1]['values'][0]['id'] = '0'

    def test_eurostat_corporate_gdp_selects_exact_sector_currency_and_common_years(self):
        sid = 'profit.eu27.corporate_operating_surplus_gdp'
        responses = []
        for sector, measure, amount in [('S11', 'B2A3G', 20), ('S12', 'B2A3G', 5), ('S1', 'B1GQ', 100)]:
            responses.append(('https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/nasa_10_nf_tr?'
                              f'freq=A&unit=CP_MEUR&direct=RECV&sector={sector}&na_item={measure}&geo=EU27_2020',
                              eurostat_payload(sector=sector, na_item=measure, years=['2024'], values={'0': amount})))
        with TemporaryDirectory() as temp:
            root = Path(temp); archive(root, sid, responses)
            item = audit(root, sid, {date(2024, 1, 1): Decimal(25)})
            self.assertTrue(item['source_values_match'], item)
            self.assertEqual(len(item['source_dependencies']), 3)

    def test_eurostat_nfc_published_ratio_keeps_gva_denominator_and_missing_years(self):
        sid = 'profit.eu27.nonfinancial_gross_surplus_value_added'
        native = eurostat_payload(dataset='nasa_10_ki', sector='S11',
            na_item='B2G_B3G_RAT_S11', unit='PC', years=['2023', '2024', '2025'],
            values={'0': '41.46', '2': '39.83'})
        values = {date(2023, 1, 1): Decimal('41.46'), date(2025, 1, 1): Decimal('39.83')}
        with TemporaryDirectory() as temp:
            root = Path(temp)
            with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=native))) as client:
                CapturedProvider(ProviderRouter(client), root).fetch(sid)
            with patch('finance_dashboard.eurostat_corporate.parse_eurostat_annual_series', side_effect=AssertionError('ingestion parser used')):
                item = audit(root, sid, values)
            self.assertTrue(item['source_values_match'], item)
            self.assertEqual(item['source_periods'], 2)
            self.assertEqual(item['source_value_kind'], 'publisher_observations')
            self.assertEqual(item['source_denominator'], 'S11 gross value added')
            source_url = json.loads(next(root.glob('responses/*/*/manifest.json')).read_bytes())['sources'][0]['url']
            for dimension, bad in [('geo', 'EU28'), ('sector', 'S12'), ('unit', 'CP_MEUR'), ('na_item', 'B1GQ')]:
                with self.subTest(dimension=dimension):
                    wrong = json.loads(json.dumps(native))
                    wrong['dimension'][dimension]['category']['index'] = {bad: 0}
                    other = root/dimension; archive(other, sid, [(source_url, wrong)])
                    self.assertEqual(audit(other, sid, {}).get('failure_code'), 'source_identity_mismatch')

    def test_oecd_composite_has_original_accounts_both_gdp_units_and_coverage(self):
        from finance_dashboard.oecd_corporate import OECD_DATA_URL, oecd_annual_data_key
        rows = input_rows()
        for row in rows:
            if row['REF_AREA'] == 'AUS' and row['SECTOR'] == 'S11': row['OBS_VALUE'] = '40'
            if row['REF_AREA'] == 'CAN': row['CURRENCY'] = 'CAD'
        rows = [row for row in rows if not (row['REF_AREA'] == 'CAN' and row['TRANSACTION'] == 'D21X31')]
        weights = wdi_payload()
        for row in weights[1]:
            if row['countryiso3code'] == 'AUS': row['value'] = 2_000_000_000_000
        local = wdi_payload()
        for row in local[1]:
            row['indicator']['id'] = 'NY.GDP.MKTP.CN'; row['value'] = 100_000_000
        responses = [(OECD_DATA_URL+'/'+oecd_annual_data_key()+'?format=csvfile&startPeriod=1990', csv_text(rows)),
                     (WDI+'all/indicator/NY.GDP.MKTP.CD?format=json&per_page=20000&date=1990:2026', weights),
                     (WDI+'all/indicator/NY.GDP.MKTP.CN?format=json&per_page=20000&date=1990:2026', local)]
        # AUS has 45% surplus/GDP and double GDP weight; CAN needs the
        # strictly currency-matched local-GDP fallback to remain included.
        for sid, expected in [('profit.oecd38.corporate_gross_surplus_gdp', Decimal(890)/Decimal(34)),
                              ('profit.oecd38.corporate_gross_surplus_gdp_coverage', Decimal(3400)/Decimal(39)),
                              ('profit.oecd38.corporate_gross_surplus_member_count', Decimal(33))]:
            with self.subTest(sid=sid), TemporaryDirectory() as temp:
                root = Path(temp); archive(root, sid, responses)
                with patch('finance_dashboard.oecd_corporate.compute_oecd_corporate_surplus', side_effect=AssertionError('ingestion formula used')):
                    item = audit(root, sid, {date(2023, 1, 1): expected})
                self.assertTrue(item['source_values_match'], item)
                self.assertEqual(len(item['source_dependencies']), 3)

    def test_gold_correlation_requires_original_gold_and_index_and_consecutive_months(self):
        from test_captured_source_families import xlsx_from_factual_cells
        from finance_dashboard.providers import PINK_SHEET_URL
        sid = 'gold.world.equity_correlation'
        gold_rows = [['Date', 'Gold'], ['', '($/troy oz)']]
        index_rows = []
        for number in range(40):
            year, month = 2020+number//12, 1+number%12
            level = 100+number*number
            gold_rows.append([f'{year}M{month:02d}', level])
            # The mean matches gold, while the final daily close differs.
            index_rows.extend([{'calc_date': f'{year}{month:02d}{day:02d}', 'level_eod': level+delta}
                               for day, delta in ((2, -10), (15, 10))])
        workbook = xlsx_from_factual_cells(gold_rows, 'Monthly Prices')
        original = {'msci_index_code': '892400', 'index_variant_type': 'NETR',
                    'ISO_currency_symbol': 'USD', 'indexes': {'INDEX_LEVELS': index_rows}}
        with TemporaryDirectory() as temp:
            root = Path(temp)
            def respond(request):
                return httpx.Response(200, content=workbook) if str(request.url).startswith(PINK_SHEET_URL) else httpx.Response(200, json=original)
            with httpx.Client(transport=httpx.MockTransport(respond)) as client:
                captured = CapturedProvider(ProviderRouter(client), root).fetch(sid)
            expected = {date(2023, month, 1): Decimal(1) for month in range(1, 5)}
            self.assertEqual(captured.observations, expected)
            with patch('finance_dashboard.remaining_sources.gold_acwi_rolling_correlation', side_effect=AssertionError('ingestion formula used')):
                item = audit(root, sid, expected)
            self.assertTrue(item['source_values_match'], item)
            self.assertEqual(len(item['source_dependencies']), 2)
            # Missing the first month removes the first eligible window,
            # while the next three windows retain their original values.
            original['indexes']['INDEX_LEVELS'] = [row for row in index_rows if not row['calc_date'].startswith('202001')]
            other = root/'missing-month'
            manifest = json.loads(next(root.glob('responses/*/*/manifest.json')).read_bytes())
            archive(other, sid, [(PINK_SHEET_URL, workbook), (manifest['sources'][1]['url'], original)])
            missing = audit(other, sid, expected)
            self.assertEqual(missing['source_periods'], 3)
            self.assertEqual(missing['extra_stored_periods'], ['2023-01-01'])
            self.assertEqual(missing['mismatched_source_values'], [])

    def test_cited_topten_metadata_is_not_original_publisher_evidence(self):
        with TemporaryDirectory() as temp:
            item = audit(Path(temp), 'concentration.global.msci_acwi_published_top10', {})
            self.assertFalse(item['source_values_match'])
            self.assertEqual(item['failure_code'], 'original_msci_documents_missing_or_invalid')
