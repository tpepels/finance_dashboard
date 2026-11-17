"""Plan phase D1a: French regional market and momentum originals for the allocation buckets.

Fixtures are factual row excerpts cut from the publisher files downloaded on
2026-11-17 (hashes and full-history extent in fixtures/research_returns/provenance.json).
"""
from datetime import date
from decimal import Decimal
import io
import json
import unittest
import zipfile

from finance_dashboard.bis import ProviderError
from finance_dashboard.catalog import load_documents
from finance_dashboard.research_returns import (
    FRENCH_DATASETS, FRENCH_DATASET_SPECS, FRENCH_SERIES, parse_french_zip,
)
from finance_dashboard.return_source_reconciliation import _french_original
from test_research_returns import FIXTURES, french_zip

NEW_AREAS = ("europe", "japan", "asia_pacific_ex_japan", "developed_momentum", "europe_momentum",
             "japan_momentum", "asia_pacific_ex_japan_momentum", "emerging_momentum")


def zip_with(member, body):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(zipfile.ZipInfo(member, (1980, 1, 1, 0, 0, 0)), body)
    return buf.getvalue()


class FrenchRegionalAndMomentumTests(unittest.TestCase):
    def test_registry_covers_the_allocation_regions_and_momentum(self):
        self.assertEqual(len(FRENCH_SERIES), 20)
        for region in ("europe", "japan", "asia_pacific_ex_japan"):
            for suffix in ("market_excess_usd", "risk_free_usd", "market_total_usd"):
                self.assertIn(f"returns.french.{region}.{suffix}", FRENCH_SERIES)
        for region in ("developed", "europe", "japan", "asia_pacific_ex_japan", "emerging"):
            self.assertEqual(FRENCH_SERIES[f"returns.french.{region}.momentum_wml_usd"][1], "WML")
        catalog = {item["id"]: item for item in load_documents()[0]["series"]}
        for sid, (dataset, variable) in FRENCH_SERIES.items():
            self.assertEqual(catalog[sid]["source_key"], f"{dataset}/{variable}")

    def test_regional_market_values_match_publisher_rows(self):
        bundle = parse_french_zip(french_zip("europe"), dataset="Europe_3_Factors")
        first = date(1990, 7, 1)
        # Publisher row: "199007    ,4.46    ,0.29   ,-1.52    ,0.68"
        self.assertEqual(bundle.observations["returns.french.europe.market_excess_usd"][first], Decimal("4.46"))
        self.assertEqual(bundle.observations["returns.french.europe.risk_free_usd"][first], Decimal("0.68"))
        self.assertEqual(bundle.observations["returns.french.europe.market_total_usd"][first], Decimal("5.14"))
        self.assertEqual(bundle.metadata["series"]["returns.french.europe.market_total_usd"]["transformation"], "Mkt-RF + RF")
        self.assertEqual(len(bundle.observations["returns.french.europe.market_total_usd"]), 8)

    def test_momentum_reads_wml_from_the_mom_member_and_stops_at_annual_block(self):
        bundle = parse_french_zip(french_zip("europe_momentum"), dataset="Europe_Mom_Factor")
        values = bundle.observations["returns.french.europe.momentum_wml_usd"]
        self.assertEqual(values[date(1990, 11, 1)], Decimal("2.45"))
        self.assertEqual(values[date(2026, 9, 1)], Decimal("6.06"))
        self.assertEqual(len(values), 8)                      # annual 1991 row is not read as a month
        meta = bundle.metadata
        self.assertEqual(meta["series"]["returns.french.europe.momentum_wml_usd"]["source_variables"], ["WML"])
        self.assertIsNone(meta["series"]["returns.french.europe.momentum_wml_usd"]["transformation"])
        self.assertEqual(set(next(iter(meta["transformation_inputs"].values()))), {"WML"})
        self.assertIn("long-short", meta["measurement_note"])

    def test_member_spelling_and_columns_are_exact(self):
        body = (FIXTURES / "europe_momentum_excerpts.csv").read_bytes()
        with self.assertRaises(ProviderError):     # URL spelling is not the archive member name
            parse_french_zip(zip_with("Europe_Mom_Factor.csv", body), dataset="Europe_Mom_Factor")
        with self.assertRaises(ProviderError):     # a 3-factor layout is not momentum
            parse_french_zip(zip_with("Europe_MOM_Factor.csv", (FIXTURES / "europe_excerpts.csv").read_bytes()),
                             dataset="Europe_Mom_Factor")
        with self.assertRaises(ProviderError):
            parse_french_zip(french_zip("japan"), dataset="Unregistered_Factor")

    def test_missing_marker_stays_missing(self):
        body = (FIXTURES / "japan_momentum_excerpts.csv").read_text().replace("199011    ,1.50", "199011    ,-99.99", 1)
        bundle = parse_french_zip(zip_with("Japan_MOM_Factor.csv", body), dataset="Japan_Mom_Factor")
        self.assertNotIn(date(1990, 11, 1), bundle.observations["returns.french.japan.momentum_wml_usd"])
        self.assertEqual(bundle.metadata["missing_values_by_variable"]["WML"], 1)

    def test_independent_verifier_agrees_with_parser_for_every_new_dataset(self):
        for area in NEW_AREAS:
            dataset = FRENCH_DATASETS[area]
            raw = french_zip(area)
            bundle = parse_french_zip(raw, dataset=dataset)
            native, periods, inputs, missing, vintage = _french_original(raw, dataset)
            self.assertEqual(inputs, bundle.metadata["transformation_inputs"], area)
            self.assertEqual(missing, bundle.metadata["missing_values_by_variable"], area)
            self.assertEqual(vintage, bundle.metadata["source_database_vintage"], area)
            for sid, (ds, variable) in FRENCH_SERIES.items():
                if ds != dataset:
                    continue
                expected = {p: (row["Mkt-RF"] + row["RF"] if variable == "Mkt-RF+RF" else row[variable])
                            for p, row in native.items()}
                self.assertEqual(bundle.observations[sid], expected, sid)

    def test_fixtures_are_excerpts_of_the_recorded_originals(self):
        provenance = {e["dataset"]: e for e in json.loads((FIXTURES / "provenance.json").read_text())["original_sources"]
                      if "dataset" in e}
        for area in NEW_AREAS:
            entry = provenance[area]
            dataset = FRENCH_DATASETS[area]
            self.assertEqual(entry["member"], FRENCH_DATASET_SPECS[dataset][0])
            self.assertTrue(entry["url"].endswith(f"/{dataset}_CSV.zip"))
            lines = (FIXTURES / f"{area}_excerpts.csv").read_text().splitlines()
            self.assertIn(entry["first_row"], lines)
            self.assertIn(entry["last_row"], lines)
            self.assertLess(entry["fixture_excerpt_months"], entry["full_publisher_months"])


if __name__ == "__main__":
    unittest.main()
