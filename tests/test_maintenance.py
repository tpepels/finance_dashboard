"""Browser maintenance API is bounded, resumable and credential-safe."""
import json
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path
from threading import Event
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from finance_dashboard.api import create_app
from finance_dashboard.catalog import load_documents
from finance_dashboard.database import Base
from finance_dashboard.maintenance import MaintenanceManager
from finance_dashboard.developer_logs import read_events
from finance_dashboard.standalone import maintenance_network_lock, manual_sync_pending
from finance_dashboard.vintage import (
    SOURCES as VINTAGE_SOURCES, VintageError, backfill_batch as real_backfill_batch,
)


PWT = ["labour.de.pwt_labour_share","labour.fr.pwt_labour_share",
       "labour.it.pwt_labour_share"]
HEADERS = {"X-GCM-Action":"dashboard"}
ACTION = {"action":"refresh_sources","series_ids":PWT}


class MaintenanceApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.engine=create_engine("sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread":False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.env=patch.dict("os.environ",{
            "FINANCE_MAINTENANCE_STATE":str(Path(self.tmp.name)/"jobs.json"),
            "FINANCE_AUTO_REFRESH":"0",
        })
        self.env.start()
        # Sync actions verify a backup. Only the backup API is mocked here;
        # the separate test_backup suite tests real SQLite archival semantics.
        self.backup_patches=[
            patch("finance_dashboard.backup.source_database_path",
                  return_value=Path(self.tmp.name,"finance.sqlite3")),
            patch("finance_dashboard.backup.backup_local",
                  return_value={"database":{"file":"finance-20261103T120000000000Z.sqlite3"}}),
            patch("finance_dashboard.backup.verify_manifest",
                  return_value={"verified":True,"components":["database"]}),
        ]
        for p in self.backup_patches:
            p.start()
        self.client=TestClient(create_app(self.engine))
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None,None,None)
        for p in reversed(self.backup_patches):
            p.stop()
        self.env.stop()
        self.engine.dispose()
        self.tmp.cleanup()

    def wait(self,id,deadline=2):
        until=time.monotonic()+deadline
        while time.monotonic()<until:
            payload=self.client.get("/api/maintenance").json()
            for job in payload["jobs"]:
                if job["id"]==id and job["status"] not in ("queued","waiting","running","cancelling"):
                    return job
            time.sleep(.02)
        self.fail("Maintenance operation did not settle")

    def test_browser_can_import_three_pwt_histories_and_persist_job_state(self):
        calls=[]
        def fake(engine,*,full,series_ids,progress,stopped):
            self.assertTrue(full)
            self.assertEqual(series_ids,set(PWT))
            progress(1,3,PWT[0])
            calls.append(set(series_ids))
            progress(3,3,PWT[-1])
            return 0
        with patch("finance_dashboard.worker.refresh_all",side_effect=fake):
            r=self.client.post("/api/maintenance",json=ACTION,headers=HEADERS)
            self.assertEqual(r.status_code,202,r.text)
            finished=self.wait(r.json()["id"])
        self.assertEqual(finished["status"],"complete")
        self.assertEqual((finished["completed"],finished["total"]),(3,3))
        self.assertEqual(calls,[set(PWT)])
        self.assertTrue(Path(self.tmp.name,"jobs.json").is_file())
        saved=json.loads(Path(self.tmp.name,"jobs.json").read_text())
        self.assertEqual(saved["jobs"][-1]["status"],"complete")
        self.assertNotIn("FRED_API_KEY",json.dumps(saved))

    def test_full_canonical_source_selection_grows_with_catalog(self):
        from finance_dashboard.providers import ProviderRouter
        router = ProviderRouter()
        try:
            expected = set(router.supported_ids())
        finally:
            router.close()
        self.assertGreater(len(expected), 53)
        collected = []
        def collect(engine, *, full, series_ids, progress, stopped):
            collected.append(series_ids)
            return 0
        with patch("finance_dashboard.worker.refresh_all", side_effect=collect):
            for payload in ({"action": "refresh_sources"},
                            {"action": "refresh_sources", "series_ids": sorted(expected)}):
                response = self.client.post("/api/maintenance", json=payload, headers=HEADERS)
                self.assertEqual(response.status_code, 202, response.text)
                self.assertEqual(self.wait(response.json()["id"])["status"], "complete")
        self.assertEqual(collected, [expected, expected])
        for ids in ([], [PWT[0], PWT[0]], ["unknown-source"]):
            response = self.client.post("/api/maintenance", headers=HEADERS,
                json={"action": "refresh_sources", "series_ids": ids})
            self.assertEqual(response.status_code, 422)

    def test_rejects_cross_origin_missing_action_header_and_unknown_ids(self):
        self.assertEqual(self.client.post("/api/maintenance",json=ACTION).status_code,403)
        self.assertEqual(self.client.post("/api/maintenance",json=ACTION,
            headers={**HEADERS,"Origin":"https://malicious.example"}).status_code,403)
        self.assertEqual(self.client.post("/api/maintenance",
            json={"action":"refresh_sources","series_ids":["arbitrary.url"]},
            headers=HEADERS).status_code,422)
        self.assertEqual(self.client.post("/api/maintenance",
            json={"action":"backfill_alfred","start":"2027-01-01",
                  "end":"2027-12-31"}, headers=HEADERS).status_code,422)
        self.assertEqual(self.client.post("/api/maintenance",
            json={"action":"refresh_sources","command":"rm -rf /data"},
            headers=HEADERS).status_code,422)
        self.assertIsNone(self.client.get("/api/maintenance").json()["active_job_id"])

    def test_only_one_active_job_and_cancellation_keeps_existing_data(self):
        entered=Event()
        release=Event()
        def running(engine,*,full,series_ids,progress,stopped):
            entered.set()
            self.assertTrue(release.wait(2))
            return 0
        with patch("finance_dashboard.worker.refresh_all",side_effect=running):
            queued=self.client.post("/api/maintenance",json=ACTION,headers=HEADERS)
            self.assertEqual(queued.status_code,202)
            self.assertTrue(entered.wait(2))
            other=self.client.post("/api/maintenance",json=ACTION,headers=HEADERS)
            self.assertEqual(other.status_code,409)
            cancel=self.client.post("/api/maintenance/"+queued.json()["id"]+"/cancel",
                json={},headers=HEADERS)
            self.assertEqual(cancel.status_code,202)
            release.set()
            result=self.wait(queued.json()["id"])
        self.assertEqual(result["status"],"cancelled")
        self.assertIsNone(self.client.get("/api/maintenance").json()["active_job_id"])

    def test_browser_sync_preempts_scheduled_refresh_and_releases_priority(self):
        with patch("finance_dashboard.worker.refresh_all", return_value=0):
            maintenance_network_lock.acquire()
            try:
                job = self.client.post("/api/maintenance", json=ACTION, headers=HEADERS)
                self.assertEqual(job.status_code, 202)
                self.assertTrue(manual_sync_pending.is_set())
                self.assertEqual(self.client.get("/api/maintenance").json()["active_job_id"],
                                 job.json()["id"])
            finally:
                maintenance_network_lock.release()
            result = self.wait(job.json()["id"])
        self.assertEqual(result["status"], "complete")
        self.assertFalse(manual_sync_pending.is_set())

    def test_single_fx_selection_never_implicitly_schedules_all_assets(self):
        calls=[]
        def market(engine,*,instrument_ids,currencies,stopped,progress):
            calls.append((instrument_ids,currencies))
            progress(1,1,"FX:USD")
            return 0
        with patch("finance_dashboard.worker.refresh_market_all",side_effect=market):
            r=self.client.post("/api/maintenance",headers=HEADERS,json={
                "action":"refresh_markets","instrument_ids":[],"currencies":["USD"]})
            self.assertEqual(r.status_code,202,r.text)
            finished=self.wait(r.json()["id"])
        self.assertEqual(finished["status"],"complete")
        self.assertEqual(calls,[(set(),{"USD"})])

    def test_historical_asof_import_resumes_batches_and_keeps_secrets_out(self):
        batch=[
            {"status":"partial","source_vintages_requested":3,"missing_after_run":1,
             "prepublication_excluded":0,
             "downloaded_now":2,"failed_now":[],
             "next_missing":{"series_id":"T10Y3M"},"halted_reason":None},
            {"status":"complete","source_vintages_requested":3,"missing_after_run":0,
             "prepublication_excluded":0,
             "downloaded_now":1,"failed_now":[],"next_missing":None,"halted_reason":None},
        ]
        with patch.dict("os.environ",{"FRED_API_KEY":"a"*32}), \
             patch("finance_dashboard.vintage.probe_access",
                   return_value={"status":"ready","requests":1}), \
             patch("finance_dashboard.vintage.first_available_vintages",
                   return_value={"T10Y3M": date(2000, 1, 1)}) as availability, \
             patch("finance_dashboard.vintage.backfill_batch",side_effect=batch) as backfill:
            request=self.client.post("/api/maintenance",headers=HEADERS,json={
                "action":"backfill_alfred","start":"2020-01-01",
                "end":"2020-03-31","series_ids":["T10Y3M"],
                "max_requests":2,"complete_range":True})
            self.assertEqual(request.status_code,202,request.text)
            result=self.wait(request.json()["id"])
        self.assertEqual(result["status"],"complete")
        self.assertEqual(result["completed"],3)
        self.assertEqual(result["total"],3)
        self.assertEqual(result["result"]["downloaded_now"],3)
        self.assertEqual(backfill.call_count,2)
        availability.assert_called_once()
        self.assertTrue(all(call.kwargs["first_available"] == {"T10Y3M": date(2000, 1, 1)}
                            for call in backfill.call_args_list))
        self.assertNotIn("a"*32,
            Path(self.tmp.name,"jobs.json").read_text(encoding="utf-8"))

    def test_default_alfred_backfill_collects_all_canonical_sources(self):
        expected = sorted(VINTAGE_SOURCES)
        with patch.dict("os.environ", {"FRED_API_KEY": "a"*32}), \
             patch("finance_dashboard.vintage.probe_access",
                   return_value={"status": "ready", "requests": 1}), \
             patch("finance_dashboard.vintage.first_available_vintages",
                   return_value={sid: date(2000, 1, 1) for sid in VINTAGE_SOURCES}) as availability, \
             patch("finance_dashboard.vintage.backfill_batch", return_value={
                 "status": "complete", "source_vintages_requested": 9,
                 "prepublication_excluded": 0,
                 "missing_after_run": 0, "downloaded_now": 9,
                 "failed_now": [], "next_missing": None, "halted_reason": None,
             }) as backfill:
            response = self.client.post("/api/maintenance", headers=HEADERS, json={
                "action": "backfill_alfred", "start": "2020-01-01", "end": "2020-01-31"})
            self.assertEqual(response.status_code, 202, response.text)
            result = self.wait(response.json()["id"])
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["options"]["series_ids"], expected)
        self.assertEqual(len(result["options"]["series_ids"]), 9)
        backfill.assert_called_once()
        self.assertEqual(backfill.call_args.args[2], expected)
        availability.assert_called_once()
        self.assertEqual(availability.call_args.args[0], expected)
        self.assertEqual(backfill.call_args.kwargs["first_available"],
                         {sid: date(2000, 1, 1) for sid in VINTAGE_SOURCES})

    def test_explicit_new_yield_and_dfa_backfill_sources_are_accepted(self):
        with patch.dict("os.environ", {"FRED_API_KEY": "a"*32}), \
             patch("finance_dashboard.vintage.probe_access",
                   return_value={"status": "ready", "requests": 1}), \
             patch("finance_dashboard.vintage.first_available_vintages",
                   return_value={sid: date(2000, 1, 1) for sid in ("DGS10", "WFRBST01134")}), \
             patch("finance_dashboard.vintage.backfill_batch", return_value={
                 "status": "complete", "source_vintages_requested": 2,
                 "prepublication_excluded": 0,
                 "missing_after_run": 0, "downloaded_now": 2,
                 "failed_now": [], "next_missing": None, "halted_reason": None,
             }) as backfill:
            response = self.client.post("/api/maintenance", headers=HEADERS, json={
                "action": "backfill_alfred", "start": "2020-01-01", "end": "2020-01-31",
                "series_ids": ["WFRBST01134", "DGS10"]})
            self.assertEqual(response.status_code, 202, response.text)
            result = self.wait(response.json()["id"])
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["options"]["series_ids"], ["DGS10", "WFRBST01134"])
        self.assertEqual(backfill.call_args.args[2], ["DGS10", "WFRBST01134"])

    def test_alfred_backfill_rejects_unknown_and_duplicate_sources(self):
        for selected in (["DGS10", "unknown-source"], ["DGS10", "DGS10"]):
            with self.subTest(selected=selected):
                response = self.client.post("/api/maintenance", headers=HEADERS, json={
                    "action": "backfill_alfred", "series_ids": selected})
                self.assertEqual(response.status_code, 422, response.text)
        self.assertIsNone(self.client.get("/api/maintenance").json()["active_job_id"])

    def test_alfred_backfill_never_requests_prepublication_months(self):
        requested_asofs = []
        metadata_ids = []
        def transport(request):
            if request.url.path.endswith("/vintagedates"):
                metadata_ids.append(request.url.params["series_id"])
                return httpx.Response(200, json={"vintage_dates": ["2000-03-15"]})
            sid = request.url.params["series_id"]
            asof = request.url.params["realtime_start"]
            if sid == "DGS10":
                requested_asofs.append(asof)
            return httpx.Response(200, json={
                "realtime_start": asof, "realtime_end": asof,
                "observations": [{"date": asof, "value": "3.5"}],
            })
        client = httpx.Client(transport=httpx.MockTransport(transport))
        source_folder = Path(self.tmp.name, "vintages")
        def local_backfill(*args, **kwargs):
            return real_backfill_batch(*args, **kwargs, root=source_folder)
        with patch.dict("os.environ", {"FRED_API_KEY": "a"*32}), \
             patch("finance_dashboard.maintenance.httpx.Client", return_value=client), \
             patch("finance_dashboard.vintage.time.sleep"), \
             patch("finance_dashboard.vintage.backfill_batch", side_effect=local_backfill):
            response = self.client.post("/api/maintenance", headers=HEADERS, json={
                "action": "backfill_alfred", "series_ids": ["DGS10"],
                "start": "2000-01-01", "end": "2000-03-31"})
            self.assertEqual(response.status_code, 202, response.text)
            job = self.wait(response.json()["id"])
        self.assertEqual(job["status"], "complete")
        self.assertEqual(metadata_ids, ["DGS10"])
        self.assertEqual(requested_asofs, ["2000-03-31"])
        self.assertEqual(job["result"]["prepublication_excluded"], 2)
        self.assertEqual(job["result"]["vintages_total"], 1)
        self.assertEqual(job["result"]["vintages_missing"], 0)
        self.assertEqual(job["result"]["downloaded_now"], 1)
        self.assertIs(job["result"].get("first_publication_vintage_verified"), False)
        self.assertTrue((source_folder / "DGS10" / "2000-03-31.json").is_file())

    def test_alfred_metadata_failure_blocks_without_fabricated_counts_or_secrets(self):
        request = httpx.Request("GET", "https://api.stlouisfed.org/fred/series/vintagedates?api_key=PRIVATE")
        response = httpx.Response(400, request=request, json={"error_message": "Invalid api_key given"})
        cases = (
            (VintageError("PRIVATE invalid publication metadata"), "fred_publication_metadata_invalid", None),
            (httpx.HTTPStatusError("PRIVATE", request=request, response=response), "fred_api_key_rejected", 400),
            (httpx.ConnectError("PRIVATE", request=request), "fred_network_error", None),
        )
        for failure, reason, status in cases:
            with self.subTest(reason=reason), \
                 patch("finance_dashboard.vintage.probe_access",
                       return_value={"status": "ready", "requests": 1}), \
                 patch("finance_dashboard.vintage.first_available_vintages", side_effect=failure), \
                 patch("finance_dashboard.vintage.backfill_batch", return_value={
                     "status": "complete", "source_vintages_requested": 3,
                     "prepublication_excluded": 0, "missing_after_run": 0,
                     "downloaded_now": 3, "failed_now": [], "next_missing": None,
                     "halted_reason": None,
                 }) as backfill:
                accepted = self.client.post("/api/maintenance", headers=HEADERS, json={
                    "action": "backfill_alfred", "series_ids": ["DGS10"],
                    "start": "2000-01-01", "end": "2000-03-31"})
                self.assertEqual(accepted.status_code, 202, accepted.text)
                result = self.wait(accepted.json()["id"])
                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["result"]["reason"], reason)
                self.assertEqual(result["result"].get("http_status"), status)
                self.assertNotIn("vintages_total", result["result"])
                self.assertNotIn("prepublication_excluded", result["result"])
                self.assertNotIn("PRIVATE", json.dumps(result))
                backfill.assert_not_called()

    def test_all_prepublication_dates_are_exclusions_without_false_no_progress(self):
        with patch("finance_dashboard.vintage.probe_access",
                   return_value={"status": "ready", "requests": 1}), \
             patch("finance_dashboard.vintage.first_available_vintages",
                   return_value={"DGS10": date(2001, 1, 1)}), \
             patch("finance_dashboard.vintage.backfill_batch", return_value={
                 "status": "complete", "source_vintages_requested": 0,
                 "prepublication_excluded": 3, "missing_after_run": 0,
                 "downloaded_now": 0, "failed_now": [], "next_missing": None,
                 "halted_reason": None,
             }):
            response = self.client.post("/api/maintenance", headers=HEADERS, json={
                "action": "backfill_alfred", "series_ids": ["DGS10"],
                "start": "2000-01-01", "end": "2000-03-31"})
            self.assertEqual(response.status_code, 202, response.text)
            job = self.wait(response.json()["id"])
        self.assertEqual(job["status"], "complete")
        self.assertIsNone(job["result"]["reason"])
        self.assertEqual(job["result"]["prepublication_excluded"], 3)
        self.assertEqual(job["result"]["vintages_total"], 0)

    def test_sec_access_and_historical_filing_import_can_run_from_ui(self):
        with patch("finance_dashboard.sec_holdings_sync.check_sec_sources",
                   return_value={"status":"ready","funds":[{
                       "instrument_id":"vt","status":"ready","reason":"index_verified"}]}):
            preflight=self.client.post("/api/maintenance",headers=HEADERS,
                                       json={"action":"check_sec"})
            self.assertEqual(preflight.status_code,202)
            self.assertEqual(self.wait(preflight.json()["id"])["status"],"complete")
        with patch("finance_dashboard.sec_holdings_sync.collect_configured",
                   return_value={"status":"complete","funds":[{
                       "instrument_id":"vt","status":"complete",
                       "stored_or_already_present":1,"attempted":1,"errors":0}]}) as collector:
            import_job=self.client.post("/api/maintenance",headers=HEADERS,
                                        json={"action":"collect_sec","limit":1})
            self.assertEqual(import_job.status_code,202)
            result=self.wait(import_job.json()["id"])
            self.assertEqual(result["status"],"complete")
            self.assertEqual(result["result"]["funds"][0]["stored"],1)
            self.assertEqual(collector.call_args.kwargs["max_filings_per_fund"],1)
            self.assertTrue(callable(collector.call_args.kwargs["progress"]))
            self.assertIsInstance(collector.call_args.kwargs["stopped"],Event)

    def test_missing_sec_contact_cannot_be_reported_as_success(self):
        with patch("finance_dashboard.sec_holdings_sync.collect_configured",
                   return_value={"status":"disabled_missing_SEC_USER_AGENT","funds":[]}):
            job=self.client.post("/api/maintenance",headers=HEADERS,
                                 json={"action":"collect_sec","limit":1})
            self.assertEqual(job.status_code,202)
            result=self.wait(job.json()["id"])
            self.assertEqual(result["status"],"blocked")
            self.assertEqual(result["error_code"],"missing_credential")

    def test_quota_deferred_earnings_is_not_reported_as_success(self):
        with patch("finance_dashboard.wisesheets_local.refresh_local_wisesheets",
                   return_value="deferred"):
            job=self.client.post("/api/maintenance",headers=HEADERS,
                                 json={"action":"refresh_earnings"})
            self.assertEqual(job.status_code,202)
            result=self.wait(job.json()["id"])
            self.assertEqual(result["status"],"partial")
            self.assertEqual(result["result"]["source_state"],"deferred")

    def test_single_current_sync_collects_all_economic_market_fx_and_earnings(self):
        tracked = []
        def macro(engine, *, full, series_ids, progress, stopped):
            self.assertFalse(full)
            self.assertEqual(len(series_ids), len(load_documents()[0]["series"]))
            progress(len(series_ids), len(series_ids), "labour.de.pwt_labour_share")
            tracked.append("macro")
            return 0
        def market(engine, *, full, instrument_ids, currencies, progress, stopped):
            self.assertFalse(full)
            self.assertEqual(len(instrument_ids),24)
            self.assertEqual(currencies,{"USD","GBP","CHF"})
            progress(27,27,"FX:USD")
            tracked.append("market")
            return 0
        with patch("finance_dashboard.worker.refresh_all",side_effect=macro), \
             patch("finance_dashboard.worker.refresh_market_all",side_effect=market), \
             patch("finance_dashboard.wisesheets_local.refresh_local_wisesheets",
                   side_effect=lambda: tracked.append("earnings") or "updated"):
            r=self.client.post("/api/maintenance",json={"action":"sync_current"},
                               headers=HEADERS)
            self.assertEqual(r.status_code,202,r.text)
            done=self.wait(r.json()["id"])
        self.assertEqual(tracked,["macro","market","earnings"])
        self.assertEqual(done["status"],"complete")
        self.assertEqual((done["completed"],done["total"]),(4,4))
        self.assertEqual(set(done["result"]["parts"]),{
            "macro","markets","earnings","backup"})
        self.assertTrue(done["result"]["parts"]["backup"]["verified"])
        journal = read_events()
        self.assertTrue(any(row.get("event")=="queued" and
                            row.get("action")=="sync_current" for row in journal))
        self.assertTrue(any(row.get("event")=="stage_finished" and
                            row.get("stage")=="macro" for row in journal))
        self.assertTrue(any(row.get("event")=="finished" and
                            row.get("action")=="sync_current" for row in journal))

    def test_current_sync_continues_after_source_errors_and_reports_partial(self):
        calls=[]
        with patch("finance_dashboard.worker.refresh_all",return_value=7), \
             patch("finance_dashboard.worker.refresh_market_all",side_effect=lambda *a,**kw:
                   calls.append("markets") or 3), \
             patch("finance_dashboard.wisesheets_local.refresh_local_wisesheets",
                   return_value="deferred"):
            r=self.client.post("/api/maintenance",json={"action":"sync_current"},
                               headers=HEADERS)
            self.assertEqual(r.status_code,202)
            done=self.wait(r.json()["id"])
        self.assertEqual(done["status"],"partial")
        self.assertEqual(calls,["markets"])
        self.assertEqual(done["result"]["parts"]["macro"]["failed"],7)
        self.assertEqual(done["result"]["parts"]["markets"]["failed"],3)
        self.assertEqual(done["result"]["parts"]["earnings"]["status"],"skipped")

    def test_history_sync_runs_full_source_backfill_alfred_and_sec(self):
        calls=[]
        def macro(engine, *, full, series_ids, progress, stopped):
            self.assertTrue(full)
            self.assertEqual(len(series_ids), len(load_documents()[0]["series"]))
            progress(len(series_ids), len(series_ids), "labour.de.pwt_labour_share")
            calls.append("macro")
            return 0
        def market(engine, *, full, instrument_ids, currencies, progress, stopped):
            self.assertTrue(full)
            self.assertEqual(len(instrument_ids),24)
            progress(27,27,"FX:USD")
            calls.append("markets")
            return 0
        bounds={sid: date(2000, 1, 1) for sid in VINTAGE_SOURCES}
        batch={"status":"complete","source_vintages_requested":12,
               "prepublication_excluded":0,
               "missing_after_run":0,"downloaded_now":12,"failed_now":[],
               "next_missing":None,"halted_reason":None}
        def sec(*,max_filings_per_fund,stopped,progress):
            self.assertEqual(max_filings_per_fund,50)
            progress(1,1,"vt")
            calls.append("sec")
            return {"status":"complete","funds":[{
                "instrument_id":"vt","status":"complete","errors":0,
                "stored_or_already_present":50,
                "unexamined_candidate_filings":0}]}
        with patch.dict("os.environ",{"FRED_API_KEY":"a"*32}), \
             patch("finance_dashboard.worker.refresh_all",side_effect=macro), \
             patch("finance_dashboard.worker.refresh_market_all",side_effect=market), \
             patch("finance_dashboard.vintage.probe_access",
                   return_value={"status":"ready","requests":1}), \
             patch("finance_dashboard.vintage.first_available_vintages",
                   return_value=bounds) as availability, \
             patch("finance_dashboard.vintage.backfill_batch",return_value=batch) as alfred, \
             patch("finance_dashboard.sec_holdings_sync.collect_configured",
                   side_effect=sec):
            r=self.client.post("/api/maintenance",json={"action":"sync_history"},
                               headers=HEADERS)
            self.assertEqual(r.status_code,202,r.text)
            done=self.wait(r.json()["id"])
        self.assertEqual(done["status"],"complete")
        self.assertEqual((done["completed"],done["total"]),(5,5))
        self.assertEqual(calls,["macro","markets","sec"])
        self.assertEqual(done["result"]["parts"]["alfred"]["downloaded"],12)
        self.assertEqual(alfred.call_count,1)
        availability.assert_called_once()
        self.assertEqual(availability.call_args.args[0], sorted(VINTAGE_SOURCES))
        self.assertEqual(alfred.call_args.args[2], sorted(VINTAGE_SOURCES))
        self.assertEqual(alfred.call_args.kwargs["first_available"],bounds)
        self.assertEqual(done["result"]["parts"]["alfred"]["prepublication_excluded"],0)
        self.assertEqual(sorted(done["result"]["parts"]),
                         ["alfred","backup","macro","markets","sec"])
        self.assertNotIn("a"*32,json.dumps(done))

    def test_history_backfill_exposes_first_failed_source_and_date(self):
        bounds={sid: date(2000, 1, 1) for sid in VINTAGE_SOURCES}
        failure = {
            "status":"blocked","source_vintages_requested":964,
            "prepublication_excluded":0,
            "missing_after_run":964,"downloaded_now":0,
            "failed_now":[{
                "series_id":"SAHMREALTIME","asof":"2000-01-31",
                "http_status":400,"reason":"fred_series_parameter_rejected",
            }],
            "halted_reason":"fred_series_parameter_rejected",
        }
        with patch.dict("os.environ",{"FRED_API_KEY":"a"*32}), \
             patch("finance_dashboard.worker.refresh_all",return_value=0), \
             patch("finance_dashboard.worker.refresh_market_all",return_value=0), \
             patch("finance_dashboard.vintage.probe_access",
                   return_value={"status":"ready","requests":1}), \
             patch("finance_dashboard.vintage.first_available_vintages",
                   return_value=bounds) as availability, \
             patch("finance_dashboard.vintage.backfill_batch",
                   return_value=failure) as backfill, \
             patch("finance_dashboard.sec_holdings_sync.collect_configured",
                   return_value={"status":"complete","funds":[]}):
            job = self.client.post("/api/maintenance",
                    json={"action":"sync_history"},headers=HEADERS)
            self.assertEqual(job.status_code,202)
            done=self.wait(job.json()["id"])
        part=done["result"]["parts"]["alfred"]
        availability.assert_called_once()
        self.assertEqual(backfill.call_args.kwargs["first_available"],bounds)
        self.assertEqual(part["first_failed_series"],"SAHMREALTIME")
        self.assertEqual(part["first_failed_asof"],"2000-01-31")
        self.assertEqual(part["first_failed_reason"],"fred_series_parameter_rejected")
        self.assertEqual(part["failures_in_run"],1)
        self.assertEqual(part["http_status"],400)
        self.assertNotIn("a"*32,json.dumps(done))

    def test_history_sync_reports_blocked_origins_without_skipping_sec(self):
        calls=[]
        with patch("finance_dashboard.worker.refresh_all",return_value=0), \
             patch("finance_dashboard.worker.refresh_market_all",return_value=0), \
             patch("finance_dashboard.vintage.probe_access",
                   return_value={"status":"blocked","reason":"invalid_api_key"}), \
             patch("finance_dashboard.sec_holdings_sync.collect_configured",
                   side_effect=lambda **kw:calls.append("sec") or
                   {"status":"disabled_missing_SEC_USER_AGENT","funds":[]}):
            r=self.client.post("/api/maintenance",json={"action":"sync_history"},
                               headers=HEADERS)
            self.assertEqual(r.status_code,202)
            done=self.wait(r.json()["id"])
        self.assertEqual(done["status"],"partial")
        self.assertEqual(calls,["sec"])
        self.assertEqual(done["result"]["parts"]["alfred"]["status"],"blocked")
        self.assertEqual(done["result"]["parts"]["alfred"]["reason"],"invalid_api_key")
        self.assertEqual(done["result"]["parts"]["sec"]["status"],"blocked")
        self.assertEqual(done["result"]["parts"]["sec"]["reason"],"missing_credential")

    def test_history_reports_per_fund_results_and_fred_http_status_without_secrets(self):
        def fake_sec(**kwargs):
            return {"status":"partial","funds":[
                {"instrument_id":"vt","status":"partial","errors":2,
                 "stored_or_already_present":11,"source_candidates_found":150,
                 "index_candidates_examined":130,
                 "unexamined_candidate_filings":20,"halted_reason":"sec_rate_limited",
                 "first_error_reason":"sec_rate_limited",
                 "no_verified_xml_in_index":4,
                 "other_series_skipped":104,
                 "http_status":429},
                {"instrument_id":"bnd","status":"complete","errors":0,
                 "stored_or_already_present":50,"source_candidates_found":50,
                 "index_candidates_examined":50,
                 "unexamined_candidate_filings":0},
            ]}
        with patch.dict("os.environ",{"FRED_API_KEY":"a"*32}), \
             patch("finance_dashboard.worker.refresh_all",return_value=0), \
             patch("finance_dashboard.worker.refresh_market_all",return_value=0), \
             patch("finance_dashboard.vintage.probe_access",return_value={
                 "status":"blocked","reason":"fred_api_key_rejected",
                 "http_status":400,"requests":1}), \
             patch("finance_dashboard.sec_holdings_sync.collect_configured",
                   side_effect=fake_sec):
            job=self.client.post("/api/maintenance",json={"action":"sync_history"},
                                 headers=HEADERS)
            self.assertEqual(job.status_code,202)
            result=self.wait(job.json()["id"])
        self.assertEqual(result["status"],"partial")
        parts=result["result"]["parts"]
        self.assertEqual(parts["alfred"]["reason"],"fred_api_key_rejected")
        self.assertEqual(parts["alfred"]["http_status"],400)
        self.assertEqual(parts["sec"]["funds"][0]["id"],"vt")
        self.assertEqual(parts["sec"]["funds"][0]["stored"],11)
        self.assertEqual(parts["sec"]["funds"][0]["reason"],"sec_rate_limited")
        self.assertEqual(parts["sec"]["funds"][0]["http_status"],429)
        self.assertTrue(parts["sec"]["funds"][0]["historical_coverage_limited"])
        self.assertEqual(parts["sec"]["funds"][0]["unexamined"],20)
        self.assertEqual(parts["sec"]["funds"][0]["missing_verified_xml"],4)
        self.assertEqual(parts["sec"]["funds"][0]["first_error_reason"],
                         "sec_rate_limited")
        self.assertNotIn("a"*32,json.dumps(result))

    def test_two_sync_actions_reject_manual_options(self):
        for action in ("sync_current","sync_history"):
            r=self.client.post("/api/maintenance",headers=HEADERS,json={
                "action":action,"series_ids":PWT})
            self.assertEqual(r.status_code,422)
        self.assertIsNone(self.client.get("/api/maintenance").json()["active_job_id"])

    def test_interrupted_jobs_are_recoverable_without_false_success(self):
        path=Path(self.tmp.name,"jobs.json")
        path.write_text(json.dumps({"version":1,"jobs":[
            {"id":"old","action":"backfill_alfred","options":{},
             "status":"running","finished_at":None,"error_code":None}
        ]}),encoding="utf-8")
        loaded=MaintenanceManager(self.engine,state_path=path)
        job=loaded.list()["jobs"][0]
        self.assertEqual(job["status"],"interrupted")
        self.assertEqual(job["error_code"],"interrupted")
        self.assertIsNone(loaded.list()["active_job_id"])


if __name__=="__main__":
    unittest.main()
