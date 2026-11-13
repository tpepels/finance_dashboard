"""Real-edition header vocabularies and complete numeric accounting smoke tests.

Small 1-country tables exercise *all* published activity codes. They avoid
shipping large publisher matrices in Git while checking mapping, account-row
validation, output aliases and Leontief ingestion end-to-end. Actual-source
acceptance remains a separate mandatory gate.
"""
from __future__ import annotations

import io
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from finance_dashboard.icio_native import (
    DIMENSIONS, SECTORS_2018, SECTORS_2021, SECTORS_2025, audit_native_csv,
    common_2018_concordance,
)
from finance_dashboard.icio_sector_codes import (
    SOURCE_BY_EDITION, INTERNAL_BY_EDITION, normalize_native_sector_labels,
)
from finance_dashboard.icio_schema import probe_archive_layout
from finance_dashboard.icio_leontief import read_native_year, solve_foreign_final_demand


def tiny_accounted_source(edition: str, *, output_label: str = "X") -> str:
    activities = SOURCE_BY_EDITION[edition]
    nodes = ["ROW_" + activity for activity in activities]
    fds = ["ROW_" + cat for cat in ("HFCE", "NPISH", "GGFC", "GFCF", "INVNT", "DIRPA")]
    header = ["V1", *nodes, *fds, output_label]
    count = len(nodes)
    rows = [header]
    for i, name in enumerate(nodes):
        intermediate = ["1" if i == j else "0" for j in range(count)]
        final = ["2", "0", "0", "0", "0", "0"]
        rows.append([name, *intermediate, *final, "3"])
    rows += [
        ["TLS", *(["0"] * count), *(["0"] * 6), "0"],
        ["VA", *(["2"] * count), *(["0"] * 6), "0"],
        ["OUT", *(["3"] * count), *(["0"] * 6), "0"],
    ]
    return "\n".join(",".join(row) for row in rows) + "\n"


def full_shape_source(edition: str, table: str, year: int, *,
                      output_label: str = "X") -> io.BytesIO:
    production_areas, fd_areas, _, _, _ = DIMENSIONS[edition]
    if table == "regular":
        production_areas = fd_areas
    countries = [f"A{i:02d}" for i in range(fd_areas)]
    producers = countries + (["CN1", "CN2", "MX1", "MX2"]
                             if production_areas != fd_areas else [])
    nodes = [f"{country}_{activity}" for country in producers
             for activity in SOURCE_BY_EDITION[edition]]
    fd = [f"{country}_{cat}" for country in countries
          for cat in ("HFCE", "NPISH", "GGFC", "GFCF", "INVNT", "DIRPA")]
    header = ["V1", *nodes, *fd, output_label]
    buffer = io.BytesIO()
    with ZipFile(buffer, "w") as archive:
        name = (f"ICIO2018_{year}.CSV" if edition == "2018" else
                f"ICIO2021_{year}.csv" if edition == "2021" else
                f"{year}_SML.csv" if table == "regular" else f"{year}.csv")
        archive.writestr(name, ",".join(header) + "\n")
    buffer.seek(0)
    return buffer


class PublisherLayoutTests(unittest.TestCase):
    def test_source_industry_concordances_are_complete_and_one_to_one(self):
        for edition, n in (("2018", 36), ("2021", 45),
                           ("2023", 45), ("2025", 50)):
            with self.subTest(edition=edition):
                source = SOURCE_BY_EDITION[edition]
                self.assertEqual(len(source), n)
                self.assertEqual(len(set(source)), n)
                bridge = normalize_native_sector_labels(source, edition)
                self.assertEqual([bridge[x] for x in source],
                                 INTERNAL_BY_EDITION[edition])
                with self.assertRaises(ValueError):
                    normalize_native_sector_labels(source[:-1], edition)
        self.assertEqual(
            normalize_native_sector_labels(SOURCE_BY_EDITION["2025"], "2025")["C24B"],
            "D242")
        self.assertIn("D86T89", common_2018_concordance(SECTORS_2025)["excluded"])

    def test_full_authentic_header_patterns_classify_each_release(self):
        for edition, table, year in [
            ("2018", "extended", 2015), ("2021", "extended", 2018),
            ("2023", "extended", 2020), ("2023", "regular", 2020),
            ("2025", "extended", 2022), ("2025", "regular", 2022),
        ]:
            with self.subTest(edition=edition, table=table):
                with ZipFile(full_shape_source(edition, table, year)) as archive:
                    result = probe_archive_layout(archive)
                self.assertEqual(result["status"], "recognized", result["headers"][0])
                self.assertEqual(result["candidate"],
                                 {"edition": edition, "table": table})
                self.assertTrue(result["headers"][0]["six_final_demand_components_per_area"])
                self.assertEqual(result["headers"][0]["output_column_label"], "X")

    def test_publisher_code_accounting_and_leontief_ingestion(self):
        sectors = {"2018": SECTORS_2018, "2021": SECTORS_2021,
                   "2023": SECTORS_2021, "2025": SECTORS_2025}
        for edition in sectors:
            with self.subTest(edition=edition):
                body = tiny_accounted_source(edition)
                original = DIMENSIONS[edition]
                with patch.dict(DIMENSIONS, {edition: (1, 1, sectors[edition],
                                                      original[3], original[4])}):
                    audit = audit_native_csv(io.StringIO(body), edition=edition,
                                             year=original[4])
                self.assertEqual(audit["output_column_label"], "X")
                self.assertEqual(audit["native_industries"], SOURCE_BY_EDITION[edition])
                self.assertTrue(audit["accounting_passed"])
                self.assertEqual(audit["row_failures"], 0)
                self.assertEqual(audit["column_failures"], 0)
                annual = read_native_year(io.StringIO(body), audit)
                self.assertEqual(annual.z.shape,
                                 (len(sectors[edition]), len(sectors[edition])))
                self.assertEqual(annual.value_added_basis, "publisher_VA_plus_TLS")
                result = solve_foreign_final_demand(annual)
                self.assertEqual(result["max_relative_residual"], 0)


if __name__ == "__main__":
    unittest.main()
