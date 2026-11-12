"""One-container dashboard: same-origin HTML/API, SQLite persistence and refresh lifecycle."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date
import os
from pathlib import Path
import tempfile
import threading
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import text

from finance_dashboard.api import create_app
from finance_dashboard.catalog import load_documents
from finance_dashboard.database import make_engine, Base
from finance_dashboard.standalone import refresh_interval


@contextmanager
def environ(**updates):
    old = {k: os.environ.get(k) for k in updates}
    try:
        for key, value in updates.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class StandaloneContainerTests(TestCase):
    def test_deferred_first_refresh_keeps_startup_read_only_until_interval(self):
        from finance_dashboard.standalone import refresh_loop
        collected = threading.Event()
        class StopAtFirstWait:
            def is_set(self): return False
            def wait(self, seconds):
                self.seconds = seconds
                return True
        stop = StopAtFirstWait()
        def collect(*args, **kwargs):
            collected.set()
            return 0
        with (environ(FINANCE_REFRESH_ON_START='0', FINANCE_VINTAGE_REFRESH='0',
                      FINANCE_SEC_HOLDINGS_REFRESH='0', FINANCE_AUTO_BACKUP='0'),
              patch('finance_dashboard.worker.refresh_all', side_effect=collect)):
            refresh_loop(None, stop, interval_seconds=86400, include_markets=False, refresh_wisesheets=False)
        self.assertFalse(collected.is_set())
        self.assertEqual(stop.seconds, 86400)

    def test_deferred_schedule_survives_restarts_without_another_full_interval(self):
        import json
        from unittest.mock import patch
        from finance_dashboard.standalone import refresh_loop
        class Shutdown:
            def __init__(self): self.seconds = None
            def is_set(self): return False
            def wait(self, seconds):
                self.seconds = seconds
                return True
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "maintenance" / "refresh-schedule.json"
            now = [1_800_000_000.0]
            def boot():
                stop = Shutdown()
                with (environ(FINANCE_REFRESH_ON_START="0",
                              FINANCE_REFRESH_SCHEDULE_PATH=str(state)),
                      patch("finance_dashboard.standalone.time.time",
                            side_effect=lambda: now[0])):
                    refresh_loop(None, stop, interval_seconds=86400,
                                 include_markets=False, refresh_wisesheets=False)
                return stop.seconds
            self.assertEqual(boot(), 86400)
            self.assertEqual(json.loads(state.read_text())["next_due_unix"],
                             now[0] + 86400)
            now[0] += 1800
            self.assertEqual(boot(), 86400 - 1800)
            now[0] += 80000
            self.assertEqual(boot(), 4600)
            self.assertEqual(json.loads(state.read_text())["schema_version"], 1)

    def test_overdue_refresh_deadline_is_not_reset_when_container_restarts(self):
        from unittest.mock import patch
        from finance_dashboard.standalone import refresh_loop
        class Shutdown:
            def is_set(self): return False
            def wait(self, seconds): return True
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "refresh-schedule.json"
            state.write_text('{"schema_version":1,"next_due_unix":1700000000.0}')
            seen = []
            class StopOne:
                def __init__(self): self.count = 0
                def is_set(self): return self.count > 0
                def wait(self, seconds):
                    self.count += 1
                    return True
            stop = StopOne()
            with (environ(FINANCE_REFRESH_ON_START="0",
                          FINANCE_REFRESH_SCHEDULE_PATH=str(state),
                          FINANCE_VINTAGE_REFRESH="0",
                          FINANCE_SEC_HOLDINGS_REFRESH="0",
                          FINANCE_AUTO_BACKUP="0"),
                  patch("finance_dashboard.standalone.time.time",
                        return_value=1800000000.0),
                  patch("finance_dashboard.worker.refresh_all",
                        side_effect=lambda *args, **kwargs: seen.append(1) or 0),
                  patch("finance_dashboard.worker.refresh_market_all")):
                refresh_loop(None, stop, interval_seconds=86400,
                             include_markets=False, refresh_wisesheets=False)
            self.assertEqual(seen, [1])
            self.assertEqual(json.loads(state.read_text())["next_due_unix"],
                             1800000000.0 + 86400)

    def test_offline_startup_serves_health_without_running_scheduled_publishers(self):
        publisher_work = threading.Event()
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(f"sqlite+pysqlite:///{Path(tmp) / 'finance.sqlite3'}")
            Base.metadata.create_all(engine)
            try:
                with (environ(FINANCE_AUTO_REFRESH="0", FINANCE_AUTO_BACKUP="1",
                              FINANCE_DASHBOARD_UI_DIR=None),
                      patch("finance_dashboard.standalone.refresh_loop",
                            side_effect=lambda *a, **kw: publisher_work.set())):
                    with TestClient(create_app(engine)) as client:
                        self.assertEqual(client.get("/api/health").status_code, 200)
                        self.assertFalse(publisher_work.wait(timeout=0.05))
            finally:
                engine.dispose()

    def test_bundled_html_and_all_existing_api_routes_share_one_origin(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            site = root / "site"
            (site / "assets").mkdir(parents=True)
            (site / "index.html").write_text("<html><title>GCM test</title></html>")
            (site / "assets/app.js").write_text("export const phase3 = true;")
            engine = make_engine(f"sqlite+pysqlite:///{root / 'finance.sqlite3'}")
            Base.metadata.create_all(engine)
            try:
                with environ(FINANCE_DASHBOARD_UI_DIR=str(site), FINANCE_AUTO_REFRESH="0"):
                    app = create_app(engine)
                    with TestClient(app) as client:
                        self.assertIn("GCM test", client.get("/").text)
                        self.assertEqual(client.get("/assets/app.js").status_code, 200)
                        self.assertEqual(client.get("/api/health").json()["status"], "ok")
                        # Catalogue growth must not break the standalone API;
                        # assert the currently registered source contract.
                        self.assertEqual(
                            len(client.get("/api/series").json()["items"]),
                            len(load_documents()[0]["series"]),
                        )
                        self.assertEqual(len(client.get("/api/charts").json()["items"]), 21)
                        response = client.post("/api/query", json={
                            "series_ids": ["policy_rate.us.bis"], "start": "2025-01-01",
                        })
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.json()["series"][0]["status"], "no_data")
                        self.assertEqual(client.get("/docs").status_code, 200)
                        # Retired readouts: no route answers (the page fallback accepts only GET).
                        self.assertIn(client.post("/api/chart-insight", json={
                            "series_ids": ["policy_rate.us.bis", "policy_rate.ea.bis"]
                        }).status_code, (404, 405))
            finally:
                engine.dispose()

    def test_one_background_refresh_thread_with_no_market_containers(self):
        started = threading.Event()
        calls = []
        def fake_refresh(_engine, *, stopped, skip_complete_pinned):
            self.assertTrue(skip_complete_pinned)
            # The scheduler passes a cooperative stop token to each source
            # collector. The previous mock omitted this required keyword,
            # causing a swallowed TypeError and a false startup timeout.
            self.assertFalse(stopped.is_set())
            calls.append("macro")
            started.set()
            return 0
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(f"sqlite+pysqlite:///{Path(tmp) / 'finance.sqlite3'}")
            Base.metadata.create_all(engine)
            try:
                with (environ(FINANCE_AUTO_REFRESH="1", FINANCE_INCLUDE_MARKETS="0",
                              FINANCE_WISESHEETS_REFRESH="0",
                              FINANCE_VINTAGE_REFRESH="0",
                              FINANCE_SEC_HOLDINGS_REFRESH="0",
                              FINANCE_AUTO_BACKUP="0",
                              FINANCE_DASHBOARD_UI_DIR=None, REFRESH_INTERVAL_SECONDS="3600"),
                      patch("finance_dashboard.worker.refresh_all", side_effect=fake_refresh),
                      patch("finance_dashboard.worker.refresh_market_all") as market):
                    with TestClient(create_app(engine)) as client:
                        self.assertTrue(started.wait(timeout=3))
                        self.assertEqual(client.get("/api/health").status_code, 200)
                    market.assert_not_called()
                    self.assertEqual(calls, ["macro"])
            finally:
                engine.dispose()

    def test_local_sqlite_persists_and_has_wal_and_busy_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_url = f"sqlite+pysqlite:///{Path(tmp) / 'finance.sqlite3'}"
            engine = make_engine(db_url)
            Base.metadata.create_all(engine)
            with engine.connect() as conn:
                self.assertEqual(conn.execute(text("PRAGMA journal_mode")).scalar(), "wal")
                self.assertEqual(conn.execute(text("PRAGMA busy_timeout")).scalar(), 30000)
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO series (id,provider,source_key,updated_at) "
                                  "VALUES ('x','TEST','source','2026-11-02')"))
            engine.dispose()
            reopened = make_engine(db_url)
            try:
                with reopened.connect() as conn:
                    self.assertEqual(conn.execute(text("SELECT count(*) FROM series")).scalar(), 1)
            finally:
                reopened.dispose()

    def test_invalid_refresh_interval_and_missing_built_ui_fail_fast(self):
        with environ(REFRESH_INTERVAL_SECONDS="59"):
            with self.assertRaisesRegex(ValueError, "at least 3600"):
                refresh_interval()
        with environ(REFRESH_INTERVAL_SECONDS="bad"):
            with self.assertRaisesRegex(ValueError, "integer"):
                refresh_interval()
        with tempfile.TemporaryDirectory() as tmp:
            engine = make_engine(f"sqlite+pysqlite:///{Path(tmp) / 'finance.sqlite3'}")
            Base.metadata.create_all(engine)
            try:
                with environ(FINANCE_DASHBOARD_UI_DIR=str(Path(tmp) / "missing")):
                    with self.assertRaisesRegex(RuntimeError, "index.html"):
                        create_app(engine)
            finally:
                engine.dispose()


if __name__ == "__main__":
    import unittest
    unittest.main()
