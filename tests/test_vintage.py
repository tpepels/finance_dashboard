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
    capture_previous_month, backfill_batch, probe_access, first_available_vintages,
)
from finance_dashboard.vintage_backtest import (
    target_after, fit_predict, metrics, walk_forward, independent_holdout_diagnostics,
)


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

    def test_sahm_vintage_preserves_source_history_since_1959_without_future_leakage(self):
        asof = date(2019, 9, 30)
        requests = []
        def handler(request):
            requests.append(request)
            self.assertEqual(request.url.params["series_id"], "SAHMREALTIME")
            self.assertEqual(request.url.params["observation_start"], "1959-12-01")
            self.assertEqual(request.url.params["observation_end"], "2019-09-30")
            self.assertEqual(request.url.params["realtime_start"], "2019-09-30")
            self.assertEqual(request.url.params["realtime_end"], "2019-09-30")
            return httpx.Response(200, json={
                "realtime_start": "2019-09-30",
                "realtime_end": "2019-09-30",
                "observations": [
                    {"date": "2019-09-01", "value": "0.0",
                     "realtime_start": "2019-09-10",
                     "realtime_end": "9999-12-31"},
                    {"date": "1959-12-01", "value": "0.77",
                     "realtime_start": "2019-09-10",
                     "realtime_end": "9999-12-31"},
                ]})
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                result = fetch_snapshot("SAHMREALTIME", asof, api_key="secret",
                                        client=client, root=root)
                stored = read_snapshot(root, "SAHMREALTIME", asof)
            self.assertEqual(len(requests), 1)
            self.assertEqual(result["observations"], [
                {"date": "1959-12-01", "value": "0.77"},
                {"date": "2019-09-01", "value": "0.0"},
            ])
            self.assertEqual(stored["observations"], result["observations"])
            self.assertEqual(result["asof"], "2019-09-30")
            self.assertNotIn("secret", (root/"SAHMREALTIME"/"2019-09-30.json").read_text())

    def test_sahm_future_observation_and_early_unpublished_revision_are_rejected(self):
        asof = date(2019, 9, 30)
        for date_text, revision_text, expected in [
            ("2019-10-01", "2019-09-12", "after requested as-of"),
            ("2019-09-01", "2019-10-01", "released after as-of"),
            ("1959-11-01", "2019-09-12", "precedes requested historical window"),
        ]:
            with self.subTest(observation=date_text, revision=revision_text):
                def handler(request):
                    return httpx.Response(200, json={"observations":[{
                        "date": date_text, "value": "0.77",
                        "realtime_start": revision_text,
                        "realtime_end": "9999-12-31",
                    }]})
                with TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                        with self.assertRaisesRegex(VintageError, expected):
                            fetch_snapshot("SAHMREALTIME", asof, api_key="secret",
                                           client=client, root=root)
                    self.assertEqual(list(root.rglob("*.json")), [])

    def test_daily_spread_retains_bounded_observation_history(self):
        def handler(request):
            self.assertNotEqual(request.url.params["observation_start"], "1959-12-01")
            self.assertEqual(request.url.params["observation_end"], "2020-03-31")
            return httpx.Response(200, json={"observations":[{
                "date": "2020-03-30", "value": "0.5",
            }]})
        with TemporaryDirectory() as tmp:
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                result = fetch_snapshot("T10Y3M", date(2020,3,31),
                                        api_key="secret", client=client, root=Path(tmp))
            self.assertEqual(result["status"], "ready")

    def test_probe_verifies_historical_alfred_parameters_not_just_authentication(self):
        requests = []
        def handler(request):
            requests.append(request)
            self.assertEqual(request.url.params["realtime_start"], "2020-01-31")
            self.assertEqual(request.url.params["realtime_end"], "2020-01-31")
            self.assertEqual(request.url.params["observation_end"], "2020-01-31")
            self.assertEqual(request.url.params["output_type"], "1")
            self.assertEqual(request.url.params["units"], "lin")
            return httpx.Response(200,json={
                "realtime_start":"2020-01-31",
                "realtime_end":"2020-01-31",
                "observations":[{"date":"2020-01-01","value":"0"}],
            })
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result=probe_access(api_key="a" * 32,client=client)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["requests"], 1)
        self.assertEqual(len(requests),1)

    def test_safe_probe_reports_rejected_api_key_without_leaking_request(self):
        secret = "a" * 32
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(400, json={
                "error_code": 400,
                "error_message": "The value for variable api_key is not registered"
            })
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            blocked = probe_access(api_key=secret, client=client)
            malformed = probe_access(api_key="placeholder", client=client)
        self.assertEqual(blocked["reason"], "fred_api_key_rejected")
        self.assertEqual(blocked["http_status"], 400)
        self.assertEqual(len(requests), 1)
        self.assertNotIn(secret, json.dumps(blocked))
        self.assertEqual(malformed["requests"], 0)

    def test_alfred_bad_request_reports_only_controlled_parameter_category(self):
        secret = "privateTOKEN123"
        cases = [
            ("The value for variable realtime_start is invalid", "fred_realtime_parameter_rejected"),
            ("Invalid observation_start", "fred_observation_parameter_rejected"),
            ("The series_id is not available", "fred_series_parameter_rejected"),
            ("Invalid limit parameter", "fred_limit_rejected"),
            ("Bad request with " + secret, "fred_bad_request"),
        ]
        from finance_dashboard.vintage import _safe_http_diagnostic
        for message, code in cases:
            with self.subTest(category=code):
                response = httpx.Response(400,json={"error_message":message},
                    request=httpx.Request("GET","https://api.stlouisfed.org/fred/series/observations"))
                item = _safe_http_diagnostic(response)
                self.assertEqual(item["reason"],code)
                self.assertNotIn(secret,json.dumps(item))

    def test_bulk_backfill_halts_immediately_on_systemic_http_errors(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(429, json={"error_message": "Rate limit exceeded"})
        with TemporaryDirectory() as tmp:
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                batch = backfill_batch(date(2020,1,1),date(2024,12,31),
                    list(SOURCES),api_key="a" * 32,client=client,root=Path(tmp),
                    max_requests=180,pause_seconds=0)
            self.assertEqual(len(calls), 1)
            self.assertEqual(batch["status"], "blocked")
            self.assertEqual(batch["halted_reason"], "fred_rate_limited")
            self.assertEqual(batch["missing_after_run"], 180)
            self.assertEqual(batch["downloaded_now"], 0)

    def test_failed_early_month_does_not_starve_later_valid_snapshot(self):
        calls = []
        def handler(request):
            sid = request.url.params["series_id"]
            asof = request.url.params["realtime_start"]
            calls.append((sid, asof))
            if sid == "SAHMREALTIME" and asof == "2020-01-31":
                return httpx.Response(503, json={"error_message": "private " + "z" * 32})
            return httpx.Response(200, json={"observations":[{
                "date":"2020-01-01", "value":"1",
                "realtime_start":"2020-01-01","realtime_end":"9999-12-31"}]})
        with TemporaryDirectory() as tmp:
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                first = backfill_batch(date(2020,1,1), date(2020,2,29),
                    ["T10Y3M","SAHMREALTIME"],api_key="a"*32,client=client,
                    root=Path(tmp),max_requests=2,pause_seconds=0)
                excluded = {("SAHMREALTIME", date(2020,1,31))}
                second = backfill_batch(date(2020,1,1), date(2020,2,29),
                    ["T10Y3M","SAHMREALTIME"],api_key="a"*32,client=client,
                    root=Path(tmp),max_requests=2,pause_seconds=0,
                    skip_failed=excluded)
            self.assertEqual(first["failed_now"][0]["reason"],"fred_server_error")
            self.assertNotIn("z"*32,json.dumps(first))
            self.assertEqual(second["downloaded_now"],2)
            self.assertEqual(second["missing_after_run"],1)
            self.assertEqual(second["status"],"partial")
            self.assertEqual(len(calls),4)

    def test_invalid_asof_reasons_are_diagnostic_without_provider_text(self):
        from finance_dashboard.vintage import _snapshot_failure_diagnostic
        expected = {
            "ALFRED observation precedes requested historical window":
                "fred_observation_before_window",
            "ALFRED observation is after requested as-of date":
                "fred_observation_after_asof",
            "Response contains observation released after as-of date":
                "fred_observation_after_publication",
            "Incorrect ALFRED realtime interval": "fred_realtime_mismatch",
        }
        for message, code in expected.items():
            self.assertEqual(
                _snapshot_failure_diagnostic(VintageError(message))["reason"],code)
        self.assertEqual(
            _snapshot_failure_diagnostic(VintageError("secret="+("x"*32)))["reason"],
            "vintage_validation_failed")

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

    def test_resume_backfill_only_requests_missing_month_end_vintages(self):
        calls=[]
        def handler(request):
            calls.append((request.url.params["series_id"],
                          request.url.params["realtime_start"]))
            return httpx.Response(200,json={"observations":[{
                "date":"2020-01-01","value":"0.5",
                "realtime_start":"2020-01-10",
                "realtime_end":"9999-12-31"}]})
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                first=backfill_batch(date(2020,1,1),date(2020,3,31),
                    ["T10Y3M"],api_key="private",client=client,root=root,
                    max_requests=2,pause_seconds=0)
                self.assertEqual(first["missing_after_run"],1)
                self.assertEqual(first["downloaded_now"],2)
                self.assertEqual(first["next_missing"]["asof"],"2020-03-31")
                second=backfill_batch(date(2020,1,1),date(2020,3,31),
                    ["T10Y3M"],api_key="private",client=client,root=root,
                    max_requests=2,pause_seconds=0)
                self.assertEqual(second["already_cached_before_run"],2)
                self.assertEqual(second["downloaded_now"],1)
                self.assertEqual(second["status"],"complete")
                self.assertEqual(len(calls),3)
                self.assertNotIn("private",(root/"T10Y3M"/"2020-01-31.json").read_text())
                with self.assertRaises(VintageError):
                    backfill_batch(date(2020,1,1),date(2020,3,31),
                        ["T10Y3M"],api_key="fake",client=client,root=root,
                        max_requests=181,pause_seconds=0)

    def test_first_real_publication_bounds_skip_unavailable_snapshots(self):
        calls = []
        def handler(request):
            calls.append((request.url.path, request.url.params["series_id"]))
            if request.url.path.endswith("/vintagedates"):
                self.assertEqual(request.url.params["sort_order"], "asc")
                self.assertEqual(request.url.params["limit"], "1")
                return httpx.Response(200, json={"vintage_dates":["2020-02-15"]})
            return httpx.Response(200, json={"observations":[{
                "date":"2020-02-01", "value":"0.5",
                "realtime_start":"2020-02-15",
                "realtime_end":"9999-12-31"}]})
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                bounds = first_available_vintages(
                    ["T10Y3M"], api_key="a" * 32, client=client)
                result = backfill_batch(date(2020,1,1), date(2020,3,31),
                    ["T10Y3M"], api_key="a" * 32, client=client,
                    root=root, max_requests=4, pause_seconds=0,
                    first_available=bounds)
            self.assertFalse((root/"T10Y3M"/"2020-01-31.json").exists())
            self.assertEqual(result["prepublication_excluded"], 1)
            self.assertEqual(result["source_vintages_requested"], 2)
            self.assertEqual(result["downloaded_now"], 2)
            self.assertEqual(result["missing_after_run"], 0)
            self.assertEqual(len(calls), 3)

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

    def test_overlapping_recession_windows_are_not_independent_events(self):
        rows=[]
        for i in range(48):
            day=date(2010+i//12,i%12+1,28).isoformat()
            rows.append({"asof":day,"outcome":int(10<=i<20 or 35<=i<43),
                "estimated_probability":0.6,"past_prevalence_baseline":0.2})
        audit=independent_holdout_diagnostics(rows,6)
        self.assertEqual(audit["positive_event_episodes_approx"],2)
        self.assertEqual(audit["nonoverlapping_test_cases"],8)
        self.assertIsNone(audit["nonoverlapping_evaluation"])
        self.assertEqual(audit["validation_status"],"not_independently_validated")

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
