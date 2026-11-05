"""One maintenance registry drives UI actions, validation and execution."""
from datetime import date
from unittest.mock import Mock, patch
import unittest

from finance_dashboard.maintenance_jobs import ACTION_REGISTRY, PUBLIC_ACTIONS, normalize_options
from finance_dashboard import maintenance_handlers
from finance_dashboard.maintenance_handlers import execute_action


class MaintenanceRegistryTests(unittest.TestCase):
    SOURCES = {"bond.us.nominal_10y", "labour.de.pwt_labour_share"}
    MARKETS = {"vt", "sxr8"}

    def normalize(self, action, options):
        return normalize_options(
            action, options, valid_sources=self.SOURCES,
            valid_markets=self.MARKETS)

    def test_declared_handlers_and_options_cover_all_public_actions(self):
        self.assertEqual(len(ACTION_REGISTRY), 10)
        self.assertEqual(PUBLIC_ACTIONS, frozenset(ACTION_REGISTRY))
        for action, spec in ACTION_REGISTRY.items():
            self.assertEqual(spec.action, action)
            self.assertTrue(callable(getattr(maintenance_handlers, spec.handler, None)))

    def test_all_sync_and_refresh_options_have_one_canonical_normalizer(self):
        for action in ("sync_current", "sync_history"):
            result = self.normalize(action, {})
            self.assertEqual(result["series_ids"], sorted(self.SOURCES))
            self.assertEqual(result["instrument_ids"], sorted(self.MARKETS))
            with self.assertRaises(ValueError):
                self.normalize(action, {"series_ids": ["vt"]})
        self.assertEqual(self.normalize("refresh_sources", {
            "series_ids": ["bond.us.nominal_10y"]}),
            {"series_ids": ["bond.us.nominal_10y"]})
        self.assertEqual(self.normalize("refresh_markets", {
            "instrument_ids": [], "currencies": ["USD"]}),
            {"instrument_ids": [], "currencies": ["USD"]})
        self.assertEqual(self.normalize("collect_sec", {"limit": 7}), {"limit": 7})
        self.assertEqual(self.normalize("check_sec", {}), {})
        self.assertEqual(self.normalize("check_alfred", {}), {})
        self.assertEqual(self.normalize("refresh_earnings", {}), {})
        self.assertEqual(self.normalize("backup", {}), {})

    def test_invalid_commands_paths_and_credentials_are_rejected(self):
        for action, options in (
            ("backup", {"path": "/tmp/anywhere"}),
            ("check_sec", {"url": "https://evil.example"}),
            ("refresh_sources", {"series_ids": ["not_in_catalog"]}),
            ("refresh_markets", {"currencies": ["INVALID"]}),
            ("collect_sec", {"limit": True}),
            ("backfill_alfred", {"max_requests": 10000}),
        ):
            with self.subTest(action=action):
                with self.assertRaises(ValueError):
                    self.normalize(action, options)
        with self.assertRaises(ValueError):
            self.normalize("unknown_action", {})

    def test_registered_handler_is_called_without_second_dispatcher(self):
        manager, stop = Mock(), Mock()
        expected = {"status": "complete"}
        target = Mock(__name__="run_backup", return_value=expected)
        with patch.object(maintenance_handlers, "run_backup", target):
            self.assertIs(execute_action(manager, "job", "backup", {}, stop), expected)
        target.assert_called_once_with(manager, "job", "backup", {}, stop)


if __name__ == "__main__":
    unittest.main()
