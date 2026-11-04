"""Independent original-source selection for academic-return reconciliation."""
from datetime import date
from decimal import Decimal
from hashlib import sha256
import importlib
import importlib.util
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx
from finance_dashboard.research_returns import FRENCH_SERIES, SWINKELS_SERIES, ResearchReturnsClient
from finance_dashboard.source_reconciliation import EvidenceError, _selected_manifest, _original_file
from test_canonical_persistence import source_response


class ReturnOriginalReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('finance_dashboard.return_source_reconciliation'),
                             'Independent return original selector is missing')
        self.reader = importlib.import_module('finance_dashboard.return_source_reconciliation').read_return_originals
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        with httpx.Client(transport=httpx.MockTransport(source_response)) as http:
            client = ResearchReturnsClient(http, archive_dir=self.root)
            for sid in list(FRENCH_SERIES)+list(SWINKELS_SERIES):
                client.fetch(sid)

    def read(self, ids=None):
        return self.reader(self.root, ids or list(FRENCH_SERIES)+list(SWINKELS_SERIES), _selected_manifest, _original_file)

    def test_independent_raw_values_keep_all_country_methods_native_scale_and_explicit_total(self):
        # Wrong columns, implicit percent scaling or using excess as total fail.
        values, proof = self.read()
        self.assertEqual(set(values), set(FRENCH_SERIES)|set(SWINKELS_SERIES))
        self.assertEqual(sum(len(values[sid]) for sid in SWINKELS_SERIES), 7435)
        self.assertEqual(sum(len(values[sid]) for sid in FRENCH_SERIES), 114)
        self.assertEqual(values['returns.french.developed.market_total_usd'][date(1990,7,1)], Decimal('1.45'))
        self.assertEqual(values['returns.french.developed.market_excess_usd'][date(1990,7,1)], Decimal('0.77'))
        self.assertEqual(values['returns.french.emerging.market_total_usd'][date(1989,7,1)], Decimal('1.30'))
        self.assertEqual(values['returns.swinkels.de.sovereign_10y_modelled_local'][date(1972,10,1)], Decimal('-0.018087803085468472'))
        self.assertEqual(values['returns.swinkels.us.sovereign_10y_original_1962_usd'][date(1962,1,1)], Decimal('0.000073667611639348894'))
        self.assertEqual(proof['returns.french.developed.market_total_usd']['source_native_unit'], 'percent')
        self.assertEqual(proof['returns.swinkels.de.sovereign_10y_modelled_local']['source_native_unit'], 'ratio')
        self.assertTrue(all(len(x['source_sha256'])==64 and len(x['source_manifest_sha256'])==64 for x in proof.values()))
        self.assertTrue(all(x['selection_method']=='acquisition_receipt' for x in proof.values()))

    def test_subset_reads_only_requested_native_series(self):
        ids = ['returns.swinkels.jp.sovereign_10y_modelled_local']
        values, proof = self.read(ids)
        self.assertEqual(list(values), ids)
        self.assertEqual(list(proof), ids)
        self.assertEqual(len(values[ids[0]]), 579)

    def test_changed_raw_binary_is_not_accepted_as_current_original(self):
        # A DB comparison must never trust raw bytes merely because a path exists.
        original = next(self.root.glob('research-returns/french/developed/*/source.zip'))
        original.write_bytes(original.read_bytes()+b'tampered')
        with self.assertRaises(EvidenceError) as raised:
            self.read(['returns.french.developed.market_total_usd'])
        self.assertEqual(raised.exception.code, 'source_hash_mismatch')

    def test_wrong_native_unit_or_source_convention_fails_even_with_valid_manifest_receipt(self):
        # A correctly hashed archive with the wrong measurement contract is unusable.
        manifest = next(self.root.glob('research-returns/french/developed/*/manifest.json'))
        record = json.loads(manifest.read_text());record['data_metadata']['native_unit']='ratio'
        manifest.write_text(json.dumps(record))
        for receipt in manifest.parent.parent.glob('retrievals/*.json'):
            item=json.loads(receipt.read_text());item['manifest_sha256']=sha256(manifest.read_bytes()).hexdigest();receipt.write_text(json.dumps(item))
        with self.assertRaises(EvidenceError) as raised:
            self.read(['returns.french.developed.market_total_usd'])
        self.assertEqual(raised.exception.code, 'source_identity_mismatch')

    def test_missing_acquisition_receipt_and_broken_receipt_hash_fail_closed(self):
        parent = self.root/'research-returns/swinkels'
        receipt = next((parent/'retrievals').glob('*.json'))
        receipt.unlink()
        with self.assertRaises(EvidenceError):
            self.read(['returns.swinkels.us.sovereign_10y_modelled_local'])
        french_parent=self.root/'research-returns/french/developed'
        receipt=next((french_parent/'retrievals').glob('*.json'));record=json.loads(receipt.read_text());record['manifest_sha256']='0'*64;receipt.write_text(json.dumps(record))
        with self.assertRaises(EvidenceError):
            self.read(['returns.french.developed.market_total_usd'])

    def test_unknown_series_and_absent_source_evidence_fail_closed(self):
        with self.assertRaises(EvidenceError):
            self.read(['returns.unidentified.global_bond'])
        with TemporaryDirectory() as empty:
            with self.assertRaises(EvidenceError):
                self.reader(Path(empty), ['returns.french.developed.market_total_usd'], _selected_manifest, _original_file)

    def test_a_b_a_receipts_select_latest_acquisition_of_older_bytes(self):
        # Lexicographic bundle ordering must not choose a superseded correction.
        from test_research_returns import FIXTURES
        original=(FIXTURES/'developed_excerpts.csv').read_text()
        for body in (original.replace('0.77    ,0.53','0.78    ,0.53',1),original):
            with httpx.Client(transport=httpx.MockTransport(lambda request: source_response(request, body))) as http:
                ResearchReturnsClient(http,archive_dir=self.root).fetch('returns.french.developed.market_total_usd')
        values,proof=self.read(['returns.french.developed.market_total_usd'])
        self.assertEqual(values['returns.french.developed.market_total_usd'][date(1990,7,1)],Decimal('1.45'))
        self.assertEqual(proof['returns.french.developed.market_total_usd']['selection_method'],'acquisition_receipt')

    def test_empty_monthly_original_cannot_generate_a_successful_empty_reconciliation(self):
        # Even a self-consistent hash/receipt envelope cannot make empty data usable.
        from test_research_returns import FIXTURES, french_zip
        parent=self.root/'research-returns/french/developed'
        manifest=next(parent.glob('*/manifest.json'));record=json.loads(manifest.read_text())
        body=(FIXTURES/'developed_excerpts.csv').read_text().split('199007')[0]
        raw=french_zip(body=body);(manifest.parent/'source.zip').write_bytes(raw)
        record['sources']['data']['sha256']=sha256(raw).hexdigest();record['sources']['data']['bytes']=len(raw)
        manifest.write_text(json.dumps(record));manifest_hash=sha256(manifest.read_bytes()).hexdigest()
        digest=sha256(json.dumps({'data':sha256(raw).hexdigest()},sort_keys=True).encode()).hexdigest()
        manifest.parent.rename(parent/digest)
        for receipt in (parent/'retrievals').glob('*.json'):
            item=json.loads(receipt.read_text());item['bundle_digest']=digest;item['manifest_sha256']=manifest_hash;receipt.write_text(json.dumps(item))
        with self.assertRaises(EvidenceError) as raised:
            self.read(['returns.french.developed.market_total_usd'])
        self.assertEqual(raised.exception.code,'source_empty')
