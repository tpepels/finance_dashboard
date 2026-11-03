"""Browser maintenance API is bounded, resumable and credential-safe."""
import json
import tempfile
import time
import unittest
from datetime import date
from pathlib import Path
from threading import Event
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from finance_dashboard.api import create_app
from finance_dashboard.database import Base
from finance_dashboard.maintenance import MaintenanceManager
from finance_dashboard.developer_logs import read_events
from finance_dashboard.standalone import maintenance_network_lock, manual_sync_pending


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
             "downloaded_now":2,"failed_now":[],
             "next_missing":{"series_id":"T10Y3M"},"halted_reason":None},
            {"status":"complete","source_vintages_requested":3,"missing_after_run":0,
             "downloaded_now":1,"failed_now":[],"next_missing":None,"halted_reason":None},
        ]
        with patch.dict("os.environ",{"FRED_API_KEY":"a"*32}), \
             patch("finance_dashboard.vintage.probe_access",
                   return_value={"status":"ready","requests":1}), \
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
        self.assertNotIn("a"*32,
            Path(self.tmp.name,"jobs.json").read_text(encoding="utf-8"))

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
            self.assertEqual(len(series_ids), 53)
            progress(53,53,"labour.de.pwt_labour_share")
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
            self.assertEqual(len(series_ids),53)
            progress(53,53,"labour.de.pwt_labour_share")
            calls.append("macro")
            return 0
        def market(engine, *, full, instrument_ids, currencies, progress, stopped):
            self.assertTrue(full)
            self.assertEqual(len(instrument_ids),24)
            progress(27,27,"FX:USD")
            calls.append("markets")
            return 0
        batch={"status":"complete","source_vintages_requested":12,
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
        self.assertEqual(sorted(done["result"]["parts"]),
                         ["alfred","backup","macro","markets","sec"])
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
