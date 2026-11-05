"""Publisher errors are diagnosed with bounded, native OECD STAN requests."""
from hashlib import sha256
import json
import unittest

import httpx

from finance_dashboard.stan_originals import STAN_DATAFLOW_ID
from scripts.phase2_stan_sources import diagnose_publisher


def value_added_original(*, activity="_T"):
    return (
        "DATAFLOW,FREQ,REF_AREA,ACTIVITY,MEASURE,PRICE_BASE,"
        "UNIT_MEASURE,TIME_PERIOD,OBS_VALUE,OBS_STATUS,UNIT_MULT,CURRENCY\n"
        f"{STAN_DATAFLOW_ID},A,PRT,{activity},B1G,V,XDC,2020,123,A,6,EUR\n"
    ).encode()


class StanNativeDiagnosticsTests(unittest.TestCase):
    def test_published_control_schema_distinguishes_candidate_measure_server_errors(self):
        requests = []
        raw = value_added_original()
        def respondent(request):
            requests.append(request)
            url = str(request.url)
            if "/A.PRT._T.B1G.V.XDC" in url:
                return httpx.Response(200, content=raw)
            if "/A.PRT..B1G.V.XDC" in url:
                return httpx.Response(200, content=raw)
            return httpx.Response(500, content=b"Do not expose upstream HTML or keys")
        with httpx.Client(transport=httpx.MockTransport(respondent)) as client:
            result = diagnose_publisher(client, country="PRT", year=2020)
        self.assertEqual(result["publisher_requests"], 8)
        self.assertEqual(len(requests), 8)
        checks = {item["check"]: item for item in result["checks"]}
        control = checks["published_value_added_control"]
        self.assertEqual(control["state"], "validated_native_csv")
        self.assertEqual(control["source_sha256"], sha256(raw).hexdigest())
        self.assertEqual(control["observed_measure_counts"], {"B1G": 1})
        self.assertEqual(control["original_numeric_observations"], 1)
        self.assertEqual(control["http_status"], 200)
        self.assertIn("format=csvfile", str(requests[0].url))
        self.assertNotIn("format=csvfile", str(requests[1].url))
        self.assertEqual(requests[0].url.params["endPeriod"], "2020")
        self.assertEqual(checks["native_measure_B2N"]["http_status"], 500)
        self.assertEqual(checks["five_measure_total_activity_one_year"]["failure_category"],
                         "publisher_http_5xx")
        self.assertTrue(result["no_archive_writes"])
        self.assertTrue(result["no_macro_database_writes"])
        self.assertFalse(result["scientific_analysis_certified"])
        self.assertFalse(result["full_historical_acquisition_verified"])
        self.assertNotIn("Do not expose", json.dumps(result))

    def test_unavailable_publisher_is_reported_without_unbounded_retries(self):
        calls = []
        def respondent(request):
            calls.append(str(request.url))
            return httpx.Response(503, content=b"Retry after maintenance")
        with httpx.Client(transport=httpx.MockTransport(respondent)) as client:
            result = diagnose_publisher(client, country="PRT", year=2020)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["publisher_requests"], 1)
        self.assertEqual(result["checks"][0]["http_status"], 503)
        self.assertEqual(result["checks"][0]["failure_category"], "publisher_http_5xx")
        self.assertNotIn("Retry after maintenance", json.dumps(result))

    def test_http_200_but_non_native_csv_is_not_accepted(self):
        with httpx.Client(transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=b"<html>error</html>"))) as client:
            result = diagnose_publisher(client, country="PRT", year=2020)
        self.assertTrue(result["checks"])
        self.assertTrue(all(item["state"] == "source_check_failed" for item in result["checks"]))
        self.assertTrue(all(item["reason_type"] == "ProviderError"
                            for item in result["checks"]))
        self.assertFalse(result["full_historical_acquisition_verified"])


if __name__ == "__main__":
    unittest.main()
