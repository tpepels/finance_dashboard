"""Jordà-Schularick-Taylor Macrohistory R6: systemic banking crisis start years as independent shock dates."""
import unittest

from finance_dashboard.jst import crisis_starts


class JstTests(unittest.TestCase):
    def test_crisis_starts_per_economy(self):
        rows = [["year", "country", "iso", "crisisJST"], [2007, "USA", "USA", 1], [2008, "USA", "USA", 0],
                [2008, "Spain", "ESP", 1], [1977, "Spain", "ESP", 1], [2009, "Spain", "ESP", ""]]
        self.assertEqual(crisis_starts(rows), {"USA": [2007], "ESP": [1977, 2008]})

    def test_layout_change_is_refused(self):
        from finance_dashboard.bis import ProviderError
        with self.assertRaises(ProviderError):
            crisis_starts([["year", "iso"], [2007, "USA"]])


if __name__ == "__main__":
    unittest.main()
