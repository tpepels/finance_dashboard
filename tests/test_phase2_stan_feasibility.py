"""OECD STAN original-field feasibility never creates research series or evidence."""
from datetime import date
from hashlib import sha256
import unittest

import httpx

from scripts.phase2_source_probe import probe_stan_candidates


HEADER = (
    "FREQ,REF_AREA,ACTIVITY,TRANSACTION,VALUATION,"
    "UNIT_MEASURE,TIME_PERIOD,OBS_VALUE\n"
)
ROWS = (
    "A,PRT,C,B1G,V,XDC,2024,123\n"
    "A,PRT,C,D1,V,XDC,2024,60\n"
    "A,PRT,C,B2N,V,XDC,2024,40\n"
    "A,PRT,C,P51C,V,XDC,2024,20\n"
    "A,PRT,C,D29X39,V,XDC,2024,3\n"
)


class StanFeasibilityTests(unittest.TestCase):
    def test_exact_original_field_sample_records_hash_without_approving_roles(self):
        raw = (HEADER + ROWS).encode("utf-8")
        calls = []
        def respondent(request):
            calls.append(request)
            return httpx.Response(200, content=raw)
        with httpx.Client(transport=httpx.MockTransport(respondent)) as client:
            result = probe_stan_candidates(client, since=date(2024, 1, 1))
        self.assertEqual(len(calls), 1)
        self.assertIn("DSD_STAN@DF_STAN_2025", str(calls[0].url))
        self.assertEqual(calls[0].url.params["startPeriod"], "2024")
        self.assertEqual(result["state"], "sampled")
        self.assertEqual(result["original_response_sha256"], sha256(raw).hexdigest())
        self.assertEqual(result["reported_industries"], 1)
        self.assertEqual(result["reported_years"], [2024])
        self.assertEqual(set(result["native_measure_observation_counts"]),
                         {"B1G", "D1", "B2N", "P51C", "D29X39"})
        self.assertEqual(result["missing_candidate_measures"], [])
        self.assertEqual(result["matched_five_measure_industry_years"], 1)
        self.assertEqual(result["nonzero_nominal_income_identity_residuals"], 0)
        self.assertEqual(result["largest_absolute_identity_residual_native"], "0")
        self.assertTrue(result["no_database_writes"])
        self.assertEqual(result["original_role_bindings_created"], 0)
        self.assertFalse(result["all_l01_l03_original_roles_verified"])
        self.assertFalse(result["first_publication_vintage_verified"])
        self.assertNotIn("response_body", result)

    def test_missing_candidate_measure_remains_explicit_and_unverified(self):
        raw = (HEADER + ROWS.splitlines(keepends=True)[0]).encode()
        with httpx.Client(transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=raw))) as client:
            result = probe_stan_candidates(client)
        self.assertEqual(result["state"], "sampled")
        self.assertEqual(result["missing_candidate_measures"],
                         ["B2N", "D1", "D29X39", "P51C"])
        self.assertFalse(result["all_l01_l03_original_roles_verified"])
        self.assertEqual(result["matched_five_measure_industry_years"], 0)
        self.assertIsNone(result["largest_absolute_identity_residual_native"])

    def test_source_income_components_report_a_discrepancy_without_approval(self):
        adjusted = ROWS.replace("2024,123", "2024,122")
        with httpx.Client(transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=(HEADER + adjusted).encode()))) as client:
            result = probe_stan_candidates(client, since=date(2024, 1, 1))
        self.assertEqual(result["matched_five_measure_industry_years"], 1)
        self.assertEqual(result["nonzero_nominal_income_identity_residuals"], 1)
        self.assertEqual(result["largest_absolute_identity_residual_native"], "1")
        self.assertEqual(result["largest_identity_residual_examples"][0]["residual_native"], "-1")
        self.assertFalse(result["all_l01_l03_original_roles_verified"])
        self.assertIn("mixed income", result["income_identity_interpretation"])

    def test_http_failure_duplicate_period_wrong_dimension_and_nonfinite_are_rejected(self):
        values = [
            (403, b"Access denied"),
            (200, (HEADER + ROWS + ROWS.splitlines(keepends=True)[0]).encode()),
            (200, (HEADER + ROWS.replace("A,PRT,C", "A,USA,C")).encode()),
            (200, (HEADER + ROWS.replace("2024,123", "2024,nan")).encode()),
            (200, b"not-an-sdmx-csv"),
        ]
        for status, raw in values:
            with self.subTest(status=status, payload=raw[:30]):
                with httpx.Client(transport=httpx.MockTransport(
                        lambda request: httpx.Response(status, content=raw))) as client:
                    result = probe_stan_candidates(client, since=date(2024, 1, 1))
                self.assertEqual(result["state"], "source_check_failed")
                self.assertFalse(result["first_publication_vintage_verified"])
                self.assertNotIn("original_response_sha256", result)
                self.assertIn("reason_type", result)
                self.assertNotIn("response_body", result)


if __name__ == "__main__":
    unittest.main()
