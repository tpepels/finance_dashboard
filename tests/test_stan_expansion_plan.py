"""Read-only expansion planning uses exact original source scopes."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from finance_dashboard.stan_originals import (
    STAN_DATAFLOW_ID, STAN_VERIFIED_PORTUGAL_MEASURES,
    store_stan_original,
)
from scripts.phase2_stan_sources import plan_expansion, brief_report


def raw(country: str) -> bytes:
    rows = [
        "DATAFLOW,FREQ,REF_AREA,ACTIVITY,MEASURE,PRICE_BASE,"
        "UNIT_MEASURE,TIME_PERIOD,OBS_VALUE,OBS_STATUS,UNIT_MULT,CURRENCY\n",
    ]
    for code in STAN_VERIFIED_PORTUGAL_MEASURES:
        rows.append(
            f"{STAN_DATAFLOW_ID},A,{country},C,{code},V,XDC,"
            "2020,123,A,6,EUR\n"
        )
    return "".join(rows).encode()


class StanExpansionPlannerTests(unittest.TestCase):
    def test_cache_plan_only_counts_exact_scope_and_start_year(self):
        with TemporaryDirectory() as t:
            root = Path(t)
            stored = store_stan_original(
                raw("PRT"), country="PRT", start_year=1970,
                root=root, measures=STAN_VERIFIED_PORTUGAL_MEASURES)
            original_archive = (root / "stan-2025" / "PRT" / "1970" /
                                "measure-B1G+D1+P51C+D29X39" /
                                stored["bundle_digest"] / "original.csv")
            original_bytes = original_archive.read_bytes()
            result = plan_expansion(
                root, countries=("PRT", "CHE", "COL", "DEU", "FRA"),
                start_year=1970, measures=STAN_VERIFIED_PORTUGAL_MEASURES,
                max_requests=2)
            self.assertEqual(result["verified_countries"], ["PRT"])
            self.assertEqual(result[
                "verified_country_scopes_with_each_requested_measure_observed"], ["PRT"])
            self.assertEqual(result["next_evidence_action"],
                             "acquire_verified_publisher_structure")
            self.assertEqual(result["pending_countries"],
                             ["CHE", "COL", "DEU", "FRA"])
            self.assertEqual(result["suggested_country_batches"],
                             [["CHE", "COL"], ["DEU", "FRA"]])
            self.assertEqual(result["planned_publisher_requests"], 4)
            self.assertEqual(result["publisher_requests_made"], 0)
            self.assertEqual(original_archive.read_bytes(), original_bytes)
            short = brief_report(result)
            self.assertEqual(short["next_batch"], ["CHE", "COL"])
            self.assertEqual(short["verified"], ["PRT"])
            self.assertEqual(short["pending_count"], 4)

    def test_requested_scope_with_missing_observations_is_not_claimed_complete(self):
        with TemporaryDirectory() as t:
            root = Path(t)
            rows = raw("PRT").decode().splitlines(keepends=True)
            incomplete = "".join(
                r for r in rows if ",D29X39," not in r).encode()
            store_stan_original(
                incomplete, country="PRT", start_year=1970, root=root,
                measures=STAN_VERIFIED_PORTUGAL_MEASURES)
            report = plan_expansion(
                root, countries=("PRT", "DEU"), start_year=1970,
                measures=STAN_VERIFIED_PORTUGAL_MEASURES)
            self.assertEqual(report["verified_countries"], ["PRT"])
            self.assertEqual(report[
                "verified_country_scopes_with_each_requested_measure_observed"], [])
            self.assertEqual(report[
                "verified_country_scopes_missing_requested_numeric_measures"],
                ["PRT"])
            self.assertEqual(report["pending_countries"], ["DEU"])
            self.assertEqual(report["publisher_measure_metadata"], "metadata_not_acquired")
            self.assertEqual(report["verified_scopes_with_missing_measures"], [{
                "country": "PRT",
                "measures_without_numeric_observations": ["D29X39"],
                "numeric_observations_in_source": 3,
            }])
            compact = brief_report(report)
            self.assertEqual(compact["archived_country_scopes"], 1)
            self.assertEqual(compact["archived_with_all_measures_observed"], 0)
            self.assertEqual(compact["archived_missing_numeric_measures"], ["PRT"])
            self.assertEqual(compact["next_evidence_action"],
                             "acquire_verified_publisher_structure")

    def test_different_original_measure_selection_is_not_cached_as_complete(self):
        with TemporaryDirectory() as t:
            root = Path(t)
            store_stan_original(
                raw("PRT"), country="PRT", start_year=1970, root=root,
                measures=STAN_VERIFIED_PORTUGAL_MEASURES)
            new_selection = ("B1G", "D1", "B2N_B3_N", "P51C", "D29X39")
            result = plan_expansion(root, countries=("PRT",), start_year=1970,
                                    measures=new_selection)
            self.assertEqual(result["verified_countries"], [])
            self.assertEqual(result["pending_countries"], ["PRT"])
            self.assertTrue(result["no_archive_writes"])

    def test_invalid_original_is_blocked_instead_of_queued(self):
        with TemporaryDirectory() as t:
            root = Path(t)
            stored = store_stan_original(
                raw("PRT"), country="PRT", start_year=1970, root=root,
                measures=STAN_VERIFIED_PORTUGAL_MEASURES)
            archive = (root / "stan-2025" / "PRT" / "1970" /
                       "measure-B1G+D1+P51C+D29X39" /
                       stored["bundle_digest"] / "original.csv")
            archive.write_bytes(b"tampered")
            result = plan_expansion(
                root, countries=("PRT", "DEU"), start_year=1970,
                measures=STAN_VERIFIED_PORTUGAL_MEASURES)
            self.assertEqual(result["blocked_invalid_original_countries"], ["PRT"])
            self.assertEqual(result["pending_countries"], ["DEU"])
            self.assertEqual(result["planned_publisher_requests"], 1)
            self.assertEqual(archive.read_bytes(), b"tampered")


    def test_rolling_refresh_requires_explicit_switch_and_preserves_vintages(self):
        import httpx
        from finance_dashboard.stan_originals import read_stan_evidence
        from scripts.phase2_stan_sources import acquire
        samples = [raw("PRT"), raw("PRT").replace(b",2020,123,", b",2020,124,")]
        calls = []
        def respondent(request):
            calls.append(str(request.url))
            return httpx.Response(200, content=samples[len(calls) - 1])
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with httpx.Client(transport=httpx.MockTransport(respondent)) as client:
                first = acquire(client, root, countries=("PRT",), start_year=1970)
                cached = acquire(client, root, countries=("PRT",), start_year=1970)
                refreshed = acquire(
                    client, root, countries=("PRT",), start_year=1970,
                    refresh_verified=True)
            self.assertEqual(len(calls), 2)
            self.assertEqual(first["original_responses_archived"], 1)
            self.assertEqual(cached["already_verified_archives"], 1)
            self.assertEqual(refreshed["new_original_versions"], 1)
            self.assertEqual(refreshed["refreshed_scopes"], 1)
            self.assertEqual(refreshed["acquisitions"][0]["status"],
                             "refreshed_revised")
            scope = read_stan_evidence(root, countries=("PRT",))[
                "country_results"][0]["source_scopes"][0]
            self.assertEqual(scope["original_versions_verified"], 2)
            self.assertEqual(scope["retrieval_receipts_verified"], 2)

    def test_refetch_with_identical_bytes_appends_receipt_only(self):
        import httpx
        from finance_dashboard.stan_originals import read_stan_evidence
        from scripts.phase2_stan_sources import acquire
        calls = []
        def respondent(request):
            calls.append(str(request.url))
            return httpx.Response(200, content=raw("PRT"))
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with httpx.Client(transport=httpx.MockTransport(respondent)) as client:
                acquire(client, root, countries=("PRT",), start_year=1970)
                refreshed = acquire(
                    client, root, countries=("PRT",), start_year=1970,
                    refresh_verified=True)
            self.assertEqual(len(calls), 2)
            self.assertEqual(refreshed["acquisitions"][0]["status"],
                             "refreshed_unchanged")
            self.assertEqual(refreshed["new_original_versions"], 0)
            scope = read_stan_evidence(root, countries=("PRT",))[
                "country_results"][0]["source_scopes"][0]
            self.assertEqual(scope["original_versions_verified"], 1)
            self.assertEqual(scope["retrieval_receipts_verified"], 2)

    def test_invalid_request_budget_rejected(self):
        with TemporaryDirectory() as t:
            root = Path(t)
            with self.assertRaises(ValueError):
                plan_expansion(
                    root, countries=("PRT",), start_year=1970,
                    measures=STAN_VERIFIED_PORTUGAL_MEASURES,
                    max_requests=0)


if __name__ == "__main__":
    unittest.main()
