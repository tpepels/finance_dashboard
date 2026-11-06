"""Deterministic bounded and read-only source probe tests."""
from datetime import date
from decimal import Decimal
import unittest

from finance_dashboard.bis import FetchedSeries
from finance_dashboard.source_probe import probe


class RecordingSource:
    def __init__(self):
        self.calls = []

    def fetch(self, identifier, start=None):
        self.calls.append((identifier, start))
        if identifier == "missing":
            raise ValueError("secret-token=should-not-leak")
        return FetchedSeries(
            identifier, "https://example.org/source", None,
            {date(2024, 1, 1): Decimal("11.5")},
        )


class ProbeTests(unittest.TestCase):
    def test_no_mutations_and_safe_error_output(self):
        source = RecordingSource()
        status = probe(source, ["observed", "missing"], date(2024, 1, 1))
        self.assertEqual(source.calls, [
            ("observed", date(2024, 1, 1)),
            ("missing", date(2024, 1, 1)),
        ])
        self.assertTrue(status["no_database_writes"])
        self.assertEqual(status["sampled"], 1)
        self.assertEqual(status["failed"], 1)
        self.assertNotIn("secret-token", str(status))
        self.assertFalse(status["sources"][0]["first_publication_vintage_verified"])


if __name__ == "__main__":
    unittest.main()
