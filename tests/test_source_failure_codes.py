"""Provider error audit must be actionable without leaking tokens or request URLs."""
import unittest

import httpx

from finance_dashboard.service import safe_source_failure_code


class SourceFailureCodeTests(unittest.TestCase):
    def test_http_429_and_404_are_preserved_without_url_or_credential(self):
        self.assertEqual(safe_source_failure_code(
            RuntimeError("Provider HTTP 429 (api.stlouisfed.org)?api_key=TOPSECRET")),
            "provider_http_429")
        self.assertEqual(safe_source_failure_code(
            RuntimeError("Provider HTTP 404 (api.stlouisfed.org)")),
            "provider_http_404")

    def test_httpx_response_status_is_classified_without_exposing_signed_query(self):
        request = httpx.Request("GET", "https://query1.finance.yahoo.com/example?secret=TOKEN")
        response = httpx.Response(503,request=request)
        exc = httpx.HTTPStatusError("Upstream failure TOKEN",request=request,response=response)
        self.assertEqual(safe_source_failure_code(exc),"provider_http_503")
        self.assertEqual(safe_source_failure_code(
            RuntimeError("Provider HTTP 502 (api.provider.example)?key=TOKEN")),
            "provider_http_502")

    def test_network_failure_and_unparseable_response_have_fixed_codes(self):
        self.assertEqual(safe_source_failure_code(httpx.ConnectTimeout("Bearer SECRET")),
                         "source_transport_failed")
        self.assertEqual(safe_source_failure_code(ValueError("Unrecognized unit SECRET")),
                         "source_invalid")
        self.assertEqual(safe_source_failure_code(Exception("api_key=my_credential")),
                         "provider_failed")


if __name__ == "__main__":
    unittest.main()
