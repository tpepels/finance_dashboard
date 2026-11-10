"""EU KLEMS 2025 industry data under the Rotta & Kumar classification: finest cover, mixed industries as bounds."""
import unittest

from finance_dashboard.euklems_marxian import CONCORDANCE, group_of, industry_cover, klems_sums

CLS = {code: "PA" for leaf in CONCORDANCE.values() for code in leaf}
CLS.update({"K64": "UA.finance", "K65": "UA.finance", "K66": "UA.finance", "L68": "UA.real estate", "O84": "UA.government",
            "G45": "UA.trade", "G46": "UA.trade", "G47": "UA.trade", "M69_M70": "UA.additional", "M73": "UA.additional",
            "N": "UA.additional", "T": "EX", "U": "EX"})


class ConcordanceTests(unittest.TestCase):
    def test_every_wiod_industry_maps_to_exactly_one_klems_leaf(self):
        codes = [code for leaf in CONCORDANCE.values() for code in leaf]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertEqual(len(codes), 56)

    def test_groups_and_mixed_industries(self):
        self.assertEqual(group_of("C20", CLS), "PA")
        self.assertEqual(group_of("K", CLS), "UA.finance")
        self.assertEqual(group_of("M", CLS), "mixed")
        self.assertEqual(group_of("M-N", CLS), "mixed")

    def test_finest_available_cover_falls_back_to_published_aggregates(self):
        available = set(CONCORDANCE) - {"C20", "C21", "M", "N"} | {"C20-C21", "M-N", "TOT"}
        cover = industry_cover(available)
        self.assertIn("C20-C21", cover)
        self.assertNotIn("C20", cover)
        self.assertIn("M-N", cover)
        self.assertNotIn("TOT", cover)

    def test_sums_by_group_with_mixed_industries_as_two_bounds(self):
        rows = [{"geo": "PT", "year": 2021, "code": "C10-C12", "VA": 10.0, "COMP": 5.0},
                {"geo": "PT", "year": 2021, "code": "M", "VA": 4.0, "COMP": 2.0},
                {"geo": "PT", "year": 2021, "code": "K", "VA": 6.0, "COMP": 3.0}]
        productive = klems_sums(rows, CLS, mixed_as="PA")
        unproductive = klems_sums(rows, CLS, mixed_as="UA")
        self.assertEqual(productive[("PRT", 2021, "VA", "PA")], 14.0)
        self.assertEqual(unproductive[("PRT", 2021, "VA", "PA")], 10.0)
        self.assertEqual(unproductive[("PRT", 2021, "VA", "UA")], 10.0)


if __name__ == "__main__":
    unittest.main()
