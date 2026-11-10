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


class VintageTests(unittest.TestCase):
    def test_m02_real_yield_has_same_genuine_asof_contract_as_nominal_and_breakeven(self):
        self.assertIn("DFII10", SOURCES)
        calls = []
        def response(request):
            calls.append(request)
            self.assertEqual(request.url.params["series_id"], "DFII10")
            self.assertEqual(request.url.params["realtime_start"], "2020-03-31")
            self.assertEqual(request.url.params["realtime_end"], "2020-03-31")
            return httpx.Response(200, json={"observations": [
                {"date": "2020-03-31", "value": "-0.07",
                 "realtime_start": "2020-03-31", "realtime_end": "2020-04-01"}]})
        with TemporaryDirectory() as temp, httpx.Client(transport=httpx.MockTransport(response)) as client:
            result = fetch_snapshot("DFII10", date(2020, 3, 31),
                api_key="syntheticsecret", client=client, root=Path(temp))
            self.assertEqual(result["observations"], [{"date": "2020-03-31", "value": "-0.07"}])
            self.assertEqual(len(calls), 1)

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

    def test_snapshot_inventory_distinguishes_no_data_from_populated_vintage(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "DGS10"
            folder.mkdir()
            for day, status, obs in (
                ("2026-01-31","no_data",[]),
                ("2026-02-28","ready",[{"date":"2026-02-02","value":"4.5"}]),
            ):
                data = {"schema_version":1, "provider":"ALFRED",
                        "series_id":"DGS10", "asof":day,
                        "realtime_start":day, "realtime_end":day,
                        "status":status, "observations":obs}
                (folder / (day+".json")).write_text(json.dumps(data))
            inventory = available_snapshots(root)
            entry = next(x for x in inventory["series"]
                         if x["series_id"] == "DGS10")
            self.assertEqual(entry["count"],2)
            self.assertEqual(entry["populated_vintage_count"],1)
            self.assertEqual(entry["first_populated_asof"],"2026-02-28")
            self.assertEqual(entry["last_populated_asof"],"2026-02-28")

    def test_dfa_vintage_preserves_actual_historical_population_without_future_leakage(self):
        series = "WFRBST01134"
        asof = date(2020, 3, 31)
        def handler(request):
            self.assertEqual(request.url.params["series_id"], series)
            self.assertEqual(request.url.params["observation_start"], "1989-01-01")
            self.assertEqual(request.url.params["observation_end"], "2020-03-31")
            self.assertEqual(request.url.params["realtime_start"], "2020-03-31")
            self.assertEqual(request.url.params["realtime_end"], "2020-03-31")
            return httpx.Response(200, json={"observations": [
                {"date": "1989-07-01", "value": "24.6",
                 "realtime_start": "2019-06-21",
                 "realtime_end": "2020-04-01"},
                {"date": "2019-10-01", "value": "31.4",
                 "realtime_start": "2020-01-15",
                 "realtime_end": "2020-04-01"},
            ]})
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                result = fetch_snapshot(series, asof, api_key="syntheticsecret",
                                        client=client, root=root)
                self.assertEqual(len(result["observations"]), 2)
                self.assertEqual(result["asof"], asof.isoformat())
                self.assertEqual(result["observations"][0]["date"], "1989-07-01")
                self.assertTrue((root / series / "2020-03-31.json").is_file())

    def test_dfa_source_date_before_first_publication_is_not_a_valid_asof(self):
        for sid in ("WFRBST01134", "WFRBSN09161",
                    "WFRBSN40188", "WFRBSB50215"):
            self.assertIn(sid, SOURCES)
            self.assertEqual(SOURCES[sid]["frequency"], "Q")
            self.assertLessEqual(SOURCES[sid]["maximum_age_days"], 225)

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
                    max_requests=180)
            # All requested vintages remain missing after a rate-limit halt.
            # This must scale with the registered source set; Phase 2 added
            # several ALFRED sources, so a fixed old 3-series count is wrong.
            requested = len(_month_ends(date(2020, 1, 1), date(2024, 12, 31))) * len(SOURCES)
            self.assertEqual(len(calls), 1)
            self.assertEqual(batch["status"], "blocked")
            self.assertEqual(batch["halted_reason"], "fred_rate_limited")
            self.assertEqual(batch["source_vintages_requested"], requested)
            self.assertEqual(batch["missing_after_run"], requested)
            self.assertEqual(batch["attempted_now"], 1)
            self.assertEqual(len(batch["failed_now"]), 1)
            self.assertEqual(batch["failed_now"][0]["reason"], "fred_rate_limited")
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
                    root=Path(tmp),max_requests=2)
                excluded = {("SAHMREALTIME", date(2020,1,31))}
                second = backfill_batch(date(2020,1,1), date(2020,2,29),
                    ["T10Y3M","SAHMREALTIME"],api_key="a"*32,client=client,
                    root=Path(tmp),max_requests=2,
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
            self.assertEqual(second["captured"],len(SOURCES))
            self.assertEqual(len(called),len(SOURCES))

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
                    max_requests=2)
                self.assertEqual(first["missing_after_run"],1)
                self.assertEqual(first["downloaded_now"],2)
                self.assertEqual(first["next_missing"]["asof"],"2020-03-31")
                second=backfill_batch(date(2020,1,1),date(2020,3,31),
                    ["T10Y3M"],api_key="private",client=client,root=root,
                    max_requests=2)
                self.assertEqual(second["already_cached_before_run"],2)
                self.assertEqual(second["downloaded_now"],1)
                self.assertEqual(second["status"],"complete")
                self.assertEqual(len(calls),3)
                self.assertNotIn("private",(root/"T10Y3M"/"2020-01-31.json").read_text())
                with self.assertRaises(VintageError):
                    backfill_batch(date(2020,1,1),date(2020,3,31),
                        ["T10Y3M"],api_key="fake",client=client,root=root,
                        max_requests=181)

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
                    root=root, max_requests=4,
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


if __name__=="__main__":
    unittest.main()
