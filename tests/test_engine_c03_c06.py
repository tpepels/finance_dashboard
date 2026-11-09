"""C03 and C06 on the engine: growth strip and dispersion; stagflation map and commodity changes."""
from datetime import date
import math
import unittest

from engine_fixtures import monthly
from finance_dashboard.engine.analyses import (C03, C06, DEFINITIONS, cross_section_sd, stagflation_points,
                                               window_range, year_on_year)


def annual(start, values, skip=()):
    return [(date(start + i, 1, 1), v) for i, v in enumerate(values) if start + i not in skip]


class C03EngineTests(unittest.TestCase):
    def test_window_range_uses_the_last_n_observations(self):
        result = window_range(annual(2000, [float(v) for v in range(15)]), 10)
        self.assertEqual((result["min"], result["max"], result["from"]), (5.0, 14.0, "2005-01-01"))
        self.assertIsNone(window_range([], 10))

    def test_dispersion_only_for_years_with_every_member(self):
        cohort = {"US": annual(2020, [2.0, 4.0]), "CN": annual(2020, [6.0, 8.0], skip=(2021,))}
        sd = cross_section_sd(cohort)
        self.assertEqual([year for year, _ in sd], ["2020"])
        self.assertAlmostEqual(sd[0][1], 2.0)          # population SD of 2 and 6

    def test_values(self):
        self.assertIs(DEFINITIONS["C03"], C03)
        points = {role: annual(2010, [1.0 + i * 0.1 for i in range(16)]) for role in C03.inputs}
        values = C03.compute(points, {}).values
        strip = {row["area"]: row for row in values["strip"]}
        self.assertEqual(strip["US"]["year"], "2025")
        self.assertAlmostEqual(strip["US"]["latest"], 2.5)
        self.assertAlmostEqual(strip["US"]["range"]["min"], 1.6)
        self.assertEqual(set(values["history"]), {"WORLD", "US", "EU", "CN", "IN", "JP"})
        self.assertEqual(len(values["dispersion"]), 16)
        self.assertAlmostEqual(values["dispersion"][0][1], 0.0)


class C06EngineTests(unittest.TestCase):
    def test_year_on_year_needs_the_month_a_year_earlier(self):
        changes = dict(year_on_year(monthly((2025, 1), [50.0] * 12 + [60.0], skip=(2025, 2))))
        self.assertAlmostEqual(changes["2026-01"], 0.2)
        self.assertNotIn("2026-02", changes)

    def test_stagflation_points_only_on_matched_years(self):
        growth = annual(2020, [1.0, 2.0, 3.0])
        inflation = annual(2020, [4.0, 5.0], skip=())
        pts = stagflation_points(growth, inflation, 8)
        self.assertEqual(pts, [["2020", 1.0, 4.0], ["2021", 2.0, 5.0]])

    def test_values(self):
        self.assertIs(DEFINITIONS["C06"], C06)
        points = {role: [] for role in C06.inputs}
        points["growth:US"] = annual(2015, [2.0] * 11)
        points["inflation:US"] = annual(2015, [3.0] * 11)
        points["commodity:brent"] = monthly((2024, 1), [80.0] * 12 + [88.0] * 12)
        values = C06.compute(points, {}).values
        self.assertEqual(len(values["map"]["US"]), 8)
        self.assertEqual(values["map"]["JP"], [])
        brent = next(c for c in values["commodities"] if c["key"] == "brent")
        self.assertAlmostEqual(brent["latest"], 0.1)
        self.assertEqual(brent["as_of"], "2025-12")
        gas = next(c for c in values["commodities"] if c["key"] == "gas")
        self.assertIsNone(gas["latest"])


if __name__ == "__main__":
    unittest.main()
