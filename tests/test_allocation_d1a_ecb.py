"""Plan phase D1a: ECB AAA par yields, €STR and EONIA for the EUR bond and cash buckets.

Fixtures are verbatim excerpts of the ECB csvdata downloads of 2026-11-18;
full-download hashes and extent are in fixtures/ecb_allocation/provenance.json.
"""
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import unittest

from finance_dashboard.bis import ProviderError
from finance_dashboard.captured_sources import _ECB_SERIES, _ecb
from finance_dashboard.catalog import load_documents
from finance_dashboard.provider_parsers import parse_ecb_csv
from finance_dashboard.source_reconciliation import EvidenceError

FIXTURES = Path(__file__).parent / "fixtures" / "ecb_allocation"
PROVENANCE = {item["source_key"]: item for item in json.loads((FIXTURES / "provenance.json").read_text())["downloads"]}
SERIES = {**{f"bond.ea.aaa_{n}y_par_yield": f"YC.B.U2.EUR.4F.G_N_A.SV_C_YM.PY_{n}Y" for n in (1, 2, 3, 5, 7, 10, 15, 20, 30)},
          **{f"bond.ea.all_issuer_{n}y_par_yield": f"YC.B.U2.EUR.4F.G_N_C.SV_C_YM.PY_{n}Y" for n in (2, 5, 10, 30)},
          **{f"expectations.ea.spf_longer_term_{name}": f"SPF.Q.U2.{topic}.POINT.LT.Q.AVG"
             for name, topic in (("inflation", "HICP"), ("real_gdp_growth", "RGDP"), ("unemployment", "UNEM"))},
          "rates.ea.estr": "EST.B.EU000A2X2A25.WT", "rates.ea.eonia_monthly_average": "FM.M.U2.EUR.4F.MM.EONIA.HSTA"}


def body(key):
    return (FIXTURES / f"{key}.csv").read_text(encoding="utf-8")


def period(text, frequency):
    if frequency == "Q":
        return date(int(text[:4]), 3 * int(text[-1]) - 2, 1)
    return date(int(text[:4]), int(text[5:7]), 1 if frequency == "M" else int(text[8:10]))


class EcbAllocationSeriesTests(unittest.TestCase):
    def setUp(self):
        self.catalog = {item["id"]: item for item in load_documents()[0]["series"]}

    def test_series_are_registered_with_approved_keys(self):
        for sid, key in SERIES.items():
            item = self.catalog[sid]
            self.assertEqual((item["provider"], item["source_key"], item["unit"]), ("ECB", key, "percent"))
            self.assertIn(key, _ECB_SERIES)
            self.assertEqual(_ECB_SERIES[key][1], item["frequency"])

    def test_parser_and_independent_reader_agree_on_real_rows(self):
        for sid, key in SERIES.items():
            item, record = self.catalog[sid], PROVENANCE[key]
            text = body(key)
            parsed = parse_ecb_csv(text, key, item["frequency"])
            values, metadata = _ecb(text, item, record["url"])
            self.assertEqual(values, parsed, sid)
            if not sid.startswith("expectations."):
                self.assertEqual(metadata["source_currency"], "EUR")
            self.assertEqual(parsed[period(record["first_period"], item["frequency"])], Decimal(record["first_value"]))
            self.assertEqual(parsed[period(record["last_period"], item["frequency"])], Decimal(record["last_value"]))

    def test_estr_reports_its_unit_as_unit_measure(self):
        item = self.catalog["rates.ea.estr"]
        key = SERIES["rates.ea.estr"]
        _values, metadata = _ecb(body(key), item, PROVENANCE[key]["url"])
        self.assertEqual(metadata["source_native_unit_codes"], ["PC"])
        with self.assertRaises(EvidenceError):    # a different native unit is refused
            _ecb(body(key).replace(",PC,0", ",PCPA,0"), item, PROVENANCE[key]["url"])

    def test_aaa_and_all_issuer_curves_are_not_interchangeable(self):
        with self.assertRaises(ProviderError):
            parse_ecb_csv(body(SERIES["bond.ea.aaa_10y_par_yield"]), SERIES["bond.ea.all_issuer_10y_par_yield"], "D")

    def test_a_maturity_cannot_be_read_as_another(self):
        with self.assertRaises(ProviderError):
            parse_ecb_csv(body(SERIES["bond.ea.aaa_5y_par_yield"]), SERIES["bond.ea.aaa_7y_par_yield"], "D")
        item = self.catalog["bond.ea.aaa_7y_par_yield"]
        with self.assertRaises(EvidenceError):
            _ecb(body(SERIES["bond.ea.aaa_5y_par_yield"]), item, PROVENANCE[SERIES["bond.ea.aaa_7y_par_yield"]]["url"])

    def test_recorded_downloads_have_the_expected_extent(self):
        for n in (1, 2, 3, 5, 7, 10, 15, 20, 30):
            record = PROVENANCE[f"YC.B.U2.EUR.4F.G_N_A.SV_C_YM.PY_{n}Y"]
            self.assertEqual((record["observations"], record["first_period"]), (5676, "2004-09-06"))
        self.assertEqual(PROVENANCE["EST.B.EU000A2X2A25.WT"]["first_period"], "2019-10-01")
        eonia = PROVENANCE["FM.M.U2.EUR.4F.MM.EONIA.HSTA"]
        self.assertEqual((eonia["observations"], eonia["first_period"], eonia["last_period"]), (336, "1994-01", "2021-12"))
        self.assertIn("must not treat them as euro cash", self.catalog["rates.ea.eonia_monthly_average"]["notes"])


if __name__ == "__main__":
    unittest.main()
