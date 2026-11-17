"""Independent reader for archived OECD earnings-dispersion originals.

Rows are copied from the production originals for the US (DEC_I and MIN2AVE
dataflows); the reader must not reuse the ingestion parser.
"""
from datetime import date
from decimal import Decimal
import unittest

from finance_dashboard.captured_sources import _oecd_earnings
from finance_dashboard.catalog import load_documents
from finance_dashboard.source_reconciliation import EvidenceError

HEADER = ("DATAFLOW,REF_AREA,MEASURE,UNIT_MEASURE,PAY_PERIOD,PRICE_BASE,"
          "AGGREGATION_OPERATION,SEX,TIME_PERIOD,OBS_VALUE,BASE_PER,OBS_STATUS,UNIT_MULT,DECIMALS\n")
DECILE = HEADER + (
    "OECD.ELS.SAE:DSD_EARNINGS@DEC_I(1.0),USA,IR_GE,FCTR_D1,_Z,_Z,D9_1,_T,1977,3.7161172161,,A,0,2\n"
    "OECD.ELS.SAE:DSD_EARNINGS@DEC_I(1.0),USA,IR_GE,FCTR_D1,_Z,_Z,D9_1,_T,2004,4.7868852459,,A,0,2\n")
MINIMUM = HEADER + (
    "OECD.ELS.SAE:DSD_EARNINGS@MIN2AVE(1.0),USA,MR_WG_FT,PT_WG_A_SAL_FT,_Z,_Z,MEDIAN,_Z,1960,46.94835681,_Z,A,0,2\n"
    "OECD.ELS.SAE:DSD_EARNINGS@MIN2AVE(1.0),USA,MR_WG_FT,PT_WG_A_SAL_FT,_Z,_Z,MEDIAN,_Z,1961,48.16513761,_Z,A,0,2\n")


def url(definition):
    flow, _, series = definition["source_key"].partition("/")
    return f"https://sdmx.oecd.org/public/rest/data/{flow}/{series}?format=csvfile"


class OecdEarningsIndependentReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = {row["id"]: row for row in load_documents()[0]["series"]}

    def test_decile_ratio_rows_are_read_as_published(self):
        definition = self.registry["labour.us.oecd_p90_p10"]
        values, meta = _oecd_earnings(DECILE, definition, url(definition))
        self.assertEqual(values, {date(1977, 1, 1): Decimal("3.7161172161"),
                                  date(2004, 1, 1): Decimal("4.7868852459")})
        self.assertEqual(meta["source_native_unit"], "FCTR_D1")

    def test_minimum_to_median_rows_are_read_as_published(self):
        definition = self.registry["labour.us.oecd_minimum_median"]
        values, meta = _oecd_earnings(MINIMUM, definition, url(definition))
        self.assertEqual(values[date(1960, 1, 1)], Decimal("46.94835681"))
        self.assertEqual(meta["source_native_unit"], "PT_WG_A_SAL_FT")

    def test_other_ratio_country_url_or_population_is_rejected(self):
        p90_p50 = self.registry["labour.us.oecd_p90_p50"]
        p90_p10 = self.registry["labour.us.oecd_p90_p10"]
        cases = [
            (DECILE, p90_p50, url(p90_p50)),                         # D9_1 rows for D9_5
            (DECILE.replace(",USA,", ",DEU,"), p90_p10, url(p90_p10)),
            (DECILE, p90_p10, url(p90_p10).replace("csvfile", "csv")),
            (DECILE.replace(",_T,", ",F,"), p90_p10, url(p90_p10)),
            (DECILE.replace(",A,0,2", ",A,3,2"), p90_p10, url(p90_p10)),
            (DECILE + DECILE.splitlines()[1] + "\n", p90_p10, url(p90_p10)),
        ]
        for body, definition, address in cases:
            with self.assertRaises(EvidenceError):
                _oecd_earnings(body, definition, address)

    def test_non_ordinary_status_rows_are_not_read(self):
        definition = self.registry["labour.us.oecd_p90_p10"]
        body = DECILE.replace("2004,4.7868852459,,A", "2004,4.7868852459,,E")
        values, _ = _oecd_earnings(body, definition, url(definition))
        self.assertEqual(list(values), [date(1977, 1, 1)])


if __name__ == "__main__":
    unittest.main()
