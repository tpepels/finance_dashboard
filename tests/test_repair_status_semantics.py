"""Unresolved source gaps must not be reported as successful repairs."""
from threading import Event
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from finance_dashboard.maintenance_handlers import run_repair_source_health


class RepairResultSemanticsTests(TestCase):
    def test_attempted_every_source_with_remaining_gaps_is_partial_not_complete(self):
        class Manager:
            engine = object()
            def _change(self, *args, **kwargs):
                return None
            def _progress(self, *args, **kwargs):
                return None

        coverage = {"items": [
            {"id": "macro.example", "family": "macro", "state": "stale"}
        ]}
        with (
            patch("finance_dashboard.catalog.load_documents",
                  return_value=({"series": [{
                      "id": "macro.example", "provider": "fred", "status": "mapped"
                  }]},)),
            patch("finance_dashboard.market.instruments", return_value=[]),
            patch("finance_dashboard.provider_registry.get_provider",
                  return_value=SimpleNamespace(acquisition="api")),
            patch("finance_dashboard.source_coverage.build_coverage",
                  return_value=coverage),
            patch("finance_dashboard.worker.refresh_all", return_value=1),
        ):
            result = run_repair_source_health(Manager(), "job-1", "repair_source_health",
                                              {}, Event())
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["reason"], "source_gaps_remaining")
        self.assertEqual(result["selected_sources"], 1)
        self.assertEqual(result["resolved_issues"], 0)
        self.assertEqual(result["issues_after"], 1)
        self.assertEqual(result["failed_sources"], 1)
        self.assertEqual(result["remaining_series_ids"], ["macro.example"])
