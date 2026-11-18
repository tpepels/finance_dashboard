"""Plan phase D1b: Philadelphia Fed SPF median inflation expectations (cell excerpt of Inflation.xlsx, 2026-11-18)."""
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import unittest

from finance_dashboard.bis import ProviderError
from finance_dashboard.captured_sources import _philly_spf, _workbook_rows
from finance_dashboard.catalog import load_documents
from finance_dashboard.philly_spf import PHILLY_SPF_SERIES, PHILLY_SPF_URL, parse_philly_spf_rows
from finance_dashboard.provider_registry import PROVIDER_REGISTRY
from test_captured_source_families import xlsx_from_factual_cells

FIXTURES = Path(__file__).parent / "fixtures" / "philly_spf"
EXCERPT = json.loads((FIXTURES / "inflation_excerpt.json").read_text())


def workbook(rows=None):
    return xlsx_from_factual_cells(rows or EXCERPT["rows"], EXCERPT["sheet"])


class PhillySpfTests(unittest.TestCase):
    def test_registration_and_agreement(self):
        catalog = {item["id"]: item for item in load_documents()[0]["series"]}
        self.assertEqual(PROVIDER_REGISTRY["PHILLY_SPF"].handler, "fetch_philly_spf")
        raw = workbook()
        rows = _workbook_rows(raw, "INFLATION")
        for sid, column in PHILLY_SPF_SERIES.items():
            self.assertEqual((catalog[sid]["provider"], catalog[sid]["source_key"], catalog[sid]["frequency"]), ("PHILLY_SPF", column, "Q"))
            values, _ = _philly_spf(raw, catalog[sid], PHILLY_SPF_URL)
            self.assertEqual(values, parse_philly_spf_rows(rows, sid))

    def test_published_values_and_missing_cells(self):
        rows = _workbook_rows(workbook(), "INFLATION")
        gdp = parse_philly_spf_rows(rows, "expectations.us.spf_inflation_gdp_price_1y")
        self.assertNotIn(date(1970, 1, 1), gdp)                         # 1970 Q1 is #N/A
        self.assertEqual(gdp[date(1970, 4, 1)], Decimal("2.9851"))
        self.assertEqual(min(parse_philly_spf_rows(rows, "expectations.us.spf_inflation_cpi_10y")), date(1991, 10, 1))
        self.assertEqual(parse_philly_spf_rows(rows, "expectations.us.spf_inflation_cpi_10y")[date(2026, 10, 1)], Decimal("2.491"))

    def test_column_and_order_changes_are_refused(self):
        rows = [list(row) for row in EXCERPT["rows"]]
        rows[0][4] = "INFCPI5YR"
        with self.assertRaises(ProviderError):
            parse_philly_spf_rows(_workbook_rows(workbook(rows), "INFLATION"), "expectations.us.spf_inflation_cpi_10y")
        rows = [EXCERPT["rows"][0]] + list(reversed(EXCERPT["rows"][1:]))
        with self.assertRaises(ProviderError):
            parse_philly_spf_rows(_workbook_rows(workbook(rows), "INFLATION"), "expectations.us.spf_inflation_cpi_1y")


if __name__ == "__main__":
    unittest.main()
