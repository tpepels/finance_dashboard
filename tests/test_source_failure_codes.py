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

    def test_ecb_and_market_wrapped_http_denials_are_not_mislabeled_source_invalid(self):
        self.assertEqual(safe_source_failure_code(
            ValueError("ECB FX HTTP 403 for USD")), "provider_http_403")
        self.assertEqual(safe_source_failure_code(
            ValueError("ECB FX HTTP 429 for GBP")), "provider_http_429")
        self.assertEqual(safe_source_failure_code(
            ValueError("Market feed rejected VT, HTTP 429")), "provider_http_429")

    def test_httpx_response_status_is_classified_without_exposing_signed_query(self):
        request = httpx.Request("GET", "https://query1.finance.yahoo.com/example?secret=TOKEN")
        response = httpx.Response(503,request=request)
        exc = httpx.HTTPStatusError("Upstream failure TOKEN",request=request,response=response)
        self.assertEqual(safe_source_failure_code(exc),"provider_http_503")
        self.assertEqual(safe_source_failure_code(
            RuntimeError("Provider HTTP 502 (api.provider.example)?key=TOKEN")),
            "provider_http_502")

    def test_source_parse_failures_use_precise_safe_categories(self):
        cases = [
            ("FRED observations list missing", "fred_schema_invalid"),
            ("FRED response contains no usable observations", "fred_empty"),
            ("FRED public DATE/VALUE table missing or ambiguous", "fred_table_invalid"),
            ("Invalid observation period: '2026-02-01'", "source_date_invalid"),
            ("Repeated observation: 2025-01-01", "source_duplicate_period"),
            ("Provider returned observations outside requested window", "source_window_invalid"),
            ("Shiller source workbook has incomplete monthly CAPE history", "shiller_incomplete"),
            ("Invalid Shiller Excel workbook or Data sheet", "shiller_workbook_invalid"),
            ("Shiller download is not an Excel workbook", "shiller_download_invalid"),
            ("FRED source has no observations in requested window", "fred_window_empty"),
            ("ECB FX series identity mismatch", "fx_identity_mismatch"),
        ]
        for message, category in cases:
            with self.subTest(category=category):
                self.assertEqual(safe_source_failure_code(ValueError(message)), category)
        secret = "FRED observations list missing api_key=SECRET"
        self.assertEqual(safe_source_failure_code(ValueError(secret)),
                         "fred_schema_invalid")

    def test_gold_spot_errors_are_actionable_and_do_not_expose_responses(self):
        from finance_dashboard.source_coverage import SAFE_ERROR_CODES
        from finance_dashboard.provider_parsers import parse_gold_api_spot
        examples = [
            ("Gold spot response malformed", "gold_spot_invalid_response"),
            ("Gold spot source identity or currency invalid", "gold_spot_identity_mismatch"),
            ("Gold spot USD exchange conversion unexpected", "gold_spot_conversion_mismatch"),
            ("Gold spot price lacks valid UTC timestamp", "gold_spot_invalid_timestamp"),
            ("Gold spot price must have timezone", "gold_spot_invalid_timestamp"),
            ("Gold spot observation future dated", "gold_spot_future_timestamp"),
            ("Gold spot observation too old for snapshot", "gold_spot_stale_quote"),
            ("Gold spot snapshot precedes requested window", "gold_spot_before_window"),
            ("Invalid indicative gold spot price", "gold_spot_invalid_price"),
            ("Gold spot catalog identity differs from live API", "gold_spot_source_mapping_mismatch"),
        ]
        for message, category in examples:
            with self.subTest(category=category):
                self.assertEqual(safe_source_failure_code(ValueError(
                    message + " api_key=PRIVATE")), category)
                self.assertIn(category, SAFE_ERROR_CODES)
        # Current documented payload remains strictly parsed; a syntactically
        # valid HTTP 200 JSON body with the wrong currency cannot be accepted.
        with self.assertRaises(ValueError) as ctx:
            parse_gold_api_spot({
                "symbol": "XAU", "name": "Gold", "currency": "EUR",
                "price": 3900, "updatedAt": "2026-11-13T10:01:53Z",
            })
        self.assertEqual(safe_source_failure_code(ctx.exception),
                         "gold_spot_identity_mismatch")

    def test_network_failure_and_unparseable_response_have_fixed_codes(self):
        self.assertEqual(safe_source_failure_code(httpx.ConnectTimeout("Bearer SECRET")),
                         "source_transport_failed")
        self.assertEqual(safe_source_failure_code(ValueError("Unrecognized unit SECRET")),
                         "source_invalid")
        self.assertEqual(safe_source_failure_code(Exception("api_key=my_credential")),
                         "provider_failed")


if __name__ == "__main__":
    unittest.main()
