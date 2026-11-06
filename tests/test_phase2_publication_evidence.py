"""Original ALFRED publisher revisions: receipt proof, cache reuse, corruption."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

import httpx

from finance_dashboard.phase2_publication_evidence import (
    capture_first_series_vintage, publisher_vintage_evidence,
    read_first_series_vintage,
)
from finance_dashboard.publication_acquisition import publication_batch


KEY = "a" * 32


class PublisherRevisionOriginalTests(unittest.TestCase):
    def test_real_response_bytes_and_receipts_are_retained_and_reverified(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            queries = []
            def handler(request):
                self.assertEqual(request.url.host, "api.stlouisfed.org")
                self.assertEqual(request.url.params["series_id"], "DGS10")
                queries.append(str(request.url))
                return httpx.Response(
                    200, json={"vintage_dates": ["2020-03-15"]})
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                first = capture_first_series_vintage(
                    "DGS10", root=root, api_key=KEY, client=client)
                self.assertEqual(first["publisher_requests"], 1)
                self.assertEqual(first["status"], "verified_original_publisher_vintage")
                self.assertEqual(first["first_available_alfred_series_vintage"],
                                 "2020-03-15")
                self.assertFalse(first["first_publication_verified"])
                second = capture_first_series_vintage(
                    "DGS10", root=root, api_key=KEY, client=client)
                self.assertTrue(second["cache_hit"])
                self.assertEqual(second["publisher_requests"], 0)
                self.assertEqual(len(queries), 1)
            evidence = publisher_vintage_evidence(root, {"DGS10", "USREC"})
            self.assertEqual(evidence["verified_series_vintage_sources"], 1)
            self.assertFalse(evidence["observation_level_first_publication_verified"])
            self.assertEqual(evidence["series"]["USREC"]["status"],
                             "missing_original_vintage")
            original = next(root.glob(
                "alfred-publisher-first-vintage/DGS10/*/response.json"))
            self.assertNotIn(KEY, original.read_text())
            self.assertNotIn(KEY, next(root.glob(
                "alfred-publisher-first-vintage/DGS10/*/manifest.json"
            )).read_text())

    def test_tampered_original_is_rejected_without_refetching(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            with httpx.Client(transport=httpx.MockTransport(
                    lambda r: httpx.Response(
                        200, json={"vintage_dates": ["2019-07-01"]}))) as client:
                capture_first_series_vintage(
                    "DGS10", root=root, api_key=KEY, client=client)
                path = next(root.glob(
                    "alfred-publisher-first-vintage/DGS10/*/response.json"))
                path.write_bytes(b'{"vintage_dates":["2020-01-01"]}')
                with self.assertRaises(ValueError):
                    read_first_series_vintage(root, "DGS10")
                with self.assertRaises(ValueError):
                    capture_first_series_vintage(
                        "DGS10", root=root, api_key=KEY, client=client)
            report = publisher_vintage_evidence(root, {"DGS10"})
            self.assertEqual(report["invalid_original_series"], ["DGS10"])

    def test_batch_read_only_and_partial_future_originals_are_not_first_release(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            result = publication_batch(
                root, series=["DGS10", "USREC"], acquire=False,
                budget=2)
            self.assertEqual(result["publisher_requests"], 0)
            self.assertFalse(result["observations_first_publication_verified"])
            with httpx.Client(transport=httpx.MockTransport(
                    lambda r: httpx.Response(
                        200, json={"vintage_dates": ["2020-01-01"]}))) as client:
                acquired = publication_batch(
                    root, series=["DGS10", "USREC"], acquire=True,
                    budget=1, api_key=KEY, client=client)
            self.assertEqual(acquired["publisher_requests"], 1)
            self.assertEqual(acquired["after_verified"], 1)
            self.assertEqual(acquired["results"][1]["state"],
                             "deferred_request_budget")
            with httpx.Client(transport=httpx.MockTransport(
                    lambda r: httpx.Response(
                        200, json={"vintage_dates": ["2010-01-01"]}))) as client:
                resumed = publication_batch(
                    root, series=["DGS10", "USREC"], acquire=True,
                    budget=2, api_key=KEY, client=client)
            self.assertEqual(resumed["publisher_requests"], 1)
            self.assertEqual(resumed["after_verified"], 2)
            self.assertFalse(resumed["scientific_analysis_certified"])

    def test_reject_unregistered_series_and_nonfinite_or_invalid_dates(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            with httpx.Client(transport=httpx.MockTransport(
                    lambda r: httpx.Response(
                        200, json={"vintage_dates": ["9999-01-01"]}))) as client:
                with self.assertRaises(ValueError):
                    capture_first_series_vintage(
                        "DGS10", root=root, api_key=KEY, client=client)
            with self.assertRaises(ValueError):
                read_first_series_vintage(root, "NOT-A-REGISTERED-SERIES")


if __name__ == "__main__":
    unittest.main()
