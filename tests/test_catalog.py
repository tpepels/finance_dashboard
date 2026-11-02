"""Fast offline catalog contract tests; no external APIs or 30-minute CI jobs."""

import copy
import unittest

from finance_dashboard.catalog import build_report, load_documents, validate


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.series, cls.charts = load_documents()

    def modified(self):
        return copy.deepcopy(self.series), copy.deepcopy(self.charts)

    def test_canonical_definitions_pass(self):
        self.assertEqual([], validate(self.series, self.charts))

    def test_all_mapped_series_have_provenance(self):
        for item in self.series["series"]:
            if item["status"] == "mapped":
                self.assertTrue(item["source_key"])
                self.assertTrue(item["source_url"].startswith("https://"))
                self.assertIn(item["frequency"], {"D", "M", "Q", "A"})

    def test_duplicate_series_is_rejected(self):
        series, charts = self.modified()
        series["series"].append(copy.deepcopy(series["series"][0]))
        self.assertTrue(any("duplicate series ID" in e for e in validate(series, charts)))

    def test_unknown_chart_dependency_is_rejected(self):
        series, charts = self.modified()
        charts["charts"][0]["series_ids"].append("not.a.real.series")
        self.assertTrue(any("unknown series" in e for e in validate(series, charts)))

    def test_unresolved_cannot_masquerade_as_mapped(self):
        series, charts = self.modified()
        series["series"][0]["source_key"] = None
        self.assertTrue(any("requires exact source_key" in e for e in validate(series, charts)))

    def test_mapped_chart_cannot_use_unresolved_series(self):
        series, charts = self.modified()
        original = copy.deepcopy(series["series"][0])
        original["id"] = "temporarily.unresolved"
        original["status"] = "unresolved"
        original["source_key"] = None
        series["series"].append(original)
        charts["charts"][0]["series_ids"].append(original["id"])
        self.assertTrue(any("unresolved series" in e for e in validate(series, charts)))

    def test_raw_chart_rejects_mixed_units(self):
        series, charts = self.modified()
        charts["charts"][0]["series_ids"].append("recession.us.sahm")
        self.assertTrue(any("raw chart mixes units" in e for e in validate(series, charts)))

    def test_mapped_chart_requires_same_frequency(self):
        series, charts = self.modified()
        charts["charts"][0]["series_ids"].append("gdp.real_growth.us")
        self.assertTrue(any("same native frequency" in e for e in validate(series, charts)))

    def test_rights_review_is_exposed(self):
        report = build_report(self.series, self.charts)
        self.assertGreater(report["mapped_series"], 0)
        self.assertGreater(len(report["rights_review"]), 0)
        self.assertEqual(report["live_verified_series"], 0)


if __name__ == "__main__":
    unittest.main()
