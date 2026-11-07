"""Independent raw response versus persisted-history proof gates."""
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from finance_dashboard.providers import ProviderRouter
from finance_dashboard.source_capture import SourceAcquisition
from finance_dashboard.source_reconciliation import reconcile
from test_phase2_source_reconcile import database, add


class CapturedSourcesTests(unittest.TestCase):
    def test_public_fred_html_fallback_reconciles_visible_and_hidden_native_rows(self):
        from decimal import Decimal
        import sqlite3
        sid='rates.us.nominal_2y'
        html='''<html><table><tr><th>Series ID</th><td>DGS2</td></tr></table>
        <table id="data-table-observations"><tr><th>DATE</th><th>VALUE</th></tr>
        <tr><th>2024-01-02</th><td>3.95</td></tr></table>
        <div id="extra-rows">#2024-01-03|3.91 #2024-01-04| . #2024-01-05|3.94</div></html>'''
        with TemporaryDirectory() as temp,patch.dict('os.environ',{'FRED_API_KEY':''}):
            root=Path(temp);db=root/'history.db';database(db)
            def source(request):
                return httpx.Response(200,text=html) if request.url.path=='/data/DGS2' else httpx.Response(503)
            with httpx.Client(transport=httpx.MockTransport(source)) as http:
                result=SourceAcquisition(ProviderRouter(http),root).fetch(sid)
            self.assertEqual(result.observations,{date(2024,1,2):Decimal('3.95'),
                date(2024,1,3):Decimal('3.91'),date(2024,1,5):Decimal('3.94')})
            with sqlite3.connect(db) as connection:
                connection.executemany('INSERT INTO observation_versions(series_id,period,value,first_seen_at,ingestion_run_id) VALUES(?,?,?,?,?)',[
                    (sid,day.isoformat(),str(value),'2026-11-04 10:00:00','source-run')
                    for day,value in result.observations.items()])
            report=reconcile('sqlite:///'+str(db),root,[sid])
            self.assertTrue(report['passed'])
            self.assertEqual(report['series'][0]['source_periods'],3)

    def test_independent_fred_html_selector_rejects_wrong_series_hidden_truncation_and_duplicates(self):
        from finance_dashboard.captured_sources import _fred
        from finance_dashboard.source_reconciliation import EvidenceError
        definition={'source_key':'DGS2','frequency':'D'}
        body='''<table><tr><th>Series ID</th><td>DGS2</td></tr></table>
        <table id="data-table-observations"><tr><th>DATE</th><th>VALUE</th></tr>
        <tr><td>2024-01-02</td><td>3.95</td></tr></table>
        <div id="extra-rows">#2024-01-03|3.91</div>'''
        for bad in (body.replace('<td>DGS2</td>','<td>DGS10</td>'),
                    body.replace('#2024-01-03|3.91','#2024-01-03'),
                    body.replace('id="extra-rows"','id="other"'),
                    body.replace('#2024-01-03','#2024-01-02'),
                    body+body):
            with self.subTest(bad=bad[-70:]):
                with self.assertRaises(EvidenceError):
                    _fred(bad,definition,'https://fred.stlouisfed.org/data/DGS2')

    def test_full_fred_originals_compare_all_periods_and_newer_partial_capture_cannot_certify_revisions(self):
        sid = "bond.us.nominal_10y"
        original = {"count": 2, "offset": 0, "observations": [
            {"date": "2024-01-02", "value": "3.95"},
            {"date": "2024-01-03", "value": "3.91"}]}
        with TemporaryDirectory() as temp, patch.dict("os.environ", {"FRED_API_KEY": "secret"}):
            root = Path(temp)
            db = root / "history.db"
            database(db)
            with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=original))) as http:
                captured = SourceAcquisition(ProviderRouter(http), root)
                captured.fetch(sid)
                # Use direct dates because the existing annual fixture helper is deliberately unsuitable here.
                import sqlite3
                with sqlite3.connect(db) as connection:
                    connection.executemany("INSERT INTO observation_versions(series_id,period,value,first_seen_at,ingestion_run_id) VALUES(?,?,?,?,?)", [
                        (sid, "2024-01-02", "3.95", "2026-11-04 10:00:00", "source-run"),
                        (sid, "2024-01-03", "3.91", "2026-11-04 10:00:00", "source-run")])
                report = reconcile("sqlite:///" + str(db), root, [sid])
                self.assertTrue(report["passed"])
                proof = report["series"][0]
                self.assertEqual(proof["source_periods"], 2)
                self.assertRegex(proof["stored_observations_sha256"], r"^[0-9a-f]{64}$")
                self.assertRegex(proof["source_contract_sha256"], r"^[0-9a-f]{64}$")
                # A consistent scheduled overlap capture is preserved but does
                # not displace the full snapshot as certification evidence.
                captured.fetch(sid, date(2024, 1, 3))
                self.assertTrue(reconcile("sqlite:///" + str(db), root, [sid])["passed"])
            # A newer overlap that revised a value, now stored as the current
            # version, must not let the stale full snapshot certify history.
            revised = {"count": 1, "offset": 0, "observations": [{"date": "2024-01-03", "value": "3.99"}]}
            with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=revised))) as http:
                SourceAcquisition(ProviderRouter(http), root).fetch(sid, date(2024, 1, 3))
            with sqlite3.connect(db) as connection:
                connection.execute("INSERT INTO observation_versions(series_id,period,value,first_seen_at,ingestion_run_id) VALUES(?,?,?,?,?)",
                    (sid, "2024-01-03", "3.99", "2026-11-05 10:00:00", "refresh-run"))
            stale = reconcile("sqlite:///" + str(db), root, [sid])
            self.assertFalse(stale["passed"])
            self.assertFalse(stale["series"][0]["source_values_match"])

    def test_later_scheduled_subsets_certify_appended_periods_only(self):
        """Daily refresh windows extend a full snapshot; unarchived periods still fail."""
        import sqlite3
        sid = "bond.us.nominal_10y"
        full = {"count": 2, "offset": 0, "observations": [
            {"date": "2024-01-02", "value": "3.95"}, {"date": "2024-01-03", "value": "3.91"}]}
        window = {"count": 2, "offset": 0, "observations": [
            {"date": "2024-01-03", "value": "3.910"}, {"date": "2024-01-04", "value": "3.88"}]}
        rows = [("2024-01-02", "3.95"), ("2024-01-03", "3.91"), ("2024-01-04", "3.88")]
        with TemporaryDirectory() as temp, patch.dict("os.environ", {"FRED_API_KEY": "secret"}):
            root = Path(temp)
            db = root / "history.db"
            database(db)
            for body, start in ((full, None), (window, date(2024, 1, 3))):
                with httpx.Client(transport=httpx.MockTransport(lambda request, body=body: httpx.Response(200, json=body))) as http:
                    SourceAcquisition(ProviderRouter(http), root).fetch(sid, start)
            with sqlite3.connect(db) as connection:
                connection.executemany("INSERT INTO observation_versions(series_id,period,value,first_seen_at,ingestion_run_id) VALUES(?,?,?,?,?)",
                    [(sid, day, value, "2026-11-04 10:00:00", "source-run") for day, value in rows])
            proof = reconcile("sqlite:///" + str(db), root, [sid])["series"][0]
            self.assertTrue(proof["source_covers_all_stored_periods"], proof)
            self.assertEqual(proof["selection_method"], "acquisition_receipt_with_appended_subsets")
            self.assertEqual(len(proof["subset_overlay_manifest_sha256s"]), 1)
            self.assertEqual(proof["source_periods"], 3)
            # A stored period that no archived original contains stays unverified.
            with sqlite3.connect(db) as connection:
                connection.execute("INSERT INTO observation_versions(series_id,period,value,first_seen_at,ingestion_run_id) VALUES(?,?,?,?,?)",
                    (sid, "2024-01-05", "3.80", "2026-11-05 10:00:00", "refresh-run"))
            extra = reconcile("sqlite:///" + str(db), root, [sid])["series"][0]
            self.assertFalse(extra["source_covers_all_stored_periods"])
            self.assertEqual(extra["extra_stored_periods"], ["2024-01-05"])

    def test_cited_reviews_added_after_capture_do_not_break_archived_contract_identity(self):
        import copy, sqlite3
        from finance_dashboard.catalog import load_documents
        sid = "bond.us.nominal_10y"
        body = {"count": 1, "offset": 0, "observations": [{"date": "2024-01-02", "value": "3.95"}]}
        with TemporaryDirectory() as temp, patch.dict("os.environ", {"FRED_API_KEY": "secret"}):
            root = Path(temp)
            db = root / "history.db"
            database(db)
            with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body))) as http:
                SourceAcquisition(ProviderRouter(http), root).fetch(sid)
            with sqlite3.connect(db) as connection:
                connection.execute("INSERT INTO observation_versions(series_id,period,value,first_seen_at,ingestion_run_id) VALUES(?,?,?,?,?)",
                    (sid, "2024-01-02", "3.95", "2026-11-04 10:00:00", "source-run"))
            series, charts = load_documents()
            reviewed = copy.deepcopy(series)
            entry = next(item for item in reviewed["series"] if item["id"] == sid)
            entry["release_dating"] = {"mode": "alfred_real_time", "evidence_url": "https://alfred.stlouisfed.org/",
                                       "reviewed_on": "2026-11-06"}
            entry["publisher_dimensions"] = {"population": "US Treasury", "currency": None, "price_basis": None,
                "index_base": None, "evidence_url": "https://fred.stlouisfed.org/series/DGS10", "reviewed_on": "2026-11-06"}
            with patch("finance_dashboard.source_reconciliation.load_documents", return_value=(reviewed, charts)):
                report = reconcile("sqlite:///" + str(db), root, [sid])
            self.assertTrue(report["passed"], report["series"][0].get("failure_code"))
            # The proof must bind the same contract digest the acceptance gate checks.
            from finance_dashboard.source_original_gate import verified_original_history
            self.assertTrue(verified_original_history(report["series"][0], entry, 1))

    def test_original_world_bank_geography_and_missing_years_are_not_filled(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            router = ProviderRouter()
            # Resolve the canonical annual country-growth ID rather than defining another provider mapping.
            definition = next(item for item in router.definitions.values()
                if item["provider"] == "WORLD_BANK" and item["source_key"] == "USA/NY.GDP.MKTP.KD.ZG")
            sid = definition["id"]
            router.close()
            payload = [{"pages": 1}, [
                {"indicator": {"id": "NY.GDP.MKTP.KD.ZG"}, "countryiso3code": "USA", "date": "2023", "value": 2.9},
                {"indicator": {"id": "NY.GDP.MKTP.KD.ZG"}, "countryiso3code": "USA", "date": "2024", "value": None}]]
            db = root / "history.db"
            database(db)
            add(db, sid, 2023, "2.9")
            with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))) as http:
                SourceAcquisition(ProviderRouter(http), root).fetch(sid)
            result = reconcile("sqlite:///" + str(db), root, [sid])
            self.assertTrue(result["passed"])
            self.assertEqual(result["series"][0]["source_periods"], 1)
            path = next(root.glob("responses/*/*/response-0.bin"))
            path.write_bytes(path.read_bytes().replace(b'USA', b'JPN'))
            broken = reconcile("sqlite:///" + str(db), root, [sid])
            self.assertEqual(broken["series"][0]["failure_code"], "source_hash_mismatch")

    def test_bis_selects_native_dimensions_independently_and_detects_wrong_sector(self):
        from test_bis_dsr import fixture
        from finance_dashboard.captured_sources import _bis
        from finance_dashboard.source_reconciliation import EvidenceError
        sid = "debt_service.us.private.bis"
        raw = fixture("US", "P")
        with TemporaryDirectory() as temp:
            root = Path(temp)
            db = root / "history.db"
            database(db)
            with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=raw))) as http:
                result = SourceAcquisition(ProviderRouter(http), root).fetch(sid)
            import sqlite3
            with sqlite3.connect(db) as connection:
                connection.executemany("INSERT INTO observation_versions(series_id,period,value,first_seen_at,ingestion_run_id) VALUES(?,?,?,?,?)", [
                    (sid, day.isoformat(), str(value), "2026-11-04 10:00:00", "source-run")
                    for day, value in result.observations.items()])
            report = reconcile("sqlite:///" + str(db), root, [sid])
            self.assertTrue(report["passed"], report)
            router = ProviderRouter()
            try:
                with self.assertRaisesRegex(EvidenceError, "source_identity_mismatch"):
                    _bis(fixture("US", "H"), router.definitions[sid])
            finally:
                router.close()


if __name__ == "__main__":
    unittest.main()
