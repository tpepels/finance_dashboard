"""Offline acceptance of one-click source-health repair and original acquisition."""
from __future__ import annotations

from threading import Event
from types import SimpleNamespace
from unittest.mock import patch
import unittest

from finance_dashboard.maintenance_handlers import run_repair_source_health
from finance_dashboard.maintenance_jobs import normalize_options


class Manager:
    engine = object()
    def __init__(self):
        self.events = []
    def _change(self, *args, **kwargs):
        self.events.append(("change", args, kwargs))
    def _progress(self, *args, **kwargs):
        self.events.append(("progress", args, kwargs))


def census(*states):
    return {
        "items": [
            {"id": sid, "family": "macro", "state": status}
            for sid, status in states
        ]
    }


class SourceHealthRepairTests(unittest.TestCase):
    def test_normalizer_rejects_paths_raw_urls_overrides_and_credentials(self):
        self.assertEqual(normalize_options(
            "repair_source_health", {},
            valid_sources=set(), valid_markets=set()), {})
        for options in ({"series_ids": ["gold.usd.spot"]},
                        {"force": True}, {"url": "https://evil.example/"},
                        {"api_key": "secret"}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                normalize_options("repair_source_health", options,
                                  valid_sources=set(), valid_markets=set())

    def test_selects_only_actionable_macro_and_reports_actual_remaining(self):
        before = census(
            ("gold.usd.spot", "collection_failed"),
            ("prices.ea.hicp_index", "stale"),
            ("inequality.world.pretax_income.top10", "refresh_deferred_with_data"),
            ("activity.us.oecd_cli", "available"))
        after = census(
            ("gold.usd.spot", "available"),
            ("prices.ea.hicp_index", "stale"),
            ("inequality.world.pretax_income.top10", "available"),
            ("activity.us.oecd_cli", "available"))
        manager = Manager()
        with patch("finance_dashboard.source_coverage.build_coverage",
                   side_effect=[before, after]), \
             patch("finance_dashboard.worker.refresh_all", return_value=1) as refresh:
            result = run_repair_source_health(manager, "job1",
                "repair_source_health", {}, Event())
        self.assertEqual(result["selected_sources"], 3)
        self.assertEqual(result["issues_before"], 3)
        self.assertEqual(result["issues_after"], 1)
        self.assertEqual(result["resolved_issues"], 2)
        self.assertEqual(result["failed_sources"], 1)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["remaining_series_ids"], ["prices.ea.hicp_index"])
        self.assertEqual(refresh.call_args.kwargs["series_ids"],
            {"gold.usd.spot", "prices.ea.hicp_index",
             "inequality.world.pretax_income.top10"})
        self.assertFalse(refresh.call_args.kwargs["full"])
        self.assertNotIn("skip_complete_pinned", refresh.call_args.kwargs)

    def test_swinkels_failed_pinned_original_is_retried_not_silenced(self):
        sid = "returns.swinkels.au.sovereign_10y_modelled_local"
        rows = census((sid, "refresh_failed_with_data"))
        manager = Manager()
        with patch("finance_dashboard.source_coverage.build_coverage",
                   side_effect=[rows, census((sid, "available"))]), \
             patch("finance_dashboard.worker.refresh_all", return_value=0) as refresh:
            result = run_repair_source_health(manager, "job", "repair_source_health",
                                              {}, Event())
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["resolved_issues"], 1)
        self.assertEqual(refresh.call_args.kwargs["series_ids"], {sid})

    def test_msi_regional_collects_exact_affected_originals_before_reingestion(self):
        ids = ("valuation.europe.msci_forward_pe",
               "valuation.japan.msci_trailing_pe",
               "valuation.eafe.msci_forward_pe")
        before = census(*[(sid, "stale") for sid in ids])
        after = census(*[(sid, "available") for sid in ids])
        manager = Manager()
        sequence = []
        def acquire(*args, **kwargs):
            sequence.append("archive")
            self.assertEqual(kwargs["indexes"], {"EUROPE", "JAPAN", "EAFE"})
            self.assertIsNotNone(kwargs["stopped"])
            return {"stored_verified": 3}
        def refresh(*args, **kwargs):
            sequence.append("ingest")
            return 0
        with patch("finance_dashboard.source_coverage.build_coverage",
                   side_effect=[before, after]), \
             patch("finance_dashboard.msci_regional_factsheets.collect",
                   side_effect=acquire), \
             patch("finance_dashboard.worker.refresh_all", side_effect=refresh):
            result = run_repair_source_health(manager, "job", "repair_source_health",
                                              {}, Event())
        self.assertEqual(sequence, ["archive", "ingest"])
        self.assertEqual(result["msci_original_acquisition"]["stored_verified"], 3)
        self.assertEqual(result["status"], "complete")

    def test_when_all_data_healthy_does_not_attempt_source_requests(self):
        manager = Manager()
        with patch("finance_dashboard.source_coverage.build_coverage",
                   return_value=census(("gold.usd.spot", "available"))), \
             patch("finance_dashboard.worker.refresh_all") as refresh:
            result = run_repair_source_health(manager, "job", "repair_source_health",
                                              {}, Event())
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["selected_sources"], 0)
        refresh.assert_not_called()


if __name__ == "__main__":
    unittest.main()
