"""Genuine source-as-of FRED snapshots and walk-forward leak guards."""
import json
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import httpx

from finance_dashboard.vintage import (
    SOURCES, VintageError, fetch_snapshot, read_snapshot,
    latest_asof_reading, available_snapshots, _month_ends,
    capture_previous_month,
)
from finance_dashboard.vintage_backtest import target_after, fit_predict, metrics, walk_forward


class VintageTests(unittest.TestCase):
    def test_real_time_query_uses_same_asof_boundary_and_never_logs_key(self):
        requests = []
        def handler(request):
            requests.append(request)
            self.assertEqual(request.url.params["realtime_start"],"2020-03-31")
            self.assertEqual(request.url.params["realtime_end"],"2020-03-31")
            self.assertEqual(request.url.params["observation_end"],"2020-03-31")
            return httpx.Response(200, json={
                "realtime_start":"2020-03-31","realtime_end":"2020-03-31",
                "observations":[
                    {"date":"2020-03-01","value":"0.4",
                     "realtime_start":"2020-03-10","realtime_end":"2020-04-10"},
                    {"date":"2020-02-01","value":".",
                     "realtime_start":"2020-03-10","realtime_end":"2020-04-10"},
                ]})
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                result=fetch_snapshot("SAHMREALTIME",date(2020,3,31),
                                      api_key="syntheticsecret",client=client,root=root)
                self.assertEqual(result["provider"],"ALFRED")
                self.assertEqual(result["observations"],[{"date":"2020-03-01","value":"0.4"}])
                again=fetch_snapshot("SAHMREALTIME",date(2020,3,31),
                                     api_key="syntheticsecret",client=client,root=root)
                self.assertEqual(len(requests),1)
            self.assertEqual(again["observations"],result["observations"])
            self.assertNotIn("syntheticsecret",(root/"SAHMREALTIME"/"2020-03-31.json").read_text())
            self.assertEqual(latest_asof_reading(again)["age_days"],30)
            self.assertEqual(available_snapshots(root)["series"][1]["count"],1)

    def test_month_end_retrieval_is_idempotent_and_requires_key(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            disabled=capture_previous_month(root,today=date(2026,11,2),api_key="")
            self.assertEqual(disabled["status"],"disabled_no_key")
            self.assertEqual(disabled["captured"],0)
            called=[]
            def handler(request):
                called.append(request.url.params["series_id"])
                self.assertEqual(request.url.params["realtime_start"],"2026-10-31")
                return httpx.Response(200,json={
                    "observations":[{
                        "date":"2026-10-01","value":"0.5",
                        "realtime_start":"2026-10-15",
                        "realtime_end":"9999-12-31"}]})
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                first=capture_previous_month(root,today=date(2026,11,2),
                    api_key="fake",client=client)
                second=capture_previous_month(root,today=date(2026,11,2),
                    api_key="fake",client=client)
            self.assertEqual(first["status"],"complete")
            self.assertEqual(second["captured"],3)
            self.assertEqual(len(called),3)

    def test_refuses_future_or_after_vintage_observation(self):
        def handler(_):
            return httpx.Response(200,json={"observations":[{
                "date":"2020-03-01","value":"1.0",
                "realtime_start":"2020-04-01","realtime_end":"2020-05-01"}]})
        with TemporaryDirectory() as tmp:
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                with self.assertRaisesRegex(VintageError,"released after"):
                    fetch_snapshot("T10Y3M",date(2020,3,31),
                                   api_key="fake",client=client,root=Path(tmp))
            self.assertEqual(list(Path(tmp).glob("**/*.json")),[])
        self.assertEqual(_month_ends(date(2020,1,1),date(2020,3,31)),
                         [date(2020,1,31),date(2020,2,29),date(2020,3,31)])

    def test_walk_forward_model_math_is_deterministic_and_evaluates_only_observed_events(self):
        # Synthetic inputs exercise the implementation; these are NOT claims
        # of historical skill, independent validation or genuine ALFRED data.
        training=[(date(2000+i//12,i%12+1,1),
                   (float((i%14)-7), float((i%11)/10)),
                   int(i%11<3)) for i in range(96)]
        first, prior=fit_predict(training,(-1.5,0.2))
        second, same_prior=fit_predict(training,(-1.5,0.2))
        self.assertEqual((first,prior),(second,same_prior))
        self.assertTrue(0<=first<=1)
        self.assertTrue(0<prior<1)
        test=[{"outcome":int(i%4==0),
               "estimated_probability":0.8 if i%4==0 else 0.2,
               "past_prevalence_baseline":0.25}
              for i in range(40)]
        outcome=metrics(test)
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome["cases"],40)
        self.assertEqual(outcome["positives"],10)
        self.assertEqual(outcome["roc_auc"],1.0)
        self.assertLess(outcome["brier"],outcome["expanding_prevalence_brier"])

    def test_training_requires_past_event_cases_and_future_outcomes_mature(self):
        self.assertIsNone(target_after(date(2020,1,31),{2020*12+1:0},6))
        with self.assertRaisesRegex(ValueError,"Insufficient"):
            fit_predict([(date(2020,1,31),(0.1,0.2),1)]*2,(1.,2.))
        self.assertIsNone(metrics([{"outcome":0,"estimated_probability":0.1,
                                   "past_prevalence_baseline":0.2}]*30))
        with TemporaryDirectory() as tmp:
            result=walk_forward(Path(tmp),horizon=12)
            self.assertEqual(result["status"],"insufficient_vintages")
            self.assertIsNone(result["evaluation"])
            self.assertEqual(result["observations"],[])


if __name__=="__main__":
    unittest.main()
