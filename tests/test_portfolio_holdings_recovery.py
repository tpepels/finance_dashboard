"""A complete application recovery includes private owner position state."""
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from finance_dashboard.backup import backup_local, restore_backup


class PortfolioHoldingsRecoveryTests(unittest.TestCase):
    def test_private_position_state_round_trips_to_an_empty_restore(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/'finance.sqlite3'
            with sqlite3.connect(source) as connection:
                connection.execute('CREATE TABLE example (value INTEGER)')
                connection.execute('INSERT INTO example VALUES (42)')
            private = root/'portfolio-holdings.json'
            private.write_text(json.dumps({'version': 1, 'revision': 3, 'positions': [{'id': 'private-fixture'}]}))
            bundle = backup_local(root/'backups', source_db=source, evidence_roots={},
                                  portfolio_holdings_path=private)
            self.assertEqual(bundle['application_state']['components']['portfolio_holdings']['member'],
                             'portfolio-holdings.json')
            manifest = next((root/'backups').glob('*.json'))
            restore_backup(manifest, root/'restored')
            self.assertEqual((root/'restored/portfolio-holdings.json').read_bytes(), private.read_bytes())

