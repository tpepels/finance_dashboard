"""Plan phase D1a: Bundesbank par-yield maturities for the EUR government buckets.

Fixtures are excerpts of the Bundesbank CSV downloads taken on 2026-11-18
(header lines verbatim, first three and last two months); full-download hashes
and extent are in fixtures/bundesbank/provenance.json.
"""
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import unittest

from finance_dashboard.bis import ProviderError
from finance_dashboard.bundesbank import BUNDESBANK_SERIES, PAR_YIELD_MATURITIES, bundesbank_url, parse_bundesbank_csv
from finance_dashboard.captured_sources import _bundesbank
from finance_dashboard.catalog import load_documents

FIXTURES = Path(__file__).parent / "fixtures" / "bundesbank"
PROVENANCE = {item["maturity_years"]: item for item in json.loads((FIXTURES / "provenance.json").read_text())["downloads"]}


def excerpt(years):
    return (FIXTURES / f"par_yield_{years}y_excerpt.csv").read_text(encoding="utf-8")


class BundesbankParYieldTests(unittest.TestCase):
    def test_every_maturity_is_registered_with_its_exact_key(self):
        catalog = {item["id"]: item for item in load_documents()[0]["series"]}
        for years in PAR_YIELD_MATURITIES:
            sid = f"bond.de.bund_{years}y_par_yield_month_end"
            flow, key, frequency = BUNDESBANK_SERIES[sid]
            self.assertEqual((flow, frequency), ("BBSIS", "M"))
            self.assertEqual(key, PROVENANCE[years]["series_key"])
            self.assertEqual(catalog[sid]["source_key"], key)
            self.assertEqual(catalog[sid]["source_url"], bundesbank_url(flow, key))
            self.assertEqual((catalog[sid]["provider"], catalog[sid]["unit"]), ("BUNDESBANK", "percent"))

    def test_real_rows_parse_to_the_published_values(self):
        for years in PAR_YIELD_MATURITIES:
            sid = f"bond.de.bund_{years}y_par_yield_month_end"
            values = parse_bundesbank_csv(excerpt(years), sid)
            first_period, first_value = PROVENANCE[years]["first_row"].split(",")[:2]
            last_period, last_value = PROVENANCE[years]["last_row"].split(",")[:2]
            first_day = date(int(first_period[:4]), int(first_period[5:]), 1)
            last_day = date(int(last_period[:4]), int(last_period[5:]), 1)
            self.assertEqual(values[first_day], Decimal(first_value), sid)
            self.assertEqual(values[last_day], Decimal(last_value), sid)
            self.assertEqual(len(values), 5, sid)
        self.assertEqual(parse_bundesbank_csv(excerpt(30), "bond.de.bund_30y_par_yield_month_end")[date(2000, 1, 1)],
                         Decimal("6.10"))

    def test_a_maturity_cannot_be_read_as_another(self):
        with self.assertRaises(ProviderError):
            parse_bundesbank_csv(excerpt(5), "bond.de.bund_7y_par_yield_month_end")

    def test_independent_reader_agrees_for_every_maturity(self):
        catalog = {item["id"]: item for item in load_documents()[0]["series"]}
        for years in PAR_YIELD_MATURITIES:
            sid = f"bond.de.bund_{years}y_par_yield_month_end"
            body = excerpt(years)
            values, dimensions = _bundesbank(body, catalog[sid], PROVENANCE[years]["url"])
            self.assertEqual(values, parse_bundesbank_csv(body, sid), sid)
            self.assertEqual(dimensions["source_native_unit"], "percent")

    def test_recorded_downloads_are_complete_and_gap_free(self):
        expected_months = {1: 650, 2: 650, 3: 650, 5: 650, 7: 650, 15: 485, 20: 485, 30: 322}
        for years, months in expected_months.items():
            self.assertEqual(PROVENANCE[years]["months"], months)
            self.assertEqual(PROVENANCE[years]["gaps"], 0)
            self.assertEqual(PROVENANCE[years]["last_row"][:7], "2026-10")


if __name__ == "__main__":
    unittest.main()
