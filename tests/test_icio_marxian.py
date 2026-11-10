"""ICIO 2025 input-origin ratio under the Rotta & Kumar rule, mixed industries as bounds."""
import unittest

from finance_dashboard.icio_marxian import ICIO_CONCORDANCE, icio_aggregates


class IcioMarxianTests(unittest.TestCase):
    def test_every_wiod_industry_maps_once(self):
        codes = [c for leaf in ICIO_CONCORDANCE.values() for c in leaf]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertEqual(len(codes), 55)            # all WIOD industries except U (extraterritorial), not in ICIO

    def test_total_value_and_value_added_follow_the_published_rule(self):
        cls = {"C10-C12": "PA", "K64": "UA.finance", "K65": "UA.finance", "K66": "UA.finance",
               "M69_M70": "UA.additional", "M71": "PA", "M72": "PA", "M73": "UA.additional", "M74_M75": "PA"}
        header = ["V1", "PRT_C10T12", "PRT_K", "PRT_M", "ESP_C10T12", "PRT_HFCE", "OUT"]
        rows = [["PRT_C10T12", 10, 1, 2, 3, 50, 0], ["PRT_K", 4, 0, 1, 0, 9, 0], ["PRT_M", 2, 1, 0, 0, 9, 0],
                ["ESP_C10T12", 5, 0, 1, 7, 9, 0], ["TLS", 1, 0, 0.5, 0, 0, 0], ["VA", 0, 0, 0, 0, 0, 0],
                ["OUT", 100, 20, 30, 40, 0, 0]]
        unproductive_m = icio_aggregates(header, rows, cls, countries={"PRT"}, mixed_as="UA")
        self.assertEqual(unproductive_m["PRT"]["TV.PA"], 101)                     # 100 + 1 taxes
        self.assertEqual(unproductive_m["PRT"]["VA.PA"], 101 - (10 + 5))          # inputs from productive rows, any country
        productive_m = icio_aggregates(header, rows, cls, countries={"PRT"}, mixed_as="PA")
        self.assertEqual(productive_m["PRT"]["TV.PA"], 101 + 30.5)
        self.assertEqual(productive_m["PRT"]["VA.PA"], 131.5 - (10 + 5 + 2 + 2 + 0 + 1))


if __name__ == "__main__":
    unittest.main()
