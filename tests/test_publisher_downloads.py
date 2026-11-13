"""Security and bounded-stream regression checks for publisher acquisition."""
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import httpx

from finance_dashboard.publisher_downloads import (
    PublisherDownloadError, _approved, fetch_publisher_file)


class PublisherDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "source.bin"
        self.url = "https://wid.world/bulk_download/WID_data_WO.csv"
        self.role = {"download_url": self.url, "max_bytes": 10000}

    def _client(self, handler):
        client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
        self.addCleanup(client.close)
        return client

    def test_streams_and_hashes_publisher_bytes(self):
        raw = b"variable;year;value\nexample;2020;3.5\n"
        def handler(req):
            self.assertEqual(str(req.url), self.url)
            return httpx.Response(200, content=raw, request=req,
                                  headers={"content-type": "text/csv"})
        result = fetch_publisher_file(self.role, self.path, client=self._client(handler))
        self.assertEqual(self.path.read_bytes(), raw)
        self.assertEqual(result["sha256"], sha256(raw).hexdigest())
        self.assertEqual(result["bytes"], len(raw))
        self.assertEqual(result["requested_url"], self.url)

    def test_redirect_to_unlisted_hostname_is_rejected_before_second_request(self):
        urls = []
        def handler(req):
            urls.append(str(req.url))
            return httpx.Response(302, request=req, headers={
                "location": "http://169.254.169.254/latest/meta-data/"})
        with self.assertRaises(PublisherDownloadError) as failure:
            fetch_publisher_file(self.role, self.path, client=self._client(handler))
        self.assertEqual(failure.exception.code, "publisher_redirect_unapproved")
        self.assertEqual(urls, [self.url])
        self.assertFalse(self.path.exists())

    def test_dataverse_documented_object_store_is_the_only_cross_host_exception(self):
        start = "https://dataverse.nl/api/access/datafile/512630"
        allowed = "https://objectstore.surf.nl/store/10.34894/YWT2IX/abc"
        self.assertTrue(_approved(start, allowed))
        self.assertFalse(_approved(start, "https://objectstore.surf.nl/other/data"))
        self.assertFalse(_approved(start, "https://objectstore.surf.nl.evil.test/store/10.34894/YWT2IX/a"))
        self.assertFalse(_approved(start, "http://objectstore.surf.nl/store/10.34894/YWT2IX/a"))
        self.assertFalse(_approved(self.url, allowed))

    def test_html_challenge_is_not_accepted_as_original(self):
        client = self._client(lambda req: httpx.Response(
            200, request=req, content=b"<!doctype html><title>Challenge</title>"))
        with self.assertRaises(PublisherDownloadError) as failure:
            fetch_publisher_file(self.role, self.path, client=client)
        self.assertEqual(failure.exception.code, "publisher_returned_html")
        self.assertFalse(self.path.exists())

    def test_truncated_or_oversized_responses_are_rejected(self):
        role = {**self.role, "max_bytes": 10}
        client = self._client(lambda req: httpx.Response(
            200, request=req, content=b"too much data to be accepted"))
        with self.assertRaises(PublisherDownloadError) as failure:
            fetch_publisher_file(role, self.path, client=client)
        self.assertEqual(failure.exception.code, "publisher_file_too_large")
        self.assertFalse(self.path.exists())

    def test_http_errors_remain_visible_as_diagnostic_codes(self):
        client = self._client(lambda req: httpx.Response(403, request=req))
        with self.assertRaises(PublisherDownloadError) as failure:
            fetch_publisher_file(self.role, self.path, client=client)
        self.assertEqual(failure.exception.code, "publisher_http_403")


if __name__ == "__main__":
    unittest.main()
