"""Edition-aware ICIO accounting and conservative cross-edition concordance."""
from __future__ import annotations

from decimal import Decimal
import io
import unittest
from zipfile import ZipFile, ZIP_DEFLATED

from finance_dashboard.icio_native import (
    audit_native_csv, audit_archive_native, common_2018_concordance, industry_members,
    DIMENSIONS, SECTORS_2018, SECTORS_2021, SECTORS_2025,
)


def tiny_extended(*, bad_output=False, duplicate=False, parent_nonzero=False, missing_va=False):
    countries = ["CHN", "MEX", "ROW", "CN1", "CN2", "MX1", "MX2"]
    fd_countries = ["CHN", "MEX", "ROW"]
    nodes = [f"{c}_D01" for c in countries]
    fd = [f"{c}_{kind}" for c in fd_countries
          for kind in ("HFCE", "NPISH", "GGFC", "GFCF", "INVNT", "DIRPA")]
    header = ["V1", *nodes, *fd, "OUT"]
    body = [header]
    for i, node in enumerate(nodes):
        values = ["0"] * len(nodes)
        final = ["0"] * len(fd)
        if not (i < 2 and not parent_nonzero):
            values[i] = "1"
            # Only the ROW node has zero cross-border final sales.
            final[(fd_countries.index("ROW" if i == 2 else "CHN" if i in (0, 3, 4) else "MEX")) * 6] = "2"
        total = 3 if values[i] == "1" else 0
        if bad_output and i == 3:
            total += 100
        body.append([node, *values, *final, str(total)])
    body.append(["TLS", *["0"] * (len(nodes) + len(fd) + 1)])
    if not missing_va:
        body.append(["VA", *["2" if i >= 2 or parent_nonzero else "0" for i in range(len(nodes))],
                     *["0"] * (len(fd) + 1)])
    body.append(["OUT", *["3" if i >= 2 or parent_nonzero else "0" for i in range(len(nodes))],
                 *["0"] * (len(fd) + 1)])
    if duplicate:
        body.append(body[1])
    return "\n".join(",".join(row) for row in body) + "\n"


TINY = (7, 3, ["D01"], 1995, 2022)


