"""Plan phase D1a: French international country portfolios (returns and annual valuation ratios).

Fixtures repack real line excerpts of every member of F-F_International_Countries.zip
(downloaded 2026-11-18; hash and extent in fixtures/french_countries/provenance.json).
"""
from datetime import date
from decimal import Decimal
import io
import json
from pathlib import Path
import unittest
import zipfile

from finance_dashboard.bis import ProviderError
from finance_dashboard.captured_sources import _french_countries
from finance_dashboard.catalog import load_documents
from finance_dashboard.french_countries import (
    COUNTRY_MEMBERS, FRENCH_COUNTRIES_URL, FRENCH_COUNTRY_SERIES, french_country_frequency,
    french_country_source_key, parse_french_country,
)
from finance_dashboard.provider_registry import PROVIDER_REGISTRY
from finance_dashboard.source_reconciliation import EvidenceError

FIXTURES = Path(__file__).parent / "fixtures" / "french_countries"
EXCERPTS = json.loads((FIXTURES / "excerpts.json").read_text())


def archive(edit=None, drop=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        for name, member in EXCERPTS.items():
            if name == drop:
                continue
            lines = list(member["lines"])
            if edit and name in edit:
                lines = edit[name](lines)
            zipped.writestr(zipfile.ZipInfo(name, tuple(member["date_time"])), "\r\n".join(lines) + "\r\n")
    return buffer.getvalue()


def definition(series_id):
    return {"source_key": french_country_source_key(series_id), "unit": "percent",
            "frequency": french_country_frequency(series_id)}


class FrenchCountryTests(unittest.TestCase):
    def test_registration(self):
        catalog = {item["id"]: item for item in load_documents()[0]["series"]}
        self.assertEqual(PROVIDER_REGISTRY["FRENCH_COUNTRIES"].handler, "fetch_french_countries")
        self.assertEqual(len(FRENCH_COUNTRY_SERIES), 100)
        for sid in FRENCH_COUNTRY_SERIES:
            item = catalog[sid]
            self.assertEqual((item["provider"], item["source_key"], item["source_url"], item["frequency"]),
                             ("FRENCH_COUNTRIES", french_country_source_key(sid), FRENCH_COUNTRIES_URL,
                              french_country_frequency(sid)))

    def test_parser_and_independent_reader_agree_for_every_series(self):
        raw = archive()
        for sid in FRENCH_COUNTRY_SERIES:
            parsed = parse_french_country(raw, sid)
            values, _metadata = _french_countries(raw, definition(sid), FRENCH_COUNTRIES_URL)
            self.assertEqual(values, parsed, sid)

    def test_published_values(self):
        raw = archive()
        # Germany.Dat: "197501  12.53 ..." (USD), local block first row "197501   9.35 ...",
        # ratio rows "1975    99  80.89  10.72  31.27   4.82" and "2025   629  66.07   7.96  14.72   3.22".
        self.assertEqual(parse_french_country(raw, "returns.french.country.de.market_usd")[date(1975, 1, 1)], Decimal("12.53"))
        self.assertEqual(parse_french_country(raw, "returns.french.country.de.market_local")[date(1975, 1, 1)], Decimal("9.35"))
        ep = parse_french_country(raw, "valuation.french.country.de.earnings_yield")
        self.assertEqual((ep[date(1975, 1, 1)], ep[date(2025, 1, 1)]), (Decimal("10.72"), Decimal("7.96")))
        self.assertEqual(parse_french_country(raw, "valuation.french.country.de.book_to_market")[date(1975, 1, 1)], Decimal("80.89"))
        self.assertEqual(parse_french_country(raw, "valuation.french.country.de.dividend_yield")[date(2025, 1, 1)], Decimal("3.22"))
        self.assertEqual(min(parse_french_country(raw, "returns.french.country.at.market_usd")), date(1987, 1, 1))

    def test_archive_identity_layout_and_missing_values(self):
        with self.assertRaises(ProviderError):
            parse_french_country(archive(drop="Malaysia.Dat"), "returns.french.country.de.market_usd")

        def shift(lines):
            return [line.replace("Firms    B/M    E/P", "Firms    E/P    B/M") for line in lines]
        edited = archive({"Germany.Dat": shift})
        with self.assertRaises(ProviderError):
            parse_french_country(edited, "valuation.french.country.de.earnings_yield")
        with self.assertRaises(EvidenceError):
            _french_countries(edited, definition("valuation.french.country.de.earnings_yield"), FRENCH_COUNTRIES_URL)

        def blank_market(lines):
            return [line.replace("197501  12.53", "197501 -99.99", 1) for line in lines]
        values = parse_french_country(archive({"Germany.Dat": blank_market}), "returns.french.country.de.market_usd")
        self.assertNotIn(date(1975, 1, 1), values)

    def test_every_registered_country_member_is_in_the_recorded_archive(self):
        provenance = json.loads((FIXTURES / "provenance.json").read_text())
        self.assertEqual(provenance["members"], 21)
        self.assertTrue(set(COUNTRY_MEMBERS.values()) < set(EXCERPTS))


if __name__ == "__main__":
    unittest.main()
