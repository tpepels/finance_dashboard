"""Native OECD STAN originals: byte preservation, scope and scientific limits."""
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import httpx

from finance_dashboard.stan_originals import (
    STAN_DATAFLOW_ID, parse_stan_original_csv, read_stan_evidence,
    stan_source_request, store_stan_original,
)
from finance_dashboard.research_artifacts import research_artifact_evidence
from scripts.phase2_stan_sources import acquire


HEADER = ("DATAFLOW,FREQ,REF_AREA,ACTIVITY,TRANSACTION,VALUATION,UNIT_MEASURE,"
          "TIME_PERIOD,OBS_VALUE,OBS_STATUS,UNIT_MULT,CURRENCY\n")


def example(*, year=2024, country="PRT", activity="C", gva="123",
            status="A", currency="EUR", skip=()):
    values = [("B1G", gva), ("D1", "60"), ("B2N", "40"),
              ("P51C", "20"), ("D29X39", "3")]
    return (HEADER + "".join(
        f"{STAN_DATAFLOW_ID},A,{country},{activity},{tx},V,XDC,{year},"
        f"{value},{status},6,{currency}\n"
        for tx, value in values if tx not in skip
    )).encode()


class StanOriginalTests(unittest.TestCase):
    def test_publisher_request_is_bounded_and_uses_canonical_dimension_order(self):
        url, params = stan_source_request("PRT", 1970)
        self.assertIn("/A.PRT..B1G+D1+B2N+P51C+D29X39.V.XDC", url)
        self.assertEqual(params, {"startPeriod": "1970",
                                   "dimensionAtObservation": "AllDimensions"})
        for country, year in (("XX", 1970), ("PRT", 1969), ("PRT", 9999)):
            with self.assertRaises(ValueError):
                stan_source_request(country, year)

    def test_native_multidimensional_measurements_do_not_certify_scientific_roles(self):
        parsed = parse_stan_original_csv(
            example(status="E"), country="PRT", start_year=2024)
        self.assertEqual(parsed["native_measure_observation_counts"],
                         {"B1G": 1, "B2N": 1, "D1": 1, "D29X39": 1, "P51C": 1})
        self.assertEqual(parsed["native_status_flag_counts"], {"E": 5})
        self.assertEqual(parsed["reported_unit_multipliers"], ["6"])
        self.assertEqual(parsed["reported_currency_codes"], ["EUR"])
        self.assertEqual(parsed["matched_five_measure_industry_years"], 1)
        self.assertEqual(parsed["largest_absolute_identity_residual_native"], "0")
        self.assertFalse(parsed["source_estimate_flags_interpreted"])
        self.assertFalse(parsed["first_publication_vintage_verified"])
        self.assertFalse(parsed["all_l01_l03_original_roles_verified"])
        self.assertEqual(parsed["original_role_bindings_created"], 0)

    def test_missing_native_measure_and_mismatching_units_fail_openly_not_filled(self):
        partial = parse_stan_original_csv(example(skip=("B2N",)), country="PRT",
                                          start_year=1970)
        self.assertEqual(partial["missing_candidate_measures"], ["B2N"])
        self.assertEqual(partial["matched_five_measure_industry_years"], 0)
        self.assertIsNone(partial["largest_absolute_identity_residual_native"])
        mixed = example().replace(b"P51C,V,XDC,2024,20,A,6,EUR",
                                  b"P51C,V,XDC,2024,20,A,3,EUR")
        parsed = parse_stan_original_csv(mixed, country="PRT", start_year=1970)
        self.assertEqual(parsed["unit_incompatible_five_measure_industry_years"], 1)
        self.assertEqual(parsed["matched_five_measure_industry_years"], 0)

    def test_signed_residual_is_reported_without_adjusting_values(self):
        parsed = parse_stan_original_csv(example(gva="122"), country="PRT",
                                         start_year=2024)
        self.assertEqual(parsed["nonzero_nominal_income_identity_residuals"], 1)
        self.assertEqual(parsed["largest_absolute_identity_residual_native"], "1")
        self.assertEqual(parsed["largest_identity_residual_examples"][0]["residual_native"], "-1")

    def test_wrong_identity_duplicates_invalid_numbers_and_oversize_rejected(self):
        bad = [
            example(country="DEU"),
            example().replace(b"2024,123", b"2024,nan"),
            example().replace(b",A,PRT,C,", b",A,PRT,,"),
            example() + example().split(b"\n", 1)[1],
            example().replace(STAN_DATAFLOW_ID.encode(), b"OTHER.DATAFLOW"),
            b"garbled-original",
            b"",
        ]
        for raw in bad:
            with self.subTest(original=raw[:36]), self.assertRaises(ValueError):
                parse_stan_original_csv(raw, country="PRT", start_year=2024)

    def test_append_only_original_bundle_and_receipts_are_independently_verified(self):
        raw = example()
        with TemporaryDirectory() as temp:
            root = Path(temp)
            first = store_stan_original(raw, country="PRT", start_year=2024, root=root)
            again = store_stan_original(raw, country="PRT", start_year=2024, root=root)
            self.assertEqual(first["bundle_digest"], again["bundle_digest"])
            bundle = root / "stan-2025" / "PRT" / "2024" / first["bundle_digest"]
            self.assertEqual((bundle / "original.csv").read_bytes(), raw)
            self.assertEqual(first["original_response_sha256"], sha256(raw).hexdigest())
            self.assertEqual(len(list((bundle.parent / "retrievals").glob("*.json"))), 2)
            evidence = read_stan_evidence(root, countries=("PRT", "DEU"))
            self.assertEqual(evidence["country_count"], 1)
            self.assertEqual(evidence["country_results"][0]["status"],
                             "verified_original_stan_partial")
            self.assertEqual(evidence["country_results"][1]["status"],
                             "missing_original_stan")
            self.assertFalse(evidence["full_history_verified"])
            self.assertFalse(evidence["first_publication_verified"])
            self.assertFalse(evidence["complete_same_industry_compensation_capital_matrix_verified"])
            artifact = research_artifact_evidence(root, kinds={"stan"})
            self.assertEqual(set(artifact), {"stan"})
            self.assertTrue(artifact["stan"]["original_source_hash_verified"])
            self.assertNotIn(temp, json.dumps(artifact))
            # Corruption is not allowed to become a certified original.
            (bundle / "original.csv").write_bytes(b"changed after receipt")
            invalid = read_stan_evidence(root, countries=("PRT",))
            self.assertEqual(invalid["country_results"][0]["status"], "invalid_original_stan")
            self.assertFalse(invalid["original_source_hash_verified"])

    def test_independent_requested_period_scopes_prefer_widest_original(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            store_stan_original(example(), country="PRT", start_year=1970, root=root)
            store_stan_original(example(), country="PRT", start_year=2024, root=root)
            evidence = read_stan_evidence(root, countries=("PRT",))
            self.assertEqual(evidence["country_results"][0]["requested_since"], 1970)
            self.assertEqual(evidence["country_results"][0]["available_requested_starts"],
                             [1970, 2024])

    def test_missing_root_is_read_only_and_explicit(self):
        with TemporaryDirectory() as temp:
            root = Path(temp) / "not-present"
            data = read_stan_evidence(root, countries=("PRT",))
            self.assertFalse(root.exists())
            self.assertEqual(data["country_results"][0]["status"], "missing_original_stan")
            self.assertFalse(data["original_source_hash_verified"])

    def test_cli_acquires_originals_without_database_rows_or_foreign_source_data(self):
        raw = example()
        calls = []
        def respondent(request):
            calls.append(str(request.url))
            if "A.PRT." in str(request.url):
                return httpx.Response(200, content=raw)
            return httpx.Response(404, content=b"not available")
        with TemporaryDirectory() as temp:
            root = Path(temp)
            with httpx.Client(transport=httpx.MockTransport(respondent)) as client:
                report = acquire(client, root, countries=("PRT", "DEU"), start_year=2024)
            self.assertEqual(report["original_responses_archived"], 1)
            self.assertEqual(report["acquisition_failures"], 1)
            self.assertEqual(report["source_evidence"]["country_count"], 1)
            self.assertFalse(report["scientific_analysis_certified"])
            self.assertTrue(report["no_macro_database_writes"])
            self.assertFalse(any(p.suffix in {".db", ".sqlite3"} for p in root.rglob("*")))
            self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