class IcioNativeTests(unittest.TestCase):
    def test_published_sector_lengths_and_concordance_coarsening(self):
        self.assertEqual([len(SECTORS_2018), len(SECTORS_2021), len(SECTORS_2025)],
                         [36, 45, 50])
        result = common_2018_concordance(SECTORS_2025)
        self.assertEqual(result["mapping"]["D241"], "D24")
        self.assertEqual(result["mapping"]["D242"], "D24")
        self.assertEqual(result["mapping"]["D301"], "D30")
        self.assertEqual(result["mapping"]["D02"], "D01T03")
        self.assertEqual(result["mapping"]["D69T75"], "D69T82")
        self.assertIn("D86T89", result["excluded"])
        self.assertNotIn("D86T88", common_2018_concordance(SECTORS_2021)["excluded"])

    def test_valid_source_accounts_audit_and_country_aggregation(self):
        parsed = audit_native_csv(io.StringIO(tiny_extended()), edition="2025",
                                  year=2021, dimensions=TINY)
        self.assertTrue(parsed["accounting_passed"])
        self.assertTrue(parsed["country_concordance"]["valid"])
        self.assertEqual(parsed["industry_nodes"], 7)
        self.assertEqual(parsed["country_direct_flows"]["CHN"]["gross_output_usd_million"], "6")
        self.assertEqual(parsed["country_direct_flows"]["MEX"]["source_value_added_usd_million"], "4")
        self.assertEqual(parsed["common_2018_sector_direct_flows"]["CHN"]["D01T03"]["gross_output_usd_million"], "6")
        self.assertFalse(parsed["tiva_equivalent"])

    def test_source_account_discrepancy_is_never_balanced_silently(self):
        parsed = audit_native_csv(io.StringIO(tiny_extended(bad_output=True)),
                                  edition="2025", year=2021, dimensions=TINY)
        self.assertFalse(parsed["accounting_passed"])
        self.assertEqual(parsed["row_failures"], 1)
        self.assertGreater(Decimal(parsed["max_row_residual"]), Decimal("0"))

    def test_unsplit_and_split_production_conflict_is_not_double_counted(self):
        parsed = audit_native_csv(io.StringIO(tiny_extended(parent_nonzero=True)),
                                  edition="2025", year=2021, dimensions=TINY)
        self.assertFalse(parsed["country_concordance"]["valid"])
        self.assertEqual(parsed["country_concordance"]["ambiguous_unsplit_parents"], ["CHN", "MEX"])
        self.assertNotIn("CHN", parsed["country_direct_flows"])
        self.assertNotIn("MEX", parsed["country_direct_flows"])

    def test_missing_publisher_accounts_does_not_claim_pass(self):
        parsed = audit_native_csv(io.StringIO(tiny_extended(missing_va=True)),
                                  edition="2025", year=2021, dimensions=TINY)
        self.assertIsNone(parsed["accounting_passed"])
        self.assertFalse(parsed["publisher_account_rows_present"])

    def test_corrupt_or_incomplete_native_matrix_fails_closed(self):
        cases = [
            tiny_extended(duplicate=True),
            tiny_extended().replace("CN1_D01", "CHN_D01", 1),
            tiny_extended().replace("ROW_D01,0", "ROW_D01,NaN", 1),
        ]
        for invalid in cases:
            with self.subTest(invalid=invalid[:80]), self.assertRaises(ValueError):
                audit_native_csv(io.StringIO(invalid), edition="2025",
                                 year=2021, dimensions=TINY)

    def test_one_archive_audits_year_member_without_expanding_to_disk(self):
        buffer = io.BytesIO()
        with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as package:
            package.writestr("2021.csv", tiny_extended())
            package.writestr("Publisher_README.txt", "2025 extension")
        buffer.seek(0)
        with ZipFile(buffer) as package:
            report = audit_archive_native(package, "2025", dimensions=TINY)
        self.assertEqual(report["annual_matrix_count"], 1)
        self.assertEqual(report["native_validation_status"], "native_accounts_verified")
        self.assertEqual(report["annual_matrices"][0]["year"], 2021)

    def test_incomplete_archive_years_are_not_certified(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        with TemporaryDirectory() as root:
            package = Path(root) / "2016-2022_EXT.zip"
            with ZipFile(package, "w") as file:
                file.writestr("2021.csv", tiny_extended())
            with ZipFile(package) as file:
                report = audit_archive_native(file, "2025", dimensions=TINY)
            self.assertEqual(report["observed_years"], [2021])
            self.assertEqual(report["expected_years"], list(range(2016, 2023)))
            self.assertEqual(report["native_validation_status"], "native_matrix_years_incomplete")

    def test_2023_regular_and_extended_release_dimensions(self):
        from finance_dashboard.icio_editions import archive_identity
        self.assertEqual(archive_identity("2016-2020_EXT.zip"),
                         {"edition": "2023", "table": "extended"})
        self.assertEqual(archive_identity("2016-2020_SML.zip"),
                         {"edition": "2023", "table": "regular"})
        self.assertEqual(archive_identity("2016-2022_EXT.zip"),
                         {"edition": "2025", "table": "extended"})
        self.assertEqual(DIMENSIONS["2023"][:2], (81, 77))
        tiny = (3, 3, ["D01"], 1995, 2020)
        countries = ("CHN", "MEX", "ROW")
        nodes = [name + "_D01" for name in countries]
        fd = [f"{name}_{kind}" for name in countries for kind in
              ("HFCE", "NPISH", "GGFC", "GFCF", "INVNT", "DIRPA")]
        header = ["V1", *nodes, *fd]
        body = [header]
        for i, node in enumerate(nodes):
            intermediate = [1 if i == j else 0 for j in range(3)]
            final = [2 if j == (i * 6) else 0 for j in range(18)]
            body.append([node, *map(str, intermediate), *map(str, final)])
        result = audit_native_csv(io.StringIO("\n".join(",".join(row) for row in body)),
                                  edition="2023", year=2020, dimensions=tiny, table="regular")
        self.assertTrue(result["structure_verified"])
        self.assertFalse(result["publisher_account_rows_present"])
        self.assertIsNone(result["accounting_passed"])
        self.assertTrue(result["country_concordance"]["valid"])
        self.assertEqual(result["country_direct_flows"]["CHN"]["gross_output_usd_million"], "3")
        self.assertEqual(result["country_direct_flows"]["CHN"]["direct_foreign_final_demand_usd_million"], "0")

    def test_nonmatrix_edition_package_is_not_called_audited(self):
        buffer = io.BytesIO()
        with ZipFile(buffer, "w") as package:
            package.writestr("econA.rdata", b"RDX3")
        buffer.seek(0)
        with ZipFile(buffer) as package:
            report = audit_archive_native(package, "2021")
        self.assertEqual(report["native_validation_status"], "no_native_csv_matrices")
        self.assertEqual(report["annual_matrices"], [])


if __name__ == "__main__":
    unittest.main()
