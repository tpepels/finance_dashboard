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
