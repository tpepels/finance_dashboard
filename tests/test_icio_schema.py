"""Regression gates for real OECD header shapes and immutable edition recovery."""
from __future__ import annotations

import io
import unittest
from zipfile import ZipFile

from finance_dashboard.icio_editions import _effective_archive_identity, archive_identity
from finance_dashboard.icio_native import DIMENSIONS, audit_archive_native
from finance_dashboard.icio_schema import probe_archive_layout


def example_zip(edition: str, table: str, year: int) -> io.BytesIO:
    n_production, n_fd, sectors, _, _ = DIMENSIONS[edition]
    if table == "regular":
        n_production = n_fd
    countries = [f"A{i:02d}" for i in range(n_fd)]
    production = countries + (["CN1", "CN2", "MX1", "MX2"]
                              if n_production > n_fd else [])
    assert len(production) == n_production
    nodes = [f"{area}_{sector}" for area in production for sector in sectors]
    fds = [f"{area}_{kind}" for area in countries for kind in
           ("HFCE", "NPISH", "GGFC", "GFCF", "INVNT", "DIRPA")]
    name = f"{year}_SML.csv" if table == "regular" else (
        f"ICIO2018_{year}.CSV" if edition == "2018" else
        f"ICIO2021_{year}.csv" if edition == "2021" else f"{year}.csv")
    body = ",".join(["V1", *nodes, *fds, "OUT"]) + "\n"
    output = io.BytesIO()
    with ZipFile(output, "w") as z:
        z.writestr(name, body)
    output.seek(0)
    return output


class StructuralIdentityTests(unittest.TestCase):
    def test_every_published_edition_is_inferred_from_complete_header_layout(self):
        for edition, table, year in (
            ("2018", "extended", 2015),
            ("2021", "extended", 2018),
            ("2023", "extended", 2020),
            ("2023", "regular", 2020),
            ("2025", "extended", 2022),
            ("2025", "regular", 2022),
        ):
            with self.subTest(edition=edition, table=table):
                with ZipFile(example_zip(edition, table, year)) as source:
                    probe = probe_archive_layout(source)
                self.assertEqual(probe["status"], "recognized")
                self.assertEqual(probe["candidate"],
                                 {"edition": edition, "table": table})
                self.assertTrue(probe["headers"][0]["full_node_cartesian_product"])
                self.assertEqual(probe["headers"][0]["final_demand_column_count"]
                                 if "final_demand_column_count" in probe["headers"][0] else
                                 probe["headers"][0]["final_demand_columns"],
                                 DIMENSIONS[edition][1] * 6)

    def test_shared_extended_archive_filename_uses_actual_structural_edition(self):
        record = {"edition": "2025", "table": "extended"}
        with ZipFile(example_zip("2023", "extended", 2015)) as source:
            probe = probe_archive_layout(source)
        result = _effective_archive_identity("2011-2015_EXT.zip", record, probe)
        self.assertEqual(result["edition"], "2023")
        self.assertEqual(result["table"], "extended")
        self.assertEqual(result["sealed_edition"], "2025")
        self.assertTrue(result["source_structure_reclassified"])
        self.assertEqual(result["status"], "source_structure_confirmed")

    def test_2016_2020_regular_fixes_old_sealed_2025_identity(self):
        record = {"edition": "2025", "table": "regular"}
        with ZipFile(example_zip("2023", "regular", 2020)) as source:
            probe = probe_archive_layout(source)
        result = _effective_archive_identity("2016-2020_SML.zip", record, probe)
        self.assertEqual(result["edition"], "2023")
        self.assertTrue(result["source_structure_reclassified"])

    def test_known_edition_conflict_fails_closed(self):
        record = {"edition": "2021", "table": "edition_specific_unresolved"}
        with ZipFile(example_zip("2023", "extended", 2020)) as source:
            probe = probe_archive_layout(source)
        result = _effective_archive_identity("ICIO2021_2015-2018.zip", record, probe)
        self.assertEqual(result["edition"], "2021")
        self.assertEqual(result["status"], "source_schema_conflicts_filename")
        self.assertFalse(result["source_structure_reclassified"])

    def test_sealed_zip_filename_does_not_destroy_year_range_verification(self):
        with ZipFile(example_zip("2023", "extended", 2020)) as source:
            report = audit_archive_native(source, "2023", table="extended",
                                          original_filename="2016-2020_EXT.zip")
        self.assertEqual(report["expected_years"], list(range(2016, 2021)))
        self.assertEqual(report["observed_years"], [2020])
        self.assertEqual(report["header_schema"]["status"], "recognized")
        self.assertEqual(report["native_validation_status"], "native_parser_rejected")
        self.assertEqual(report["rejected_matrices"][0]["error_code"],
                         "icio_native_missing_industry_rows")

    def test_malformed_matrix_does_not_become_certified_from_shape_alone(self):
        with ZipFile(example_zip("2025", "extended", 2022)) as source:
            report = audit_archive_native(source, "2025", table="extended")
        self.assertEqual(report["annual_matrix_count"], 0)
        self.assertEqual(report["native_validation_status"], "native_parser_rejected")


if __name__ == "__main__":
    unittest.main()
