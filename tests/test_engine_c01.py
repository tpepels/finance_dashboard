"""C01 on the engine: the business-cycle clock and the US activity panels."""
from datetime import date
import math
import unittest

from engine_fixtures import monthly
from finance_dashboard.engine.analyses import C01, DEFINITIONS, cycle_positions, log_change


class C01EngineTests(unittest.TestCase):
    def test_quadrant_follows_level_against_100_and_direction(self):
        rising_above = cycle_positions(monthly((2026, 1), [100.5, 100.8]))
        self.assertEqual(rising_above["phase"], "expansion")
        self.assertAlmostEqual(rising_above["trail"][-1][1], 0.8)
        self.assertAlmostEqual(rising_above["trail"][-1][2], 0.3)
        self.assertEqual(cycle_positions(monthly((2026, 1), [101.0, 100.6]))["phase"], "slowdown")
        self.assertEqual(cycle_positions(monthly((2026, 1), [99.5, 99.1]))["phase"], "contraction")
        self.assertEqual(cycle_positions(monthly((2026, 1), [99.1, 99.4]))["phase"], "recovery")

    def test_trail_is_twelve_months_and_a_gap_breaks_it(self):
        full = cycle_positions(monthly((2024, 1), [100 + 0.1 * i for i in range(30)]))
        self.assertEqual(len(full["trail"]), 12)
        gapped = cycle_positions(monthly((2026, 1), [100.0, 100.1, 100.2, 100.3, 100.4], skip=(2026, 3)))
        self.assertEqual([m for m, *_ in gapped["trail"]], ["2026-05"])   # April needs March; only May remains
        self.assertEqual(gapped["as_of"], "2026-05")

    def test_too_short_has_no_position(self):
        self.assertIsNone(cycle_positions(monthly((2026, 1), [100.0])))

    def test_log_change_needs_both_ends(self):
        points = monthly((2025, 1), [100.0] * 12 + [110.0], skip=(2025, 3))
        changes = dict(log_change(points, 12))
        self.assertAlmostEqual(changes["2026-01"], 100 * math.log(1.1))
        self.assertNotIn("2026-03", changes)

    def test_definition_and_values(self):
        self.assertIs(DEFINITIONS["C01"], C01)
        self.assertEqual(sorted(k for k in C01.inputs if k.startswith("cli:")),
                         ["cli:CN", "cli:DE", "cli:FR", "cli:G20", "cli:G7", "cli:GB", "cli:IN", "cli:JP", "cli:US"])
        points = {role: [] for role in C01.inputs}
        points["cli:US"] = monthly((2025, 1), [99 + 0.1 * i for i in range(21)])
        points["cli:JP"] = monthly((2025, 1), [101 - 0.1 * i for i in range(17)])     # stops four months earlier
        points["ip"] = monthly((2024, 1), [100 + i for i in range(33)])
        points["gdp"] = [(date(2026, 1, 1), 100.0), (date(2026, 4, 1), 101.0)]
        points["unemployment"] = monthly((2026, 1), [4.1, 4.2])
        result = C01.compute(points, {})
        clock = {row["area"]: row for row in result.values["clock"]}
        self.assertEqual(clock["US"]["phase"], "expansion")
        self.assertEqual(clock["JP"]["as_of"], "2026-05")
        self.assertNotIn("DE", clock)                      # no data, no dot
        self.assertAlmostEqual(result.values["us_activity"]["gdp_qoq"][0][1], 100 * math.log(1.01))
        self.assertEqual(result.values["us_activity"]["unemployment"][-1], ["2026-02-28", 4.2])
        names = {t["name"] for t in result.transforms}
        self.assertTrue({"cycle_position", "log_change"} <= names)


if __name__ == "__main__":
    unittest.main()
