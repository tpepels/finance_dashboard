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
        self.client=TestClient(create_app(self.engine))
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None,None,None)
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
            collector.assert_called_once_with(max_filings_per_fund=1)

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
