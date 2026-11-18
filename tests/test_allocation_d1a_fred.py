"""Plan phase D1a: German short rates and DEM/USD before the euro (OECD MEI and Federal Reserve via FRED).

Fixtures are verbatim excerpts of the public FRED CSV downloads of 2026-11-18.
"""
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import unittest

from finance_dashboard.catalog import load_documents
from finance_dashboard.provider_parsers import parse_fred_csv

FIXTURES = Path(__file__).parent / "fixtures" / "fred_allocation"
SERIES = {"rates.de.immediate_rate_oecd": ("IRSTCI01DEM156N", "percent", 802),
          "rates.de.interbank_3m_oecd": ("IR3TIB01DEM156N", "percent", 802),
          "fx.dem_per_usd.fred": ("EXGEUS", "currency_per_usd", 372),
          "credit.us.moodys_aaa_yield": ("AAA", "percent", 1294),
          "credit.us.moodys_baa_yield": ("BAA", "percent", 1294)}


class GermanPreEuroInputsTests(unittest.TestCase):
    def test_registration_and_real_rows(self):
        catalog = {item["id"]: item for item in load_documents()[0]["series"]}
        provenance = {d["series"]: d for d in json.loads((FIXTURES / "provenance.json").read_text())["downloads"]}
        for sid, (code, unit, months) in SERIES.items():
            item = catalog[sid]
            self.assertEqual((item["provider"], item["source_key"], item["frequency"], item["unit"]), ("FRED", code, "M", unit))
            record = provenance[code]
            self.assertEqual(record["observations"], months)
            values = parse_fred_csv((FIXTURES / f"{code}.csv").read_text(), code, "M")
            for row in (record["first_row"], record["last_row"]):
                day, value = row.split(",")
                self.assertEqual(values[date.fromisoformat(day)], Decimal(value))
        self.assertIn("1.95583", catalog["fx.dem_per_usd.fred"]["notes"])
        self.assertIn("proxy", catalog["rates.de.immediate_rate_oecd"]["notes"])


if __name__ == "__main__":
    unittest.main()
