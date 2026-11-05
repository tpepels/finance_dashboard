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
