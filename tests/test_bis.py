"""Offline SDMX decoding and transport contract tests. No network calls."""
from datetime import date
from decimal import Decimal
import unittest

import httpx

from finance_dashboard.bis import ACCEPT, BisPolicyClient, ProviderError, parse_bis_json


def fixture(country="US", values=("3.625", "3.5")):
    return {
        "meta": {"prepared": "2026-08-21T07:45:40Z"},
        "data": {
            "dataSets": [{"series": {
                "0:0": {"observations": {"0": [values[0], 0, 0], "1": [values[1], 0, 0]}}
            }}],
            "structures": [{
                "dimensions": {
                    "series": [
                        {"id": "FREQ", "values": [{"id": "D"}]},
                        {"id": "REF_AREA", "values": [{"id": country}]},
                    ],
                    "observation": [{"id": "TIME_PERIOD", "values": [
                        {"id": "2026-08-17"}, {"id": "2026-08-18"}
                    ]}],
                }
            }],
        }
    }


class BisTests(unittest.TestCase):
    def test_valid_response(self):
        result, prepared = parse_bis_json(fixture(), "policy_rate.us.bis")
        self.assertEqual(result[date(2026, 8, 17)], Decimal("3.625"))
        self.assertEqual(prepared.isoformat(), "2026-08-21T07:45:40+00:00")

    def test_wrong_country_rejected(self):
        with self.assertRaisesRegex(ProviderError, "unexpected series"):
            parse_bis_json(fixture("JP"), "policy_rate.us.bis")

    def test_source_nan_is_missing_not_zero(self):
        result, _ = parse_bis_json(fixture(values=("NaN", "3")), "policy_rate.us.bis")
        self.assertEqual(result, {date(2026, 8, 18): Decimal("3")})

    def test_source_null_is_missing_not_zero(self):
        result, _ = parse_bis_json(fixture(values=(None, "3")), "policy_rate.us.bis")
        self.assertEqual(result, {date(2026, 8, 18): Decimal("3")})

    def test_infinite_value_rejected(self):
        with self.assertRaisesRegex(ProviderError, "Infinite BIS observation"):
            parse_bis_json(fixture(values=("Infinity", "3")), "policy_rate.us.bis")

    def test_malformed_index_rejected(self):
        data = fixture()
        data["data"]["dataSets"][0]["series"] = {
            "0:88": {"observations": {"0": ["2"]}}
        }
        with self.assertRaisesRegex(ProviderError, "dimension index"):
            parse_bis_json(data, "policy_rate.us.bis")

    def test_missing_observations_rejected(self):
        data = fixture()
        data["data"]["dataSets"][0]["series"]["0:0"]["observations"] = {}
        with self.assertRaisesRegex(ProviderError, "No observations"):
            parse_bis_json(data, "policy_rate.us.bis")

    def test_source_transport(self):
        seen = {}
        def handler(request):
            seen["url"] = str(request.url)
            seen["accept"] = request.headers["accept"]
            return httpx.Response(200, json=fixture())
        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as client:
            result = BisPolicyClient(client, retries=0).fetch("policy_rate.us.bis", date(2026, 1, 1))
        self.assertEqual(seen["accept"], ACCEPT)
        self.assertIn("D.US", seen["url"])
        self.assertIn("startPeriod=2026-01-01", seen["url"])
        self.assertEqual(len(result.observations), 2)

    def test_provider_http_error_is_not_silenced(self):
        with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(404))) as client:
            with self.assertRaises(httpx.HTTPStatusError):
                BisPolicyClient(client, retries=0).fetch("policy_rate.us.bis")

    def test_no_unbounded_retry(self):
        calls = []
        def handler(request):
            calls.append(1)
            return httpx.Response(503)
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(httpx.HTTPStatusError):
                BisPolicyClient(client, retries=0).fetch("policy_rate.us.bis")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
