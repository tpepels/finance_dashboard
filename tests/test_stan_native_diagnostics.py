"""Publisher errors are diagnosed with bounded, native OECD STAN requests."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

import httpx

from finance_dashboard.stan_originals import (
    STAN_DATAFLOW_ID, STAN_VERIFIED_PORTUGAL_MEASURES,
    read_stan_evidence, store_stan_original,
)
from scripts.phase2_stan_sources import acquire, diagnose_publisher


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

    def test_429_is_rate_limiting_and_stops_probe_requests(self):
        calls = []
        def respondent(request):
            calls.append(request)
            return httpx.Response(429, content=b"Publisher rate limiting")
        with httpx.Client(transport=httpx.MockTransport(respondent)) as client:
            result = diagnose_publisher(client, country="PRT", year=2020)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["publisher_requests"], 1)
        self.assertEqual(result["checks"][0]["failure_category"],
                         "publisher_rate_limited")
        self.assertNotIn("Publisher rate limiting", json.dumps(result))

    def test_http_200_but_non_native_csv_is_not_accepted(self):
        with httpx.Client(transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=b"<html>error</html>"))) as client:
            result = diagnose_publisher(client, country="PRT", year=2020)
        self.assertTrue(result["checks"])
        self.assertTrue(all(item["state"] == "source_check_failed" for item in result["checks"]))
        self.assertTrue(all(item["reason_type"] == "ProviderError"
                            for item in result["checks"]))
        self.assertFalse(result["full_historical_acquisition_verified"])


def four_measure_original():
    return (
        "DATAFLOW,FREQ,REF_AREA,ACTIVITY,MEASURE,PRICE_BASE,"
        "UNIT_MEASURE,TIME_PERIOD,OBS_VALUE,OBS_STATUS,UNIT_MULT,CURRENCY\n"
        + "".join(
            f"{STAN_DATAFLOW_ID},A,PRT,C,{measure},V,XDC,2020,{value},A,6,EUR\n"
            for measure, value in (("B1G", 120), ("D1", 70),
                                   ("P51C", 12), ("D29X39", 3))
        )
    ).encode()


class StanAcquisitionResilienceTests(unittest.TestCase):
    def test_four_validated_native_measures_preserved_and_cached(self):
        calls = []
        raw = four_measure_original()
        def respondent(request):
            calls.append(request)
            self.assertIn("B1G+D1+P51C+D29X39", str(request.url))
            self.assertNotIn("B2N", str(request.url))
            return httpx.Response(200, content=raw)
        with TemporaryDirectory() as temp:
            root = Path(temp)
            with httpx.Client(transport=httpx.MockTransport(respondent)) as client:
                first = acquire(client, root, countries=("PRT",), start_year=1970)
                second = acquire(client, root, countries=("PRT",), start_year=1970)
            self.assertEqual(len(calls), 1)
            self.assertEqual(first["original_responses_archived"], 1)
            self.assertEqual(first["acquisition_failures"], 0)
            self.assertEqual(first["unresolved_candidate_measures"], ["B2N"])
            self.assertEqual(second["already_verified_archives"], 1)
            self.assertEqual(second["original_responses_archived"], 0)
            self.assertEqual(second["acquisition_failures"], 0)
            checked = read_stan_evidence(root, countries=("PRT",))
            self.assertEqual(checked["country_count"], 1)
            self.assertEqual(checked["country_results"][0]["covered_native_measures"],
                             sorted(STAN_VERIFIED_PORTUGAL_MEASURES))
            self.assertEqual(checked["country_results"][0]["missing_candidate_measures"],
                             ["B2N"])
            self.assertFalse(checked["full_history_verified"])
            self.assertFalse(first["scientific_analysis_certified"])

    def test_rate_limit_stops_country_batch_and_archives_nothing(self):
        calls = []
        def respondent(request):
            calls.append(str(request.url))
            return httpx.Response(429, content=b"Rate limited")
        with TemporaryDirectory() as temp:
            root = Path(temp)
            with httpx.Client(transport=httpx.MockTransport(respondent)) as client:
                result = acquire(client, root, countries=("PRT", "DEU"),
                                 start_year=1970)
            self.assertEqual(len(calls), 1)
            self.assertTrue(result["stopped_on_publisher_backpressure"])
            self.assertEqual(result["original_responses_archived"], 0)
            self.assertEqual(result["acquisition_failures"], 2)
            self.assertEqual(result["acquisitions"][0]["failure_category"],
                             "publisher_rate_limited")
            self.assertEqual(result["acquisitions"][1]["status"],
                             "deferred_publisher_backpressure")
            self.assertFalse((root / "stan-2025").exists())
            self.assertNotIn("Rate limited", json.dumps(result))

    def test_404_does_not_reclassify_unavailable_measure_as_zero(self):
        with TemporaryDirectory() as temp:
            with httpx.Client(transport=httpx.MockTransport(
                    lambda request: httpx.Response(404, content=b"No matching series"))) as client:
                result = acquire(client, Path(temp), countries=("PRT",),
                                 start_year=1970, measures=("B2N",))
            self.assertEqual(result["acquisition_failures"], 1)
            self.assertEqual(result["acquisitions"][0]["http_status"], 404)
            self.assertEqual(result["acquisitions"][0]["failure_category"],
                             "no_published_observations_for_selection")
            self.assertFalse(result["source_evidence"]["original_source_hash_verified"])
            self.assertFalse(result["scientific_analysis_certified"])


if __name__ == "__main__":
    unittest.main()
