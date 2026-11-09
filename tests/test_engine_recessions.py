"""NBER US recession periods from the stored monthly indicator."""
from datetime import date
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from engine_fixtures import memory_engine, monthly, seed
from finance_dashboard.api import create_app
from finance_dashboard.engine.recessions import recession_periods


class RecessionPeriodTests(unittest.TestCase):
    def test_consecutive_recession_months_form_one_named_period(self):
        flags = monthly((2000, 12), [0] + [1] * 8 + [0] * 70 + [1] * 18 + [0] * 3)
        periods = recession_periods(flags)
        self.assertEqual([(p["start"], p["end"]) for p in periods],
                         [("2001-01-01", "2001-08-31"), ("2007-07-01", "2008-12-31")])

    def test_named_episodes_and_generic_labels(self):
        def run(start, months):
            return monthly(start, [1] * months)
        flags = run((2001, 4), 8) + run((2008, 1), 18) + run((2020, 3), 2) + run((1973, 12), 16)
        names = {p["start"][:4]: p["name"] for p in recession_periods(flags)}
        self.assertEqual(names, {"2001": "Dot-com recession", "2008": "Financial crisis",
                                 "2020": "COVID-19 recession", "1973": "US recession 1973–75"})

    def test_open_recession_at_the_end_has_no_end(self):
        periods = recession_periods(monthly((2026, 1), [0, 1, 1]))
        self.assertEqual(periods[-1]["start"], "2026-02-01")
        self.assertIsNone(periods[-1]["end"])


class RecessionApiTests(unittest.TestCase):
    def test_endpoint_serves_periods_with_their_source(self):
        engine = memory_engine()
        seed(engine, {"recession.us.nber_indicator": monthly((2020, 1), [0, 0, 1, 1, 0])})
        with patch.dict(os.environ, {"FINANCE_AUTO_REFRESH": "0", "FINANCE_INCLUDE_MARKETS": "0",
                                     "FINANCE_AUTO_BACKUP": "0"}):
            with TestClient(create_app(engine)) as client:
                body = client.get("/api/recessions").json()
        self.assertEqual(body["series_id"], "recession.us.nber_indicator")
        self.assertEqual(body["periods"], [{"start": "2020-03-01", "end": "2020-04-30",
                                            "name": "COVID-19 recession", "scope": "US (NBER)"}])
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
