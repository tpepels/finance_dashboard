"""OECD value-added accounting must never manufacture Marxian or capital-stock inputs."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from hashlib import sha256

from finance_dashboard.marx_accounts import (
    AccountingError, parse_oecd_normalized_csv, compute_country_year,
    store, read, SOURCE, REFERENCE,
)


def csv_rows(rows):
    header=("country,year,isic_section,employee_compensation,consumption_fixed_capital,"
            "net_operating_surplus,imputed_selfemployed_compensation,"
            "net_fixed_capital_stock,unit,currency,source_release,"
            "original_table,source_url,imputation_method,capital_stock_source\n")
    return (header+"".join(",".join(map(str,row))+"\n" for row in rows)).encode()


def row(section, comp, cfc, surplus, imputed="", stock="",
        method="",stock_source=""):
    return ("US","2020",section,str(comp),str(cfc),str(surplus),str(imputed),
            str(stock),"millions_usd","USD",SOURCE,
            "OECD_2025_IOT_value_added_components",REFERENCE,method,stock_source)


class MarxAccountsTests(unittest.TestCase):
    def test_source_accounting_ratio_is_not_claimed_as_measured_exploitation(self):
        source=csv_rows([row("C",100,20,80), row("K",200,40,60)])
        data=parse_oecd_normalized_csv(source,expected_sha256=sha256(source).hexdigest())
        result=compute_country_year(data,country="US",year=2020,
                                    scenario="all_industries")
        self.assertEqual(result["status"],"accounting_sensitivity_not_marxian_exploitation_rate")
        self.assertEqual(result["employee_compensation"],"300")
        self.assertEqual(result["net_operating_surplus"],"140")
        self.assertIsNone(result["net_surplus_over_net_capital_stock_pct"])
        self.assertFalse(result["capital_stock_coverage_complete"])
        self.assertIn("not observed Marxian surplus",result["limitation"])

    def test_industry_classification_sensitivity_and_documented_stock(self):
        source=csv_rows([
            row("C",100,20,80,imputed="10",stock="500",
                method="reported imputation",stock_source="OECD_STAN_2025"),
            row("K",200,40,60,imputed="5",stock="300",
                method="reported imputation",stock_source="OECD_STAN_2025"),
        ])
        data=parse_oecd_normalized_csv(source)
        broad=compute_country_year(data,country="US",year=2020,
                                   scenario="all_industries",adjust_selfemployment=True)
        narrow=compute_country_year(data,country="US",year=2020,
                                    scenario="market_narrow",adjust_selfemployment=True)
        self.assertEqual(broad["selfemployment_imputed"],"15")
        self.assertEqual(broad["net_surplus_over_net_capital_stock_pct"],
                         str((140-15)/800*100))
        self.assertEqual(narrow["included_isic_sections"],["C"])
        self.assertEqual(narrow["net_operating_surplus"],"80")
        self.assertEqual(narrow["employee_compensation"],"100")
        self.assertEqual(narrow["net_surplus_over_net_capital_stock_pct"],"14.00")

    def test_missing_imputation_must_block_adjusted_result(self):
        data=parse_oecd_normalized_csv(csv_rows([row("C",100,20,50)]))
        with self.assertRaisesRegex(AccountingError,"requires documented"):
            compute_country_year(data,country="US",year=2020,
                                 adjust_selfemployment=True)

    def test_duplicate_industries_and_bad_checksum_rejected(self):
        repeated=csv_rows([row("C",100,20,50)]*2)
        with self.assertRaisesRegex(AccountingError,"Duplicate"):
            parse_oecd_normalized_csv(repeated)
        with self.assertRaisesRegex(AccountingError,"SHA256"):
            parse_oecd_normalized_csv(csv_rows([row("C",100,20,50)]),
                                      expected_sha256="0"*64)

    def test_source_extract_version_is_persistent_and_immutable(self):
        data=parse_oecd_normalized_csv(csv_rows([row("C",100,20,50)]))
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.assertEqual(store(data,root=root),store(data,root=root))
            self.assertEqual(read(root)["record_count"],1)
            other=parse_oecd_normalized_csv(csv_rows([row("C",100,20,51)]))
            with self.assertRaisesRegex(AccountingError,"migration"):
                store(other,root=root)


if __name__=="__main__":
    unittest.main()
