"""Philadelphia Fed Real-Time Data Set: unemployment-rate vintages and the Sahm rule as known at each vintage."""
import unittest

from finance_dashboard.philly_rtdsm import parse_vintages, realtime_sahm


def sheet():
    months = ["1999:11", "1999:12"] + [f"2000:{m:02d}" for m in range(1, 13)] + [f"2001:{m:02d}" for m in range(1, 6)]
    rows = [["DATE", "RUC01Q1", "RUC01Q2"]]
    for i, m in enumerate(months):
        early = 4.0 if i < 15 else "#N/A"                      # 2001Q1 vintage knows data through 2001-01
        late = (4.0 if i < 16 else 4.9) if i < 18 else "#N/A"  # 2001Q2 vintage knows data through 2001-04
        rows.append([m, early, late])
    return rows


class RtdsmTests(unittest.TestCase):
    def test_vintages_keep_only_reported_months(self):
        vintages = parse_vintages(sheet())
        self.assertEqual(sorted(vintages), ["2001Q1", "2001Q2"])
        self.assertEqual(max(vintages["2001Q1"]), "2001-01")
        self.assertEqual(max(vintages["2001Q2"]), "2001-04")

    def test_sahm_rule_from_each_vintages_own_data(self):
        points = realtime_sahm(parse_vintages(sheet()))
        self.assertEqual([p["vintage"] for p in points], ["2001Q1", "2001Q2"])
        self.assertEqual(points[0], {"vintage": "2001Q1", "month": "2001-01", "value": 0.0})
        # last three months 4.0, 4.9, 4.9 -> 4.6; lowest prior three-month average 4.0
        self.assertEqual(points[1]["month"], "2001-04")
        self.assertAlmostEqual(points[1]["value"], 0.6)


if __name__ == "__main__":
    unittest.main()
