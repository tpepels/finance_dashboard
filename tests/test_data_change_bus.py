"""Post-commit pub/sub, reconciliation and source-health race regressions."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import time
import unittest

from finance_dashboard.collection_workflow import SourceHealthCache
from finance_dashboard.data_change_bus import DataChangeCoordinator, publish_change, subscribe
from finance_dashboard.engine.acceptance import (
    AcceptanceCache, AcceptanceLoading, AcceptanceSnapshot)
from finance_dashboard.standalone import maintenance_network_lock


def wait_for(check, timeout=4):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(.015)
    return False


class Sink:
    def __init__(self):
        self.events = []

    def changed(self, reason):
        self.events.append(reason)


class Worker:
    def __init__(self):
        self.count = 0

    def invalidate(self):
        self.count += 1


class Health:
    def __init__(self):
        self.count = 0

    def mark_dirty(self):
        self.count += 1


class Engine:
    pass


class PostIngestionTests(unittest.TestCase):
    def test_two_engines_do_not_leak_notifications(self):
        left, right = Engine(), Engine()
        a, b = Sink(), Sink()
        subscribe(left, a)
        subscribe(right, b)
        publish_change(left, "committed")
        self.assertEqual(a.events, ["committed"])
        self.assertEqual(b.events, [])

    def test_many_commits_coalesce_one_assessment_and_health_scan(self):
        engine = Engine()
        acceptance, health = Worker(), Health()
        coordinator = DataChangeCoordinator(acceptance, health, quiet_seconds=.08)
        subscribe(engine, coordinator)
        for _ in range(25):
            publish_change(engine, "series_ingested")
        self.assertTrue(wait_for(lambda: coordinator.status()["state"] == "complete"))
        self.assertEqual(acceptance.count, 1)
        self.assertEqual(health.count, 1)
        self.assertEqual(coordinator.status()["events_reconciled"], 25)

    def test_new_commits_wait_for_active_refresh_batch(self):
        acceptance, health = Worker(), Health()
        coordinator = DataChangeCoordinator(acceptance, health, quiet_seconds=.01)
        maintenance_network_lock.acquire()
        try:
            coordinator.changed("source_ingested")
            time.sleep(.06)
            self.assertEqual(acceptance.count, 0)
            self.assertEqual(coordinator.status()["state"], "pending")
        finally:
            maintenance_network_lock.release()
        self.assertTrue(wait_for(lambda: coordinator.status()["state"] == "complete",
                                 timeout=3))
        self.assertEqual(acceptance.count, 1)
        self.assertEqual(health.count, 1)

    def test_ingestion_arriving_mid_health_scan_forces_another_scan(self):
        with TemporaryDirectory() as temporary:
            entered, release = Event(), Event()
            calls = []
            def scan():
                calls.append(1)
                if len(calls) == 1:
                    entered.set()
                    release.wait(3)
                return {"asof": "2026-11-14", "summary": {"macro": {
                    "total": len(calls), "with_data": len(calls),
                    "needs_attention": 0}}}
            cache = SourceHealthCache(scan, path=Path(temporary) / "health.json")
            cache.mark_dirty()
            self.assertTrue(entered.wait(2))
            cache.mark_dirty()
            release.set()
            self.assertTrue(wait_for(lambda: len(calls) == 2 and
                                     cache.status(schedule=False)["state"] == "ready"))
            self.assertEqual(cache.status(schedule=False)["snapshot"]["sources"]["total"], 2)

    def test_invalidation_mid_phase2_evaluation_discards_old_snapshot_and_restarts(self):
        pending = []
        calls = []
        cache = None
        first = AcceptanceSnapshot(datetime(2026, 11, 13, tzinfo=timezone.utc), {})
        second = AcceptanceSnapshot(datetime(2026, 11, 14, tzinfo=timezone.utc), {})
        def loader():
            calls.append(1)
            if len(calls) == 1:
                cache.invalidate()
                return first
            return second
        cache = AcceptanceCache(loader, ttl_seconds=3600, spawn=pending.append)
        cache.warm()
        pending.pop(0)()
        self.assertIsNone(cache.peek())
        with self.assertRaises(AcceptanceLoading):
            cache.get()
        self.assertEqual(len(pending), 1)
        pending.pop(0)()
        self.assertIs(cache.get(), second)

    def test_conflicting_evidence_retries_twice_then_reports_failure(self):
        from finance_dashboard.engine.evidence_guard import AcceptedInputsChanged
        pending = []
        count = []
        def loader():
            count.append(1)
            raise AcceptedInputsChanged("source changed during phase2")
        cache = AcceptanceCache(loader, ttl_seconds=3600, spawn=pending.append)
        cache.warm()
        while pending:
            pending.pop(0)()
        self.assertEqual(len(count), 3)
        self.assertFalse(cache.loading)


if __name__ == "__main__":
    unittest.main()
