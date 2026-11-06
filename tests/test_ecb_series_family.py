"""ECB reference rates, HICP and AAA yield curve share one strict original reader."""
from decimal import Decimal
import unittest

from finance_dashboard.captured_sources import _ecb
from finance_dashboard.catalog import load_documents
from finance_dashboard.source_reconciliation import EvidenceError

REG = {row["id"]: row for row in load_documents()[0]["series"]}
EXR_URL = "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?format=csvdata"
HEADER = "KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE,UNIT,TITLE\n"


class EcbSeriesFamilyTests(unittest.TestCase):
    def test_reference_rate_reader_checks_every_dimension(self):
        definition = REG["fx.usd_per_eur.ecb"]
        body = HEADER + "EXR.D.USD.EUR.SP00.A,D,USD,EUR,SP00,A,2026-11-02,1.0821,USD,US dollar/Euro\n"
        values, meta = _ecb(body, definition, EXR_URL)
        self.assertEqual(list(values.values()), [Decimal("1.0821")])
        self.assertEqual(meta["source_native_unit"], "currency_per_eur")
        self.assertNotIn("source_currency", meta)
        wrong = body.replace(",D,USD,EUR,SP00", ",D,JPY,EUR,SP00")
        with self.assertRaises(EvidenceError):
            _ecb(wrong, definition, EXR_URL)
        with self.assertRaises(EvidenceError):
            _ecb(body, definition, EXR_URL.replace("/EXR/", "/FM/"))
        with self.assertRaises(EvidenceError):
            _ecb(body, {**definition, "source_key": "EXR.D.SEK.EUR.SP00.A"}, EXR_URL)

    def test_new_series_are_registered_with_matching_units(self):
        for sid, unit, freq in (("fx.usd_per_eur.ecb", "currency_per_eur", "D"),
                                ("prices.ea.hicp_index", "index", "M"),
                                ("bond.ea.aaa_10y_spot", "percent", "D")):
            self.assertEqual((REG[sid]["unit"], REG[sid]["frequency"], REG[sid]["provider"]), (unit, freq, "ECB"))


if __name__ == "__main__":
    unittest.main()


class BeaTableRowTests(unittest.TestCase):
    def test_table_b_row_is_selected_by_caption_and_both_year_parts(self):
        from finance_dashboard.captured_sources import _bea_table_row
        from finance_dashboard.remaining_sources import BEA_Q_URL, parse_bea_table_row
        def part(caption, years, values):
            head = "".join(f"<th>{y}</th>" for y in years)
            cells = "".join(f"<td>{v}</td>" for v in values)
            return (f"<table><caption>{caption}</caption><tr><th></th>{head}</tr>"
                    f"<tr><td>Nonfinancial corporations</td>{cells}</tr>"
                    f"<tr><td>Mining</td>{''.join('<td>1</td>' for _ in years)}</tr></table>")
        b = "Table B. Produced Assets of Domestic Nonfinancial Corporations and Nonfinancial Industries"
        body = ("[Billions of dollars]" + part(b + ", 2004–2005", ["2004", "2005"], ["10,829.7", "11,772.8"])
                + part(b + ", 2006–2007", ["2006", "2007"], ["12,000.0", "13,000.5"])
                + part("Table A. Net Operating Surplus of Domestic Nonfinancial Corporations, 2004–2005", ["2004", "2005"], ["988.6", "1"]))
        key = "BEA_2026_TABLE_B_NFC_PRODUCED_ASSETS"
        definition = {"source_key": key, "frequency": "A", "unit": "billion_usd"}
        values = _bea_table_row(body, definition, BEA_Q_URL)
        self.assertEqual(len(values), 4)
        self.assertEqual(values, parse_bea_table_row(body, key))
        with self.assertRaises(EvidenceError):
            _bea_table_row(body.replace(b + ", 2006–2007", "Other table"), definition, BEA_Q_URL)
