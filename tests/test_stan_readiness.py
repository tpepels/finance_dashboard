"""STAN Phase 2 readiness and governed publisher interruption regressions."""
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from time import time
import unittest

import httpx

from finance_dashboard.source_policy import (
    PolicyDeferred, PolicyViolation, publisher_interruption,
)
from finance_dashboard.stan_originals import (
    STAN_DATAFLOW_ID, STAN_VERIFIED_PORTUGAL_MEASURES,
    store_stan_original,
)
from finance_dashboard.stan_research import summarize_stan_readiness
from scripts.phase2_stan_sources import acquire, brief_report, probe_surplus


HEADER = (
    "DATAFLOW,FREQ,REF_AREA,ACTIVITY,MEASURE,PRICE_BASE,UNIT_MEASURE,"
    "TIME_PERIOD,OBS_VALUE,OBS_STATUS,UNIT_MULT,CURRENCY\n"
)


def original(measures, *, status="A", country="PRT"):
    values = {
        "B1G": 100, "D1": 60, "P51C": 20, "D29X39": 5,
        "B2N_B3_N": 15, "B2G_B3G": 35,
    }
    return (HEADER + "".join(
        f"{STAN_DATAFLOW_ID},A,{country},_T,{measure},V,XDC,"
        f"2020,{values[measure]},{status},6,EUR\n"
        for measure in measures
    )).encode()


class StanReadinessTests(unittest.TestCase):
    def test_partial_original_does_not_invent_surplus_or_identity(self):
        with TemporaryDirectory() as t:
            root = Path(t)
            saved = store_stan_original(
                original(STAN_VERIFIED_PORTUGAL_MEASURES), country="PRT",
                start_year=1970, root=root,
                measures=STAN_VERIFIED_PORTUGAL_MEASURES)
            source = (root / "stan-2025" / "PRT" / "1970" /
                      "measure-B1G+D1+P51C+D29X39" /
                      saved["bundle_digest"] / "original.csv")
            before = source.read_bytes()
            report = summarize_stan_readiness(
                root, countries=("PRT", "DEU"))
            self.assertEqual(report["verified_scope_countries"], 1)
            self.assertEqual(report["same_scope_identity_countries"], 0)
            self.assertEqual(report["country_readiness"][0]["status"],
                             "four_measure_coverage_only")
            self.assertEqual(report["country_readiness"][0][
                "net_max_matched_in_single_scope"], 0)
            self.assertEqual(report["country_readiness"][1]["status"],
                             "missing_verified_original")
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(report["publisher_requests"], 0)
            self.assertFalse(report["scientific_analysis_certified"])
            self.assertEqual(brief_report(report)["operation"], "stan_readiness")

    def test_full_same_original_supports_accounting_diagnostic_only(self):
        with TemporaryDirectory() as t:
            root = Path(t)
            measures = ("B1G", "D1", "B2N_B3_N", "B2G_B3G", "P51C", "D29X39")
            store_stan_original(original(measures), country="PRT",
                                start_year=1970, root=root, measures=measures)
            report = summarize_stan_readiness(root, countries=("PRT",))
            country = report["country_readiness"][0]
            self.assertEqual(country["status"],
                             "same_scope_identity_diagnostic_available")
            self.assertEqual(country["net_max_matched_in_single_scope"], 1)
            self.assertEqual(country["gross_max_matched_in_single_scope"], 1)
            self.assertFalse(country["identity_residuals_outside_printed_precision"])
            self.assertFalse(report["publication_vintages_aligned"])
            self.assertFalse(report["scientific_analysis_certified"])

    def test_estimate_flags_cannot_be_interpreted_as_verified(self):
        with TemporaryDirectory() as t:
            measures = ("B1G", "D1", "B2N_B3_N", "P51C", "D29X39")
            store_stan_original(original(measures, status="E"), country="PRT",
                                start_year=1970, root=Path(t), measures=measures)
            report = summarize_stan_readiness(Path(t), countries=("PRT",))
            self.assertEqual(report["country_readiness"][0]["status"],
                             "identity_overlap_contains_uninterpreted_flags")
            self.assertFalse(report["source_status_flag_meanings_verified"])

    def test_overlapping_scopes_not_added_as_independent_observations(self):
        with TemporaryDirectory() as t:
            measures = ("B1G", "D1", "B2N_B3_N", "P51C", "D29X39")
            for start in (1970, 2020):
                store_stan_original(original(measures), country="PRT",
                                    start_year=start, root=Path(t), measures=measures)
            report = summarize_stan_readiness(Path(t), countries=("PRT",))
            row = report["country_readiness"][0]
            self.assertEqual(row["verified_scopes"], 2)
            self.assertEqual(row["net_max_matched_in_single_scope"], 1)
            self.assertFalse(report["observations_merged_across_retrievals"])


class PublisherInterruptionTests(unittest.TestCase):
    def test_classification_does_not_reinterpret_missing_data_as_policy_stop(self):
        self.assertIsNone(publisher_interruption(ValueError("unavailable"), 404))
        stop = publisher_interruption(ValueError("blocked"), 403)
        self.assertEqual(stop["category"], "publisher_access_denied")
        self.assertTrue(stop["request_emitted"])
        self.assertEqual(publisher_interruption(ValueError("x"), 503)[
            "category"], "publisher_unavailable")

    def test_policy_deferral_prevents_repeated_country_requests(self):
        calls = []
        def block(request):
            calls.append(request)
            raise PolicyDeferred("oecd-sdmx", "publisher_cooldown", time() + 60)
        with TemporaryDirectory() as t:
            with httpx.Client(transport=httpx.MockTransport(block)) as client:
                result = acquire(client, Path(t), countries=("PRT", "DEU", "FRA"),
                                 start_year=1970)
            self.assertEqual(len(calls), 1)
            self.assertEqual(result["publisher_requests"], 0)
            self.assertTrue(result["stopped_on_source_policy"])
            self.assertFalse(result["stopped_on_publisher_backpressure"])
            self.assertGreater(result["retry_after_seconds"], 0)
            self.assertEqual(result["acquisitions"][0]["status"], "blocked_source_policy")
            self.assertEqual(result["acquisitions"][1]["status"],
                             "skipped_source_policy_block")
            self.assertEqual(result["acquisitions"][2]["status"],
                             "skipped_source_policy_block")
            self.assertFalse((Path(t) / "stan-2025").exists())

    def test_access_violation_stops_probe_without_retrying_candidates(self):
        calls = []
        def block(request):
            calls.append(request)
            raise PolicyViolation("oecd-sdmx", "publisher_acknowledgement_missing")
        with httpx.Client(transport=httpx.MockTransport(block)) as client:
            result = probe_surplus(client, country="PRT", year=2020)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["publisher_requests"], 0)
        self.assertEqual(result["checks"][0]["failure_category"],
                         "source_policy_blocked")
        self.assertTrue(result["stopped_on_publisher_backpressure"])
        self.assertEqual(len(result["checks"]), 1)


if __name__ == "__main__":
    unittest.main()
